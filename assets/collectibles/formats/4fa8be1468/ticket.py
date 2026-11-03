"""Trade ticket: a trade offer as an image that Bent°Corner can read back in.

The image carries the data twice:
  1. in full as text in the PNG file ("BentCornerTicket") – lost when a messenger recompresses the image;
  2. as a pixel code at the bottom of the ticket (light/dark blocks like a tear-off edge) – survives downscaling
     and JPEG.
     Layout: header (version, blocks, length) + data (zlib JSON without card names), each block with Reed-Solomon
     parity bytes (rscode), XORed with a fixed pattern, row by row from bottom to top.

Ticket (dict): {"v": 1, "id", "t", "f": [profile ID, name] (who issued it), "o": [profile ID, name] (to whom),
"a": cards from f to o, "b": cards from o to f}. Card: [set, number, language, foil 0/1, count, name?, game?].
Mixed tickets: cards of a game other than the ticket's ("g") carry their game in 7th position; in the pixel code
they appear as "ga"/"gb" ([index, game]) – older versions only see the first five fields there.
"""
import json
import time
import uuid
import zlib

import rscode

VERSION = 1
TEXT_KEY = "BentCornerTicket"
# Grid in the image (logical pixels). Two formats: the receipt (portrait, 720 px wide – for zooming in on a
# phone; this is what gets issued now) and the old landscape format (1200 px – still read).
class Layout:
    def __init__(self, w, x0, m, max_rows):
        self.W, self.X0, self.M, self.MAX_ROWS = w, x0, m, max_rows
        self.COLS = (w - 2 * x0) // m


RECEIPT = Layout(720, 40, 8, 110)
WIDE = Layout(1200, 48, 6, 40)
LAYOUTS = (RECEIPT, WIDE)
W, X0, M, COLS, MAX_ROWS = RECEIPT.W, RECEIPT.X0, RECEIPT.M, RECEIPT.COLS, RECEIPT.MAX_ROWS
BOTTOM = 30          # distance from the lowest block row to the bottom edge of the image
_HEAD, _HEAD_SYM = 4, 8
ID_LEN = 12          # in the pixel code the start of the profile ID is enough


def new(me, friend, give, get, trade_id=None, version=1, kind="o", money=0.0):
    """me/friend: (profile ID, name); give: cards from me to friend, get: from friend to me.
    trade_id: trade ID (same across all versions of a trade, default = ticket number), version: 1, 2 … for
    counter-offers, kind: "o" offer · "f" closing (whoever reads it in gets it booked), money: € from me to friend
    (negative = friend pays)."""
    tid = uuid.uuid4().hex[:8]
    cur = _game()

    def full(c):   # every card with its game (if not given: the open one)
        c = _card(c)
        while len(c) < 6:
            c.append("")
        return c[:6] + [c[6] if len(c) > 6 and c[6] else cur]
    a, b = [full(c) for c in give], [full(c) for c in get]
    n = {}
    for c in a + b:
        n[c[6]] = n.get(c[6], 0) + int(c[4] or 1)
    # game of the ticket = the one with the most cards (tie: the open one); cards sorted from most to fewest
    rank = sorted(n, key=lambda x: (-n[x], x != cur))
    g = rank[0] if rank else cur

    def norm(cards):
        cards = sorted(cards, key=lambda c: rank.index(c[6]))
        return [c[:6] if c[6] == g else c for c in cards]
    return {"v": VERSION, "id": tid, "t": int(time.time()),
            "f": [me[0] or "", me[1] or ""], "o": [friend[0] or "", friend[1] or ""],
            "a": norm(a), "b": norm(b),
            "x": trade_id or tid, "n": int(version), "k": kind, "m": int(round(float(money or 0) * 100)),
            "g": g}


def _game():   # key of the open game (games.current_key) – a name of its own so tests can replace it
    import games
    return games.current_key()


def game_of(t):
    """Game of the ticket (tickets without one: Magic)."""
    return t.get("g") or "mtg"


def card_game(c, t):
    """Game of a card in the ticket: its own (7th field) or the ticket's."""
    return (c[6] if isinstance(c, list) and len(c) > 6 and c[6] else None) or game_of(t)


def games_in(t):
    """All games of a ticket (the ticket's own first)."""
    out = [game_of(t)]
    for c in (t.get("a") or []) + (t.get("b") or []):
        g = card_game(c, t)
        if g not in out:
            out.append(g)
    return out


def kind(t):
    """"o" offer, "f" closing – tickets before v0.8.2 (without a kind) count as closing (they were booked directly)."""
    return t.get("k") or "f"


def money_from_me(t, my_id):
    """Money amount from my point of view in €: positive = I pay, negative = I receive."""
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
    """Ticket number for display: 7F3A-21C9."""
    i = str(t.get("id") or "").upper()
    return f"{i[:4]}-{i[4:8]}" if len(i) >= 8 else i


def side(t, my_id):
    """From my point of view: -> ("give", "get", partner [ID, name]) or None if the ticket does not concern me."""
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
    """For the pixel code: without card names, profile IDs shortened."""
    out = {"v": t["v"], "id": t["id"], "t": t["t"],
           "f": [str(t["f"][0])[:ID_LEN], t["f"][1][:24]], "o": [str(t["o"][0])[:ID_LEN], t["o"][1][:24]],
           "a": [c[:5] for c in t["a"]], "b": [c[:5] for c in t["b"]]}
    if t.get("g") and t["g"] != "mtg":   # game (Magic: omitted – like old tickets)
        out["g"] = t["g"]
    for key in ("a", "b"):   # cards from other games: [index, game]
        other = [[i, c[6]] for i, c in enumerate(t[key]) if len(c) > 6 and c[6]]
        if other:
            out["g" + key] = other
    for k in ("x", "n", "k", "m"):   # trade ID, version, kind, money (missing in old tickets)
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
    """Fixed scrambling pattern (so the code looks evenly "pixelated", even with many zeros)."""
    x, out = 0x2F6B, []
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((x >> 16) & 1)
    return out


def bits(t, lay=RECEIPT):
    """-> (rows, [0/1 …]) for the grid; row 0 is the lowest. None if the ticket is too large."""
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
    """Block i -> (x, y, edge length) in logical pixels (img_h = logical image height)."""
    r, c = divmod(i, lay.COLS)
    return lay.X0 + c * lay.M, img_h - BOTTOM - (r + 1) * lay.M, lay.M


# ---------- Reading ----------
def _sample(gray, s, dy, start, count, lay):
    """Mean values of blocks start … start+count (grayscale image as a numpy array)."""
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
    """Pixel code from a grayscale image (numpy, ticket at full width) -> ticket (without card names) or None."""
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
    """Pixel code -> ticket: attach the card games from "ga"/"gb" back onto the cards."""
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
    """4 points -> top left, top right, bottom right, bottom left."""
    import numpy as np
    pts = np.array(pts, np.float32)
    sm, df = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[sm.argmin()], pts[df.argmin()], pts[sm.argmax()], pts[df.argmax()]], np.float32)


def decode_photo(bgr):
    """Pixel code from a camera image (e.g. a phone screen held in front of the webcam): find the bright block strip,
    straighten it, place it on a clean "virtual ticket" and read it with decode_gray. -> ticket or None."""
    import cv2
    import numpy as np
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    t = decode_gray(g)   # image already fills the width (screenshot, file)
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
        if rw / max(rh, 1) < 1.15:   # receipt: the code block is almost square
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
                for kr in range(3):   # at the far left/right a column may be empty
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
    """Ticket from an image file: first the text in the PNG file, otherwise the pixel code. -> dict or None."""
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
