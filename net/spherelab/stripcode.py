"""Strip code ("Lochstreifen"): a short secret (pairing code, later friend code) as a picture a camera reads back.

Looks like the tear-off stub of the trade ticket: punched dots between two bars, brackets at three corners, a dot
at the fourth. Every layout has its own id (LAYOUTS) – drawing and reading go through it, so the look can change
later without touching what is carried (the payload's own first byte is its format version, e.g. pairing v2).

Carried: payload bytes + Reed-Solomon parity (rscode), XORed with a fixed pattern, row by row from the top, bit 7
first. Geometry in module units (1 = distance between two dots), origin = top left of the dot field; every shape is
[x0, y0, x1, y1, r, kind]: kind 0 = capsule (a line with round ends, radius r – a round dot is one of length 0),
kind 1 = square around (x0, y0) with half side r. The same list for SVG, canvas, raster and the tests.

Reading (decode): adaptive threshold (bright and dark – dark and light theme), connected components, two long
parallel bars -> their centre lines -> homography -> sample the dot grid -> Reed-Solomon. Four orientations
(upside down, mirrored) are tried; Reed-Solomon decides. Plain numpy, the same steps as web/scan/logic/stripcode.js.
"""
import numpy as np

from collection import rscode


class Layout:
    def __init__(self, key, cols, rows, data, nsym, dot=0.4, bar=0.3, gap=1.2, side=1.3, arm=1.4, stroke=0.14,
                 margin=0.7, seed=0x51A7, forms=2, frame="brackets", reach=0.0, ring=0.32, neck=0.2, rneck=0.22,
                 rt=0.13, band=0.17, probe=0.25, inset=0.4):
        """dot/bar: radius of a dot / half thickness of a bar; gap: bar centre line to the dot field; side: bracket
        corner to the bar (outwards and sideways); arm: bracket arm length; stroke: half thickness of an arm.
        forms: shapes a cell can take – 2 = dot or nothing (1 bit), 4 = gap · hole · ring · bar (2 bits, equal
        neighbours in a row melted into one shape). frame: "brackets" (three corners + a dot) or "rails" (a line down
        each side + a dot top right); reach: how far the bars stick out beyond the field (module units).
        4 forms: ring = outer radius of a ring, neck/rneck = half height of the joint between two dots/rings,
        rt = ring stroke, band = half thickness of a bar, probe = where a cell is felt above and below its centre;
        inset = how far the side lines stay away from the bars' centre lines (air, so blur doesn't join them)."""
        self.key, self.cols, self.rows, self.data, self.nsym = key, cols, rows, data, nsym
        self.dot, self.bar, self.gap, self.side, self.arm = dot, bar, gap, side, arm
        self.stroke, self.margin, self.seed = stroke, margin, seed
        self.forms, self.frame = forms, frame
        self.ring, self.neck, self.rneck, self.rt, self.band, self.probe = ring, neck, rneck, rt, band, probe
        self.inset = inset
        self.per = 2 if forms == 4 else 1   # bits per cell
        assert (data + nsym) * 8 <= cols * rows * self.per
        self.top = -gap                 # centre line of the top bar
        self.bottom = rows + gap        # … and of the bottom bar
        self.x0, self.x1 = -reach, float(cols) + reach   # bar centre line from x0 to x1 (plus round caps)


# c1: 24 × 6 dots, 8 bytes payload + 10 parity (Oliver's choice "Lochstreifen", 2026-10-28)
# f1: "4 Formen, verbunden" (Oliver 2026-10-29): 12 × 6 cells of gap · hole · ring · bar, 2 bits each – half the
#     area of c2, same 8 + 10 bytes; equal neighbours in a row become one shape (dots → a filled wave, rings → an
#     outlined wave, bars → one stripe). Thin bars, a line down each side, a dot top right (the specimen sheet).
LAYOUTS = {
    "c1": Layout("c1", 24, 6, 8, 10),
    "c2": Layout("c2", 18, 8, 8, 10),
    "f1": Layout("f1", 12, 6, 8, 10, dot=0.3, bar=0.11, gap=1.04, side=0.71, stroke=0.07, margin=0.7, forms=4,
                 frame="rails", reach=0.39),
    # f2: the same look, made easier to read (test bench 2026-10-29): hole a little larger, ring stroke thicker,
    # bar thinner, frame bars a little stronger
    "f2": Layout("f2", 12, 6, 8, 10, dot=0.34, bar=0.15, gap=1.08, side=0.75, stroke=0.08, margin=0.7, forms=4,
                 frame="rails", reach=0.35, ring=0.36, neck=0.2, rneck=0.25, rt=0.18, band=0.13, probe=0.28),
    # f3: f2 with more air between bars and side lines (under blur they joined into one bracket – no bar found)
    "f3": Layout("f3", 12, 6, 8, 10, dot=0.34, bar=0.15, gap=1.08, side=0.75, stroke=0.08, margin=0.7, forms=4,
                 frame="rails", reach=0.35, ring=0.36, neck=0.2, rneck=0.25, rt=0.18, band=0.13, probe=0.28,
                 inset=0.75),
    # f4: f3 with stronger bars (they carry the finding – under heavy blur thin ones fade before the cells do)
    "f4": Layout("f4", 12, 6, 8, 10, dot=0.34, bar=0.22, gap=1.15, side=0.75, stroke=0.08, margin=0.7, forms=4,
                 frame="rails", reach=0.28, ring=0.36, neck=0.2, rneck=0.25, rt=0.18, band=0.13, probe=0.28,
                 inset=0.85),
    # f5 – the tickets (Oliver 2026-10-29): f4's cells in c2's frame – the two bars, brackets at three corners, the odd
    # dot outside bottom right; no side lines
    "f5": Layout("f5", 12, 6, 8, 10, dot=0.34, forms=4, ring=0.36, neck=0.2, rneck=0.25, rt=0.18, band=0.13,
                 probe=0.28),
}
KINDS = ("gap", "hole", "ring", "bar")   # 4 forms: the cell value (2 bits, first bit high) -> its shape
DEFAULT = "c2"   # 18 × 8: same look, dots ~25 % larger at the same width (test bench 2026-10-28)
DOTS = ("round", "square")   # dot shape – only the look, reading does not care


def mask(n, seed):
    """Fixed scrambling pattern (so the dots look evenly spread, even for zeros)."""
    x, out = seed, []
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((x >> 16) & 1)
    return out


def bits(payload, key=DEFAULT):
    """payload (bytes, exactly layout.data long) -> [0/1] per dot, row by row from the top."""
    lay = LAYOUTS[key]
    payload = bytes(payload)
    if len(payload) != lay.data:
        raise ValueError("payload length")
    block = rscode.encode(payload, lay.nsym)
    raw = [(b >> (7 - k)) & 1 for b in block for k in range(8)]
    raw += [0] * (lay.cols * lay.rows * lay.per - len(raw))
    return [a ^ m for a, m in zip(raw, mask(len(raw), lay.seed))]


def cells(payload, key):
    """4 forms: the cell values 0–3 (KINDS) row by row – two bits per cell, the first one high."""
    b = bits(payload, key)
    return [b[2 * i] * 2 + b[2 * i + 1] for i in range(len(b) // 2)]


def box(key=DEFAULT):
    """Picture frame in module units: (x, y, w, h) – shapes plus a quiet margin."""
    lay = LAYOUTS[key]
    if lay.frame == "rails":
        ext = lay.side + lay.stroke + lay.margin
        left, top = -ext, lay.top - lay.bar - lay.margin
        return left, top, lay.cols + 2 * ext, lay.bottom - lay.top + 2 * (lay.bar + lay.margin)
    ext = lay.side + lay.stroke + lay.margin
    left, top = -ext, lay.top - ext
    w, h = lay.cols + 2 * ext, lay.bottom - lay.top + 2 * ext
    return left, top, w, h


def _runs(lay, vals):
    """4 forms, row by row: equal neighbours become one shape (ink capsules, then "paper" capsules cut into it)."""
    ink, cut = [], []
    for row in range(lay.rows):
        y = row + 0.5
        c = 0
        while c < lay.cols:
            d = vals[row * lay.cols + c]
            k = 1
            while c + k < lay.cols and vals[row * lay.cols + c + k] == d:
                k += 1
            xa, xb = c + 0.5, c + k - 0.5      # centres of the first and the last cell of the run
            kind = KINDS[d]
            if kind == "hole":      # a filled wave: a dot per cell, joined by a narrower neck
                ink += [[xa + j, y, xa + j, y, lay.dot, 0] for j in range(k)]
                if k > 1:
                    ink.append([xa, y, xb, y, lay.neck, 0])
            elif kind == "ring":    # the same as an outline
                ink += [[xa + j, y, xa + j, y, lay.ring, 0] for j in range(k)]
                cut += [[xa + j, y, xa + j, y, lay.ring - lay.rt, 2] for j in range(k)]
                if k > 1:
                    ink.append([xa, y, xb, y, lay.rneck, 0])
                    cut.append([xa, y, xb, y, lay.rneck - lay.rt, 2])
            elif kind == "bar":     # one stripe through the whole run (its ends 0.45 beyond the outer centres)
                ink.append([xa - 0.45 + lay.band, y, xb + 0.45 - lay.band, y, lay.band, 0])
            c += k
    return ink + cut


def shapes(payload, key=DEFAULT, dots="round"):
    """-> [[x0, y0, x1, y1, r, kind]]: bars, three brackets, the corner mark, then the dots that are on.
    dots: "round" or "square" (square dots: the same area as the round ones). kind 2 = a capsule in the paper's
    colour (the inside of a ring) – drawn after all the ink."""
    lay = LAYOUTS[key]
    sq = dots == "square"
    out = [[lay.x0, lay.top, lay.x1, lay.top, lay.bar, 0], [lay.x0, lay.bottom, lay.x1, lay.bottom, lay.bar, 0]]
    if lay.frame == "rails":   # a line down each side (clear of the bars), a dot top right
        lx, rx = -lay.side, lay.cols + lay.side
        y0, y1 = lay.top + lay.inset, lay.bottom - lay.inset
        out += [[lx, y0, lx, y1, lay.stroke, 0], [rx, y0, rx, y1, lay.stroke, 0],
                [lay.cols + 0.36, -0.36, lay.cols + 0.36, -0.36, 0.157, 0]]
        return out + _runs(lay, cells(payload, key))
    gx, gy = -lay.side, lay.top - lay.side        # bracket corner top left
    rx, by = lay.cols + lay.side, lay.bottom + lay.side
    s, a = lay.stroke, lay.arm
    out += [[gx, gy, gx + a, gy, s, 0], [gx, gy, gx, gy + a, s, 0],     # top left
            [rx, gy, rx - a, gy, s, 0], [rx, gy, rx, gy + a, s, 0],     # top right
            [gx, by, gx + a, by, s, 0], [gx, by, gx, by - a, s, 0],     # bottom left
            [rx, by, rx, by, 2.2 * s * (0.886 if sq else 1), int(sq)]]  # bottom right: a dot
    if lay.forms == 4:   # 4 forms in the brackets of c2 (f5, the tickets)
        return out + _runs(lay, cells(payload, key))
    r = lay.dot * (0.886 if sq else 1)   # sqrt(pi)/2: a square of the same area
    for i, v in enumerate(bits(payload, key)):
        if v:
            x, y = i % lay.cols + 0.5, i // lay.cols + 0.5
            out.append([x, y, x, y, r, int(sq)])
    return out


def raster(shp, key=DEFAULT, scale=10.0, fg=230, bg=24, ss=3):
    """Shapes -> grayscale picture (numpy uint8), scale = pixels per module, ss = supersampling per axis."""
    left, top, w, h = box(key)
    W, H = int(round(w * scale)), int(round(h * scale))
    acc = np.zeros((H, W), np.float32)
    for sy in range(ss):
        for sx in range(ss):
            ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
            px = (xs + (sx + 0.5) / ss) / scale + left
            py = (ys + (sy + 0.5) / ss) / scale + top
            hit = np.zeros((H, W), bool)
            for x0, y0, x1, y1, r, kind in shp:
                # only the shape's own box (+1 px): the same pixels as over the whole picture, far less work
                c0 = max(0, int(np.floor((min(x0, x1) - r - left) * scale)) - 1)
                c1 = min(W, int(np.ceil((max(x0, x1) + r - left) * scale)) + 2)
                r0 = max(0, int(np.floor((min(y0, y1) - r - top) * scale)) - 1)
                r1 = min(H, int(np.ceil((max(y0, y1) + r - top) * scale)) + 2)
                if c0 >= c1 or r0 >= r1:
                    continue
                qx, qy, h_ = px[r0:r1, c0:c1], py[r0:r1, c0:c1], hit[r0:r1, c0:c1]
                if kind == 1:
                    h_ |= (np.abs(qx - x0) <= r) & (np.abs(qy - y0) <= r)
                    continue
                dx, dy = x1 - x0, y1 - y0
                ll = dx * dx + dy * dy
                t = np.clip(((qx - x0) * dx + (qy - y0) * dy) / ll, 0, 1) if ll else 0.0
                inside = (qx - x0 - t * dx) ** 2 + (qy - y0 - t * dy) ** 2 <= r * r
                if kind == 2:   # paper: cut out of the ink drawn so far
                    h_ &= ~inside
                else:
                    h_ |= inside
            acc += hit
    cov = acc / (ss * ss)
    return np.round(bg + (fg - bg) * cov).astype(np.uint8)


# ---------- Reading ----------
MAX_SIDE = 960
MIN_AREA = 24


def _shrink(g):
    """Box-average by an integer factor so the longer side is at most MAX_SIDE."""
    h, w = g.shape
    f = -(-max(h, w) // MAX_SIDE)
    if f <= 1:
        return g.astype(np.float64)
    h2, w2 = h // f, w // f
    return g[:h2 * f, :w2 * f].astype(np.float64).reshape(h2, f, w2, f).sum(axis=(1, 3)) / (f * f)


def _smooth(g):
    """3 × 3 box average, borders clamped (takes out pixel noise and the finest screen grid)."""
    p = np.pad(g, 1, mode="edge")
    h, w = g.shape
    acc = np.zeros((h, w), np.float64)
    for dy in range(3):
        for dx in range(3):
            acc += p[dy:dy + h, dx:dx + w]
    return acc / 9.0


def _local_mean(g):
    """Mean over a square window (radius = 1/16 of the shorter side, at least 6), borders clamped."""
    h, w = g.shape
    r = max(6, min(h, w) // 16)
    ii = np.zeros((h + 1, w + 1), np.float64)
    ii[1:, 1:] = g.cumsum(0).cumsum(1)
    ys, xs = np.arange(h), np.arange(w)
    y0, y1 = np.clip(ys - r, 0, h), np.clip(ys + r + 1, 0, h)
    x0, x1 = np.clip(xs - r, 0, w), np.clip(xs + r + 1, 0, w)
    s = ii[y1][:, x1] - ii[y0][:, x1] - ii[y1][:, x0] + ii[y0][:, x0]
    n = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    return s / n


def _components(m):
    """8-connected components of a boolean picture -> label image (0 = none), number of labels."""
    import cv2
    n, lab = cv2.connectedComponents(m.astype(np.uint8), connectivity=8)
    return lab, n - 1


def _blobs(lab, n):
    """Per label: area, centroid, covariance -> [{area, cx, cy, ax, ay (unit major axis), l1, l2, idx}]."""
    ys, xs = np.nonzero(lab)
    ls = lab[ys, xs]
    area = np.bincount(ls, minlength=n + 1).astype(np.float64)
    sx = np.bincount(ls, xs, n + 1)
    sy = np.bincount(ls, ys, n + 1)
    sxx = np.bincount(ls, xs.astype(np.float64) * xs, n + 1)
    syy = np.bincount(ls, ys.astype(np.float64) * ys, n + 1)
    sxy = np.bincount(ls, xs.astype(np.float64) * ys, n + 1)
    out = {}
    for i in range(1, n + 1):
        a = area[i]
        if a < MIN_AREA:
            continue
        cx, cy = sx[i] / a, sy[i] / a
        vxx, vyy, vxy = sxx[i] / a - cx * cx, syy[i] / a - cy * cy, sxy[i] / a - cx * cy
        tr, det = vxx + vyy, vxx * vyy - vxy * vxy
        d = max(0.0, tr * tr / 4 - det) ** 0.5
        l1, l2 = tr / 2 + d, max(tr / 2 - d, 1e-6)
        ang = 0.5 * np.arctan2(2 * vxy, vxx - vyy)
        out[i] = {"area": a, "cx": cx, "cy": cy, "ax": float(np.cos(ang)), "ay": float(np.sin(ang)),
                  "l1": l1, "l2": l2}
    return out, ys, xs, ls


def _bars(blobs):
    """Long thin blobs (bar candidates), longest first."""
    out = [dict(b, id=i, len=(12 * b["l1"]) ** 0.5) for i, b in blobs.items()
           if b["l1"] / b["l2"] >= 36 and b["area"] >= 40]
    out.sort(key=lambda b: (-b["len"], b["id"]))
    return out[:12]


def _ends(b, ys, xs, ls):
    """Both ends of a bar's centre line: extreme projections onto its axis (the round caps included)."""
    sel = ls == b["id"]
    t = (xs[sel] - b["cx"]) * b["ax"] + (ys[sel] - b["cy"]) * b["ay"]
    t0, t1 = float(t.min()), float(t.max())
    return ([b["cx"] + b["ax"] * t0, b["cy"] + b["ay"] * t0], [b["cx"] + b["ax"] * t1, b["cy"] + b["ay"] * t1])


def _pairs(bars, lay):
    """Pairs of bars that could be the top and bottom bar of this layout, best first."""
    want = (lay.bottom - lay.top) / (lay.x1 - lay.x0 + 2 * lay.bar)
    out = []
    for i in range(len(bars)):
        for j in range(i + 1, len(bars)):
            p, q = bars[i], bars[j]
            dot = abs(p["ax"] * q["ax"] + p["ay"] * q["ay"])
            if dot < 0.95:                      # more than ~18° apart
                continue
            L = (p["len"] + q["len"]) / 2
            if not 0.6 <= p["len"] / q["len"] <= 1 / 0.6:
                continue
            dx, dy = q["cx"] - p["cx"], q["cy"] - p["cy"]
            along = abs(dx * p["ax"] + dy * p["ay"])
            across = abs(-dx * p["ay"] + dy * p["ax"])
            if along > 0.6 * L or across < 1e-6:   # perspective shifts the bars against each other
                continue
            ratio = across / L / want
            if not 0.45 <= ratio <= 2.2:
                continue
            out.append((abs(np.log(ratio)) + (1 - dot) * 4 + along / L, i, j))
    out.sort()
    return [(bars[i], bars[j]) for _, i, j in out[:4]]


def _solve(a, b):
    """Gaussian elimination with partial pivoting (8 × 8) -> x or None."""
    n = len(b)
    m = [list(map(float, a[i])) + [float(b[i])] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: (abs(m[r][c]), -r))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                if f:
                    for k in range(c, n + 1):
                        m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def homography(src, dst):
    """4 point pairs (model -> picture) -> 3×3 as a flat list of 9, or None."""
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    h = _solve(a, b)
    return None if h is None else h + [1.0]


PROBES_2 = ((0, 0), (-0.18, 0), (0.18, 0), (0, -0.18), (0, 0.18))   # a dot: its centre and four points around it
# 4 forms: the centre (a hole or bar fills it, a ring and a gap leave it empty) – then above and below it (a hole or
# ring reaches there, a bar and a gap don't). Two independent questions, one bit each; runs need no length counting.
PROBES_C = ((0, 0), (-0.05, 0), (0.05, 0))


def _probes(lay):
    if lay.forms != 4:
        return PROBES_2
    p = lay.probe
    return PROBES_C + ((0, -p), (-0.05, -p), (0.05, -p), (0, p), (-0.05, p), (0.05, p))


def _sample_points(lay):
    """Model points per cell (_probes)."""
    pts = []
    for i in range(lay.cols * lay.rows):
        x, y = i % lay.cols + 0.5, i // lay.cols + 0.5
        for ox, oy in _probes(lay):
            pts.append((x + ox, y + oy))
    return np.array(pts, np.float64)


def _sample(g, H, pts):
    """Bilinear samples of g at the picture positions of model points pts (any point outside -> None)."""
    x, y = pts[:, 0], pts[:, 1]
    w = H[6] * x + H[7] * y + H[8]
    u = (H[0] * x + H[1] * y + H[2]) / w
    v = (H[3] * x + H[4] * y + H[5]) / w
    h, wd = g.shape
    ok = (u >= 0) & (v >= 0) & (u <= wd - 1.001) & (v <= h - 1.001)
    if not ok.all():
        return None
    x0, y0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    a = g[y0, x0] * (1 - fx) + g[y0, x0 + 1] * fx
    b = g[y0 + 1, x0] * (1 - fx) + g[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


_SEEDS = {}
BLURS = (0.0, 0.12, 0.2, 0.3)   # sharpness the starting points are made for (gaussian sigma, module units)


def _seeds(lay):
    """Where the four forms sit in (centre, above/below) for this layout, ink scaled 0..1 like _classify does –
    one set per sharpness (BLURS), measured once on a perfect, then blurred picture of it. Sharp: a hole reaches only
    partly up to "above/below"; blurred: a ring's centre fills in until it sits between hole and bar, so starting
    from the sharp places the rings would be swallowed."""
    if lay.key not in _SEEDS:
        import cv2
        rng = np.random.default_rng(3)
        scale = 12.0
        left, top, _w, _h = box(lay.key)
        H = [scale, 0, -left * scale - 0.5, 0, scale, -top * scale - 0.5, 0, 0, 1]
        pics = []
        for _ in range(4):
            payload = bytes(rng.integers(0, 256, lay.data, dtype=np.uint8).tolist())
            pics.append((payload, raster(shapes(payload, lay.key), lay.key, scale=scale, fg=255, bg=0).astype(np.float64)))
        sets = []
        for sigma in BLURS:
            acc = {k: [] for k in range(4)}
            for payload, g in pics:
                if sigma:
                    g = cv2.GaussianBlur(g, (0, 0), sigma * scale)
                per = _sample(g, H, _sample_points(lay)).reshape(-1, len(_probes(lay)))
                c, r = per[:, :len(PROBES_C)].mean(axis=1), per[:, len(PROBES_C):].mean(axis=1)
                f = _scaled(np.stack([c, r], axis=1))
                for k, v in zip(cells(payload, lay.key), f):
                    acc[k].append(v)
            sets.append(np.array([np.mean(acc[k], axis=0) for k in range(4)]))
        _SEEDS[lay.key] = sets
    return _SEEDS[lay.key]


def _scaled(f):
    lo, hi = np.percentile(f, 10), np.percentile(f, 90)
    return (f - lo) / max(hi - lo, 1e-6)


def _classify(centre, rim, bright, lay):
    """4 forms: each cell's (centre, above/below) brightness -> candidate readings [values 0–3 per cell] (KINDS),
    one per starting set (_seeds) – Reed-Solomon picks the right one. Ink scaled to 0..1 between the faint and the
    strong tenth, then the four groups found in this very picture (blur and light move them, a fixed threshold
    would cut through them). The groups are named by what they are, not by where they started: gap = the faintest,
    hole = the strongest, of the two others the ring reaches further above/below than its centre."""
    f = np.stack([centre, rim], axis=1).astype(np.float64)
    f = _scaled(f if bright else -f)
    out = []
    for seed in _seeds(lay):
        c = seed.copy()
        lab = np.zeros(len(f), int)
        for _ in range(8):
            d = ((f[:, None, :] - c[None, :, :]) ** 2).sum(axis=2)
            lab = d.argmin(axis=1)
            for k in range(4):
                if (lab == k).any():
                    c[k] = f[lab == k].mean(axis=0)
        total = c.sum(axis=1)
        gap, hole = int(total.argmin()), int(total.argmax())
        rest = [k for k in range(4) if k not in (gap, hole)]
        if len(rest) != 2:
            continue
        # ring = the one reaching further up/down than its centre (blurred, a ring's centre fills in as bright as a
        # bar's – only above/below still tells them apart)
        bar, ring = sorted(rest, key=lambda k: c[k][1] - c[k][0])
        name = np.zeros(4, int)
        name[[gap, hole, ring, bar]] = [0, 1, 2, 3]
        val = name[lab]
        if any(np.array_equal(val, o[0]) for o in out):
            continue
        srt = np.sort(d, axis=1)
        second = name[np.argsort(d, axis=1)[:, 1]]
        out.append((val, second, srt[:, 1] - srt[:, 0]))   # + each cell's second choice and how sure it was
    return out


def _read(g, H, lay, pts, bright):
    """g: the picture – or several (4 forms: unsmoothed first, then smoothed), tried in turn."""
    if isinstance(g, tuple):
        for gi in g:
            r = _read(gi, H, lay, pts, bright)
            if r is not None:
                return r
        return None
    s = _sample(g, H, pts)
    if s is None:
        return None

    def ink(vals):   # threshold halfway between the faint and the strong tenth (dark or light theme)
        srt = np.sort(vals)
        k = len(srt) // 10
        thr = (srt[k] + srt[-k - 1]) / 2
        return (vals > thr) if bright else (vals < thr)
    n = lay.data + lay.nsym

    def rs(on):
        raw = [int(a) ^ m for a, m in zip(on, mask(len(on), lay.seed))]
        block = bytes(sum(raw[i * 8 + k] << (7 - k) for k in range(8)) for i in range(n))
        try:
            return bytes(rscode.decode(block, lay.nsym))
        except ValueError:
            return None
    if lay.forms != 4:
        return rs(ink(s.reshape(-1, 5).mean(axis=1)))
    per = s.reshape(-1, len(_probes(lay)))
    for val, second, sure in _classify(per[:, :len(PROBES_C)].mean(axis=1), per[:, len(PROBES_C):].mean(axis=1),
                                       bright, lay):
        # as read; then the least sure cells take their second choice, more and more of them (Reed-Solomon checks
        # each – cheap, and it fixes what the code alone can't: several doubtful cells in a byte)
        order = np.argsort(sure)
        for m in CHASE:
            v = val.copy()
            v[order[:m]] = second[order[:m]]
            out = rs([b for x in v for b in ((int(x) >> 1) & 1, int(x) & 1)])
            if out is not None:
                LAST["cells"] = [int(x) for x in v]   # what each cell was read as (the test bench counts mix-ups)
                return out
    return None


CHASE = (0, 1, 2, 3, 4, 6, 8, 10, 12)   # how many of the least sure cells try their second choice


LAST = {}   # the last successful read: "cells" = the cell values as read (4 forms)


STEPS = (0.0, -0.35, 0.35, -0.7, 0.7)   # nudges of the bar ends along the bar (module units) when reading fails


def _inv(H):
    m = np.array(H, np.float64).reshape(3, 3)
    try:
        return np.linalg.inv(m)
    except np.linalg.LinAlgError:
        return None


def _rails_fix(H, lay, others, p):
    """"rails" frame: where the two side lines really are (the bar ends only give the sides roughly – a few tenths
    of a module off under blur, and 4 forms feel a cell above and below its centre, so that matters). others: the
    other long thin blobs. -> (a, b): model x as seen = a · x + b, or None (no side line found)."""
    Hi = _inv(H)
    if Hi is None:
        return None
    want = {-lay.side: None, lay.cols + lay.side: None}
    mid = (lay.top + lay.bottom) / 2
    for b in others:
        if abs(b["ax"] * p["ax"] + b["ay"] * p["ay"]) > 0.5:   # a side line runs across the bars
            continue
        u = Hi @ np.array([b["cx"], b["cy"], 1.0])
        if abs(u[2]) < 1e-9:
            continue
        mx, my = u[0] / u[2], u[1] / u[2]
        if abs(my - mid) > 1.0:
            continue
        for x in want:
            if abs(mx - x) < 0.9 and (want[x] is None or abs(mx - x) < abs(want[x] - x)):
                want[x] = mx
    (xl, ml), (xr, mr) = sorted(want.items())
    if ml is not None and mr is not None:
        a = (mr - ml) / (xr - xl)
        return a, ml - a * xl
    if ml is not None or mr is not None:
        return 1.0, (ml - xl) if ml is not None else (mr - xr)
    return None


def _try_pair(g, p, q, pe, qe, lay, pts, bright, others=()):
    """Four orientations, then nudged bar ends -> payload or None."""
    model = [(lay.x0 - lay.bar, lay.top), (lay.x1 + lay.bar, lay.top),
             (lay.x0 - lay.bar, lay.bottom), (lay.x1 + lay.bar, lay.bottom)]
    # order q's ends along p's direction
    if (qe[1][0] - qe[0][0]) * p["ax"] + (qe[1][1] - qe[0][1]) * p["ay"] < 0:
        qe = (qe[1], qe[0])
    hyps = []
    for top, bot in ((pe, qe), (qe, pe)):
        hyps.append((top[0], top[1], bot[0], bot[1]))
        hyps.append((top[1], top[0], bot[1], bot[0]))
    L = (p["len"] + q["len"]) / 2 / (lay.x1 - lay.x0 + 2 * lay.bar)   # pixels per module along the bars

    def attempt(c):
        H = homography(model, c)
        if H is None:
            return None
        if lay.frame == "rails" and others:
            fix = _rails_fix(H, lay, others, p)
            if fix is not None:
                moved = pts.copy()
                moved[:, 0] = fix[0] * pts[:, 0] + fix[1]
                r = _read(g, H, lay, moved, bright)
                if r is not None:
                    return r
        return _read(g, H, lay, pts, bright)
    for c in hyps:
        r = attempt(c)
        if r is not None:
            return r
    for c in hyps:
        dirs = []
        for a, b in ((0, 1), (1, 0), (2, 3), (3, 2)):   # unit vector pointing outwards at each end
            dx, dy = c[a][0] - c[b][0], c[a][1] - c[b][1]
            n = (dx * dx + dy * dy) ** 0.5 or 1
            dirs.append((dx / n, dy / n))
        for s0 in STEPS:
            for s1 in STEPS:
                for s2 in STEPS:
                    for s3 in STEPS:
                        if not (s0 or s1 or s2 or s3):
                            continue
                        if sum(1 for s in (s0, s1, s2, s3) if s) > 2:
                            continue
                        cc = [(c[k][0] + dirs[k][0] * s * L, c[k][1] + dirs[k][1] * s * L)
                              for k, s in enumerate((s0, s1, s2, s3))]
                        r = attempt(cc)
                        if r is not None:
                            return r
    return None


def decode(gray, keys=None):
    """Grayscale picture (numpy, any size) -> (layout key, payload bytes) or None. keys: layouts to try
    (default: all, the standard one first)."""
    g0 = _shrink(np.asarray(gray))
    g = _smooth(g0)   # finding the frame, reading dots – 4 forms are felt on g0 (a cell is only a few pixels)
    mean = _local_mean(g)
    for bright in (True, False):
        m = (g > mean + 6) if bright else (g < mean - 6)
        lab, n = _components(m)
        blobs, ys, xs, ls = _blobs(lab, n)
        bars = _bars(blobs)
        if len(bars) < 2:
            continue
        ends = {b["id"]: _ends(b, ys, xs, ls) for b in bars}
        for key in (keys or [DEFAULT] + [k for k in LAYOUTS if k != DEFAULT]):
            lay = LAYOUTS[key]
            pts = _sample_points(lay)
            for p, q in _pairs(bars, lay):
                others = [b for b in bars if b["id"] not in (p["id"], q["id"])]
                r = _try_pair((g0, g) if lay.forms == 4 else g, p, q, ends[p["id"]], ends[q["id"]], lay, pts, bright,
                              others)
                if r is not None:
                    return key, r
    return None
