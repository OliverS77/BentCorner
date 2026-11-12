"""The pairing sphere ("Kugel A1", Oliver 29.10./03.11.2026, PAIRING.md §2): the pairing code as a punched band wound
four times round a turning sphere. Only a camera watching it turn reads it (the web's sphere.js); a screenshot shows
the front half only. This is the drawing side for the desktop – the same pictures as labs/webapp/stripcode/sphere.py
(render), which the readers and their test bench were built against (tests/test_sphere.py checks they match).

    frames(payload, n=120, size=300, dark=True) -> [uint8 gray image (size × size)]   one full turn
    render(tex, rot, size, radius, fg, bg)       -> one frame
    texture(payload)                             -> the band as a flat picture

The band: 72 cells of the 4 forms (gap · hole · ring · bar, 2 bits each = 8 + 10 bytes, the ticket code "f5"), equal
neighbours melted into one shape; along one edge a row of feed holes, the reader finds the turning angle from them.
The 4 cells of a byte sit a quarter turn apart: no view of the front ever holds a whole byte.
"""
import cv2
import numpy as np

from collection import rscode

PERIOD = 4.0                 # s per turn (the readers expect it: sphere.js / sphere.py PERIOD)
FPS = 30

# ---------- the cells (stripcode.py: Layout "f5", mask, bits, cells, _runs) ----------
KINDS = ("gap", "hole", "ring", "bar")
F5 = dict(cols=12, rows=6, data=8, nsym=10, seed=0x51A7)


class _Band:
    """The geometry of the band's shapes (stripcode Layout "s1": 72 × 1, the 4 forms)."""
    rows, cols = 1, 72
    dot, ring, neck, rneck, rt, band = 0.34, 0.36, 0.2, 0.25, 0.18, 0.13


def _mask(n, seed):
    x, out = seed, []
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((x >> 16) & 1)
    return out


def cells(payload):
    """payload (8 bytes) -> 72 cell values 0–3: payload + Reed-Solomon, XORed with the fixed pattern, 2 bits a cell."""
    payload = bytes(payload)
    if len(payload) != F5["data"]:
        raise ValueError("payload length")
    block = rscode.encode(payload, F5["nsym"])
    raw = [(b >> (7 - k)) & 1 for b in block for k in range(8)]
    raw += [0] * (F5["cols"] * F5["rows"] * 2 - len(raw))
    b = [a ^ m for a, m in zip(raw, _mask(len(raw), F5["seed"]))]
    return [b[2 * i] * 2 + b[2 * i + 1] for i in range(len(b) // 2)]


def _runs(lay, vals):
    """Row by row: equal neighbours become one shape (ink capsules, then "paper" capsules cut into it).
    A shape is [x0, y0, x1, y1, r, kind]: kind 0 = capsule (ink), 2 = cut out."""
    ink, cut = [], []
    for row in range(lay.rows):
        y = row + 0.5
        c = 0
        while c < lay.cols:
            d = vals[row * lay.cols + c]
            k = 1
            while c + k < lay.cols and vals[row * lay.cols + c + k] == d:
                k += 1
            xa, xb = c + 0.5, c + k - 0.5
            kind = KINDS[d]
            if kind == "hole":
                ink += [[xa + j, y, xa + j, y, lay.dot, 0] for j in range(k)]
                if k > 1:
                    ink.append([xa, y, xb, y, lay.neck, 0])
            elif kind == "ring":
                ink += [[xa + j, y, xa + j, y, lay.ring, 0] for j in range(k)]
                cut += [[xa + j, y, xa + j, y, lay.ring - lay.rt, 2] for j in range(k)]
                if k > 1:
                    ink.append([xa, y, xb, y, lay.rneck, 0])
                    cut.append([xa, y, xb, y, lay.rneck - lay.rt, 2])
            elif kind == "bar":
                ink.append([xa - 0.45 + lay.band, y, xb + 0.45 - lay.band, y, lay.band, 0])
            c += k
    return ink + cut


# ---------- the band on the sphere (sphere.py) ----------
TURNS = 4
TH0, TH1 = 0.1, 0.9          # the band runs from 0.1 π to 0.9 π (pole to pole, the caps left free)
TILT = 0.35                  # axis tipped towards the camera (rad): both poles a little visible
N = 72                       # cells
BW = 1.5                     # band width in cell lengths: feed holes | data | edges
V_DATA, V_FEED = 0.12, -0.5  # across the band (cell units, 0 = centre line): data row, feed holes
EDGE = 0.72                  # the band's two edge lines at ±EDGE
FEED = np.ones(N, bool)
_K = TURNS * 2 * np.pi / ((TH1 - TH0) * np.pi)   # dφ/dθ of the spiral


def _spiral(t):
    th = np.pi * (TH0 + (TH1 - TH0) * t)
    return th, TURNS * 2 * np.pi * t


def _arc_table(m=20000):
    t = np.linspace(0, 1, m)
    th, ph = _spiral(t)
    d = np.sqrt(np.diff(th) ** 2 + (np.sin(th[:-1]) * np.diff(ph)) ** 2)
    return t, np.concatenate([[0], np.cumsum(d)])


T_TAB, S_TAB = _arc_table()
LENGTH = S_TAB[-1]
PITCH = LENGTH / N


def _slot_order():
    """Which band slot carries data cell j: the 4 cells of byte b a quarter turn apart (by the slot's longitude)."""
    s = (np.arange(N) + 0.5) * PITCH
    t = np.interp(s, S_TAB, T_TAB)
    ph = (_spiral(t)[1] % (2 * np.pi))
    quad = (ph // (np.pi / 2)).astype(int)
    pools = [list(np.nonzero(quad == q)[0]) for q in range(4)]
    order = [0] * N
    for b in range(N // 4):
        for k in range(4):
            q = max(range(4), key=lambda q: len(pools[(k + q) % 4]))
            q = (k + q) % 4 if not pools[k % 4] else k % 4
            order[b * 4 + k] = pools[q].pop(0)
    return order


ORDER = _slot_order()


def strip_values(payload):
    """payload -> the 72 band slots' values, data cells moved to their slots."""
    vals = cells(payload)
    out = [0] * N
    for j, slot in enumerate(ORDER):
        out[slot] = vals[j]
    return out


def texture(payload, S=48):
    """The band as a flat picture: N·S × BW·2·S, ink = 1 (data shapes melted along the band, feed holes, edges)."""
    shp = _runs(_Band, strip_values(payload))
    feed = [[i + 0.5, 0.5 + V_FEED - V_DATA, i + 0.5, 0.5 + V_FEED - V_DATA, 0.09, 0] for i in range(N) if FEED[i]]
    edges = [[0, 0.5 - EDGE - V_DATA, N, 0.5 - EDGE - V_DATA, 0.04, 0],
             [0, 0.5 + EDGE - V_DATA, N, 0.5 + EDGE - V_DATA, 0.04, 0]]
    H, W = int(2 * BW * S), N * S
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    u = (xs + 0.5) / S
    v = (ys + 0.5) / S - BW + 0.5 - V_DATA
    hit = np.zeros((H, W), bool)
    for x0, y0, x1, y1, r, kind in feed + edges + shp:
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy
        tt = np.clip(((u - x0) * dx + (v - y0) * dy) / ll, 0, 1) if ll else 0.0
        inside = (u - x0 - tt * dx) ** 2 + (v - y0 - tt * dy) ** 2 <= r * r
        if kind == 2:
            hit &= ~inside
        else:
            hit |= inside
    return hit.astype(np.float32)


def _rot(rot):
    c, s = np.cos(rot), np.sin(rot)
    Ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    ct, st = np.cos(TILT), np.sin(TILT)
    Rx = np.array([[1, 0, 0], [0, ct, -st], [0, st, ct]])
    return Rx @ Ry


def _band_coords(q):
    th = np.arccos(np.clip(q[..., 1], -1, 1))
    ph = np.arctan2(q[..., 2], q[..., 0])
    t_th = (th / np.pi - TH0) / (TH1 - TH0)
    n = np.round(t_th * TURNS - ph / (2 * np.pi))
    t = (ph / (2 * np.pi) + n) / TURNS
    ok = (t >= 0) & (t <= 1)
    tc = np.clip(t, 0, 1)
    ths, _ = _spiral(tc)
    s = np.interp(tc, T_TAB, S_TAB)
    sk = np.sin(ths) * _K
    nrm = np.sqrt(1 + sk ** 2)
    d = th - ths
    v = d * sk / nrm / PITCH
    u = (s + d / nrm) / PITCH
    return u, v, ok


def render(tex, rot, size=640, radius=270, fg=230, bg=24):
    """The sphere's front at turning angle rot (texture-mapped band), a faint outline."""
    S = tex.shape[1] / N
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    x, y = (xs + 0.5 - size / 2) / radius, -(ys + 0.5 - size / 2) / radius
    r2 = x * x + y * y
    front = r2 < 1
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    p = np.stack([x, y, z], axis=-1)[front]
    u, v, ok = _band_coords(p @ _rot(rot))
    tx = np.clip(u * S, 0, tex.shape[1] - 1.001)
    ty = (v + BW) * S
    inb = ok & (ty >= 0) & (ty <= tex.shape[0] - 1.001)
    ink = np.zeros(len(p))
    xi, yi = tx[inb], ty[inb]
    x0, y0 = xi.astype(int), yi.astype(int)
    fx, fy = xi - x0, yi - y0
    a = tex[y0, x0] * (1 - fx) + tex[y0, x0 + 1] * fx
    b = tex[y0 + 1, x0] * (1 - fx) + tex[y0 + 1, x0 + 1] * fx
    ink[inb] = a * (1 - fy) + b * fy
    img = np.full((size, size), float(bg))
    img[front] = bg + (fg - bg) * ink
    cv2.circle(img, (size // 2, size // 2), int(round(radius * 1.03)), fg, max(2, int(round(radius * 0.012))),
               cv2.LINE_AA)
    return img.clip(0, 255).astype(np.uint8)


def outline_radius(size):
    """Outer edge of the drawn sphere in a frame of frames(size=size): the outline circle plus half its stroke (px)."""
    radius = size * 270 / 640
    return round(radius * 1.03) + max(2, round(radius * 0.012)) / 2 + 0.5


def frames(payload, n=int(PERIOD * FPS), size=300, dark=True):
    """One full turn as n frames (shown at FPS: a turn takes PERIOD s, as the readers expect). dark: light band on a
    dark ground (the app's look); the readers take both."""
    tex = texture(payload)
    fg, bg = (230, 24) if dark else (30, 245)
    radius = size * 270 / 640
    return [render(tex, 2 * np.pi * i / n, size=size, radius=radius, fg=fg, bg=bg) for i in range(n)]
