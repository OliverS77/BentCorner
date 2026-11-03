"""Tauschticket: ein Tauschangebot als Bild, das Bent°Corner wieder einlesen kann.

Das Bild trägt die Daten zweimal:
  1. vollständig als Text in der PNG-Datei („BentCornerTicket“) – geht verloren, wenn ein Messenger das Bild neu
     komprimiert;
  2. als Pixel-Code unten auf dem Ticket (helle/dunkle Blöcke wie ein Abriss-Rand) – übersteht Verkleinern und JPEG.
     Aufbau: Kopf (Version, Blöcke, Länge) + Daten (zlib-JSON ohne Kartennamen), je Block mit Reed-Solomon-Prüfbytes
     (rscode), mit einem festen Muster gemischt, Zeile für Zeile von unten nach oben.

Ticket (dict): {"v": 1, "id", "t", "f": [Profil-ID, Name] (wer es ausgestellt hat), "o": [Profil-ID, Name] (an wen),
"a": Karten von f an o, "b": Karten von o an f}. Karte: [Set, Nummer, Sprache, Foil 0/1, Anzahl, Name?, Spiel?].
Gemischte Tickets: Karten eines anderen Spiels als das des Tickets („g“) tragen ihr Spiel an 7. Stelle; im Pixel-Code
stehen sie als „ga“/„gb“ ([Index, Spiel]) – ältere Versionen sehen dort nur die ersten fünf Felder.
"""
import json
import time
import uuid
import zlib

import rscode

VERSION = 1
TEXT_KEY = "BentCornerTicket"
# Raster im Bild (logische Pixel). Zwei Formate: der Kassenbon (hochkant, 720 px breit – auf dem Handy zum
# Reinzoomen; so wird jetzt ausgestellt) und das alte Querformat (1200 px – wird weiter gelesen).
class Layout:
    def __init__(self, w, x0, m, max_rows):
        self.W, self.X0, self.M, self.MAX_ROWS = w, x0, m, max_rows
        self.COLS = (w - 2 * x0) // m


RECEIPT = Layout(720, 40, 8, 110)
WIDE = Layout(1200, 48, 6, 40)
LAYOUTS = (RECEIPT, WIDE)
W, X0, M, COLS, MAX_ROWS = RECEIPT.W, RECEIPT.X0, RECEIPT.M, RECEIPT.COLS, RECEIPT.MAX_ROWS
BOTTOM = 30          # Abstand der untersten Blockzeile zum unteren Bildrand
_HEAD, _HEAD_SYM = 4, 8
ID_LEN = 12          # im Pixel-Code reicht der Anfang der Profil-ID


def new(me, friend, give, get, trade_id=None, version=1, kind="o", money=0.0):
    """me/friend: (Profil-ID, Name); give: Karten von mir an friend, get: von friend an mich.
    trade_id: Tausch-ID (gleich über alle Versionen eines Tauschs, Standard = Ticketnummer), version: 1, 2 … bei
    Gegenangeboten, kind: "o" Angebot · "f" Abschluss (wer es einliest, bekommt gebucht), money: € von me an friend
    (negativ = friend zahlt)."""
    tid = uuid.uuid4().hex[:8]
    g = _game()

    def norm(c):
        c = _card(c)
        return c[:6] if len(c) > 6 and c[6] in (g, "", None) else c
    return {"v": VERSION, "id": tid, "t": int(time.time()),
            "f": [me[0] or "", me[1] or ""], "o": [friend[0] or "", friend[1] or ""],
            "a": [norm(c) for c in give], "b": [norm(c) for c in get],
            "x": trade_id or tid, "n": int(version), "k": kind, "m": int(round(float(money or 0) * 100)),
            "g": g}


def _game():
    import games
    return games.current().key


def game_of(t):
    """Spiel des Tickets (Tickets ohne Angabe: Magic)."""
    return t.get("g") or "mtg"


def card_game(c, t):
    """Spiel einer Karte im Ticket: eigenes (7. Feld) oder das des Tickets."""
    return (c[6] if isinstance(c, list) and len(c) > 6 and c[6] else None) or game_of(t)


def games_in(t):
    """Alle Spiele eines Tickets (das des Tickets zuerst)."""
    out = [game_of(t)]
    for c in (t.get("a") or []) + (t.get("b") or []):
        g = card_game(c, t)
        if g not in out:
            out.append(g)
    return out


def kind(t):
    """"o" Angebot, "f" Abschluss – Tickets vor v0.8.2 (ohne Art) gelten als Abschluss (wurden direkt gebucht)."""
    return t.get("k") or "f"


def money_from_me(t, my_id):
    """Geldbetrag aus meiner Sicht in €: positiv = ich zahle, negativ = ich bekomme."""
    m = int(t.get("m") or 0) / 100
    sd = side(t, my_id)
    if sd is None:
        return 0.0
    return m if sd[2] == (t.get("o") or ["", ""]) else -m


def _card(c):
    if isinstance(c, (list, tuple)):
        return list(c)
    out = [str(c.get("set") or "").lower(), str(c.get("number") or ""), c.get("lang") or "en",
           1 if c.get("foil") else 0, int(c.get("count") or 1), c.get("name") or ""]
    return out + [c["game"]] if c.get("game") else out


def label(t):
    """Ticketnummer zum Anzeigen: 7F3A-21C9."""
    i = str(t.get("id") or "").upper()
    return f"{i[:4]}-{i[4:8]}" if len(i) >= 8 else i


def side(t, my_id):
    """Aus meiner Sicht: -> ("give", "get", Partner [ID, Name]) oder None, wenn das Ticket nicht mich betrifft."""
    def me(pid):
        pid = str(pid or "")
        return bool(pid) and bool(my_id) and (my_id.startswith(pid) if len(pid) < len(my_id) else pid == my_id)
    if me((t.get("o") or [""])[0]):
        return t.get("b") or [], t.get("a") or [], t.get("f") or ["", ""]
    if me((t.get("f") or [""])[0]):
        return t.get("a") or [], t.get("b") or [], t.get("o") or ["", ""]
    return None


# ---------- Bytes ----------
def _compact(t):
    """Für den Pixel-Code: ohne Kartennamen, Profil-IDs gekürzt."""
    out = {"v": t["v"], "id": t["id"], "t": t["t"],
           "f": [str(t["f"][0])[:ID_LEN], t["f"][1][:24]], "o": [str(t["o"][0])[:ID_LEN], t["o"][1][:24]],
           "a": [c[:5] for c in t["a"]], "b": [c[:5] for c in t["b"]]}
    if t.get("g") and t["g"] != "mtg":   # Spiel (Magic: ohne Angabe – wie alte Tickets)
        out["g"] = t["g"]
    for key in ("a", "b"):   # Karten aus anderen Spielen: [Index, Spiel]
        other = [[i, c[6]] for i, c in enumerate(t[key]) if len(c) > 6 and c[6]]
        if other:
            out["g" + key] = other
    for k in ("x", "n", "k", "m"):   # Tausch-ID, Version, Art, Geld (fehlen bei alten Tickets)
        if t.get(k) not in (None, "", 0) or k == "k" and t.get(k):
            out[k] = t[k]
    return out


def _nsym(n):
    return max(10, (n // 4 + 1) & ~1)


def _sizes(total, blocks):
    return [total // blocks + (1 if i < total % blocks else 0) for i in range(blocks)]


def to_bytes(t):
    body = zlib.compress(json.dumps(_compact(t), separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 9)
    blocks = 1
    while max(_sizes(len(body), blocks)) + _nsym(max(_sizes(len(body), blocks))) > 255:
        blocks += 1
    out = bytearray(rscode.encode(bytes([VERSION, blocks, len(body) >> 8, len(body) & 255]), _HEAD_SYM))
    pos = 0
    for n in _sizes(len(body), blocks):
        out += rscode.encode(body[pos:pos + n], _nsym(n))
        pos += n
    return bytes(out)


def _mask(n):
    """Festes Mischmuster (damit der Code gleichmäßig „pixelig“ aussieht, auch bei vielen Nullen)."""
    x, out = 0x2F6B, []
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((x >> 16) & 1)
    return out


def bits(t, lay=RECEIPT):
    """-> (Zeilen, [0/1 …]) für das Raster; Zeile 0 ist die unterste. None, wenn das Ticket zu groß ist."""
    data = to_bytes(t)
    raw = [(b >> (7 - k)) & 1 for b in data for k in range(8)]
    rows = -(-len(raw) // lay.COLS)
    if rows > lay.MAX_ROWS:
        return None
    raw += [0] * (rows * lay.COLS - len(raw))
    return rows, [a ^ m for a, m in zip(raw, _mask(len(raw)))]


def band_height(rows, lay=RECEIPT):
    return rows * lay.M + BOTTOM


def module_rect(i, img_h, lay=RECEIPT):
    """Block i -> (x, y, Kante) in logischen Pixeln (img_h = Bildhöhe logisch)."""
    r, c = divmod(i, lay.COLS)
    return lay.X0 + c * lay.M, img_h - BOTTOM - (r + 1) * lay.M, lay.M


# ---------- Lesen ----------
def _sample(gray, s, dy, start, count, lay):
    """Mittelwerte der Blöcke start … start+count (Graustufenbild als numpy-Array)."""
    h, w = gray.shape
    rad = max(1, int(lay.M * s * 0.22))
    out = []
    for i in range(start, start + count):
        r, c = divmod(i, lay.COLS)
        cx = int(round((lay.X0 + (c + 0.5) * lay.M) * s))
        cy = int(round(h - (BOTTOM + (r + 0.5) * lay.M) * s + dy))
        if not (rad <= cx < w - rad and rad <= cy < h - rad):
            return None
        out.append(float(gray[cy - rad:cy + rad + 1, cx - rad:cx + rad + 1].mean()))
    return out


def _bits_of(vals):
    lo, hi = sorted(vals)[len(vals) // 10], sorted(vals)[-(len(vals) // 10) - 1]
    thr = (lo + hi) / 2
    return [1 if v > thr else 0 for v in vals]


def _bytes(bitlist):
    return bytes(sum(b << (7 - k) for k, b in enumerate(bitlist[i:i + 8])) for i in range(0, len(bitlist) - 7, 8))


def decode_gray(gray, layouts=LAYOUTS):
    """Pixel-Code aus einem Graustufenbild (numpy, Ticket in ganzer Breite) -> Ticket (ohne Kartennamen) oder None."""
    for lay in layouts:
        t = _decode_gray(gray, lay)
        if t is not None:
            return t
    return None


def _decode_gray(gray, lay):
    h, w = gray.shape[:2]
    s = w / lay.W
    head_bits = (_HEAD + _HEAD_SYM) * 8
    for dy in (0, -0.35, 0.35, -0.7, 0.7):
        dy *= lay.M * s
        vals = _sample(gray, s, dy, 0, head_bits, lay)
        if vals is None:
            continue
        b = [a ^ m for a, m in zip(_bits_of(vals), _mask(head_bits))]
        try:
            ver, blocks, hi, lo = rscode.decode(_bytes(b), _HEAD_SYM)
        except ValueError:
            continue
        if ver != VERSION or not blocks:
            continue
        sizes = _sizes((hi << 8) | lo, blocks)
        total = head_bits + sum((n + _nsym(n)) * 8 for n in sizes)
        vals = _sample(gray, s, dy, 0, total, lay)
        if vals is None:
            continue
        b = [a ^ m for a, m in zip(_bits_of(vals), _mask(total))]
        data = _bytes(b[head_bits:])
        body, pos = bytearray(), 0
        try:
            for n in sizes:
                k = n + _nsym(n)
                body += rscode.decode(data[pos:pos + k], _nsym(n))
                pos += k
            t = json.loads(zlib.decompress(bytes(body)).decode("utf-8"))
        except (ValueError, zlib.error):
            continue
        if isinstance(t, dict) and t.get("v") == VERSION:
            return _expand(t)
    return None


def _expand(t):
    """Pixel-Code -> Ticket: Spiele der Karten aus „ga“/„gb“ wieder an die Karten hängen."""
    for key in ("a", "b"):
        for i, g in t.pop("g" + key, None) or []:
            cards = t.get(key) or []
            if 0 <= i < len(cards) and isinstance(cards[i], list):
                c = cards[i]
                while len(c) < 6:
                    c.append("")
                c[6:] = [g]
    return t


def _order(pts):
    """4 Punkte -> oben links, oben rechts, unten rechts, unten links."""
    import numpy as np
    pts = np.array(pts, np.float32)
    sm, df = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[sm.argmin()], pts[df.argmin()], pts[sm.argmax()], pts[df.argmax()]], np.float32)


def decode_photo(bgr):
    """Pixel-Code aus einem Kamerabild (z. B. Handy-Bildschirm vor der Webcam): den hellen Block-Streifen suchen,
    gerade ziehen, auf ein sauberes „virtuelles Ticket“ setzen und mit decode_gray lesen. -> Ticket oder None."""
    import cv2
    import numpy as np
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    t = decode_gray(g)   # Bild füllt schon die Breite (Bildschirmfoto, Datei)
    if t is not None:
        return t
    h, w = g.shape[:2]
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, -18)
    k = max(3, int(min(h, w) / 160))
    blob = cv2.morphologyEx(cv2.dilate(th, np.ones((k, k), np.uint8)), cv2.MORPH_CLOSE,
                            np.ones((2 * k + 1, 2 * k + 1), np.uint8))
    cnts, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:6]:
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        if min(rw, rh) < 6 or max(rw, rh) < w * 0.15:
            continue
        if rh > rw:
            rw, rh, ang = rh, rw, ang + 90
        if rw / max(rh, 1) < 1.15:   # Kassenbon: der Code-Block ist fast quadratisch
            continue
        box = _order(cv2.boxPoints(((cx, cy), (rw * 1.04, rh * 1.25), ang)))
        tw = WIDE.COLS * 8
        tht = max(8, int(round(tw * rh * 1.25 / (rw * 1.04))))
        mat = cv2.getPerspectiveTransform(box, np.float32([[0, 0], [tw, 0], [tw, tht], [0, tht]]))
        wg = cv2.warpPerspective(g, mat, (tw, tht), flags=cv2.INTER_LINEAR)
        for img, lay in ((im, ly) for im in (wg, cv2.rotate(wg, cv2.ROTATE_180)) for ly in LAYOUTS):
            _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            ys, xs = np.nonzero(bw)
            if len(xs) < 50:
                continue
            x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
            band = img[y0:y1, x0:x1]
            bg = int(np.median(img[bw == 0])) if (bw == 0).any() else 10
            for kl in range(3):
                for kr in range(3):   # ganz links/rechts kann eine Spalte leer sein
                    m = (x1 - x0) / (lay.COLS - kl - kr)
                    s2 = m / lay.M
                    rows = max(1, int(round((y1 - y0) / m)))
                    cw, ch = int(round(lay.W * s2)), int(round((BOTTOM + rows * lay.M + 24) * s2))
                    canvas = np.full((ch, cw), bg, np.uint8)
                    bx = int(round((lay.X0 + kl * lay.M) * s2))
                    by = int(round(ch - BOTTOM * s2)) - band.shape[0]
                    if by < 0 or bx + band.shape[1] > cw:
                        continue
                    canvas[by:by + band.shape[0], bx:bx + band.shape[1]] = band
                    t = decode_gray(canvas, (lay,))
                    if t is not None:
                        return t
    return None


def read_image(path):
    """Ticket aus einer Bilddatei: erst der Text in der PNG-Datei, sonst der Pixel-Code. -> dict oder None."""
    from PySide6 import QtGui
    img = QtGui.QImage(str(path))
    if img.isNull():
        return None
    txt = img.text(TEXT_KEY)
    if txt:
        try:
            t = json.loads(txt)
            if isinstance(t, dict) and t.get("v") == VERSION:
                return t
        except ValueError:
            pass
    import numpy as np
    g = img.convertToFormat(QtGui.QImage.Format_Grayscale8)
    arr = np.frombuffer(g.constBits(), np.uint8, g.bytesPerLine() * g.height()).reshape(g.height(), g.bytesPerLine())
    return decode_gray(arr[:, :g.width()].copy())


def is_ticket_file(path):
    return str(path).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
