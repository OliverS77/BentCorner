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

from collection import rscode

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


# ---------- checking a ticket from outside (image, photo, mailbox) – review 08.11. (T1/T2/T5/T6) ----------
MAX_CARDS = 2000      # cards per ticket (an image holds far fewer)
MAX_COUNT = 999       # copies of one card
_ID = __import__("re").compile(r"[A-Za-z0-9_-]{1,40}")
_FIELD = __import__("re").compile(r"(?!.*\.\.)[^/\\:*?\"<>|\x00-\x1f]{0,24}")   # set, number, language: short, no path characters


def _known_games():
    import games
    return {key for key, _name, _ready in games.GAMES}


def _markup(s):
    """A name with < or > could become rich text with links in a label (review 08.11. T3) – never in a ticket."""
    return "<" in s or ">" in s


def valid(t):
    """Is a ticket from outside well-formed? The game names a known game (it becomes part of file paths), ids are
    short tokens, names and fields have sane lengths, counts and amounts are in range. -> bool"""
    try:
        if not isinstance(t, dict) or t.get("v") != VERSION:
            return False
        if not _ID.fullmatch(str(t.get("id") or "")) or ("x" in t and not _ID.fullmatch(str(t.get("x") or ""))):
            return False
        known = _known_games()
        if t.get("g") not in (None, "") and t.get("g") not in known:
            return False
        for side_ in ("f", "o"):
            p = t.get(side_)
            if not (isinstance(p, list) and len(p) == 2 and all(isinstance(x, str) for x in p)):
                return False
            if len(p[0]) > 64 or len(p[1]) > 80 or _markup(p[1]):
                return False
        cards = (t.get("a") or []) + (t.get("b") or [])
        if not (isinstance(t.get("a", []), list) and isinstance(t.get("b", []), list)) or len(cards) > MAX_CARDS:
            return False
        for c in cards:
            if not isinstance(c, list) or not 4 <= len(c) <= 7:
                return False
            if not all(isinstance(x, str) and _FIELD.fullmatch(x) for x in (str(c[0]), str(c[1]), str(c[2] or ""))):
                return False
            if c[3] not in (0, 1, True, False, None, ""):   # foil: a flag, nothing else (review 08.11., ports)
                return False
            if len(c) > 4 and not (isinstance(c[4], int) and 1 <= c[4] <= MAX_COUNT):
                return False
            if len(c) > 5 and not (isinstance(c[5], str) and len(c[5]) <= 200 and not _markup(c[5])):
                return False
            if len(c) > 6 and c[6] not in ("", None) and c[6] not in known:
                return False
        if not isinstance(t.get("n", 1), int) or not 1 <= t.get("n", 1) <= 1000:
            return False
        if t.get("k", "o") not in ("o", "f") or not isinstance(t.get("m", 0), int) or abs(t.get("m", 0)) > 10 ** 9:
            return False
        return True
    except (TypeError, ValueError, AttributeError):
        return False


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
        # a shortened ID only from the pixel code's length on (review 08.11. T5: never „a“ for anyone)
        return bool(pid) and bool(my_id) and (my_id.startswith(pid) and len(pid) >= ID_LEN if len(pid) < len(my_id)
                                              else pid == my_id)
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
def _sample(gray, s, dy, start, count, lay, ii=None):
    """Mean values of blocks start … start+count (grayscale image as a numpy array)."""
    import numpy as np
    h, w = gray.shape
    rad = max(1, int(lay.M * s * 0.22))
    r, c = np.divmod(np.arange(start, start + count), lay.COLS)
    cx = np.round((lay.X0 + (c + 0.5) * lay.M) * s).astype(np.int64)
    cy = np.round(h - (BOTTOM + (r + 0.5) * lay.M) * s + dy).astype(np.int64)
    if count and not ((cx >= rad).all() and (cx < w - rad).all() and (cy >= rad).all() and (cy < h - rad).all()):
        return None
    # the squares' means from the integral image – the same numbers as .mean() block by block, without the Python
    # loop (a camera frame tries thousands of placements; 0.9.7.38)
    if ii is None:
        ii = _integral(gray)
    y0, y1, x0, x1 = cy - rad, cy + rad + 1, cx - rad, cx + rad + 1
    tot = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]
    return (tot.astype(np.float64) / float((2 * rad + 1) ** 2)).tolist()


def _integral(gray):
    import cv2
    import numpy as np
    return cv2.integral(np.ascontiguousarray(gray, np.uint8), sdepth=cv2.CV_32S)   # exact up to 8 Mpx


def _bits_of(vals):
    lo, hi = sorted(vals)[len(vals) // 10], sorted(vals)[-(len(vals) // 10) - 1]
    thr = (lo + hi) / 2
    return [1 if v > thr else 0 for v in vals]


def _bytes(bitlist):
    return bytes(sum(b << (7 - k) for k, b in enumerate(bitlist[i:i + 8])) for i in range(0, len(bitlist) - 7, 8))


def decode_gray(gray, layouts=LAYOUTS):
    """Pixel code from a grayscale image (numpy, ticket at full width) -> ticket (without card names) or None."""
    ii = _integral(gray)   # once for every layout and offset
    for lay in layouts:
        t = _decode_gray(gray, lay, ii)
        if t is not None:
            return t
    return None


def _decode_gray(gray, lay, ii=None):
    h, w = gray.shape[:2]
    s = w / lay.W
    head_bits = (_HEAD + _HEAD_SYM) * 8
    for dy in (0, -0.35, 0.35, -0.7, 0.7):
        dy *= lay.M * s
        vals = _sample(gray, s, dy, 0, head_bits, lay, ii)
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
        vals = _sample(gray, s, dy, 0, total, lay, ii)
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
    """Pixel code -> ticket: attach the card games from "ga"/"gb" back onto the cards (a broken list: dropped)."""
    for key in ("a", "b"):
        extra = t.pop("g" + key, None) or []
        if not isinstance(extra, list) or not all(isinstance(e, list) and len(e) == 2 for e in extra):
            continue
        for i, g in extra:
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
    cnts, _ = cv2.findContours(blob, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    mids = None
    for n, c in enumerate(sorted(cnts, key=cv2.contourArea, reverse=True)[:6]):
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        if min(rw, rh) < 6 or max(rw, rh) < w * 0.15:
            continue
        if rh > rw:
            rw, rh, ang = rh, rw, ang + 90
        if rw / max(rh, 1) < 1.15:   # receipt: the code block is almost square
            continue
        box = _order(cv2.boxPoints(((cx, cy), (rw * 1.04, rh * 1.25), ang)))
        t = _read_box(g, box, rw, rh)
        if t is not None:
            return t
        # held at an angle (one side nearer): the rectangle cuts the code askew – straighten by the block's own four
        # corners (lead 03.11.2026; 8 px of perspective were enough to fail before). Second, not instead: on the
        # synthetic test pictures each way reads some the other doesn't
        if n >= 3:   # the code is among the three largest blobs; a camera frame without it must stay quick
            continue
        if mids is None:
            mids = np.float32([x.reshape(-1, 2).mean(0) for x in cnts])
        for pts in _pieces(cnts, mids, c):
            q = _quad(pts)
            if q is not None:
                t = _read_box(g, q[0], q[1], q[2])
                if t is not None:
                    return t
    return None


def _pieces(cnts, mids, c):
    """The points to fit the edges to: the blob alone, then – if others join – the blob with its neighbours."""
    yield c.reshape(-1, 2)
    p = _grow(cnts, mids, c)
    if len(p) > len(c):
        yield p


def _rect(p):
    """minAreaRect with the long side along -> (center, angle, length, height)."""
    import cv2
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(p)
    if rh > rw:
        rw, rh, ang = rh, rw, ang + 90
    return (cx, cy), ang, rw, rh


def _grow(cnts, mids, c):
    """The blob and its neighbours in the same strip -> its points. Held close the blocks are big, and a run of empty
    ones splits the code into pieces side by side; a piece joins when it lies wholly within the block's height (+10 %)
    and starts at most 0.15 heights past an end (three rounds; text lines above, the screen's frame and stray dots lie
    outside)."""
    import numpy as np
    p = c.reshape(-1, 2)
    for _ in range(3):
        (cx, cy), ang, rw, rh = _rect(p)
        a = np.radians(ang)
        eu, ev = np.float32([np.cos(a), np.sin(a)]), np.float32([-np.sin(a), np.cos(a)])
        o = np.float32([cx, cy])
        keep = [c.reshape(-1, 2)]
        for i in np.nonzero(np.abs((mids - o) @ ev) <= rh * 0.5)[0]:
            if cnts[i] is c:
                continue
            q = cnts[i].reshape(-1, 2) - o
            u = q @ eu
            if np.abs(q @ ev).max() <= rh * 0.6 and u.min() <= rw / 2 + rh * 0.15 and u.max() >= -rw / 2 - rh * 0.15:
                keep.append(cnts[i].reshape(-1, 2))
        n, p = len(p), np.concatenate(keep)
        if len(p) == n:
            break
    return p


def _quad(p):
    """The code block's four corners: each edge a robust line (Huber) through its outermost points strip by strip, the
    corners where the lines meet. Not the hull's corners: the last block row is mostly only partly filled, a corner at
    its end would tilt the whole edge by a block – here it is an outlier, or the line runs one row lower but parallel
    (the band reading measures the height itself). Long side on top, widened like the rectangle (×1.04 along, ×1.25
    across – in the quadrilateral's own coordinates) -> (box, rw, rh) or None."""
    import cv2
    import numpy as np
    p = p.astype(np.float32)
    center, ang, rw, rh = _rect(p)
    if min(rw, rh) < 6 or rw / max(rh, 1) < 1.15:
        return None
    a = np.radians(ang)
    eu, ev = np.float32([np.cos(a), np.sin(a)]), np.float32([-np.sin(a), np.cos(a)])
    u, v = (p - center) @ eu, (p - center) @ ev

    def outer(along, across, half, n, side):   # per strip along the edge the point farthest out
        pts = []
        for lo in np.linspace(-half * 0.85, half * 0.85, n, endpoint=False):
            sel = np.nonzero((along >= lo) & (along < lo + half * 1.7 / n))[0]
            if len(sel):
                pts.append(p[sel[np.argmax(across[sel] * side)]])
        return np.float32(pts) if len(pts) >= 4 else None

    lines = []
    for along, across, half, n, side in ((u, v, rw / 2, 24, -1), (v, u, rh / 2, 8, 1), (u, v, rw / 2, 24, 1),
                                         (v, u, rh / 2, 8, -1)):   # top, right, bottom, left
        pts = outer(along, across, half, n, side)
        if pts is None:
            return None
        vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        lines.append((np.float32([x0, y0]), np.float32([vx, vy])))
    corners = []
    for (p1, d1), (p2, d2) in zip(lines, lines[1:] + lines[:1]):
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 0.2:   # nearly parallel neighbours: no corner
            return None
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        corners.append(p1 + t * d1)
    q = _order(corners)
    if np.linalg.norm(q[3] - q[0]) > np.linalg.norm(q[1] - q[0]):   # portrait: the long side to the top
        q = np.float32([q[3], q[0], q[1], q[2]])
    rw = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    rh = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    if min(rw, rh) < 6 or rw / max(rh, 1) < 1.15:
        return None
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), q)
    ex = np.float32([[[-0.02, -0.125], [1.02, -0.125], [1.02, 1.125], [-0.02, 1.125]]])
    return cv2.perspectiveTransform(ex, m)[0].astype(np.float32), rw, rh


def _read_box(g, box, rw, rh):
    """The quadrilateral box (tl, tr, br, bl) straightened to WIDE.COLS·8 px, also turned by 180°; the bright band put
    onto a clean "virtual ticket" of each layout and read -> ticket or None."""
    import cv2
    import numpy as np
    tw = WIDE.COLS * 8
    tht = max(8, int(round(tw * rh * 1.25 / (rw * 1.04))))
    mat = cv2.getPerspectiveTransform(np.float32(box), np.float32([[0, 0], [tw, 0], [tw, tht], [0, tht]]))
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
            if valid(t):
                return t
        except ValueError:
            pass
    import numpy as np
    g = img.convertToFormat(QtGui.QImage.Format_Grayscale8)
    arr = np.frombuffer(g.constBits(), np.uint8, g.bytesPerLine() * g.height()).reshape(g.height(), g.bytesPerLine())
    t = decode_gray(arr[:, :g.width()].copy())
    return t if valid(t) else None


def is_ticket_file(path):
    return str(path).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
