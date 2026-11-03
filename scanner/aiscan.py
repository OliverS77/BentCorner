"""Scan mode "AI fingerprint": fingerprint of the camera image -> most similar cards of the loaded sets ->
confirmation via image match (keypoints, robust against fingers at the edge) -> for identical artwork a
whole-card comparison, booster version, session sets, otherwise ask. If nothing fits, text recognition takes over.
"""
import time

import cv2
import numpy as np

from scanner import fingerprint
import games
from scanner import hybrid
from cards import carddb
from cards import imgcache
from scanner.common import BASE

TOP_K = 8
SIM_WINDOW = 0.1   # candidates up to this far below the best fingerprint are checked via image match
# Measured: correct cards almost always > 100 points, cards from sets that are not loaded < 20 (except reprints with
# identical artwork). Below this, text recognition takes over.
MIN_INLIERS = 35


def as_row(entry):
    """Entry from the set files -> row as from the card database (for the ask window/image paths)."""
    return {"id": entry["id"].rsplit("_", 1)[0], "set_code": entry["set"].lower(), "number": entry["number"],
            "name": entry["name"], "set_name": entry.get("set_name") or "", "rarity": entry.get("rarity") or "",
            "img_normal": None, "faces": None, "_entry": entry}


def _dewarp(frame, quad):
    from scanner import common   # card format of the game (Magic/Pokémon 336 × 468, Yu-Gi-Oh! 336 × 490)
    w, h = common.W, common.H
    q = np.asarray(quad, np.float32)
    dst = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    return cv2.warpPerspective(frame, cv2.getPerspectiveTransform(q, dst), (w, h))


# A card held in the hand rarely fills the scan frame (hand, fingers, neighbouring cards around it): several card-sized
# windows in two sizes and three positions (measured on the test video: 49 instead of 9 of 117 frames confirmed).
DEWARP = True                       # straighten the card before fingerprinting (additional window)
WINDOW_SIZES = (0.5, 0.7, 0.95)    # share of the frame width (0.95: card fills the frame – centred only)
WINDOW_OFFSETS = (-0.15, 0.0, 0.15)  # horizontal shift (share of the frame width)
PER_WINDOW = 3                     # candidates per window
POOL = 6                           # check at most this many of them via image match
STRONG = 45                        # this many points: count immediately (below, from 35: 2 out of 3 agree)
WEAK = 20                          # from here a candidate is a hint (never enough on its own)
SURE = 60                          # from here a candidate counts as clear – stop checking other cards
RIVALS = 6                         # check at most this many other prints of the same card (name + artist) directly
RIVAL_WINS = 1.25                  # a rival with this much more image-match points is the card
RIVAL_CLOSE = 0.8                  # a rival this close (share of the points) …
RIVAL_FP_GAP = 0.03                # … and the fingerprint doesn't tell them apart either (Enchanted vs. normal: it
                                   # does, 0.90 vs 0.92 – Lorcana 9-205/9-1) = can't tell them apart: ask
FP_KNOWN = 0.75                    # below this best fingerprint similarity the AI doesn't really know the card
# … then the image match must be clearly strong: right hits with such a weak fingerprint had 156+ points; on the CPU
# (quantized fingerprint) a covered Lorcana Baloo reached Launchpad with 77 points from the shared frame (bench :cpu)
FP_WEAK_NEEDS = 120
# A count that rests on the image match needs this many points – below: ask instead (the user's rule "not sure -> ask").
# Measured (bench, 8 kinds of trouble per card): right image-match counts below 100 points – pokemon 2 of 141, mtg 2 of
# 125; with the true card unknown to SCAN° (all its prints hidden from the search) the wrong cards it still counted via
# the image match had 51 and 60 points; a tester's Bronzong (live 0.9.2) 79–92, after lying there for minutes.
COUNT_NEEDS = 100
# Unambiguous fingerprint: this far ahead of every other card (name) and of other prints of the same name -> count
# without image match (two identical frames in a row are still required). Measured on 1712 card images of all games
# (covered, tilted, blurry, dark, glare): misrecognised ones were at most 0.045 (name) or 0.059 (print) ahead –
# 0.12 is a good double margin; this way ~40 % of the cards count immediately.
# filtered scan ("Only these sets", sets chosen in the log): the fingerprint is also ranked among those sets' prints only
# – a window takes that ranking when its best print overall is at most FOCUS_EPS better than the best in the sets (the
# card is from there); same-art prints of other sets then no longer blur the gap. Otherwise the full search counts.
FOCUS_EPS = 0.02
# prints the collector line can't tell apart (46 / prerelease 46s): the card must be this much closer to one of
# their reference images where those differ (a stamp, a frame detail) – relative to the other's distance. Scan bench
# prerelease-dsk + booster-fin (2026-10-29): wrong picks up to 0.64 (glare or a finger over the stamp), 0.70 = 0 wrong
TWIN_MARGIN = 0.70
TWIN_DIFF = 40        # grey difference (0..255, blurred) that counts as "the images differ here"
TWIN_AREA = 0.0015    # … over at least this share of the card – less: the images are the same, nothing to compare
STAMP_BOX = (0.04, 0.40, 0.42, 0.62)   # where modern prerelease stamps sit ("20/25", bottom left of the art) – the
                                        # loupe's place when the reference images don't show the difference
_loupe = {}   # the last undecided stamp twins: {"img": the region of the card, enlarged} – the print question shows it
FP_NAME_GAP = 0.12
FP_PRINT_GAP = 0.12
CENTER_TOL = 0.22                  # card centre at most this far (share of the frame width) from the frame centre


def windows(frame, rect):
    """Card-sized crops in the scan frame (aspect ratio of the game, e.g. 63:88) -> [(image, (x, y, w, h))]."""
    from scanner import common
    aspect = common.H / common.W
    fh, fw = frame.shape[:2]
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    out = []
    for k in WINDOW_SIZES:
        ww = w * k
        hh = min(fh, ww * aspect)
        for ox in (WINDOW_OFFSETS if k < 0.9 else (0.0,)):
            x0 = int(max(0, min(fw - ww, cx - ww / 2 + ox * w)))
            y0 = int(max(0, min(fh - hh, cy - hh / 2)))
            out.append((frame[y0:y0 + int(hh), x0:x0 + int(ww)], (x0, y0, int(ww), int(hh))))
    return out


def _is_warped(box):
    return type(box).__name__ == "Warped"   # ocrscan.Warped (without loading ocrscan here)


def _local_contrast(frame):
    """More local contrast (CLAHE on the lightness) – in weak light the card's edges are too faint to be found.
    Local, so a bright spot (lamp) in the picture doesn't cancel it out."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def card_windows(frame, rect):
    """Like windows(), but with the card in the frame – if found – straightened and put first (clean fingerprint,
    even for a tilted card). In exchange the two small side windows are dropped: 6 images fit into one
    GPU pass."""
    out = windows(frame, rect)
    if not DEWARP:
        return out
    try:
        from scanner import ocrscan
        card = ocrscan.find_card_boxed(frame, rect)
    except Exception:  # noqa: BLE001 – without a found card, carry on as before
        card = []
    if card and len(out) == 7:
        out = [out[1]] + out[3:]
    return card + out


ASIAN = {"ja", "zhs", "zht", "zh", "ko", "th", "id"}
PREFER_ASIAN = False   # later: for users who mostly collect Asian cards (setting)


def recognize(frame, rect, index, prefer_sets=(), quad=None):
    """-> {"status": "ok"|"ask"|"none", "entry", "cands": [(row, inliers)], "img", "how", "sim", "strength"}"""
    boxed = [(_dewarp(frame, quad), None)] if quad is not None else windows(frame, rect)
    boxed = [(im, box) for im, box in boxed if im.size]
    wins = [im for im, _ in boxed]
    out = {"status": "none", "entry": None, "cands": [], "img": wins[0] if wins else None, "how": "", "sim": 0.0,
           "strength": 0, "box": None}
    if not wins:
        return out
    pool = {}  # card ID -> (similarity, entry, window)
    for wi, vec in enumerate(fingerprint.embed(wins)):
        for entry, sim in index.search(vec, PER_WINDOW):
            if entry["id"] not in pool or pool[entry["id"]][0] < sim:
                pool[entry["id"]] = (sim, entry, wi)
    if not pool:
        return out
    near = sorted(pool.values(), key=lambda t: -t[0])[:POOL]
    top = near[0][0]
    near = [t for t in near if t[0] >= top - SIM_WINDOW]
    # cards from sets that are not loaded: fetch the image once for confirmation (cached afterwards)
    missing = [e for _, e, _ in near if not (BASE / e["img"]).exists() and e.get("img_normal")]
    if missing and not imgcache.offline():
        list(hybrid._pool.map(lambda e: imgcache.fetch(BASE / e["img"], e["img_normal"]), missing[:4]))
    feats = {}
    scored = []
    for sim, entry, wi in near:
        ref = hybrid._ref_path(BASE / entry["img"])
        if ref is None:
            scored.append((entry, sim, 0, wi))
            continue
        if wi not in feats:
            feats[wi] = hybrid.query_features(wins[wi])
        scored.append((entry, sim, hybrid._inliers(feats[wi], ref), wi))
    scored.sort(key=lambda t: -t[2])
    best = scored[0]
    out["sim"], out["strength"], out["img"], out["box"] = top, best[2], wins[best[3]], boxed[best[3]][1]
    if best[2] < MIN_INLIERS:
        return out  # nothing confirmed -> text recognition
    close = [t[:3] for t in scored if t[2] >= hybrid.CLOSE * best[2] and t[0]["name"] == best[0]["name"]]
    # same image also exists as a western edition (Pokémon: Japanese/Chinese sets often share the artwork):
    # then keep only the western ones – Asian prints only if the card exists only there
    west = [t for t in close if t[0].get("plang") not in ASIAN]
    if west and len(west) < len(close) and not PREFER_ASIAN:
        close = west
    pick, why = (close[0], "") if len(close) == 1 else _tiebreak(wins[best[3]], close, prefer_sets)
    if pick is not None:
        out.update(status="ok", entry=pick[0],
                   how=f"SCAN° fingerprint ({pick[1]:.2f}) + image match ({pick[2]}){why}")
    else:
        out.update(status="ask", cands=[(as_row(t[0]), t[2]) for t in close[:hybrid.ASK_MAX]])
    return out


def _tiebreak(img, close, prefer_sets):
    """Same artwork in several prints (promo stamp, showcase …)."""
    ranked = sorted(((hybrid._overlay_score(img, as_row(t[0])), t) for t in close), key=lambda x: -x[0])
    if ranked[0][0] > 0.5 and ranked[0][0] - ranked[1][0] >= hybrid.OVERLAY_GAP:
        return ranked[0][1], " · whole card"
    booster = [t for t in close if t[0].get("booster")]
    if len(booster) == 1:
        return booster[0], " · booster version"
    pref = [t for t in close if t[0]["set"].lower() in prefer_sets]
    if len(pref) == 1:
        return pref[0], " · log set"
    return None, ""


# ---------- Which print? (same image in several sets) ----------
FOOTER_BAND = (0.02, 0.895, 0.66, 0.985)   # collector line bottom left ("C 0123 FDN • DE"), shares of the card
SYMBOL_BAND = (0.82, 0.545, 0.965, 0.615)  # set symbol on the right of the type line
_ref_symbols = {}


def _band(card, box):
    h, w = card.shape[:2]
    x0, y0, x1, y1 = box
    return card[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


def _symbol_gray(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.resize(g, (96, 52), interpolation=cv2.INTER_AREA)
    return hybrid._clahe.apply(g)


def _ref_symbol(entry):
    p = BASE / entry["img"]
    key = str(p)
    if key not in _ref_symbols:
        img = cv2.imdecode(np.fromfile(key, np.uint8), cv2.IMREAD_COLOR) if p.exists() else None
        if img is None:
            return None
        from scanner import langcheck
        _ref_symbols[key] = _symbol_gray(_band(cv2.resize(img, (langcheck.OUT_W, langcheck.OUT_H)), SYMBOL_BAND))
    return _ref_symbols[key]


ASIA_LANGS = ("ja", "ko", "zhs", "zht", "th", "id")
_asia_prints = {}


def asian_prints():
    """(set, number) of all Asian prints of the open game – per print, not per set (Yu-Gi-Oh! has mixed
    sets with JP and EN numbers, Pokémon has separate Asian sets). Works this way for every game."""
    from cards import carddb
    key = games.current().key
    if key not in _asia_prints:
        try:
            with carddb.connection() as con:
                _asia_prints[key] = {(r[0], str(r[1])) for r in con.execute(
                    f"SELECT set_code, number FROM cards WHERE lang IN ({','.join('?' * len(ASIA_LANGS))})", ASIA_LANGS)}
        except Exception:  # noqa: BLE001
            _asia_prints[key] = set()
    return _asia_prints[key]


ART_SAME = 0.92   # Pokémon: fingerprints this close = the same artwork (other artwork, same artist: ≤ 0.85)


def art_group(entry, allow_foil=False, index=None):
    """All prints with the same image as entry from the card database -> [row] – per game
    (games.<game>.same_image_prints: Magic same name + artist, Yu-Gi-Oh! same image file, others same fingerprint)."""
    from cards import carddb
    try:
        with carddb.connection() as con:
            return games.current().same_image_prints(con, entry, index, allow_foil)
    except Exception:  # noqa: BLE001 – no card database
        return []


def _row_entry(row, like=None):
    """A print of the card database as a scan entry; like = the entry it stands in for – a double-faced card keeps the
    face that was seen (the back of a card counts as its back, not its front)."""
    from cards import carddb
    face = str((like or {}).get("id") or "").rpartition("_")[2]
    if face.isdigit() and face != "0" and row.get("faces"):
        e = fingerprint._entry_from_row(f"{row['id']}_{face}", row)
        if e is not None:
            return e
    e = carddb.entry_from_row(row)
    e["img_normal"] = hybrid.image_url(row)
    return e


def resolve_print(frame, img, box, best, group, prefer_sets=(), fetch=None):
    """Same image, several prints (group = all rows with this image): read the collector line (set code and/or
    number), otherwise compare the set symbol with the reference images, otherwise session set.
    -> (entry, reason) or (None, "") = ask (don't guess)."""
    from scanner import langcheck
    from scanner import ocrscan
    _loupe.clear()
    # box = None: img already is the whole card (straightened) – read from it directly
    card = langcheck.card_view(img, best, frame, box) if box is not None else langcheck.card_view(img, best)
    if card is not None:
        foot = ocrscan.read_footer(langcheck._read(_band(card, FOOTER_BAND)))
        hits = group
        if foot.get("set"):
            hits = [r for r in hits if r["set_code"] == foot["set"]] or hits
        if foot.get("number"):
            hits = [r for r in hits if carddb.norm_number(r["number"], "").upper() == foot["number"].upper()] or                 (hits if foot.get("set") else [])
        # "FIN 46" read: 46 or the prerelease 46s (its "s" isn't printed) – where their images differ decides, or ask
        twins = [r for r in group if len(hits) == 1 and r is not hits[0] and _stamp_twins(r, hits[0])]
        if twins:
            return _twin_pick(card, hits + twins, best, fetch)
        if len(hits) == 1 and (foot.get("set") or foot.get("number")):
            why = f" · collector line ({(foot.get('set') or '').upper()} {foot.get('number') or ''})".replace(" )", ")")
            return _row_entry(hits[0], best), why
        pool = hits if len(hits) > 1 else group
        tpl = _symbol_gray(_band(card, SYMBOL_BAND))[6:-6, 10:-10]
        scores = []
        for r in pool:
            e = _row_entry(r, best)
            ref = _ref_symbol(e)
            if ref is None:
                if fetch is not None:
                    fetch([e])  # load for the next frame
                continue
            scores.append((float(cv2.matchTemplate(ref, tpl, cv2.TM_CCOEFF_NORMED).max()), e))
        scores.sort(key=lambda x: -x[0])
        # only if all prints could be compared and the symbol is unambiguous
        if len(scores) == len(pool) and len(scores) >= 2 and scores[0][0] >= 0.55 and                 scores[0][0] - scores[1][0] >= 0.15:
            pick = scores[0][1]
            twins = [r for r in group if r["id"] != pick["id"].rpartition("_")[0] and
                     _stamp_twins(r, {"number": pick["number"], "set_code": pick["set"]})]
            if twins:   # the symbol can't tell a print from its stamped twin
                own = next((r for r in group if r["id"] == pick["id"].rpartition("_")[0]), None)
                return _twin_pick(card, ([own] if own else []) + twins, best, fetch)
            return pick, f" · set symbol ({scores[0][0]:.2f} vs {scores[1][0]:.2f})"
    pref = [r for r in group if r["set_code"] in prefer_sets]
    # the log's set decides between reprints of other sets – never between a print and its stamped promo
    if len(pref) == 1 and not any(r is not pref[0] and _stamp_twins(r, pref[0]) for r in group):
        return _row_entry(pref[0], best), " · log set"
    if card is not None and "img" not in _loupe and any(_stamp_twins(a, b) for a in group for b in group):
        _loupe["img"] = _loupe_of(card, np.zeros(card.shape[:2], bool))   # the usual stamp place
    return None, ""


def _twin_pick(card, rows, best, fetch=None):
    """Prints the collector line can't tell apart (a print and its stamped promo): where their reference images
    differ – a stamp, a frame detail – which one the card in the camera matches. -> (entry, reason) or (None, "") =
    can't tell: an image missing (loaded for the next frame), the images the same, or too close -> the print
    question (the user's rule: print not certain -> ask)."""
    entries = [_row_entry(r, best) for r in rows]
    refs = []
    for e in entries:
        path = BASE / e["img"]
        ref = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE) if path.exists() else None
        if ref is None:
            if fetch is not None:
                fetch([e])
            return None, ""
        refs.append(cv2.GaussianBlur(cv2.resize(ref, (card.shape[1], card.shape[0]), interpolation=cv2.INTER_AREA),
                                     (5, 5), 0).astype(np.float32))
    seen = cv2.GaussianBlur(cv2.cvtColor(card, cv2.COLOR_BGR2GRAY) if card.ndim == 3 else card, (5, 5), 0)
    seen = seen.astype(np.float32)
    differ = np.zeros(seen.shape, bool)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            differ |= np.abs(refs[i] - refs[j]) > TWIN_DIFF
    _loupe.clear()
    _loupe["img"] = _loupe_of(card, differ)   # for the print question, in case it comes to that
    if differ.mean() < TWIN_AREA:
        return None, ""

    def z(a):   # brightness and contrast of the camera don't count – the shape of the difference does
        v = a[differ]
        return (v - v.mean()) / (v.std() + 1e-6)
    s = z(seen)
    dist = sorted((float(np.abs(s - z(r)).mean()), k) for k, r in enumerate(refs))
    (d1, k1), d2 = dist[0], dist[1][0]
    if d2 <= 0 or (d2 - d1) / d2 < TWIN_MARGIN:
        return None, ""
    e = entries[k1]
    _loupe.clear()
    return e, f" · stamp/detail ({e['set'].upper()} {e['number']}, {d1:.2f} vs {d2:.2f})"


def _loupe_of(card, differ):
    """The part of the card where the twins differ (or where a stamp sits), enlarged – so the print question shows the
    stamp at a glance instead of the user hunting for it on the card."""
    h, w = card.shape[:2]
    ys, xs = np.nonzero(differ)
    if differ.mean() >= TWIN_AREA and len(xs):
        x0, x1, y0, y1 = (float(np.percentile(xs, 2)) / w, float(np.percentile(xs, 98)) / w,
                          float(np.percentile(ys, 2)) / h, float(np.percentile(ys, 98)) / h)
        px, py = max(0.04, (x1 - x0) * 0.25), max(0.03, (y1 - y0) * 0.25)
        x0, x1, y0, y1 = max(0.0, x0 - px), min(1.0, x1 + px), max(0.0, y0 - py), min(1.0, y1 + py)
        bw, bh = (x1 - x0) * w, (y1 - y0) * h
        # spread over the card (a frame) or a thin line (a text line rendered a bit differently) – not a stamp: the
        # usual stamp place
        if (x1 - x0) * (y1 - y0) > 0.25 or max(bw, bh) > 3 * min(bw, bh):
            x0, y0, x1, y1 = STAMP_BOX
    else:
        x0, y0, x1, y1 = STAMP_BOX
    part = card[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    if not part.size:
        return None
    k = min(4.0, 420.0 / max(1, part.shape[1]))
    return cv2.resize(part, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)


def _stamp_twins(a, b):
    """Two prints the collector line can't tell apart: the same number apart from a stamp letter (46 / 46s, 46p) –
    the promo in "p" + the set or in the set itself. Magic only (Oliver): the other games mark their special editions
    differently – first the real-video list, then their own step."""
    import re
    if games.current().key != "mtg":
        return False
    na, nb = (re.sub(r"[sp★†]+$", "", str(r["number"]).lower()) for r in (a, b))
    sa, sb = a["set_code"].lower(), b["set_code"].lower()
    return na == nb and str(a["number"]) != str(b["number"]) and (sa == sb or sa == "p" + sb or sb == "p" + sa)


_groups = {}   # (game, print) -> rows with the same image (sure_print asks on every frame of a card)


def uncertain_prints(entry, index=None):
    """All prints the counted one can't be told from by its image: same image (art_group, without Magic – it
    settles that before counting) plus the game's twins (Magic: The List). [] or [one] = certain."""
    from cards import carddb
    g = games.current()
    key = (g.key, entry.get("id"))
    if key not in _groups:
        rows = [] if g.key == "mtg" else art_group(entry, index=index)
        try:
            with carddb.connection() as con:
                twins = g.print_twins(con, entry)
                if twins and not rows:
                    own = con.execute("SELECT * FROM cards WHERE set_code = ? AND number = ?",
                                      (entry["set"].lower(), str(entry["number"]))).fetchone()
                    rows = [dict(own)] if own else []
        except Exception:  # noqa: BLE001 – no card database
            twins = []
        if len(_groups) > 500:
            _groups.clear()
        _groups[key] = (rows + twins, bool(twins))
    return _groups[key]


def sure_print(frame, res, index=None):
    """The user's rule – if the print isn't certain, ask: a hit whose image several prints share is only counted
    if the collector line decides on this frame; otherwise it becomes a print question (the image match's pick
    first, then the most likely ones – carddb.print_likeliness). Twins only a symbol tells apart (The List) always
    ask. -> res (unchanged / the decided print / status "ask")"""
    from cards import carddb
    if res.get("status") == "ok" and _weak_match(res):   # not sure it's this card at all: ask, never count
        return dict(res, status="ask", cands=[(as_row(res["entry"]), res.get("strength", 0))],
                    pick=res["entry"].get("id"), how=(res.get("how") or "") + " · image match weak")
    if res.get("status") != "ok" or not games.current().print_ask:
        return res
    entry = res["entry"]
    group, twins = uncertain_prints(entry, index)
    if len(group) < 2:
        return res
    if not twins:
        box = None if _is_warped(res.get("box")) else res.get("box")
        pick, why = resolve_generic(frame, res["img"], box, entry, group)
        if why:
            return dict(res, entry=pick, how=(res.get("how") or "") + why)
    else:   # what the card shows narrows them down (e.g. Japanese or English name)
        card = res.get("card") if res.get("card") is not None else res.get("img") if _is_warped(res.get("box")) else None
        group = games.current().narrow_twins(card, entry, group) or group
        if len(group) == 1:
            pick = _row_entry(group[0])
            return dict(res, entry=pick, how=(res.get("how") or "") + " · language of the name")
    rows = sorted(group, key=lambda r: carddb.print_likeliness(r, pick=entry.get("id")))
    return dict(res, status="ask", cands=[(r, 1) for r in rows], pick=entry.get("id"),
                how=(res.get("how") or "") + " · print unclear")


def _weak_match(res):
    """Does this count rest on an image match below COUNT_NEEDS? (not: the unambiguous fingerprint, the collector line)"""
    how = res.get("how") or ""
    return "image match (" in how and "unambiguous" not in how and "collector line" not in how \
        and 0 < res.get("strength", 0) < COUNT_NEEDS


def resolve_generic(frame, img, box, best, group):
    """Pokémon, Yu-Gi-Oh!: same artwork in several prints – the collector line decides ("055/191", "RA05-EN085").
    Unreadable: the image match's pick stays (asking every time would hold up every reprint). -> (entry, reason)
    Runs after counting, in the background (app._print_check)."""
    from scanner import langcheck
    card = langcheck.card_view(img, best, frame, box) if box is not None else langcheck.card_view(img, best)
    if card is not None:
        hit = LiveScanner._read_pick(card, [(0.0, _row_entry(r), 0) for r in group])
        if hit is not None:
            return hit[0], f" · collector line ({hit[0]['set']} {hit[0]['number']})"
    return best, ""


# ---------- Live scanner: fast with stacks in the hand ----------
def match(q, ref):
    """Image match -> (points, homography crop->reference at working size, or None)."""
    qp, qd = q
    rp, rd = ref
    if len(qd) < 10 or len(rd) < 10:
        return 0, None
    good = [m[0] for m in hybrid._bf.knnMatch(qd, rd, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
    if len(good) < 10:
        return 0, None
    hmat, mask = cv2.findHomography(qp[[m.queryIdx for m in good]], rp[[m.trainIdx for m in good]], cv2.RANSAC, 6.0)
    if hmat is None or mask is None:
        return 0, None
    return int(mask.sum()), hmat


def card_box(hmat, box, frame_shape):
    """Position of the whole card in the camera image (from the homography) -> rect (x, y, w, h), slightly enlarged."""
    from scanner.common import H as RH, W as RW
    x0, y0, w, h = box
    try:
        inv = np.linalg.inv(hmat)
    except np.linalg.LinAlgError:
        return None
    corners = np.float32([[0, 0], [RW, 0], [RW, RH], [0, RH]]).reshape(-1, 1, 2)
    pts = cv2.perspectiveTransform(corners, inv).reshape(-1, 2)  # in the crop's working size
    pts[:, 0] = pts[:, 0] * w / RW + x0
    pts[:, 1] = pts[:, 1] * h / RH + y0
    fh, fw = frame_shape[:2]
    bx0, by0 = pts.min(axis=0)
    bx1, by1 = pts.max(axis=0)
    bw, bh = bx1 - bx0, by1 - by0
    if bw < 40 or bh < 56 or bw > fw or bh > fh * 1.2 or not 0.45 < bw / max(1, bh) < 1.1:
        return None  # implausible (homography distorted)
    pad = 0.05
    bx0, by0 = max(0, bx0 - bw * pad), max(0, by0 - bh * pad)
    bx1, by1 = min(fw, bx1 + bw * pad), min(fh, by1 + bh * pad)
    return int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)


def lang_img_path(entry, lang):
    """Reference image of a card in another language (cache; a separate folder per game)."""
    from scanner import common
    root = BASE if games.current().key == "mtg" else common.IMAGES.parent
    return root / "images_lang" / entry["set"].lower() / f"{entry['number']}_{lang}.jpg"


class LiveScanner:
    """Recognition frame by frame, built for speed:
    1. First look exactly where the last card was (in a stack the next one is almost always in the same
       place): one window, ~40 ms.
    2. Otherwise six card-sized windows in the scan frame.
    Missing reference images (cards from sets that are not loaded) are loaded in the background – recognition never
    waits for them; they are usually there by the next frame."""

    def __init__(self):
        self.prior = None          # (x, y, w, h) of the last confirmed card in the camera image
        self._loading = set()
        self.allow_foil = False    # scan mode "AI, foil – beta": allow foil-only prints
        self._groups = {}          # (name, set, number) -> all prints with this image
        self._resolved = None      # (name, chosen print, time) – valid as long as the card stays there
        # Languages to compare additionally when the English image barely fits (e.g. a German card with
        # little distinctive artwork: different text -> too few points). Set by the main window from the settings.
        self.langs = []
        # for identical images prefer Asian prints (when currently scanning Asian cards) – otherwise western ones
        self.asia_ok = False

    def _crop(self, frame, box):
        x, y, w, h = box
        return frame[y:y + h, x:x + w]

    def _fetch_later(self, entries):
        for e in entries:
            p = BASE / e["img"]
            key = str(p)
            if key in self._loading or p.exists() or not e.get("img_normal") or imgcache.offline():
                continue
            self._loading.add(key)

            def work(p=p, url=e["img_normal"], key=key):
                try:
                    imgcache.fetch(p, url)
                    hybrid._ref_path(p)  # compute the image features right away
                finally:
                    self._loading.discard(key)
            hybrid._prefetch_pool.submit(work)

    def _lang_ref(self, entry, lang):
        """Features of the image in this language – otherwise None (then load in the background, never wait for it)."""
        p = lang_img_path(entry, lang)
        ref = hybrid._ref_path(p)
        if ref is not None:
            return ref
        key = str(p)
        if key in self._loading or imgcache.is_missing(key) or imgcache.offline():
            return None
        from cards import carddb
        if carddb.exists() and carddb.lacks_language(entry["set"], entry["number"], lang):
            imgcache.mark_missing(key)   # the print doesn't exist in this language: compare with English, ask nobody
            return None
        self._loading.add(key)

        def work():
            try:
                from cards import library   # the game's own source (Magic: Scryfall, Pokémon: TCGdex …)
                url = library.image_url(entry["set"], entry["number"], lang, "normal")
                if not url:
                    imgcache.mark_missing(key)
                    return
                if imgcache.fetch(p, url):
                    hybrid._ref_path(p)
                else:
                    imgcache.mark_missing(key)  # doesn't exist in this language – not again for an hour
            finally:
                self._loading.discard(key)
        hybrid._prefetch_pool.submit(work)
        return None

    def still(self, frame, entry, need):
        """Is the known card still there (at its last position, at least need points)?"""
        if self.prior is None:
            return False
        ref = hybrid._ref_path(BASE / entry["img"])
        img = self._crop(frame, self.prior)
        if ref is None or not img.size:
            return False
        inl, _ = match(hybrid.query_features(img), ref)
        return inl >= need

    def step(self, frame, rect, index, prefer_sets=(), focus=()):
        """-> like recognize(): {"status", "entry", "cands", "img", "how", "sim", "strength", "box"}"""
        if not len(index) and games.current().footer_parse is not None:
            return self._footer_only(frame, rect)
        if self.prior is not None:
            res = self._try(frame, [(self._crop(frame, self.prior), self.prior)], index, prefer_sets, focus=focus)
            if res["status"] != "none":
                res["from_prior"] = True
                return res
        res = self._try(frame, card_windows(frame, rect), index, prefer_sets, center=rect, focus=focus)
        res["from_prior"] = False
        return res

    def _try(self, frame, boxed, index, prefer_sets, center=None, focus=()):
        boxed = [(im, box) for im, box in boxed if im.size]
        out = {"status": "none", "entry": None, "cands": [], "img": boxed[0][0] if boxed else None, "how": "",
               "sim": 0.0, "strength": 0, "box": None}
        if not boxed:
            return out
        wins = [im for im, _ in boxed]
        pool, lists = {}, []
        embs = fingerprint.embed(wins)
        self._embs = embs   # the windows' fingerprints – _rival compares a print outside the search window with them
        for wi, found in enumerate(index.search_many(embs, 8)):
            lists.append(found)
            for entry, sim in found[:PER_WINDOW]:
                if entry["id"] not in pool or pool[entry["id"]][0] < sim:
                    pool[entry["id"]] = (sim, entry, wi)
        if not pool:
            return out
        quick_lists = lists
        if focus:   # filtered scan: the chosen sets' prints ranked on their own – taken only where the card is from
            rows = index.rows_of_sets(focus)   # there (the full search above is the check, never a guess into them)
            if len(rows):
                flists = index.search_many(embs, 8, rows=rows)
                # only for a print without same-image twins: those (a stamped promo of the set's print …) are
                # settled by resolve_print, the focus ranking would hide them
                quick_lists = [fl if fl and gl and gl[0][1] - fl[0][1] <= FOCUS_EPS
                               and len(self._group(fl[0][0], index)) <= 1 else gl
                               for gl, fl in zip(lists, flists)]
                for wi, (gl, fl) in enumerate(zip(lists, flists)):   # … and they join the image match
                    if fl and gl and gl[0][1] - fl[0][1] <= FOCUS_EPS:
                        for entry, sim in fl[:PER_WINDOW]:
                            if entry["id"] not in pool or pool[entry["id"]][0] < sim:
                                pool[entry["id"]] = (sim, entry, wi)
        quick = self._clear_fingerprint(quick_lists, boxed, center)
        if quick is not None:
            entry, wi, gap_name, gap_print = quick
            out.update(status="ok", entry=entry, strength=WEAK + 1, img=wins[wi], box=boxed[wi][1],
                       sim=quick_lists[wi][0][1], how=f"SCAN° fingerprint unambiguous (gap {gap_name:.2f} / {gap_print:.2f})"
                       + (" · set focus" if quick_lists[wi] is not lists[wi] else ""))
            self.prior = boxed[wi][1]
            return out
        near = sorted(pool.values(), key=lambda t: -t[0])[:POOL]
        out["guess"] = near[0][1]["name"]   # most likely name (card search offered when nothing is found)
        top = near[0][0]
        near = [t for t in near if t[0] >= top - SIM_WINDOW]
        self._fetch_later([e for _, e, _ in near])
        # image features cost ~12 ms per window: check only the two most promising windows
        best_win = []
        for _, _, wi in near:
            if wi not in best_win:
                best_win.append(wi)
        near = [t for t in near if t[2] in best_win[:2]]
        feats, scored, sure = {}, [], None
        for sim, entry, wi in near:
            if sure is not None and entry["name"] != sure:
                continue  # clear hit found: only check other prints of the same card (print question)
            ref = hybrid._ref_path(BASE / entry["img"])  # only what is already there
            if ref is None:
                continue
            if wi not in feats:
                feats[wi] = hybrid.query_features(wins[wi])
            inl, hmat = match(feats[wi], ref)
            scored.append((entry, sim, inl, wi, hmat))
            if inl >= SURE and sure is None:
                sure = entry["name"]
        lang_hit = None
        if self.langs and near and (not scored or max(t[2] for t in scored) < SURE):
            # English image fits only narrowly: compare the image in the card's language (different text, ~5 ms each)
            sim, entry, wi = near[0]
            for lang in self.langs:
                ref = self._lang_ref(entry, lang)
                if ref is None:
                    continue
                if wi not in feats:
                    feats[wi] = hybrid.query_features(wins[wi])
                inl, hmat = match(feats[wi], ref)
                if inl >= MIN_INLIERS and inl > max([t[2] for t in scored] + [0]):
                    scored.append((entry, sim, inl, wi, hmat))
                    lang_hit = (entry["name"], lang)
                    break
        out["sim"] = top
        if not scored:
            # Reference images still missing (first scan of this card): don't wait – read the collector line and match
            # it against the fingerprint candidates. If exactly one print matches (number + set or "no./total"),
            # two independent methods agree: count it. The reference image keeps loading in the background.
            hit = self._text_pick(frame, boxed, near)
            if hit is not None:
                entry, wi = hit
                out.update(status="ok", entry=entry, strength=STRONG, img=wins[wi], box=boxed[wi][1],
                           how=f"SCAN° fingerprint ({top:.2f}) + collector line")
                # a print and its stamped promo (FIN 91 / the prerelease 91s) have the same collector line – without
                # the reference images nothing can tell them apart: ask (the user's rule), never count one of them
                twins = self._stamp_twins_of(entry, index)
                if twins:
                    out.update(status="ask", cands=[(r, 0) for r in twins], pick=entry["id"],
                               how=out["how"] + " · stamp twin, no reference image yet")
                return out
            out["how"] = "Loading reference images …"
            return out
        scored.sort(key=lambda t: -t[2])
        # same image as a western and an Asian print (e.g. Eisenbündel DE / "Festival Terastal ex" JA): the image
        # can't decide – on a (near) tie take the print of the language group currently being scanned
        # (default western); if the language is wrong, language detection then switches to the correct print.
        # Nothing is excluded: a Japanese card in the middle of a German collection stays recognisable.
        asia = asian_prints()
        if len(scored) > 1 and asia:
            is_asia = lambda s: (s[0]["set"].lower(), str(s[0]["number"])) in asia   # noqa: E731
            if is_asia(scored[0]) != self.asia_ok:
                alt = next((s for s in scored[1:] if is_asia(s) == self.asia_ok and s[2] >= 0.85 * scored[0][2]), None)
                if alt is not None:
                    scored.remove(alt)
                    scored.insert(0, alt)
        best = scored[0]
        out["strength"], out["img"], out["box"] = best[2], wins[best[3]], boxed[best[3]][1]
        if best[2] >= WEAK:
            out["hint"] = best[0]["name"]  # weak hint (counts as a second vote for a real hit)
        if best[2] < MIN_INLIERS:
            return out
        fp_first = max(pool.values(), key=lambda v: v[0])[1]["name"]   # rank 1 by fingerprint
        if (best[2] < SURE and best[1] < top - 0.06) or (best[2] < 50 and best[0]["name"] != fp_first) or                 (best[2] < FP_WEAK_NEEDS and top < FP_KNOWN):
            # narrow image match for a card the fingerprint clearly does NOT rank first: cards of one generation
            # share frames and text boxes – a partly covered card then also fits another one (measured:
            # Mega Charizard X ex with a covered corner -> Mega Gardevoir ex with 39 points). Likewise when the
            # fingerprint knows none of the candidates well (Lorcana Baloo with a covered corner -> Genie, 55 points
            # from the shared frame; right hits with such a weak fingerprint had 156+ points). Rather the next frame.
            out["how"] = "Image match close, fingerprint disagrees"
            return out
        warped = _is_warped(out["box"])   # straightened card: its position IS the card
        box = tuple(out["box"]) if warped else             card_box(best[4], out["box"], frame.shape) if best[4] is not None and out["box"] is not None else None
        if center is not None:  # whole-frame search: only the card in the centre counts (not the stack beside it)
            cx, cy, cw, ch = center
            if box is None or abs(box[0] + box[2] / 2 - (cx + cw / 2)) > cw * CENTER_TOL:
                out["strength"] = 0
                out["how"] = "Card at the edge (not the top one)"
                return out
        if box is not None:
            self.prior = box
        if lang_hit is not None and lang_hit[0] == best[0]["name"]:
            out["lang"] = lang_hit[1]  # confirmed via the image in this language – so the language is settled
        # all prints with this image (the AI search only returns a few of them by chance)
        # Magic: the print question is settled here (collector line, set symbol, otherwise ask). Other games: the
        # image match's pick counts right away – app._print_check reads the collector line afterwards in the
        # background (reprints cost no scan time)
        group = [] if games.current().print_check_after_count else self._group(best[0], index)
        how = f"SCAN° fingerprint ({best[1]:.2f}) + image match ({best[2]})"
        if games.current().print_check_after_count:
            # other prints of the same card with a similar but different image (Lorcana p2-24a/24b: same artist, two
            # versions of the art) may never reach the image match – the fingerprint (on the CPU: quantized) can rank
            # one of them outside the window. Compare them directly: clearly better = that one, close = ask.
            rival = self._rival(best, feats, index)
            if rival == "wait":   # their reference images are still loading – rather the next frame than a guess
                out["status"], out["how"] = "none", "Checking a similar print …"
                return out
            if rival is not None:
                r_entry, r_row, r_inl = rival
                if r_inl >= RIVAL_WINS * best[2]:
                    out.update(status="ok", entry=r_entry, strength=r_inl,
                               how=f"SCAN° fingerprint + image match ({r_inl}, similar print {best[2]})")
                    return out
                r_fp = self._fp_of(r_entry, best[3], index)
                if r_inl >= RIVAL_CLOSE * best[2] and (r_fp is None or r_fp >= best[1] - RIVAL_FP_GAP):
                    from cards import carddb
                    with carddb.connection() as con:
                        mine = con.execute("SELECT * FROM cards WHERE set_code = ? AND number = ?",
                                           (best[0]["set"].lower(), str(best[0]["number"]))).fetchone()
                    if mine is not None:
                        out.update(status="ask", cands=[(dict(mine), best[2]), (r_row, r_inl)], pick=best[0]["id"],
                                   how=how + f" · similar print ({r_inl})")
                        return out
        if len(group) <= 1:
            out.update(status="ok", entry=best[0] if not group else _row_entry(group[0], best[0]) if
                       group[0]["set_code"] != best[0]["set"].lower() else best[0], how=how)
            return out
        last = self._resolved
        if last is not None and last[0] == best[0]["name"] and time.time() - last[2] < 4.0:
            pick, why = last[1], " · same print as before"  # same card still there: don't re-read every frame
        else:
            pick, why = resolve_print(frame, wins[best[3]], None if warped else out["box"], best[0], group,
                                      prefer_sets, self._fetch_later)
        if pick is not None:
            self._resolved = (best[0]["name"], pick, time.time())
            out.update(status="ok", entry=pick, how=how + why)
        else:
            seen = {(t[0]["set"].lower(), str(t[0]["number"])) for t in scored if t[2] >= hybrid.CLOSE * best[2]}
            ranked = sorted(group, key=lambda r: ((r["set_code"], str(r["number"])) not in seen, r["set_code"]))
            out.update(status="ask", cands=[(r, best[2] if (r["set_code"], str(r["number"])) in seen else 0)
                                            for r in ranked])
            if _loupe.get("img") is not None:   # stamp twins undecided: the stamp's place, enlarged
                img = _loupe.pop("img")
                if str(best[0].get("id") or "").endswith("_1"):   # the back of a double-faced card: no stamp there
                    out["stamp_front"] = True
                else:
                    out["loupe"] = img
        return out

    @staticmethod
    def _clear_fingerprint(lists, boxed, center):
        """Is the fingerprint unambiguous on its own? -> (entry, window, name gap, print gap) or None.
        In the best window: rank 1 must be FP_NAME_GAP ahead of the best card with a different name and FP_PRINT_GAP
        ahead of the next print of the same name (reprints with the same image are otherwise settled by the collector
        line/image match). Search in the whole frame: only the card in the centre."""
        best = max(range(len(lists)), key=lambda i: lists[i][0][1] if lists[i] else -1, default=None)
        if best is None or len(lists[best]) < 2:
            return None
        found = lists[best]
        top, sim = found[0]
        other = next((s for e, s in found[1:] if e["name"] != top["name"]), None)
        same = next((s for e, s in found[1:] if e["name"] == top["name"]), None)
        if other is None:   # only the same name among the top 8: gap unknown – better check
            return None
        gap_name, gap_print = sim - other, sim - (same if same is not None else other)
        if gap_name < FP_NAME_GAP or gap_print < FP_PRINT_GAP:
            return None
        if top.get("art_series"):   # an art card is the card's artwork alone: the image match decides (bench
            return None             # prerelease-dsk: a glared DSK card read as its ADSK art card)
        if center is not None:
            cx, _cy, cw, _ch = center
            bx, _by, bw, _bh = boxed[best][1]
            if abs(bx + bw / 2 - (cx + cw / 2)) > cw * CENTER_TOL:
                return None
        return top, best, gap_name, gap_print

    TEXT_GAP = 0.35   # read the collector line at most this often (s) while reference images are missing

    def _text_pick(self, frame, boxed, near):
        """Read the collector line and find the matching candidate -> (entry, window) or None. Reads in the
        background (~0.3 s, the scanner keeps running) and uses the result on the next frame of the same card."""
        import threading
        now = time.time()
        ids = {e["id"] for _, e, _ in near}
        res = getattr(self, "_text_res", None)
        if res is not None and now - res[0] < 1.5 and res[1] & ids:
            hit = res[2]
            if hit is not None and hit[0]["id"] in ids:
                return hit[0], near[0][2]
        job = getattr(self, "_text_job", None)
        if near and (job is None or not job.is_alive()) and now - getattr(self, "_text_t", 0.0) >= self.TEXT_GAP:
            self._text_t = now
            wi = near[0][2]
            img, box, full, cands = boxed[wi][0].copy(), boxed[wi][1], frame.copy(), list(near)

            def work():
                card = img
                try:   # find the card in the window and straighten it – else the number line misses the read band
                    from scanner import ocrscan
                    found = [] if _is_warped(box) else ocrscan.find_card(full, box)   # already straightened
                    if found:
                        card = found[0]
                except Exception:  # noqa: BLE001
                    pass
                self._text_res = (time.time(), {e["id"] for _, e, _ in cands}, self._read_pick(card, cands))
            self._text_job = threading.Thread(target=work, daemon=True)
            self._text_job.start()
        return None

    @staticmethod
    def _read_pick(img, near):
        """Game-independent: the candidates know set and number; a hit only if exactly ONE print appears on the card
        that way – as "no./total" (Pokémon 055/191), with the set code next to it (Magic "MKM … 0123") or as one string
        (Yu-Gi-Oh! "SV04-EN055"). Only the band at the bottom and the one below the artwork are read."""
        import re
        if games.current().footer_parse is not None:   # e.g. Lorcana: set "1" would match every digit in the text
            got = LiveScanner.read_footer(img)
            if got is None:
                return None
            hits = [(e, w) for _sim, e, w in near
                    if (str(e["set"]).lower(), str(e["number"]).lower()) == (got["set"], got["number"])]
            return hits[0] if hits else None
        try:
            from scanner import ocrscan
            if not ocrscan.available():
                return None
            img = cv2.resize(img, (ocrscan.W, ocrscan.H), interpolation=cv2.INTER_AREA)
            text = " ".join(t[0] for band in ((0.0, 0.89, 1.0, 1.0), (0.45, 0.68, 1.0, 0.77))
                            for t in ocrscan._lines(ocrscan._box(img, band)))
        except Exception:  # noqa: BLE001 – no text recognition: wait for the reference image as before
            return None
        up = re.sub(r"\s+", " ", text.upper()).replace("O", "0").replace("’", "")
        flat = up.replace(" ", "")
        # "no./total" – on a Magic card "3/3" is power/toughness, not a number: there only a total above 20 counts
        # (Tellah 3/3 was read as Syncopate GK1 3)
        nums = {carddb.norm_number(m.group(1), "") for m in re.finditer(r"(?<![A-Z0-9])(\d{1,4})\s*/\s*(\d{1,4})", up)
                if games.current().key != "mtg" or int(m.group(2)) > 20}
        hits = []
        mtg = games.current().key == "mtg"
        for _sim, entry, w in near:
            num = str(entry["number"]).upper().replace("O", "0")
            code = str(entry["set"]).upper().replace("O", "0")
            bare = carddb.norm_number(num)
            # Magic: the set code as a word of its own ("DSK • EN") – in the text without spaces "P10E" turns up in
            # any run of letters and digits, and "2" fits nearly every line (The Swarmweaver read as Treetop Village)
            has_code = re.search(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])", up) is not None if mtg else code in flat
            ok = (bare in nums                                                     # 055/191
                  or (len(num) >= 4 and not num.isdigit() and num in flat)         # EN055, SWSH286, TG12
                  or (has_code and re.search(rf"(?<!\d)0*{re.escape(bare)}(?!\d)", up) is not None))  # MKM … 0123
            if ok and entry["id"] not in {e["id"] for e, _ in hits}:
                hits.append((entry, w))
        if len(hits) == 1 or (len(hits) > 1 and len({(e["set"], e["number"]) for e, _ in hits}) == 1):
            return hits[0]
        return None

    @staticmethod
    def read_footer(img):
        """Collector line of a straightened card via the game's bands and parser (games.<game>.footer_bands /
        footer_parse) -> {"set", "number", "lang"} or None. Landscape cards (Lorcana Locations) lie turned by 90° on
        the straightened image – their bands (footer_bands_landscape) are read rotated, after the normal ones.
        footer_margin (games.base): a number line that starts closer than this to the band's edge (share of the band
        width) may be cut off – the card held at an angle, partly outside the picture: "240/204" read as "40/204" twice
        = a wrong card counted. Such a read only counts if the game confirms it (footer_confirm: e.g. the print's name
        on the card) – as does a read the game marks as doubtful anywhere (footer_needs_confirm: Lorcana's variant
        letters)."""
        g = games.current()
        margin = g.footer_margin
        try:
            from scanner import ocrscan
            if not ocrscan.available() or img is None or not img.size:
                return None
            img = cv2.resize(img, (ocrscan.W, ocrscan.H), interpolation=cv2.INTER_AREA)
            turn = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
            for item in tuple(g.footer_bands) + tuple(g.footer_bands_landscape):
                band, deg = (item, 0) if len(item) == 4 else item   # (x0, y0, x1, y1) or ((x0, y0, x1, y1), degrees)
                crop = ocrscan._box(img, band)
                if deg in turn:
                    crop = cv2.rotate(crop, turn[deg])
                lines = ocrscan._lines(crop)
                got = g.footer_parse(" ".join(t[0] for t in lines))
                if got is None:
                    continue
                start = min((t[3] for t in lines if any(ch.isdigit() for ch in t[0])), default=None)
                edge = margin and start is not None and start < margin * crop.shape[1]
                if (edge or g.footer_needs_confirm(got)) and not g.footer_confirm(img, got, deg):
                    continue   # at the edge (front of the number may be cut off) or a doubtful read, not confirmed
                return got
        except Exception:  # noqa: BLE001 – no text recognition: nothing read
            return None
        return None

    FOOT_AGREE = 1.5   # collector line only: two reads of the same print within this time (s) count

    def _footer_only(self, frame, rect):
        """No fingerprint index for this game (Lorcana: not shipped until the user OKs it): find the card, read its
        collector line in the background (TEXT_GAP) and look the print up in the card database. Counts only when two
        reads within FOOT_AGREE seconds agree – never asks, otherwise "none" (that keeps it at 0 false)."""
        import threading
        out = {"status": "none", "entry": None, "cands": [], "img": None, "how": "Reading the collector line …",
               "sim": 0.0, "strength": 0, "box": None, "footer": True}   # footer: the slower read-only path
        now = time.time()
        reads = [r for r in getattr(self, "_foot_reads", []) if now - r[0] < self.FOOT_AGREE]
        self._foot_reads = reads
        if len(reads) >= 2 and reads[-1][1] is not None and reads[-1][1]["id"] == (reads[-2][1] or {}).get("id"):
            _t, entry, img, box, lang = reads[-1]
            out.update(status="ok", entry=entry, strength=STRONG, img=img, box=box, card=img,   # the straightened card
                       how="Collector line (read twice)")
            if lang and lang != "en":
                out["lang"] = lang   # printed on the card – the language is settled
            return out
        job = getattr(self, "_foot_job", None)
        if (job is None or not job.is_alive()) and now - getattr(self, "_foot_t", 0.0) >= self.TEXT_GAP:
            self._foot_t = now
            full = frame.copy()

            def work():
                entry = img = box = lang = None
                try:
                    from scanner import ocrscan
                    found = ocrscan.find_card_boxed(full, rect)
                    if not found:   # weak light: once more with more local contrast (only then – good frames
                        found = ocrscan.find_card_boxed(_local_contrast(full), rect)   # don't pay for it)
                    if found:
                        img, box = found[0]
                        got = self.read_footer(img)
                        row = hybrid.row_by_print(got["set"], got["number"]) if got is not None else None
                        if row is None:   # tilted card: once more by its real corners (only then – costs a read)
                            again = ocrscan.find_card_boxed(full, rect, corners=True) \
                                or ocrscan.find_card_boxed(_local_contrast(full), rect, corners=True)
                            if again:
                                got = self.read_footer(again[0][0])
                                row = hybrid.row_by_print(got["set"], got["number"]) if got is not None else None
                                if row is not None:
                                    img, box = again[0]
                        if row is not None:   # by set code + number – fits every game ("AB17-001" too)
                            from cards import carddb
                            entry = carddb.entry_from_row(row)
                            entry["img_normal"] = row.get("img_normal")
                            lang = got.get("lang")
                except Exception:  # noqa: BLE001 – a failed read is just no read
                    entry = None
                self._foot_reads = [r for r in getattr(self, "_foot_reads", [])
                                    if time.time() - r[0] < self.FOOT_AGREE] + [(time.time(), entry, img, box, lang)]
            self._foot_job = threading.Thread(target=work, daemon=True)
            self._foot_job.start()
        return out

    _rivals = {}   # (name, artist) -> rows with that name + artist (_rival)

    def _fp_of(self, entry, wi, index):
        """Fingerprint similarity of window wi to this print (also when the search didn't return it) or None."""
        v = index.vector(entry["id"]) if index is not None else None
        embs = getattr(self, "_embs", None)
        if v is None or embs is None or wi >= len(embs):
            return None
        return float(np.asarray(embs[wi], np.float32) @ v)

    def _rival(self, best, feats, index):
        """The best other print of best's card with its OWN image (same name + artist, not in its art group: those are
        settled by the collector line in sure_print), by image match against the same window. -> (entry, row, points),
        None (no such print, or all far behind), or "wait" (a reference image is still loading)."""
        from cards import carddb
        entry, wi = best[0], best[3]
        try:
            with carddb.connection() as con:
                me = con.execute("SELECT name, artist FROM cards WHERE set_code = ? AND number = ?",
                                 (entry["set"].lower(), str(entry["number"]))).fetchone()
                if me is None or not me["artist"]:
                    return None
                key = (me["name"], me["artist"])
                if key not in LiveScanner._rivals:
                    if len(LiveScanner._rivals) > 2000:
                        LiveScanner._rivals.clear()
                    LiveScanner._rivals[key] = [dict(r) for r in con.execute(
                        "SELECT * FROM cards WHERE name = ? AND artist = ?", key)]
        except Exception:  # noqa: BLE001 – no card database
            return None
        same = {str(r["id"]) for r in uncertain_prints(entry, index)[0]}
        own = entry["id"].rsplit("_", 1)[0]
        # stamped twins (46 / prerelease 46s, promo pack 46p) aren't rivals: the same image, the image match would pick
        # by noise – resolve_print decides them (where their images differ) or asks
        mine = {"number": entry["number"], "set_code": entry["set"]}
        rows = [r for r in LiveScanner._rivals[key] if str(r["id"]) != own and str(r["id"]) not in same
                and not _stamp_twins(r, mine)][:RIVALS]
        if not rows or wi not in feats:
            return None
        found, waiting = None, False
        for r in rows:
            e = _row_entry(r)
            ref = hybrid._ref_path(BASE / e["img"])
            if ref is None:
                self._fetch_later([e])
                waiting = waiting or bool(e.get("img_normal")) and not imgcache.is_missing(e.get("img_normal"))
                continue
            inl, _ = match(feats[wi], ref)
            if found is None or inl > found[2]:
                found = (e, r, inl)
        if found is not None and found[2] >= RIVAL_CLOSE * best[2]:
            return found
        return "wait" if waiting else None

    @staticmethod
    def _stamp_twins_of(entry, index=None):
        """The print and its stamped twins (46 / 46s, 46p; the promo set "p" + set) straight from the card database –
        whether or not their images are in the art group. -> [own row, twin rows …], or [] when it has none (other
        games: always [] – _stamp_twins is Magic only)."""
        import re
        from cards import carddb
        if games.current().key != "mtg":
            return []
        code, num = str(entry["set"]).lower(), str(entry["number"])
        base = re.sub(r"[sp★†]+$", "", num.lower())
        sets = {code, "p" + code} | ({code[1:]} if code.startswith("p") else set())
        try:
            with carddb.connection() as con:
                rows = [dict(r) for r in con.execute(
                    f"SELECT * FROM cards WHERE set_code IN ({','.join('?' * len(sets))}) AND number LIKE ?",
                    (*sets, base + "%"))]
        except Exception:  # noqa: BLE001 – no card database
            return []
        own = [r for r in rows if r["set_code"] == code and str(r["number"]) == num]
        seen = set(str(entry["name"]).split(" // "))   # a double-faced card: either face (its back was read)
        twins = [r for r in rows if r not in own and seen & set(str(r["name"]).split(" // "))
                 and _stamp_twins(r, {"set_code": code, "number": num})]
        return own + twins if own and twins else []

    def _group(self, entry, index=None):
        key = (entry["name"], entry["set"].lower(), str(entry["number"]), self.allow_foil)
        if key not in self._groups:
            self._groups[key] = art_group(entry, self.allow_foil, index)
        return self._groups[key]
