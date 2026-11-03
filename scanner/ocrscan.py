"""Scan mode "All cards (read text)": read the name (top) and collector lines (bottom left: number,
set code · language) from the scan frame crop via OCR and look them up in the card database.

Needs no downloaded sets and hardly any memory – only the card database. OCR: RapidOCR
(ONNX, runs offline). Only a narrow band at the top and the bottom left is read -> ~100 ms.
"""
import difflib
import re
import threading

import cv2
import numpy as np

from cards import carddb

try:  # fast fuzzy matching (C++), ~50x faster than difflib
    from rapidfuzz import fuzz as _rf_fuzz, process as _rf_process
except ImportError:
    _rf_fuzz = _rf_process = None

W, H = 700, 978                                 # working size of the card (smaller = faster)
LANGS = {"EN": "en", "DE": "de", "FR": "fr", "IT": "it", "ES": "es", "SP": "es", "PT": "pt", "JP": "ja", "JA": "ja",
         "KR": "ko", "KO": "ko", "RU": "ru", "CS": "zhs", "CT": "zht", "PH": "ph"}
_SET_LINE = re.compile(r"([A-Z0-9]{3,5})\s*[^A-Z0-9\s]{0,2}\s*(EN|DE|FR|IT|ES|SP|PT|JP|JA|KR|KO|RU|CS|CT|PH)")
_engine, _lock = None, threading.Lock()
_names, _set_codes, _flavor = None, None, {}


def engine():
    """Load the OCR engine once (~0.3 s)."""
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            from rapidocr_onnxruntime.utils import infer_engine
            base_opts = infer_engine.OrtInferSession._init_sess_opts

            def opts(config):
                # Default: all cores, which keep spinning after every call (measured: 73 ms and 1.3 s CPU time
                # per line). 4 threads without spinning: 36 ms and 0.09 s – twice as fast, 14× more frugal.
                so = base_opts(config)
                so.intra_op_num_threads = 4
                so.add_session_config_entry("session.intra_op.allow_spinning", "0")
                so.add_session_config_entry("session.inter_op.allow_spinning", "0")
                return so
            infer_engine.OrtInferSession._init_sess_opts = staticmethod(opts)
            # limit text detection to the original size (default upscales small images to 736 px -> 10x slower)
            kw = dict(det_limit_type="max", det_limit_side_len=720)
            if _gpu_ok():   # on the GPU (DirectML) like the AI: measured ~5x faster (135 instead of 684 ms per card)
                try:
                    from scanner import fingerprint
                    with fingerprint._run_lock:
                        _engine = RapidOCR(**kw, det_use_dml=True, rec_use_dml=True, cls_use_dml=True)
                        _engine(np.zeros((32, 96, 3), np.uint8), use_cls=False)   # run once: driver acting up? -> CPU
                    _gpu[0] = True
                except Exception:  # noqa: BLE001
                    _engine = None
            if _engine is None:
                _engine = RapidOCR(**kw)
    return _engine


_gpu = [False]   # OCR runs on the GPU -> never at the same time as the AI (DirectML crashes otherwise)


def run(img, use_cls=False):
    """OCR on an image -> (result, timings) like RapidOCR. On the GPU in the AI process (aiworker: there it is
    serialized with the AI automatically); on the CPU here in the app – otherwise the AI would have to wait for
    every slow CPU OCR run."""
    from scanner import aiworker
    if aiworker.usable() and _gpu_ok():
        try:
            return aiworker.call("ocr", img, use_cls)
        except aiworker.Unavailable:
            pass
    return run_local(img, use_cls)


def blank():
    return np.zeros((32, 96, 3), np.uint8)


def run_local(img, use_cls=False):
    """OCR here in this process. On the GPU never at the same time as the AI (same DirectML binding;
    concurrently -> "GPU not responding" and a crash)."""
    eng = engine()
    if _gpu[0]:
        from scanner import fingerprint
        with fingerprint._run_lock:
            return eng(img, use_cls=use_cls)
    return eng(img, use_cls=use_cls)


def _gpu_ok():
    """Use the GPU for OCR? Only via DirectML from Windows (accel: also not with BENTCORNER_NO_GPU or a too old
    DirectML) and only if the AI isn't on the CPU (measured: CPU faster, or the GPU crashed)."""
    try:
        from scanner import accel
        if not accel.ocr_gpu():
            return False
        if _gpu_known:
            return _gpu_known[0]
        from scanner import fingerprint
        choice = fingerprint._load_choice()   # None = CPU was faster; "?" = not measured yet
        if choice != "?":
            _gpu_known.append(choice is not None)   # settled: don't read the file for every line
        return choice is not None
    except Exception:  # noqa: BLE001
        return False


_gpu_known = []


def gpu_off():
    """The GPU crashed (fingerprint.gpu_crashed): text recognition only on the CPU from now on."""
    global _engine
    _gpu_known[:] = [False]
    with _lock:
        if _gpu[0]:
            _engine, _gpu[0] = None, False


def available():
    import importlib.util
    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


# ---------- Image ----------
def _box(img, box):
    x0, y0, x1, y1 = box
    return img[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]


# ---------- Reading ----------
TOP_BAND, BOTTOM_BAND = (0.0, 0.0, 1.0, 0.16), (0.0, 0.86, 0.62, 1.0)


def _lines(part):
    """Text lines in a region: [(text, confidence, y center, x left, height)]."""
    res, _ = run(part)
    out = []
    for box, text, score in res or []:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        out.append((text.strip(), float(score), sum(ys) / 4, min(xs), max(ys) - min(ys)))
    return out


def read(card):
    """-> {"name", "number", "set", "lang", "raw"} from the card image (crop of the scan frame).
    Top: the largest text line on the left = name (mana cost on the right ignored). Bottom left: number + set line."""
    top = _lines(_box(card, TOP_BAND))
    name = ""
    words = [t for t in top if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", t[0])) >= 3 and t[3] < W * 0.6]
    if words:
        name = max(words, key=lambda t: (t[4], len(t[0])))[0]  # tallest line = card name
    bottom = _lines(_box(card, BOTTOM_BAND))
    bottom.sort(key=lambda t: (round(t[2] / 8), t[3]))
    text = " ".join(t[0] for t in bottom)
    out = {"name": _clean_name(name), "number": None, "set": None, "lang": None, "raw": [name, text]}
    m = _find_set(text.upper()) or _find_set(text.upper().replace(" ", ""))
    if m:
        out["set"], out["lang"] = m.group(1).lower(), LANGS.get(m.group(2))
    else:  # order swapped ("EN FRA") or separator misread: look for a known set code + language code separately
        toks = re.findall(r"[A-Z0-9]{2,5}", text.upper())
        code = next((t for t in toks if len(t) >= 3 and not t.isdigit() and t.lower() in _set_codes), None)
        lang = next((t for t in toks if t in LANGS), None)
        if code and lang:
            out["set"], out["lang"] = code.lower(), LANGS[lang]
    # collector number: digits before/without the set code, e.g. "R 0100", "100/271", "C0101"
    num_zone = (text[:m.start()] if m else text).upper()
    num_zone = re.sub(r"(?<=[CURMLTSPB0-9])O|O(?=\d)", "0", num_zone)  # „RO450“, „CO041“ -> 0
    d = (re.search(r"(?<!\d)([CURMLTSPB])\s?(\d{3,4})(?!\d)", num_zone)  # rarity + number: R0160
         or re.search(r"(?<!\d)(\d{3,4})(?!\d)", num_zone)                # 0160 / 160
         or re.search(r"(?<!\d)(\d{1,4})\s*/\s*\d{1,4}", num_zone))     # 160/271 (older cards)
    if d:
        out["number"] = str(int(d.group(d.lastindex)))
        out["rarity"] = d.group(1) if d.lastindex == 2 else None
    return out


def _find_set(text):
    """Find set code + language ("FRA·EN") – only known set codes (otherwise e.g. "RO450 FR…" gets mistaken)."""
    _load_names()
    for i in range(len(text)):
        if i and text[i - 1].isalnum():
            continue  # code starts at the beginning of a word
        m = _SET_LINE.match(text, i)
        if m:
            for k in range(len(m.group(1)), 2, -1):  # "FRAEN": also try shorter codes
                code = m.group(1)[:k]
                if code.lower() in _set_codes:
                    return _SET_LINE.match(text[:i] + code + " " + m.group(2), i)
    return None


def _clean_name(s):
    s = re.sub(r"[^\w' ,\-!?:.&]", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


# ---------- Lookup ----------
def _load_names():
    global _names, _set_codes, _flavor
    if _names is None:
        with carddb.connection() as con:
            names = {}
            for (n,) in con.execute("SELECT DISTINCT name FROM cards"):
                front = n.split(" // ")[0].lower()
                # "Haunted Ridge // Haunted Ridge" (art/double-faced card) must not replace the normal name
                if front not in names or " // " in names[front] and " // " not in n:
                    names[front] = n
            # flavor names (name on the card, real name small below it): lead to exactly these prints
            flavor = {}
            if carddb.has_flavor_names():
                for fn, n in con.execute("SELECT DISTINCT flavor_name, name FROM cards WHERE flavor_name IS NOT NULL"):
                    for part in fn.split(" // "):
                        key = part.lower()
                        if key not in names:
                            flavor[key] = n
                            names[key] = n
            _names, _flavor = names, flavor
            _set_codes = {r[0] for r in con.execute("SELECT DISTINCT set_code FROM cards")}
    return _names


# ---------- Names in other languages ("Burgwache der Zwerge" = FIN 18 in German) ----------
_local, _local_by_lang, _local_cache = None, {}, {}
FUZZY_LANGS = ("de", "fr", "it", "es", "pt")  # Latin script: fuzzy search (~0.05 s each)


def _load_local():
    """Printed names in all languages from the language index (once, ~1 s)."""
    global _local
    if _local is None:
        idx, by = {}, {}
        if carddb.has_languages():
            with carddb.connection() as con:
                for set_code, number, lang, name in con.execute(
                        "SELECT set_code, number, lang, name FROM langs WHERE lang != 'en'"):
                    key = (name or "").lower()
                    if key:
                        idx.setdefault(key, []).append((set_code, number, lang))
                        by.setdefault(lang, set()).add(key)
        _local_by_lang.clear()
        _local_by_lang.update({lang: list(v) for lang, v in by.items()})
        _local = idx
    return _local


def local_prints(name, lang=None):
    """Name read in another language -> [(set, number, language)] or []."""
    if not name or len(name) < 4:
        return []
    key = name.lower()
    cache_key = (key, lang)
    if cache_key in _local_cache:
        return _local_cache[cache_key]
    idx = _load_local()
    hits = idx.get(key)
    if hits is None:
        flat = key.replace(" ", "")
        langs = [lang] if lang in _local_by_lang else [lg for lg in FUZZY_LANGS if lg in _local_by_lang]
        best = None
        for lg in langs:
            for k in _close(key, _local_by_lang[lg], n=1, cutoff=0.78):
                sim = max(_similar(key, k), _similar(flat, k.replace(" ", "")))
                if best is None or sim > best[0]:
                    best = (sim, k)
        hits = idx[best[1]] if best else []
    if len(_local_cache) > 500:
        _local_cache.clear()
    _local_cache[cache_key] = hits
    return hits


def _rows_for_prints(con, prints):
    out = []
    for set_code, number, _lang in prints:
        row = con.execute("SELECT * FROM cards WHERE set_code = ? AND number = ?", (set_code, number)).fetchone()
        if row:
            out.append(dict(row))
    return out


def _similar(a, b):
    a, b = (a or "").lower(), (b or "").lower()
    if _rf_fuzz is not None:
        return _rf_fuzz.ratio(a, b) / 100
    return difflib.SequenceMatcher(None, a, b).ratio()


def _close(query, choices, n=1, cutoff=0.6):
    """Most similar entries (best first) – like difflib.get_close_matches, just faster."""
    if _rf_process is not None:
        return [m[0] for m in _rf_process.extract(query, choices, scorer=_rf_fuzz.ratio, limit=n,
                                                   score_cutoff=cutoff * 100)]
    return difflib.get_close_matches(query, choices, n=n, cutoff=cutoff)


_name_list = None


def _names_list():
    global _name_list
    names = _load_names()
    if _name_list is None or len(_name_list) != len(names):
        _name_list = list(names)
    return _name_list


def _front(name):
    return (name or "").split(" // ")[0]


_SKIP_LAYOUTS = "('art_series', 'token', 'double_faced_token', 'emblem')"


def lookup(r, owned_pref=None):
    """Read result -> (card database row or None, confidence 0..1, reason)."""
    names = _load_names()
    with carddb.connection() as con:
        con.row_factory = __import__("sqlite3").Row
        set_code = r["set"] if r["set"] in _set_codes else None
        if set_code and r.get("rarity") == "T" and "t" + set_code in _set_codes:
            set_code = "t" + set_code  # tokens carry the code of the main set
        rows = []
        if set_code and r["number"]:
            rows = [dict(x) for x in con.execute(
                "SELECT * FROM cards WHERE set_code = ? AND (number = ? OR ltrim(number, '0') = ?)",
                (set_code, r["number"], r["number"]))]
            for row in rows:
                if not r["name"] or max(_similar(r["name"], _front(row["name"])),
                                        _similar(r["name"], _front(row.get("flavor_name")))) >= 0.55:
                    return row, 0.95, "Set + Nummer"
        # determine the name (fuzzy)
        full = None
        if r["name"] and len(r["name"]) >= 3:
            key = r["name"].lower().replace(" ", "")
            key = next((k for k in names if k.replace(" ", "") == key), r["name"].lower())
            full = names.get(key)
            if full is None:
                close = _close(key, _names_list(), n=1, cutoff=0.72)
                full = names[close[0]] if close else None
                key = close[0] if close else key
        if full is None and r["name"]:
            prints = local_prints(r["name"], r.get("lang"))
            if prints:
                cands = _rows_for_prints(con, prints)
                langs = {lg for _, _, lg in prints}
                if len(langs) == 1 and not r.get("lang"):
                    r["lang"] = next(iter(langs))  # language from the name (footer unreadable)
                if set_code:
                    cands = [c for c in cands if c["set_code"] == set_code] or cands
                if r["number"]:
                    cands = [c for c in cands if carddb.norm_number(c["number"], "") == r["number"]] or cands
                if cands:
                    cands.sort(key=lambda c: c["released"] or "", reverse=True)
                    label = f"Name ({'/'.join(sorted(langs)).upper()})"
                    return cands[0], 0.9 if len(cands) == 1 else 0.6, label
        if full is None:
            if set_code and r["number"] and rows:  # name unreadable (e.g. other language): trust the number
                return rows[0], 0.7, "Set + Nummer (Name unlesbar)"
            return None, 0.0, "nicht erkannt"
        cands = [dict(x) for x in con.execute(
            f"SELECT * FROM cards WHERE (name = ? OR name LIKE ?) AND layout NOT IN {_SKIP_LAYOUTS}",
            (full, _front(full) + " // %"))]
        if not cands:
            return None, 0.0, "nicht erkannt"
        if key in _flavor:
            special = [c for c in cands if (c.get("flavor_name") or "").lower().split(" // ")[0] == key
                       or key in (c.get("flavor_name") or "").lower().split(" // ")]
            if special:
                special.sort(key=lambda c: (c["set_code"] != set_code, c["released"] or ""))
                return special[0], 0.9 if len(special) == 1 else 0.6, "Sondername"
        if set_code:
            same = [c for c in cands if c["set_code"] == set_code]
            if not same:  # promo/token/Commander variant of the same set (pfin, tfin, fic …)
                same = [c for c in cands if set_code[-3:] in c["set_code"]]
            if same:
                if r["number"]:  # misread number: take the closest one
                    same.sort(key=lambda c: abs(int(re.sub(r"\D", "", c["number"]) or 0) - int(r["number"])))
                return same[0], 0.85, "Name + Set"
        if r["number"] and not set_code:  # set unreadable, number read: the print with this number
            num = [c for c in cands if carddb.norm_number(re.sub(r"\D", "", c["number"]), "") == r["number"]]
            if len(num) == 1:
                return num[0], 0.8, "Name + Nummer"
            if num:
                num.sort(key=lambda c: c["released"] or "", reverse=True)
                return num[0], 0.7, "Name + Nummer"
        if set_code and rows:  # set + number read, name matches nothing in the set: trust the number
            return rows[0], 0.6, "Set + Nummer (Name unsicher)"
        if owned_pref and full in owned_pref:
            own = next((c for c in cands if c["id"] == owned_pref[full]), None)
            if own:
                return own, 0.6, "Name (eigener Druck)"
        cands.sort(key=lambda c: (not c["booster"], c["released"] or ""), reverse=False)
        cands.sort(key=lambda c: c["released"] or "", reverse=True)
        return cands[0], 0.5 if len(cands) > 1 else 0.8, "Name (neuester Druck)" if len(cands) > 1 else "Name"


def find_card(frame, rect):
    """Card candidates in the area around the scan frame (may be tilted), straightened, best first.
    Looks for outlines in card format (63:88) near the frame center; rotated to portrait."""
    x, y, w, h = rect
    fh, fw = frame.shape[:2]
    mx, my = int(w * 0.35), int(h * 0.2)
    x0, y0, x1, y1 = max(0, x - mx), max(0, y - my), min(fw, x + w + mx), min(fh, y + h + my)
    region = frame[y0:y1, x0:x1]
    scale = 700 / max(region.shape[:2])
    small = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)  # inner outlines too
    zone_area = w * h * scale * scale
    zc = np.array([(x - x0 + w / 2) * scale, (y - y0 + h / 2) * scale])
    found = []
    for c in cnts:
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        if min(rw, rh) < 1:
            continue
        ratio = min(rw, rh) / max(rw, rh)
        area = rw * rh
        if cv2.contourArea(cv2.convexHull(c)) < 0.88 * area:
            continue  # not a rectangle (e.g. hand + card merged)
        if 0.62 <= ratio <= 0.80 and 0.3 * zone_area <= area <= 2.2 * zone_area:
            # preferred: close to the frame center and about as large as the frame
            score = abs(np.log(area / zone_area)) + np.linalg.norm(np.array([cx, cy]) - zc) / np.sqrt(zone_area)
            # black card border blends into a dark background -> often the inner edge is found;
            # enlarge by the border width (~4 %) so the name and collector line are safely in the image
            found.append((score, cv2.boxPoints(((cx, cy), (rw * 1.045, rh * 1.035), ang))))
    found.sort(key=lambda t: t[0])
    return [_warp_box(frame, box / scale + np.array([x0, y0], np.float32)) for _, box in found[:2]]


class Warped(tuple):
    """Position (x, y, w, h) of a STRAIGHTENED image in the camera frame: the image already is the whole card, not
    an axis-aligned crop at this position (do not map homographies on it back into the camera frame)."""


def find_card_boxed(frame, rect, corners=False):
    """Like find_card, but only the best card -> [(straightened image, (x, y, w, h) in the camera frame)] or [].
    corners: straighten by the outline's own four corners (when it has exactly four) instead of the rotated
    rectangle – a tilted card is a trapezoid, the rectangle cuts its corners off (often the collector line). Same card
    choice; only a second attempt for the collector line (scan-bench: + hits, 0 false)."""
    x, y, w, h = rect
    fh, fw = frame.shape[:2]
    mx, my = int(w * 0.35), int(h * 0.2)
    x0, y0, x1, y1 = max(0, x - mx), max(0, y - my), min(fw, x + w + mx), min(fh, y + h + my)
    region = frame[y0:y1, x0:x1]
    if not region.size:
        return []
    scale = 700 / max(region.shape[:2])
    small = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    zone_area = w * h * scale * scale
    zc = np.array([(x - x0 + w / 2) * scale, (y - y0 + h / 2) * scale])
    best = None
    for c in cnts:
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        if min(rw, rh) < 1:
            continue
        ratio, area = min(rw, rh) / max(rw, rh), rw * rh
        hull = cv2.convexHull(c)
        if cv2.contourArea(hull) < 0.88 * area:
            continue
        if 0.62 <= ratio <= 0.80 and 0.3 * zone_area <= area <= 2.2 * zone_area:
            score = abs(np.log(area / zone_area)) + np.linalg.norm(np.array([cx, cy]) - zc) / np.sqrt(zone_area)
            if best is None or score < best[0]:
                pts = cv2.boxPoints(((cx, cy), (rw * 1.045, rh * 1.035), ang))
                if corners:
                    quad = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
                    # enlarged around the centre like the rectangle (the border width) – along the image axes, not
                    # the card's: slightly uneven on a strongly turned card, no effect on the scan bench
                    if len(quad) == 4:
                        q = quad.reshape(4, 2).astype(np.float32)
                        pts = (q - q.mean(0)) * np.float32([1.045, 1.035]) + q.mean(0)
                best = (score, pts)
    if best is None:
        return []
    pts = best[1] / scale + np.array([x0, y0], np.float32)
    bx0, by0 = pts.min(0)
    bx1, by1 = pts.max(0)
    box = (int(max(0, bx0)), int(max(0, by0)), int(min(fw, bx1) - max(0, bx0)), int(min(fh, by1) - max(0, by0)))
    return [(_warp_box(frame, pts), Warped(box))]


def _warp_box(frame, pts):
    # order the corners: long side vertical (portrait)
    c = pts.mean(0)
    pts = sorted(pts, key=lambda p: np.arctan2(p[1] - c[1], p[0] - c[0]))
    pts = np.array(pts, np.float32)
    d01, d12 = np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[1] - pts[2])
    if d01 > d12:  # first edge is long -> shift by one corner so the short edge is at the top
        pts = np.roll(pts, -1, axis=0)
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], np.float32)
    return cv2.warpPerspective(frame, cv2.getPerspectiveTransform(pts, dst), (W, H))


def read_region(frame, rect):
    """Fallback for tilted cards: read the whole area around the frame (OCR reads tilted lines by itself)
    and classify the lines by their position on the card: topmost = name, bottommost = collector line."""
    x, y, w, h = rect
    fh, fw = frame.shape[:2]
    mx, my = int(w * 0.35), int(h * 0.15)
    region = frame[max(0, y - my):min(fh, y + h + my), max(0, x - mx):min(fw, x + w + mx)]
    scale = min(1.0, 1100 / max(region.shape[:2]))
    region = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    res, _ = run(region, use_cls=True)
    lines = []
    for box, text, score in res or []:
        b = np.array(box, np.float32)
        ang = np.degrees(np.arctan2(b[1][1] - b[0][1], b[1][0] - b[0][0]))
        lines.append((text.strip(), b.mean(0), ang, np.linalg.norm(b[3] - b[0]), np.linalg.norm(b[1] - b[0])))
    out = {"name": "", "number": None, "set": None, "lang": None, "raw": ["", ""]}
    if not lines:
        return out
    ang = float(np.median([a for *_, a, _, _ in lines]))  # reading direction of the card
    t = np.radians(ang)
    down = np.array([-np.sin(t), np.cos(t)])  # "down" on the card
    right = np.array([np.cos(t), np.sin(t)])
    ys = [float(c @ down) for _, c, *_ in lines]
    top, bottom = min(ys), max(ys)
    span = max(1.0, bottom - top)
    # name: in the top 15 %, largest font, with letters
    head = [(ln, yy) for ln, yy in zip(lines, ys) if yy - top < 0.15 * span
            and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", ln[0])) >= 3]
    if head:
        out["name"] = _clean_name(max(head, key=lambda t: (t[0][3], len(t[0][0])))[0][0])
    # collector line: bottom 12 %, left to right
    foot = sorted([(ln, yy) for ln, yy in zip(lines, ys) if bottom - yy < 0.12 * span],
                  key=lambda t: (round(t[1] / 10), float(t[0][1] @ right)))
    text = " ".join(ln[0] for ln, _ in foot)
    out["raw"] = [out["name"], text]
    part = read_footer(text)
    out.update({k: v for k, v in part.items() if v})
    return out


def read_footer(text):
    """Set, language, number from the collector line."""
    out = {"set": None, "lang": None, "number": None, "rarity": None}
    up = text.upper()
    m = _find_set(up) or _find_set(up.replace(" ", ""))
    if m:
        out["set"], out["lang"] = m.group(1).lower(), LANGS.get(m.group(2))
    else:
        toks = re.findall(r"[A-Z0-9]{2,5}", up)
        code = next((t for t in toks if len(t) >= 3 and not t.isdigit() and t.lower() in _set_codes), None)
        lang = next((t for t in toks if t in LANGS), None)
        if code and lang:
            out["set"], out["lang"] = code.lower(), LANGS[lang]
    num_zone = up[:m.start()] if m else up
    num_zone = re.sub(r"(?<=[CURMLTSPB0-9])O|O(?=\d)", "0", num_zone)
    d = (re.search(r"(?<!\d)([CURMLTSPB])\s?(\d{3,4})(?!\d)", num_zone)
         or re.search(r"(?<!\d)(\d{3,4})(?!\d)", num_zone)
         or re.search(r"(?<!\d)(\d{1,4})\s*/\s*\d{1,4}", num_zone))
    if d:
        out["number"] = str(int(d.group(d.lastindex)))
        out["rarity"] = d.group(1) if d.lastindex == 2 else None
    return out


def scan_frame(frame, rect, owned_pref=None, detail=False):
    """Camera frame + scan frame: find the card (tilted too), read it, look it up. If no outline is found, the
    frame crop is read. Upside-down cards are tried rotated.
    -> (entry, read result, confidence, path); detail=True: additionally the database row and the card image
    (straightened, for image matching) as a dict."""
    x, y, w, h = rect
    tries = []
    for card in find_card(frame, rect):
        tries += [card, cv2.rotate(card, cv2.ROTATE_180)]
    tries.append(cv2.resize(frame[y:y + h, x:x + w], (W, H), interpolation=cv2.INTER_AREA))
    best = None
    for img in tries:
        r = read(img)
        row, conf, how = lookup(r, owned_pref)
        if best is None or conf > best[2]:
            best = (row, r, conf, how, img)
        if conf >= 0.85:
            break
    if best[2] < 0.85:  # held tilted or similar: read the whole area
        r = read_region(frame, rect)
        row, conf, how = lookup(r, owned_pref)
        if conf > best[2] or conf == best[2] and len(r.get("name") or "") > len(best[1].get("name") or ""):
            best = (row, r, conf, how + " · tilted", tries[0])
    row, r, conf, how, img = best
    entry = carddb.entry_from_row(row) if row else None
    if entry is not None:
        entry["img_normal"] = row.get("img_normal")
    if detail:
        fh, fw = frame.shape[:2]
        mx, my = int(w * 0.2), int(h * 0.1)
        region = frame[max(0, y - my):min(fh, y + h + my), max(0, x - mx):min(fw, x + w + mx)]
        return {"entry": entry, "r": r, "conf": conf, "how": how, "row": row, "img": img, "region": region}
    return entry, r, conf, how


def unique_result(conf, how):
    """Did OCR identify exactly one print (then one image is enough for confirmation)?"""
    base = (how or "").split(" · ")[0]
    return conf >= 0.8 and (base in ("Sondername", "Name + Nummer", "Name")
                            or re.fullmatch(r"Name \([A-Z/]+\)", base) is not None)


def candidates(r, first=None, prefer_sets=(), limit=40):
    """Candidates for image matching, most likely first: the read set + number, then all prints of the most
    similar names (prints from the read set or preferred sets and with a matching number first)."""
    names = _load_names()
    out, seen = [], set()

    def add(rows):
        for row in rows:
            row = dict(row)
            if row["id"] not in seen:
                seen.add(row["id"])
                out.append(row)
    with carddb.connection() as con:
        set_code = r.get("set") if r.get("set") in _set_codes else None
        if set_code and r.get("rarity") == "T" and "t" + set_code in _set_codes:
            set_code = "t" + set_code
        if first:
            add([first])
        if set_code and r.get("number"):
            add(con.execute("SELECT * FROM cards WHERE set_code = ? AND (number = ? OR ltrim(number, '0') = ?)",
                            (set_code, r["number"], r["number"])))
        found = []
        if r.get("name") and len(r["name"]) >= 3:
            key = r["name"].lower()
            flat = key.replace(" ", "")
            exact = next((k for k in names if k.replace(" ", "") == flat), None)
            if exact:
                found.append(exact)
            close = _close(key, _names_list(), n=6, cutoff=0.55)
            sure = bool(close) and _similar(key, close[0]) >= 0.8
            # only a fragment read ("Teyo.", "yomancer"): names containing the fragment (word start first)
            frags = re.findall(r"[a-zà-ÿ]{4,}", key)
            part = []
            if frags and not exact:
                frag = max(frags, key=len)
                part = [k for k in names if frag in k]
                part.sort(key=lambda k: (not re.search(r"\b" + re.escape(frag), k), len(k)))
                part = part[:6]
            for k in (close + part if sure else part[:4] + close + part[4:]):
                if k not in found:
                    found.append(k)
        if r.get("name") and (not found or not sure):
            loc = sorted(_rows_for_prints(con, local_prints(r["name"], r.get("lang"))),
                         key=lambda c: c["released"] or "", reverse=True)
            add(sorted(loc, key=lambda c: c["set_code"] != set_code))
        for key in found:
            prints = [dict(x) for x in con.execute(
                f"SELECT * FROM cards WHERE (name = ? OR name LIKE ?) AND layout NOT IN {_SKIP_LAYOUTS}",
                (names[key], _front(names[key]) + " // %"))]
            prints.sort(key=lambda c: c["released"] or "", reverse=True)
            prints.sort(key=lambda c: (key in _flavor and key not in (c.get("flavor_name") or "").lower(),
                                       c["set_code"] != set_code, c["set_code"] not in prefer_sets,
                                       bool(r.get("number")) and carddb.norm_number(c["number"], "") != r["number"]))
            add(prints)
            if len(out) >= limit:
                break
        return out[:limit]


def scan(crop, owned_pref=None):
    """Complete pipeline for a camera crop. -> (card entry or None, read result, confidence, path)."""
    card = cv2.resize(crop, (W, H), interpolation=cv2.INTER_AREA)  # scan frame = card format
    r = read(card)
    row, conf, how = lookup(r, owned_pref)
    entry = carddb.entry_from_row(row) if row else None
    if entry is not None:
        entry["img_normal"] = row.get("img_normal")
    return entry, r, conf, how
