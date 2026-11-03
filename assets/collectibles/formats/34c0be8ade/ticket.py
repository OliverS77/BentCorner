"""Tauschticket: ein Tauschangebot als Bild, das Bent°Corner wieder einlesen kann.

Das Bild trägt die Daten zweimal:
  1. vollständig als Text in der PNG-Datei („BentCornerTicket“) – geht verloren, wenn ein Messenger das Bild neu
     komprimiert;
  2. als Pixel-Code unten auf dem Ticket (helle/dunkle Blöcke wie ein Abriss-Rand) – übersteht Verkleinern und JPEG.
     Aufbau: Kopf (Version, Blöcke, Länge) + Daten (zlib-JSON ohne Kartennamen), je Block mit Reed-Solomon-Prüfbytes
     (rscode), mit einem festen Muster gemischt, Zeile für Zeile von unten nach oben.

Ticket (dict): {"v": 1, "id", "t", "f": [Profil-ID, Name] (wer es ausgestellt hat), "o": [Profil-ID, Name] (an wen),
"a": Karten von f an o, "b": Karten von o an f}. Karte: [Set, Nummer, Sprache, Foil 0/1, Anzahl, Name?].
"""
import json
import time
import uuid
import zlib

import rscode

VERSION = 1
TEXT_KEY = "BentCornerTicket"
# Raster im Bild (logische Pixel bei 1200 px Breite)
W = 1200
X0 = 48              # linker Rand
M = 6                # Kantenlänge eines Blocks
COLS = (W - 2 * X0) // M
BOTTOM = 30          # Abstand der untersten Blockzeile zum unteren Bildrand
MAX_ROWS = 40
_HEAD, _HEAD_SYM = 4, 8
ID_LEN = 12          # im Pixel-Code reicht der Anfang der Profil-ID


def new(me, friend, give, get):
    """me/friend: (Profil-ID, Name); give: Karten von mir an friend, get: von friend an mich."""
    return {"v": VERSION, "id": uuid.uuid4().hex[:8], "t": int(time.time()),
            "f": [me[0] or "", me[1] or ""], "o": [friend[0] or "", friend[1] or ""],
            "a": [_card(c) for c in give], "b": [_card(c) for c in get]}


def _card(c):
    if isinstance(c, (list, tuple)):
        return list(c)
    return [str(c.get("set") or "").lower(), str(c.get("number") or ""), c.get("lang") or "en",
            1 if c.get("foil") else 0, int(c.get("count") or 1), c.get("name") or ""]


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
    return {"v": t["v"], "id": t["id"], "t": t["t"],
            "f": [str(t["f"][0])[:ID_LEN], t["f"][1][:24]], "o": [str(t["o"][0])[:ID_LEN], t["o"][1][:24]],
            "a": [c[:5] for c in t["a"]], "b": [c[:5] for c in t["b"]]}


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


def bits(t):
    """-> (Zeilen, [0/1 …]) für das Raster; Zeile 0 ist die unterste. None, wenn das Ticket zu groß ist."""
    data = to_bytes(t)
    raw = [(b >> (7 - k)) & 1 for b in data for k in range(8)]
    rows = -(-len(raw) // COLS)
    if rows > MAX_ROWS:
        return None
    raw += [0] * (rows * COLS - len(raw))
    return rows, [a ^ m for a, m in zip(raw, _mask(len(raw)))]


def band_height(rows):
    return rows * M + BOTTOM


def module_rect(i, img_h):
    """Block i -> (x, y, Kante) in logischen Pixeln (img_h = Bildhöhe logisch)."""
    r, c = divmod(i, COLS)
    return X0 + c * M, img_h - BOTTOM - (r + 1) * M, M


# ---------- Lesen ----------
def _sample(gray, s, dy, start, count):
    """Mittelwerte der Blöcke start … start+count (Graustufenbild als numpy-Array)."""
    h, w = gray.shape
    rad = max(1, int(M * s * 0.22))
    out = []
    for i in range(start, start + count):
        r, c = divmod(i, COLS)
        cx = int(round((X0 + (c + 0.5) * M) * s))
        cy = int(round(h - (BOTTOM + (r + 0.5) * M) * s + dy))
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


def decode_gray(gray):
    """Pixel-Code aus einem Graustufenbild (numpy, Ticket in ganzer Breite) -> Ticket (ohne Kartennamen) oder None."""
    h, w = gray.shape[:2]
    s = w / W
    head_bits = (_HEAD + _HEAD_SYM) * 8
    for dy in (0, -0.35, 0.35, -0.7, 0.7):
        dy *= M * s
        vals = _sample(gray, s, dy, 0, head_bits)
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
        vals = _sample(gray, s, dy, 0, total)
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
