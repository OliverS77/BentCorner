"""Your profile: name, unique ID and your own card back (pixel art).

Everything stays on this computer (settings["profile"]). The ID (128 random bits) is embedded invisibly in every
export – that way Bent°Corner recognizes on import whose collection it is, even if two people have the same name.

Card back (pixel art in a card's aspect ratio), stored as text, one character per pixel:
    old (v1):  280 hex characters = 14 × 20 pixels, 16 colors (PICO-8), default corners – stays readable (friends!)
    v2:        "v2;28x40;c1;<chars>" – 14 × 20, 28 × 40 or 56 × 80 pixels, 32 fixed colors (PICO-8 + the 16
               "secret" ones), characters 0-9a-v – stays readable
    new (v3):  "v3;28x40;c1;<colors>;<chars>" – always 28 × 40, free colors (color wheel): <colors> is the back's own
               palette ("ff004d,1d2b53,…", at most 62), each character (0-9a-zA-Z) points to one of them
Drawing happens only on 28 × 40 – older backs are converted for that (normalize). Plus ready-made presets:
the card games (stylized, without logos) and a few motifs.
"""
import math
import random
import uuid

from PySide6 import QtGui
from PySide6.QtCore import QRectF, Qt

from system.i18n import tr

GW, GH = 14, 20   # base grid = aspect ratio (7:10); older grids are a multiple of it
W, H = 28, 40     # the one grid that is drawn on
SCALES = (1, 2, 4)
PALETTE = ["#000000", "#1d2b53", "#7e2553", "#008751", "#ab5236", "#5f574f", "#c2c3c7", "#fff1e8",
           "#ff004d", "#ffa300", "#ffec27", "#00e436", "#29adff", "#83769c", "#ff77a8", "#ffccaa",
           # the 16 "secret" PICO-8 colors – colors of the old backs (v1/v2)
           "#291814", "#111d35", "#422136", "#125359", "#742f29", "#49333b", "#a28879", "#f3ef7d",
           "#be1250", "#ff6c24", "#a8e72e", "#00b543", "#065ab5", "#754665", "#ff6e59", "#ff9d81"]
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"   # v2 uses the first 32
MAX_COLORS = len(DIGITS)


def encode(w, h, corner, cells, colors):
    return f"v3;{w}x{h};c{int(corner)};{','.join(c.lstrip('#').lower() for c in colors)};{cells}"


# ---------- Presets (computed so they are cleanly symmetrical) ----------
CX, CY = (W - 1) / 2, (H - 1) / 2


def _make(colors, fn):
    """colors: ["#rrggbb"]; fn(x, y) -> index into colors."""
    cells = "".join(DIGITS[fn(x, y)] for y in range(H) for x in range(W))
    return encode(W, H, 1, cells, colors)


def _ring(x, y):
    """0 = outermost edge, 1 = second ring … (distance to the edge)."""
    return min(x, y, W - 1 - x, H - 1 - y)


def _inside(px, py, poly):
    """Point in polygon (ray casting test)."""
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _sparkle(x, y, seed, p):
    return random.Random(x * 7919 + y * 104729 + seed).random() < p


def _mtg():
    """Magic, stylized: brown frame, blue swirl in the oval, five color dots."""
    c = ["#2a180c", "#6b3f1f", "#93582c", "#0f1a40", "#28529e", "#76a9f0", "#f3ead0", "#3a7bd5", "#3a2f45",
         "#d8452f", "#2f9a4c"]
    dots = [(CX + 6.2 * math.cos(math.radians(-90 + 72 * k)), CY + 9.0 * math.sin(math.radians(-90 + 72 * k)))
            for k in range(5)]

    def fn(x, y):
        r = _ring(x, y)
        if r == 0:
            return 0
        for k, (dx, dy) in enumerate(dots):
            if (x - dx) ** 2 + (y - dy) ** 2 < 4.2:
                return 6 + k
        d = ((x - CX) / 11) ** 2 + ((y - CY) / 17) ** 2
        if d < 1:
            if d > 0.86:
                return 5
            a = math.atan2(y - CY, x - CX)
            return 4 if math.sin(3 * a + math.sqrt(d) * 9) > 0.25 else 3
        return 2 if (x + 2 * y) % 5 == 0 else 1
    return _make(c, fn)


def _pokemon():
    """Pokémon, stylized: blue swirl, yellow lightning bolt."""
    c = ["#0b1b52", "#1a45a8", "#3d7fe6", "#9cc6ff", "#ffd23f", "#d99a00", "#13307a"]
    bolt = [(16.5, 8), (8.5, 21), (13.5, 21), (10.5, 32), (20.5, 17.5), (15, 17.5), (19.5, 8)]

    def fn(x, y):
        r = _ring(x, y)
        if r < 2:
            return 6 if r == 0 else 2
        if _inside(x + 0.5, y + 0.5, bolt):
            edge = any(not _inside(x + 0.5 + dx, y + 0.5 + dy, bolt) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            return 5 if edge else 4
        dx, dy = x - CX, y - CY
        a, rr = math.atan2(dy, dx), math.hypot(dx, dy * 0.75)
        s = math.sin(2 * a + rr * 0.42)
        return 3 if s > 0.85 else 2 if s > 0.3 else 1 if s > -0.4 else 0
    return _make(c, fn)


def _yugioh():
    """Yu-Gi-Oh!, stylized: brown swirl around a dark oval."""
    c = ["#160a03", "#4a240c", "#83461a", "#c47a30", "#f0bd70", "#070707"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 0
        d = ((x - CX) / 6.5) ** 2 + ((y - CY) / 9.5) ** 2
        if d < 1:
            return 4 if d > 0.78 else 5
        a, rr = math.atan2(y - CY, x - CX), math.hypot(x - CX, (y - CY) * 0.7)
        s = math.sin(4 * a - rr * 0.55)
        return 3 if s > 0.6 else 2 if s > -0.1 else 1
    return _make(c, fn)


def _riftbound():
    """Riftbound, stylized: glowing crystal on a violet background."""
    c = ["#0c0920", "#21184a", "#3a2a78", "#2ad6c9", "#168f8a", "#e8fffd", "#5b45b0"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 4
        m = abs(x - CX) / 6.5 + abs(y - CY) / 12
        if m < 1:
            if abs(x - CX) < 0.6:
                return 5
            return 4 if x < CX else 3
        if m < 1.3:
            return 6
        if _sparkle(x, y, 7, 0.04):
            return 5
        return 2 if m < 1.7 else 1 if (y + x // 3) % 7 else 0
    return _make(c, fn)


def _lorcana():
    """Lorcana, stylized: golden hexagon on dark ink."""
    c = ["#0d0916", "#1c142e", "#2d2148", "#d4a944", "#f6dc8a", "#6b4bb8"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 3
        dx, dy = abs(x - CX), abs(y - CY) * 0.72
        h = max(dx * 0.866 + dy * 0.5, dy)
        if 8.2 <= h < 9.8:
            return 4 if h < 8.9 else 3
        if h < 8.2:
            a, rr = math.atan2(y - CY, x - CX), math.hypot(x - CX, y - CY)
            return 5 if math.sin(3 * a + rr * 0.6) > 0.55 else 2
        if _sparkle(x, y, 11, 0.035):
            return 4
        return 1 if (x + y) % 2 else 0
    return _make(c, fn)


def _nacht():
    """Starry sky with moon."""
    c = ["#060b1f", "#111d4a", "#1d2b53", "#ffec27", "#fff1e8", "#29adff", "#83769c"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 6
        mx, my = 18, 10
        if (x - mx) ** 2 + (y - my) ** 2 <= 26 and (x - mx - 3) ** 2 + (y - my + 2) ** 2 > 20:
            return 3
        if _sparkle(x, y, 1, 0.05):
            return 4
        if _sparkle(x, y, 2, 0.02):
            return 5
        return 2 if y < 14 else 1 if y < 28 else 0
    return _make(c, fn)


def _flamme():
    """Blazing flames from below."""
    c = ["#120404", "#7e2553", "#ff004d", "#ffa300", "#ffec27", "#ff6c24"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 1
        h = H - 1 - y
        wave = 14 + 6 * math.sin(x * 0.65) + 3.5 * math.sin(x * 1.45 + 1)
        if h < wave * 0.45:
            return 4
        if h < wave * 0.75:
            return 3
        if h < wave:
            return 2
        if h < wave + 2:
            return 1
        if h < wave + 9 and _sparkle(x, y, 5, 0.08):
            return 5
        return 0
    return _make(c, fn)


def _pilz():
    """Fly agaric mushroom on a meadow."""
    c = ["#29adff", "#83c7ff", "#ff004d", "#fff1e8", "#ffccaa", "#00e436", "#008751"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 6
        if 10 <= y <= 19 and ((x - CX) / 11) ** 2 + ((y - 19) / 9) ** 2 <= 1:   # cap
            if any((x - px) ** 2 + (y - py) ** 2 < 2.2 for px, py in ((8, 15), (16, 12), (12, 17), (20, 16), (14, 11.5))):
                return 3
            return 2
        if 20 <= y <= 29 and abs(x - CX) <= 3:   # stem
            return 4
        if y >= 30:
            return 5 if (x + y) % 2 else 6
        return 0 if y > 6 else 1
    return _make(c, fn)


def _herz():
    """Pixel heart on a violet background."""
    c = ["#7e2553", "#83769c", "#ff004d", "#ff77a8", "#fff1e8"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 3
        u, v = (x - CX) / 9.5, -(y - 19) / 9.5
        if (u * u + v * v - 1) ** 3 - u * u * v ** 3 <= 0:
            if (x - 9) ** 2 + (y - 14) ** 2 < 3:
                return 4
            return 2 if (u * u + v * v) > 0.35 else 3
        return 0 if (x // 4 + y // 4) % 2 else 1
    return _make(c, fn)


def _ozean():
    """Under water: waves, bubbles, a fish."""
    c = ["#06223f", "#0b3d6b", "#1666a8", "#5fb7ff", "#ffa300", "#fff1e8", "#c2c3c7"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 6
        if ((x - 12) / 5) ** 2 + ((y - 22) / 2.6) ** 2 < 1 or (17 <= x <= 19 and abs(y - 22) <= x - 16):
            return 5 if (x, y) == (9, 21) else 4
        if any((x - bx) ** 2 + (y - by) ** 2 < 1.6 for bx, by in ((20, 12), (22, 8), (19, 5))):
            return 5
        if y < 4 + math.sin(x * 0.7):
            return 3
        return 2 if y < 14 else 1 if y < 30 else 0
    return _make(c, fn)


def _wald():
    """Fir forest under the evening sky."""
    c = ["#ff9d81", "#ffccaa", "#125359", "#008751", "#0b3b2c", "#422136"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 5
        for tx, top, wd in ((6, 12, 5), (15, 8, 6), (23, 14, 5)):
            if y >= top and abs(x - tx) <= (y - top) * wd / 18 + 0.5 and y < 34:
                return 3 if (y - top) % 5 < 3 else 2
        if y >= 34:
            return 4
        return 1 if y < 10 else 0
    return _make(c, fn)


def _galaxie():
    """Spiral galaxy with stars."""
    c = ["#05040f", "#1a1240", "#3d2b7a", "#ff77a8", "#ffccaa", "#fff1e8"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 2
        dx, dy = x - CX, (y - CY) * 0.7
        rr = math.hypot(dx, dy)
        a = math.atan2(dy, dx)
        if rr < 2.2:
            return 5
        s = math.sin(2 * a - rr * 0.55)
        if rr < 13 and s > 0.6:
            return 4 if rr < 6 else 3
        if rr < 13 and s > 0.1:
            return 2
        if _sparkle(x, y, 13, 0.05):
            return 5
        return 1 if rr < 16 else 0
    return _make(c, fn)


def _schach():
    """Chessboard with frame."""
    c = ["#1c1c1c", "#e8e2d0", "#6b3f1f", "#93582c"]

    def fn(x, y):
        r = _ring(x, y)
        if r < 2:
            return 2 if r == 0 else 3
        return 0 if ((x - 2) // 3 + (y - 2) // 3) % 2 else 1
    return _make(c, fn)


def _sonne():
    """Sunset over the sea."""
    c = ["#422136", "#7e2553", "#ff004d", "#ff6c24", "#ffa300", "#ffec27", "#1d2b53", "#29adff"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 0
        if y >= 26:
            if abs(x - CX) < (36 - y) * 0.6 and (y + x) % 3 == 0:
                return 4
            return 7 if (y + x // 2) % 4 == 0 else 6
        if (x - CX) ** 2 + (y - 24) ** 2 < 60:
            return 5 if y < 19 else 4
        return 0 if y < 6 else 1 if y < 12 else 2 if y < 18 else 3
    return _make(c, fn)


def _kirsch():
    """Cherry blossom branch against the morning sky."""
    c = ["#2b2140", "#ffd1dc", "#ff9ec0", "#e35d8a", "#fff1e8", "#5a3a2e", "#3d2a40", "#ffe7a8"]

    def fn(x, y):
        if _ring(x, y) == 0:
            return 6
        by = 26 - (x - 2) * 0.45 + 2 * math.sin(x * 0.5)   # branch running diagonally from the bottom left
        if abs(y - by) < 1.2 and x < 24:
            return 5
        if abs(y - (by - (x - 12) * 0.9)) < 0.9 and 12 <= x <= 19:   # twig pointing upward
            return 5
        for bx, bly in ((6, 22), (11, 19), (16, 13), (20, 17), (9, 15), (22, 9), (14, 24)):
            d = (x - bx) ** 2 + (y - bly) ** 2
            if d < 2:
                return 4 if d < .6 else 3
            if d < 6:
                return 2 if (x + y) % 3 else 1
        if _sparkle(x, y, 17, 0.025) and y > 26:
            return 1
        return 0
    return _make(c, fn)


# game backs first (also on the games page of the first-run setup), then the motifs
GAME_PRESETS = {"mtg": _mtg(), "pokemon": _pokemon(), "yugioh": _yugioh(), "riftbound": _riftbound(),
                "lorcana": _lorcana()}
PRESETS = [("mtg", "Magic", GAME_PRESETS["mtg"]), ("pokemon", "Pokémon", GAME_PRESETS["pokemon"]),
           ("yugioh", "Yu-Gi-Oh!", GAME_PRESETS["yugioh"]),
           ("riftbound", "Riftbound", GAME_PRESETS["riftbound"]), ("lorcana", "Lorcana", GAME_PRESETS["lorcana"]),
           ("nacht", "Sternennacht", _nacht()), ("flamme", "Flamme", _flamme()), ("pilz", "Fliegenpilz", _pilz()),
           ("herz", "Herzblatt", _herz()), ("ozean", "Ozean", _ozean()), ("wald", "Wald", _wald()),
           ("galaxie", "Galaxie", _galaxie()), ("schach", "Schachbrett", _schach()), ("sonne", "Sonnenuntergang", _sonne()),
           ("kirsch", "Kirschblüte", _kirsch())]


def _add_extra_presets():
    """Backs of private games (games/extras.py): into GAME_PRESETS and PRESETS right after their neighbour."""
    import sys
    global GAME_PRESETS
    me = sys.modules[__name__]
    for after, key, name, make in __import__("games").extra("PROFILE_PRESETS", ()):
        img = make(me)
        keys = list(GAME_PRESETS)
        at = keys.index(after) + 1 if after in keys else len(keys)
        GAME_PRESETS = {**dict(list(GAME_PRESETS.items())[:at]), key: img, **dict(list(GAME_PRESETS.items())[at:])}
        at = next((n + 1 for n, p in enumerate(PRESETS) if p[0] == after), len(PRESETS))
        PRESETS.insert(at, (key, name, img))


_add_extra_presets()
DEFAULT_BACK = PRESETS[0][2]


# ---------- Profile ----------
def get(settings):
    """Profile or None (not created yet)."""
    p = settings.get("profile")
    return p if p and p.get("id") else None


def ensure(settings, name="", back=None):
    """Create the profile (once) – the ID stays the same forever afterwards."""
    p = dict(settings.get("profile") or {})
    p.setdefault("id", uuid.uuid4().hex)
    p["name"] = (name or p.get("name") or "").strip()[:40]
    p["back"] = back or p.get("back") or DEFAULT_BACK
    settings["profile"] = p
    return p


def shared_back(profile):
    """The card back for a picture that leaves the app (log and deck image, lead 03.11.2026): only one the user chose.
    Never the default back – a pixel copy of a game's own back, which ensure() stores when nothing was chosen – and
    nothing unreadable. None = no back on the picture (the name alone)."""
    b = (profile or {}).get("back")
    if not b or parse(b) is None or normalize(b) == normalize(DEFAULT_BACK):
        return None
    return b


def parse(back):
    """-> {"w", "h", "corner", "cells", "colors"} or None. Understands v1, v2 and v3."""
    if not isinstance(back, str):
        return None
    if back.startswith("v3;"):
        try:
            _, size, corner, cols, cells = back.split(";", 4)
            w, h = (int(v) for v in size.split("x"))
            c = int(corner[1:])
        except ValueError:
            return None
        colors = ["#" + x.lower() for x in cols.split(",")] if cols else []
        if (w, h) != (W, H) or len(cells) != w * h or c not in (0, 1, 2) or not 0 < len(colors) <= MAX_COLORS \
                or any(len(x) != 7 or any(ch not in "0123456789abcdef" for ch in x[1:]) for x in colors) \
                or any(ch not in DIGITS[:len(colors)] for ch in cells):
            return None
        return {"w": w, "h": h, "corner": c, "cells": cells, "colors": colors}
    if back.startswith("v2;"):
        try:
            _, size, corner, cells = back.split(";", 3)
            w, h = (int(v) for v in size.split("x"))
            c = int(corner[1:])
        except ValueError:
            return None
        if (w, h) not in [(GW * k, GH * k) for k in SCALES] or len(cells) != w * h or c not in (0, 1, 2) \
                or any(ch not in DIGITS[:32] for ch in cells):
            return None
        return {"w": w, "h": h, "corner": c, "cells": cells, "colors": list(PALETTE)}
    if len(back) == GW * GH and all(ch in "0123456789abcdef" for ch in back):
        return {"w": GW, "h": GH, "corner": 1, "cells": back, "colors": list(PALETTE)}
    return None


def normalize(back):
    """Any card back -> v3 at 28 × 40 (to keep drawing). Finer ones are downscaled using the most frequent color per
    block, coarser ones are upscaled; only used colors stay in the palette."""
    d = parse(back) or parse(DEFAULT_BACK)
    cells = []
    for y in range(H):
        for x in range(W):
            x0, x1 = x * d["w"] // W, max(x * d["w"] // W + 1, (x + 1) * d["w"] // W)
            y0, y1 = y * d["h"] // H, max(y * d["h"] // H + 1, (y + 1) * d["h"] // H)
            block = [d["cells"][yy * d["w"] + xx] for yy in range(y0, y1) for xx in range(x0, x1)]
            cells.append(max(block, key=block.count))
    used = sorted(set(cells), key=DIGITS.index)
    remap = {ch: DIGITS[i] for i, ch in enumerate(used)}
    colors = [d["colors"][DIGITS.index(ch)] for ch in used]
    return encode(W, H, d["corner"], "".join(remap[ch] for ch in cells), colors)


def from_image(path, corner=1, dither=True):
    """Upload an image (hidden for now): crop centered to 7:10, shrink to 28 × 40, convert to the 32
    PICO-8 colors (with error diffusion = finer gradients). -> card back or None."""
    img = QtGui.QImage(str(path))
    if img.isNull():
        return None
    w, h = W, H
    iw, ih = img.width(), img.height()
    if iw * h > ih * w:   # too wide: crop the sides
        cw = ih * w // h
        img = img.copy((iw - cw) // 2, 0, cw, ih)
    else:                 # too tall: crop top and bottom
        chh = iw * h // w
        img = img.copy(0, (ih - chh) // 2, iw, chh)
    img = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QtGui.QImage.Format_RGB32)
    pal = [QtGui.QColor(c) for c in PALETTE]
    pal = [(c.red(), c.green(), c.blue()) for c in pal]
    px = [[list(QtGui.QColor(img.pixel(x, y)).getRgb()[:3]) for x in range(w)] for y in range(h)]
    out = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[y][x]
            # color distance roughly weighted like the eye (green counts the most)
            best = min(range(len(pal)), key=lambda i: 2 * (pal[i][0] - r) ** 2 + 4 * (pal[i][1] - g) ** 2
                       + 3 * (pal[i][2] - b) ** 2)
            out.append(DIGITS[best])
            if dither:
                er, eg, eb = r - pal[best][0], g - pal[best][1], b - pal[best][2]
                for dx, dy, f in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < w and 0 <= yy < h:
                        q = px[yy][xx]
                        q[0] += er * f
                        q[1] += eg * f
                        q[2] += eb * f
    return normalize(encode(w, h, corner, "".join(out), PALETTE))


CORNERS = {0: 0.0, 1: 0.09, 2: 0.2}   # corner rounding (fraction of the width)


def back_image(back, height, radius=None, border="#3a4260"):
    """Card back as an image at the requested height – sharp pixels, corners as chosen, thin border."""
    d = parse(back) or parse(DEFAULT_BACK)
    w = max(1, round(height * GW / GH))
    dpr = 2.0
    img = QtGui.QImage(round(w * dpr), round(height * dpr), QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    img.setDevicePixelRatio(dpr)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    r = radius if radius is not None else max(2.0, w * CORNERS[1])   # corners always rounded (requested: no choice)
    path = QtGui.QPainterPath()
    path.addRoundedRect(QRectF(0.5, 0.5, w - 1, height - 1), r, r)
    p.setClipPath(path)
    p.setRenderHint(QtGui.QPainter.Antialiasing, False)
    small = QtGui.QImage(d["w"], d["h"], QtGui.QImage.Format_RGB32)   # pixel by pixel first, then scaled up sharply
    cols = [QtGui.QColor(c).rgb() for c in d["colors"]]
    for i, ch_ in enumerate(d["cells"]):
        small.setPixel(i % d["w"], i // d["w"], cols[DIGITS.index(ch_)])
    p.drawImage(QRectF(0, 0, w, height), small)
    p.setClipping(False)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    if border:
        p.setPen(QtGui.QPen(QtGui.QColor(border), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    p.end()
    return img


def back_pixmap(back, height, **kw):
    return QtGui.QPixmap.fromImage(back_image(back, height, **kw))


# ---------- "Who's scanning?" (existing users without a profile; new users: first-run setup, onboarding.py) ----------
def welcome(settings, done_cb):
    """Asks once for name and card back – playful, with the note that everything stays local.
    Does not wait (the program keeps running behind it)."""
    from ui import qdialogs
    st = {"name": "", "back": DEFAULT_BACK}

    def finish(d, skip=False):
        ensure(settings, "" if skip else st["name"], st["back"])
        done_cb()
        d.close(True)

    def build(ui, d):
        return ui.col(profile_items(ui, st) + [
            ui.row([ui.button(tr("Later"), lambda: finish(d, skip=True)), ui.stretch(),
                    ui.button(tr("Let's go"), lambda: finish(d), primary=True)])], spacing=12)
    return qdialogs.show(tr("Who's scanning?"), build, wait=False, wide=760)


def profile_items(ui, st):
    """Name + draw a card back (st: {"name", "back"}) – for "Who's scanning?" and the first-run setup."""
    name = ui.edit(st["name"], lambda t: st.update(name=t[:40]), key="name",
                   live=lambda t: st.update(name=t[:40]), placeholder=tr("Your name or nickname"))
    name["focus"] = True
    return [
        ui.label(tr("Hey! Who's scanning? 👋"), px=22, bold=True),
        ui.label(tr("When you trade collections and wishlists with friends, they see this name and your card back. Both stay on your computer until you share something yourself.")),
        name,
        ui.label(tr("Your own card back ✦ – pick one or draw your own:")),
        ui.pixel(st["back"], lambda b: st.update(back=b)),
    ]
