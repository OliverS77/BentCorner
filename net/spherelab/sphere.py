"""The pairing sphere's READER in the app (taken over 1:1 from labs/webapp/stripcode/sphere.py – the reader its test
bench was built and tuned with; only the import changed). The PC reads the phone's sphere with the webcam
(net/sync_cam.py). Drawing for the desktop: ui/sphere.py.

Labs text: Feasibility probe "Kugel A1" (Oliver 2026-10-29): the pairing code as a punched band wound four times round a
turning sphere – only a camera watching it turn reads it; a screenshot shows the front half only.

The band is a 1 × 72 strip of the 4-form cells (gap · hole · ring · bar, 2 bits each = 8 + 10 bytes, like f5), equal
neighbours along it melt into one shape. Along one edge a row of small feed holes (one per cell, like real punched
tape) – data-independent, so the reader finds the turning angle from them and from the band's two edges. The 4 cells
of a byte sit a quarter turn apart round the sphere: no view of the front ever shows a whole byte.

Synthetic test: the turning sphere is drawn on a "monitor" frame by frame and photographed by a "phone" (tilt, blur,
noise, JPEG, screen moiré, shake); the reader collects the cells over the frames until Reed-Solomon accepts.

    python sphere.py [--n 10] [--only name] [--fps 30] [--period 4]
"""
import sys

import cv2
import numpy as np

from net.spherelab import stripcode as sc
from collection import rscode

TURNS = 4
TH0, TH1 = 0.1, 0.9          # the band runs from 0.1 π to 0.9 π (pole to pole, the caps left free)
TILT = 0.35                  # axis tipped towards the camera (rad): both poles a little visible
N = 72                       # cells
BW = 1.5                     # band width in cell lengths: feed holes | data | edges
V_DATA, V_FEED = 0.12, -0.5  # across the band (cell units, 0 = centre line): data row, feed holes
EDGE = 0.72                  # the band's two edge lines at ±EDGE
# feed holes: all (FEED_CODE False, the look so far) or a fixed pattern with gaps – then only one angle puts the holes
# on holes and the gaps on paper (uniform holes fit several angles of the spiral almost as well)
FEED_CODE = __import__("os").environ.get("SPHERE_FEED_CODE") == "1"
FEED = (np.random.default_rng(1729).random(N) < 0.5) if FEED_CODE else np.ones(N, bool)
LAY = sc.Layout("s1", N, 1, 8, 10, dot=0.34, forms=4, ring=0.36, neck=0.2, rneck=0.25, rt=0.18, band=0.13,
                probe=0.28)

# ---------- the band on the sphere ----------
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
LENGTH = S_TAB[-1]           # band length (sphere radius = 1)
PITCH = LENGTH / N           # one cell along the band


def slot_order():
    """Which band slot carries data cell j: the 4 cells of byte b go to slots a quarter turn apart (by the slot's
    longitude) – a front view never holds a whole byte."""
    s = (np.arange(N) + 0.5) * PITCH
    t = np.interp(s, S_TAB, T_TAB)
    ph = (_spiral(t)[1] % (2 * np.pi))
    quad = (ph // (np.pi / 2)).astype(int)
    pools = [list(np.nonzero(quad == q)[0]) for q in range(4)]
    order = [0] * N
    for b in range(N // 4):
        for k in range(4):
            q = max(range(4), key=lambda q: len(pools[(k + q) % 4]))   # (pools aren't exactly 18 each)
            q = (k + q) % 4 if not pools[k % 4] else k % 4
            order[b * 4 + k] = pools[q].pop(0)
    return order


ORDER = slot_order()


def strip_values(payload):
    """payload -> the 72 band slots' values (KINDS), data cells moved to their slots."""
    cells = sc.cells(payload, "f5")   # the same bits as the flat ticket code (8 + 10 bytes, mask)
    out = [0] * N
    for j, slot in enumerate(ORDER):
        out[slot] = cells[j]
    return out


def texture(payload, S=48):
    """The band as a flat picture: N·S × BW·2·S, ink = 1 (data shapes melted along the band, feed holes, edges)."""
    vals = strip_values(payload)
    shp = sc._runs(LAY, vals)    # 1 row: y = 0.5 is its centre line
    feed = [[i + 0.5, 0.5 + V_FEED - V_DATA, i + 0.5, 0.5 + V_FEED - V_DATA, 0.09, 0] for i in range(N) if FEED[i]]
    edges = [[0, 0.5 - EDGE - V_DATA, N, 0.5 - EDGE - V_DATA, 0.04, 0],
             [0, 0.5 + EDGE - V_DATA, N, 0.5 + EDGE - V_DATA, 0.04, 0]]
    H, W = int(2 * BW * S), N * S
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    u = (xs + 0.5) / S
    v = (ys + 0.5) / S - BW + 0.5 - V_DATA   # strip y of the shapes (their row centre at 0.5)
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
    """sphere (local) -> view: turn about the axis, then tip the axis towards the camera."""
    c, s = np.cos(rot), np.sin(rot)
    Ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    ct, st = np.cos(TILT), np.sin(TILT)
    Rx = np.array([[1, 0, 0], [0, ct, -st], [0, st, ct]])
    return Rx @ Ry


def band_point(u, v, rot):
    """Band coordinates (u along in cells from the start, v across in cells) -> 3D point in view (unit sphere)."""
    s = np.asarray(u, np.float64) * PITCH
    t = np.interp(s, S_TAB, T_TAB)
    th, ph = _spiral(t)
    # across: perpendicular to the spiral on the sphere, mostly along θ (the spiral runs mostly round)
    dth, dph = 1.0, _K
    nrm = np.sqrt(dth ** 2 + (np.sin(th) * dph) ** 2)
    th2 = th + np.asarray(v, np.float64) * PITCH * (np.sin(th) * dph / nrm)
    ph2 = ph - np.asarray(v, np.float64) * PITCH * (dth / nrm) / np.maximum(np.sin(th), 0.2)
    p = np.stack([np.sin(th2) * np.cos(ph2), np.cos(th2), np.sin(th2) * np.sin(ph2)], axis=-1)
    return p @ _rot(rot).T


def band_coords(q):
    """Sphere-local points (unit vectors) -> band coordinates (u along, v across, in cells; the inverse of
    band_point to first order) and whether a winding is near at all."""
    th = np.arccos(np.clip(q[..., 1], -1, 1))
    ph = np.arctan2(q[..., 2], q[..., 0])
    # nearest winding: where the spiral passes this longitude
    t_th = (th / np.pi - TH0) / (TH1 - TH0)
    n = np.round(t_th * TURNS - ph / (2 * np.pi))
    t = (ph / (2 * np.pi) + n) / TURNS
    ok = (t >= 0) & (t <= 1)
    tc = np.clip(t, 0, 1)
    ths, _ = _spiral(tc)
    s = np.interp(tc, T_TAB, S_TAB)
    sk = np.sin(ths) * _K
    nrm = np.sqrt(1 + sk ** 2)
    d = th - ths                 # straight down/up from the band's centre line at this longitude, split into
    v = d * sk / nrm / PITCH     # across the band …
    u = (s + d / nrm) / PITCH    # … and a little along it
    return u, v, ok


def render(tex, rot, size=640, radius=270, fg=230, bg=24):
    """The monitor: the sphere's front at turning angle rot (texture-mapped band), a faint outline."""
    S = tex.shape[1] / N
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    x, y = (xs + 0.5 - size / 2) / radius, -(ys + 0.5 - size / 2) / radius
    r2 = x * x + y * y
    front = r2 < 1
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    p = np.stack([x, y, z], axis=-1)[front]
    u, v, ok = band_coords(p @ _rot(rot))   # (row vectors: p @ R = R^T p, back to sphere coordinates)
    tx = np.clip(u * S, 0, tex.shape[1] - 1.001)
    ty = (v + BW) * S            # texture row of band v (texture() puts band v = 0 at row BW·S)
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
    # the outline in ink, a little outside the sphere (the reader measures it to the pixel)
    cv2.circle(img, (size // 2, size // 2), int(round(radius * 1.03)), fg, max(2, int(round(radius * 0.012))),
               cv2.LINE_AA)
    return img.clip(0, 255).astype(np.uint8)


# ---------- the phone ----------
BASE = dict(width=300, tilt=0.05, blur=0.7, gain=0.8, noise=3, jpeg=80, moire=0.85, shake=2.0)
SETS = {
    "clean": dict(blur=0.4, noise=1, jpeg=95, moire=False, shake=0),
    "phone": {},
    "small 200": dict(width=200),
    "small 150": dict(width=150),
    "blur 1.5": dict(blur=1.5),
    "tilt 25": dict(angles=(25, 25, 10)),   # phone turned/tipped up to 25°, rolled up to 10° (camera model)
    "dim": dict(gain=0.35, noise=5),
    "shaky": dict(shake=6.0, blur=1.0),
    # stress test, the old way (until 02.11): corners jittered ±20 % anew in EVERY frame – shears no lens makes, up to
    # 38° roll between two frames. Not the goal (no hand does that), but it must never read wrong (lead 02.11.)
    "stress old": dict(tilt=0.2, perframe=True),
    "phone mix": dict(width=200, angles=(20, 20, 8), blur=1.1, gain=0.45, noise=4, jpeg=55, moire=0.75, shake=4.0),
}


def photo(rng, screen, p, FW=640, FH=480):
    """The monitor photographed: sphere width p.width px in the frame, perspective, shake, blur, light, noise, JPEG."""
    scr = screen.astype(np.float32)
    if p["moire"]:
        grid = np.ones_like(scr)
        grid[:, 2::3] *= p["moire"]
        grid[2::3, :] *= (1 + p["moire"]) / 2
        scr = scr * grid
    sh, sw = scr.shape
    s = p["width"] / sw
    src = np.float32([[0, 0], [sw, 0], [sw, sh], [0, sh]])
    dst = (src - [sw / 2, sh / 2]) * s
    # the phone's slant: fixed for one video (p["_pose"], drawn once per reading) + a little hand tremor per frame –
    # until 02.11 it was drawn anew for every frame (up to 38° roll between two frames, no hand does that)
    pose = p.get("_pose")
    if pose is None:
        pose = rng.uniform(-p.get("tilt", 0), p.get("tilt", 0), dst.shape)
    tremor = rng.normal(0, 0.004, dst.shape)
    dst += ((pose + tremor) * p["width"] * p.get("_tiltfix", 1)).astype(np.float32)
    dst += [FW / 2 + rng.normal(0, p["shake"]), FH / 2 + rng.normal(0, p["shake"])]
    M = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    if p.get("angles"):
        # a real camera turned against the screen (02.11 – the corner jitter above made shears no lens makes at large
        # slants): yaw/pitch/roll of the phone (fixed per video, "_angles"), ~70° field of view; the homography of a
        # camera turning about its centre is K·R·K^-1 (the screen stays put)
        ang = p.get("_angles")
        if ang is None:
            ang = [rng.uniform(-a, a) for a in p["angles"]]
        ang = np.radians(np.asarray(ang, float) + rng.normal(0, 0.15, 3))   # + a little tremor
        f = FW / 2 / np.tan(np.radians(35))
        K = np.array([[f, 0, FW / 2], [0, f, FH / 2], [0, 0, 1]])
        cy_, sy_ = np.cos(ang[0]), np.sin(ang[0])
        cx_, sx_ = np.cos(ang[1]), np.sin(ang[1])
        cz_, sz_ = np.cos(ang[2]), np.sin(ang[2])
        R = (np.array([[cy_, 0, sy_], [0, 1, 0], [-sy_, 0, cy_]]) @ np.array([[1, 0, 0], [0, cx_, -sx_], [0, sx_, cx_]])
             @ np.array([[cz_, -sz_, 0], [sz_, cz_, 0], [0, 0, 1]]))
        M = K @ R @ np.linalg.inv(K) @ M
        c = M @ [sw / 2, sh / 2, 1]                       # the user aims the phone at the sphere: centre it again
        tx, ty = FW / 2 + rng.normal(0, p["shake"]) - c[0] / c[2], FH / 2 + rng.normal(0, p["shake"]) - c[1] / c[2]
        M = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]]) @ M
    img = cv2.warpPerspective(scr, M, (FW, FH), flags=cv2.INTER_AREA, borderValue=40)
    if p["blur"] > 0:
        img = cv2.GaussianBlur(img, (0, 0), p["blur"])
    img = 90 + (img - 128) * p["gain"]
    img += rng.normal(0, p["noise"], img.shape)
    img = img.clip(0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, p["jpeg"]])
    return cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE), M


# ---------- reading ----------
OUTLINE = 1.03   # the outline's radius / the sphere's


def find_sphere(g, bright=None):
    """-> (cx, cy, radius) of the sphere (not its outline), or None. Hough finds it roughly; then along 180 rays the
    outermost ink line near that circle, and a circle fitted to those points (least squares)."""
    b = cv2.GaussianBlur(g, (0, 0), 1.5)
    c = cv2.HoughCircles(b, cv2.HOUGH_GRADIENT, dp=1.5, minDist=200, param1=60, param2=30, minRadius=40,
                         maxRadius=int(min(g.shape) * 0.55))
    if c is None:
        return None
    cx, cy, r = (float(v) for v in c[0][0])
    gf = b.astype(np.float64)
    ang = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    # wide: Hough often locks onto an inner winding (up to 20 % too small)
    rad = np.linspace(0.85 * r, 1.4 * r, 140)
    step = rad[1] - rad[0]
    xs = cx + np.cos(ang)[:, None] * rad[None, :]
    ys = cy + np.sin(ang)[:, None] * rad[None, :]
    prof = _bilinear(gf, xs, ys)
    if bright is None:   # ink = whichever way the outline stands out from the paper around it
        bright = np.nanmean(prof) > np.nanmedian(prof)   # ink is the minority: the mean leans its way
    ink = prof if bright else -prof
    thin, after = max(2, int(0.06 * r / step)), max(3, int(0.05 * r / step))
    pts = []
    for i in range(len(ang)):
        row = ink[i]
        if np.isnan(row).all():
            continue
        thr = np.nanmin(row) + 0.5 * (np.nanmax(row) - np.nanmin(row))
        on = np.nan_to_num(row, nan=-1e9) > thr
        # runs of ink, outermost first: the outline is thin and has paper right outside it (the screen's border in
        # the light look is ink too, but nothing but border follows it)
        j = len(on) - 1
        while j >= 0:
            if not on[j]:
                j -= 1
                continue
            k = j
            while k > 0 and on[k - 1]:
                k -= 1
            if j - k + 1 <= thin and j + after < len(on) and not on[j + 1:j + 1 + after].any():
                rr = (rad[k] + rad[j]) / 2
                pts.append((cx + np.cos(ang[i]) * rr, cy + np.sin(ang[i]) * rr))
                break
            j = k - 1
    if len(pts) < 40:
        return geo(cx, cy, r / OUTLINE)
    P = np.array(pts, np.float32)
    for _ in range(2):   # fit, drop the worst tenth (a band edge touching the outline), fit again
        (x0, y0), (w, h), ang = cv2.fitEllipse(P)
        if not all(np.isfinite([x0, y0, w, h])) or min(w, h) < 20:
            return None
        G = geo(x0, y0, 1.0, w / 2, h / 2, ang)
        q = np.linalg.solve(G[2], (P - [x0, y0]).T)        # back onto the unit circle
        err = np.abs(np.hypot(*q) - 1)
        P = P[err <= np.percentile(err, 90)]
    (x0, y0), (w, h), ang = cv2.fitEllipse(P)
    if not all(np.isfinite([x0, y0, w, h])) or min(w, h) < 0.7 * max(w, h) or min(w, h) < 20:
        return None   # degenerate (too few or scattered outline points): not this frame
    return geo(x0, y0, 1 / OUTLINE, w / 2, h / 2, ang)


def geo(cx, cy, k, a=1.0, b=None, ang=0.0):
    """The sphere in the photo: centre + a 2×2 map from the sphere's (x right, y down) to pixels. A circle of radius
    k (a, b unset) or an ellipse with half axes a, b turned by ang degrees (cv2.fitEllipse), scaled by k – a monitor
    photographed at a slant shows the sphere as an ellipse."""
    if b is None:
        return float(cx), float(cy), np.eye(2) * k
    t = np.radians(ang)
    R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    return float(cx), float(cy), R @ np.diag([a * k, b * k]) @ R.T   # stretch along the axes, never turn


def shifted(G, dx, dy):
    return (G[0] + dx, G[1] + dy) + tuple(G[2:])


def posed(G, pose):
    """The same geometry with the phone's pose (roll in rad, perspective px, py) – see _to_image."""
    return (G[0], G[1], G[2], tuple(pose))


def _to_image(p3, G):
    """Sphere point (x right, y up, unit radius) -> pixel. G = (cx, cy, A[, (roll, px, py)]): the phone's roll about
    its view axis, then a perspective (a screen photographed at a slant: x/(1 + px·x + py·y)), then the 2×2 map A (the
    outline's ellipse) and the centre."""
    cx, cy, A = G[0], G[1], G[2]
    x, y = p3[..., 0], -p3[..., 1]
    if len(G) > 3 and G[3] is not None:
        roll, px, py = G[3][:3]
        exact = G[3][3] if len(G[3]) > 3 else EXACT_OUTLINE
        if roll:
            c, s_ = np.cos(roll), np.sin(roll)
            x, y = c * x - s_ * y, s_ * x + c * y
        if px or py:
            w = 1 + px * x + py * y
            x, y = x / w, y / w
            if exact:   # the slanted circle is another ellipse: put IT onto the outline (not the unit circle)
                ex, ey, S = _persp_outline(px, py)
                x, y = x - ex, y - ey
                x, y = S[0, 0] * x + S[0, 1] * y, S[1, 0] * x + S[1, 1] * y
    return cx + A[0, 0] * x + A[0, 1] * y, cy + A[1, 0] * x + A[1, 1] * y


EXACT_OUTLINE = __import__("os").environ.get("SPHERE_EXACT_OUTLINE", "1") == "1"
# fit_video with EXACT_OUTLINE: "both" fits the plain model (centre shift, no exact outline) too and keeps the better
# fit – the exact outline wins at strong slants, the shift on phone photos and small spheres (bench50v6)
BOTH_MODELS = __import__("os").environ.get("SPHERE_BOTH", "1") == "1"
PERSP_GRID = (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3)   # fit_video's start grid for px, py (with EXACT_OUTLINE)
CAND_PERSP_ON = __import__("os").environ.get("SPHERE_CAND_PERSP", "0") == "1"   # candidates under several slants
CAND_PERSP = ((0.0, 0.0), (0.15, 0.0), (-0.15, 0.0), (0.0, 0.15), (0.0, -0.15),
              (0.15, 0.15), (0.15, -0.15), (-0.15, 0.15), (-0.15, -0.15))
CAND_MAX = int(__import__("os").environ.get("SLIM_CAND", "10"))   # starts handed to fit_video (best scores first)
SAMPLE = int(__import__("os").environ.get("SLIM_SAMPLE", "24"))   # frames used by candidates and fit_video
CAND_STEP = float(__import__("os").environ.get("SLIM_CSTEP", "1.0"))   # degrees between candidate angles
_PERSP = {}


def _persp_outline(px, py):
    """The unit circle under v = u / (1 + q·u) is the ellipse vᵀ(I − qqᵀ)v + 2qᵀv − 1 = 0: centre e = −(I − qqᵀ)^-1q,
    (v − e)ᵀ (I − qqᵀ)/k (v − e) = 1 with k = 1 + qᵀ(I − qqᵀ)^-1q. -> (ex, ey, S) with S = ((I − qqᵀ)/k)^½: S·(v − e)
    lies on the unit circle again – the outline's map A then puts it exactly onto the outline found in the photo (a
    homography that keeps the outline, three free values: roll, px, py)."""
    key = (round(float(px), 6), round(float(py), 6))
    r = _PERSP.get(key)
    if r is None:
        q = np.array(key)
        M = np.eye(2) - np.outer(q, q)
        Mi = np.linalg.inv(M)
        e = -Mi @ q
        k = 1 + q @ Mi @ q
        w, V = np.linalg.eigh(M / k)
        S = V @ np.diag(np.sqrt(np.maximum(w, 1e-12))) @ V.T
        r = (float(e[0]), float(e[1]), S)
        if len(_PERSP) > 50000:
            _PERSP.clear()
        _PERSP[key] = r
    return r


def _bilinear(g, x, y):
    h, w = g.shape
    ok = np.isfinite(x) & np.isfinite(y) & (x >= 0) & (y >= 0) & (x < w - 1) & (y < h - 1)
    x, y = np.clip(np.nan_to_num(x), 0, w - 1.001), np.clip(np.nan_to_num(y), 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = x - x0, y - y0
    v = (g[y0, x0] * (1 - fx) + g[y0, x0 + 1] * fx) * (1 - fy) + (g[y0 + 1, x0] * (1 - fx) + g[y0 + 1, x0 + 1] * fx) * fy
    return np.where(ok, v, np.nan)


# data-independent marks: feed holes (one per cell) and the two edges, in band coordinates
_FI = np.nonzero(FEED)[0]
_FO = np.nonzero(~FEED)[0]
_MU = np.concatenate([_FI + 0.5, np.arange(0, N, 0.5), np.arange(0, N, 0.5)])
_MV = np.concatenate([np.full(len(_FI), V_FEED), np.full(2 * N, -EDGE), np.full(2 * N, EDGE)])
# … and places that are always paper: between the feed holes, beside the edges
_PU = np.concatenate([np.arange(N) + 0.0, _FO + 0.5, np.arange(0, N, 0.5), np.arange(0, N, 0.5)])
_PV = np.concatenate([np.full(N, V_FEED), np.full(len(_FO), V_FEED), np.full(2 * N, -EDGE - 0.25),
                      np.full(2 * N, EDGE + 0.25)])


_MARKS = {}
HOLE_WEIGHT = float(__import__("os").environ.get("SPHERE_HOLE_WEIGHT", "3"))   # holes pin the angle


def _marks(rot):
    """The data-independent marks at an angle – feed holes and edges apart (the edges are continuous spirals: turning
    looks like moving up or down, only the holes pin the angle) – each with its paper neighbours, the visible ones."""
    key = round(float(rot) % (2 * np.pi), 5)
    m = _MARKS.get(key)
    if m is None:
        nh, nhp = len(_FI), N + len(_FO)
        pm, pp = band_point(_MU, _MV, rot), band_point(_PU, _PV, rot)
        vm, vp = pm[:, 2] > 0.35, pp[:, 2] > 0.35
        hole_m, hole_p = np.arange(len(_MU)) < nh, np.arange(len(_PU)) < nhp
        m = (pm[vm & hole_m], pp[vp & hole_p], pm[vm & ~hole_m], pp[vp & ~hole_p])
        if len(_MARKS) > 20000:
            _MARKS.clear()
        _MARKS[key] = m
    return m


def _score(g, circ, rot, bright):
    hm, hp, em, ep = _marks(rot)
    dh = np.nanmean(_bilinear(g, *_to_image(hm, circ))) - np.nanmean(_bilinear(g, *_to_image(hp, circ)))
    de = np.nanmean(_bilinear(g, *_to_image(em, circ))) - np.nanmean(_bilinear(g, *_to_image(ep, circ)))
    d = (HOLE_WEIGHT * dh + de) / (1 + HOLE_WEIGHT) * 2
    return d if bright else -d


REFINE = True
MAX_SHIFT = 8.0   # px: how far perspective can move the centre off the outline's centre (as a share of 150 px radius)


def refine(g, G, rot, bright, start=(0.0, 0.0)):
    """Perspective moves the sphere's centre off the outline's centre: find the shift (and angle) that puts the
    marks on ink best – never further than MAX_SHIFT·radius/150 from the outline's centre G. start: last frame's
    shift. -> (geometry, angle, score, shift)"""
    gf = g.astype(np.float64)
    lim = MAX_SHIFT * float(np.sqrt(abs(np.linalg.det(G[2])))) / 150
    sx, sy = (float(np.clip(v, -lim, lim)) for v in start)
    best = (_score(gf, shifted(G, sx, sy), rot, bright), sx, sy, rot)
    if not REFINE:
        return shifted(G, sx, sy), rot, best[0], (sx, sy)
    for step in (2.0, 1.0, 0.5):
        _, bx, by, br = best
        n = 3 if step == 2.0 else 2
        for dx in np.clip(bx + np.arange(-n, n + 1) * step, -lim, lim):
            for dy in np.clip(by + np.arange(-n, n + 1) * step, -lim, lim):
                for r in (br - 0.01, br, br + 0.01):
                    sc_ = _score(gf, shifted(G, dx, dy), r, bright)
                    if sc_ > best[0]:
                        best = (sc_, dx, dy, r)
    sc_, dx, dy, r = best
    return shifted(G, dx, dy), r, sc_, (dx, dy)


POSE = True
MAX_ROLL, MAX_PERSP = np.radians(25), 0.35


def refine_pose(g, G, rot, bright, pose=(0.0, 0.0, 0.0), shift=(0.0, 0.0)):
    """The phone's roll and slant (they hardly change during a video – start from the last frame's): coordinate
    descent on the marks' fit, together with the centre shift. -> (geometry, pose, shift, score)"""
    gf = g.astype(np.float64)
    lim = MAX_SHIFT * float(np.sqrt(abs(np.linalg.det(G[2])))) / 150
    cur = [float(pose[0]), float(pose[1]), float(pose[2]), float(shift[0]), float(shift[1])]
    bounds = [MAX_ROLL, MAX_PERSP, MAX_PERSP, lim, lim]

    def fit(v):
        return _score(gf, posed(shifted(G, v[3], v[4]), v[:3]), rot, bright)
    best = fit(cur)
    if not POSE:
        return posed(shifted(G, cur[3], cur[4]), cur[:3]), tuple(cur[:3]), (cur[3], cur[4]), best
    for steps in ((np.radians(2), 0.03, 0.03, 1.0, 1.0), (np.radians(0.7), 0.01, 0.01, 0.5, 0.5)):
        for _ in range(3):
            moved = False
            for i, st in enumerate(steps):
                for d in (-st, st):
                    v = list(cur)
                    v[i] = float(np.clip(v[i] + d, -bounds[i], bounds[i]))
                    sc_ = fit(v)
                    if sc_ > best:
                        best, cur, moved = sc_, v, True
            if not moved:
                break
    return posed(shifted(G, cur[3], cur[4]), cur[:3]), tuple(cur[:3]), (cur[3], cur[4]), best


def find_turn(g, circ, bright, around=None):
    """The turning angle of this frame: where the feed holes and edges sit on ink and their neighbours on paper.
    around: last frame's angle (search only near it) or None (all the way round)."""
    gf = g.astype(np.float64)
    if around is None:
        cand = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    else:
        cand = around + np.linspace(-0.5, 0.5, 101)
    sc_ = [_score(gf, circ, r, bright) for r in cand]
    r = cand[int(np.nanargmax(sc_))]
    for step in (0.01, 0.003):
        fine = r + np.arange(-6, 7) * step
        r = fine[int(np.nanargmax([_score(gf, circ, x, bright) for x in fine]))]
    return r, float(np.nanmax(sc_))


def angle_peaks(g, G, bright, k=4, rel=0.75, apart=np.radians(12)):
    """The marks are data-independent and the band is a spiral: other angles fit them almost as well as the true one
    (measured: 130° off scored higher). -> up to k angles where they fit best (local maxima ≥ rel·best)."""
    gf = g.astype(np.float64)
    cand = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    sc_ = np.array([_score(gf, G, r, bright) for r in cand])
    out = []
    for i in np.argsort(sc_)[::-1]:
        if sc_[i] < rel * sc_.max() or len(out) >= k:
            break
        if all(abs((cand[i] - c + np.pi) % (2 * np.pi) - np.pi) > apart for c in out):
            out.append(cand[i])
    return out


def cell_features(g, circ, rot):
    """Per band slot: (centre, above/below) brightness and how squarely it faces the camera (0 = edge-on)."""
    u = np.arange(N) + 0.5
    cs = []
    for dv in sc.PROBES_C:
        cs.append(band_point(u + dv[0], np.full(N, V_DATA + dv[1]), rot))
    rs_ = []
    for dv in sc._probes(LAY)[len(sc.PROBES_C):]:
        rs_.append(band_point(u + dv[0], np.full(N, V_DATA + dv[1]), rot))
    face = band_point(u, np.full(N, V_DATA), rot)[:, 2]
    gf = g.astype(np.float64)
    c = np.nanmean([_bilinear(gf, *_to_image(p, circ)) for p in cs], axis=0)
    r = np.nanmean([_bilinear(gf, *_to_image(p, circ)) for p in rs_], axis=0)
    return c, r, face


def decode_band(c, r, bright):
    """Collected (centre, above/below) per slot -> payload or None (4-form clustering + Reed-Solomon, as stripcode)."""
    if np.isnan(c).any() or np.isnan(r).any():
        return None
    for val, second, sure in sc._classify(c, r, bright, sc.LAYOUTS["f5"]):   # the same cells as f5
        order = np.argsort(sure)
        for m in sc.CHASE:
            v = val.copy()
            v[order[:m]] = second[order[:m]]
            cells = [int(v[slot]) for slot in ORDER]   # slots back into data order
            bits = [b for x in cells for b in ((x >> 1) & 1, x & 1)]
            raw = [a ^ mm for a, mm in zip(bits, sc.mask(len(bits), sc.LAYOUTS["f5"].seed))]
            block = bytes(sum(raw[i * 8 + k] << (7 - k) for k in range(8)) for i in range(18))
            try:
                return bytes(rscode.decode(block, 10))
            except ValueError:
                continue
    return None


def _best_face():
    """How squarely each slot ever faces the camera over a whole turn (the band reaches near the far pole: some
    slots are only ever seen slanted – they count relative to their best)."""
    u = np.arange(N) + 0.5
    return np.max([band_point(u, np.full(N, V_DATA), r)[:, 2] for r in np.linspace(0, 2 * np.pi, 360)], axis=0)


BEST_FACE = _best_face()


PERIOD = 4.0   # s per turn – the desktop turns the sphere steadily, always the same way


GRID = int(__import__("os").environ.get("SLIM_GRID", "720"))   # turning angles searched (720: 0.5° apart)


def _grid_scores(gf, G, bright):
    """The marks' fit at every grid angle for one frame."""
    return np.array([_score(gf, G, 2 * np.pi * k / GRID, bright) for k in range(GRID)])


class Reader:
    """The sphere turns at a KNOWN speed (the desktop draws it): its angle in frame t is φ + ω·t, so one number φ
    places the band in every frame. Each frame adds the marks' fit of every φ (its own angle grid shifted by ω·t) –
    noise averages out, and the angles that fit by chance (the spiral looks alike at other angles) don't keep fitting.
    The frames are kept; every few frames the best φ's read the cells over all of them, Reed-Solomon decides."""

    def __init__(self, period=PERIOD, every=10, keep=4, acc=False):
        self.omega = 2 * np.pi / period
        self.acc = np.zeros(GRID) if acc else None   # only phi_peaks (the screenshot check) needs it – reading never
        self.frames = []         # (gray float, geometry, t)
        self.bright = None
        self.shift = (0.0, 0.0)
        self.pose = (0.0, 0.0, 0.0)
        self.flow = []           # direction of the motion at the sphere's centre per frame pair (rad) – the phone's roll
        self.prev = None
        self.every, self.keep = every, keep
        self.n = 0
        self.hyp = []            # the φ's tried last (for diagnosis)

    def phi_peaks(self):
        out = []
        for k in np.argsort(self.acc)[::-1]:
            if len(out) >= self.keep:
                break
            if all(min(abs(k - j), GRID - abs(k - j)) > GRID // 72 for j in out):   # ≥ 5° apart
                out.append(int(k))
        res = []
        for k in out:            # parabola through the neighbours: below the grid step
            a, b_, c = self.acc[(k - 1) % GRID], self.acc[k], self.acc[(k + 1) % GRID]
            d = 0.5 * (a - c) / (a - 2 * b_ + c) if (a - 2 * b_ + c) else 0.0
            res.append(2 * np.pi * (k + float(np.clip(d, -0.5, 0.5))) / GRID)
        return res

    def candidates(self, rolls=(-8, -4, 0, 4, 8), top=2, sample=None):
        """(φ, roll) to start fit_video from: the roll from the motion's direction (± a few degrees – it is only that
        accurate), for each a φ scan over a sample of frames at 1° steps (the accumulated φ above assumes no roll)."""
        sample = sample or SAMPLE
        r_flow = float(np.median(self.flow)) if self.flow else 0.0
        pick = self.frames[:: max(1, len(self.frames) // sample)]
        out = []
        slants = CAND_PERSP if (EXACT_OUTLINE and CAND_PERSP_ON) else ((0.0, 0.0),)
        for q in slants:   # a strongly slanted phone moves the band: the φ scan under a few slants
            for dr in rolls:
                roll = r_flow + np.radians(dr)
                if abs(roll) > MAX_ROLL:
                    continue
                cand = np.radians(np.arange(0, 360, CAND_STEP))
                sc_ = np.zeros(len(cand))
                for fg, G, t in pick:
                    Gr = posed(G, (roll, q[0], q[1]))
                    sc_ += [_score(fg, Gr, c + self.omega * t, self.bright) for c in cand]
                for i in np.argsort(sc_)[::-1][:20]:
                    if len([o for o in out if o[2] == (dr, q)]) >= top:
                        break
                    if all(abs((cand[i] - o[0] + np.pi) % (2 * np.pi) - np.pi) > np.radians(5) for o in out if o[2] == (dr, q)):
                        out.append((float(cand[i]), (roll, q[0], q[1]), (dr, q), float(sc_[i])))
        out.sort(key=lambda o: -o[3])
        return [(o[0], o[1]) for o in out[:CAND_MAX]]

    def add(self, g, t):
        self.n += 1
        G = find_sphere(g)
        if G is None:
            return None
        gf = g.astype(np.float64)
        if self.bright is None:   # dark or light theme: the band's ink is the minority inside the sphere
            cx, cy, A = G
            rr = float(np.sqrt(abs(np.linalg.det(A))))
            ys, xs = np.mgrid[0:g.shape[0], 0:g.shape[1]]
            vals = g[(xs - cx) ** 2 + (ys - cy) ** 2 < (rr * 0.8) ** 2]
            self.bright = float(np.percentile(vals, 50)) < float(np.mean([np.percentile(vals, 5), np.percentile(vals, 95)]))
        # the plain outline ellipse per frame; the phone's pose (roll, slant, centre shift – the same for the whole
        # video) is fitted once over all frames together with φ before reading (fit_video)
        if self.prev is not None:   # the front moves sideways (+x) as the sphere turns: its direction = the roll
            fl = cv2.calcOpticalFlowFarneback(self.prev, g, None, 0.5, 3, 21, 3, 5, 1.1, 0)
            cx, cy, A = G[0], G[1], G[2]
            rr = float(np.sqrt(abs(np.linalg.det(A))))
            ys, xs = np.mgrid[0:g.shape[0], 0:g.shape[1]]
            m = (xs - cx) ** 2 + (ys - cy) ** 2 < (0.45 * rr) ** 2
            if m.any():
                self.flow.append(float(np.arctan2(np.median(fl[..., 1][m]), np.median(fl[..., 0][m]))))
        self.prev = g
        if self.acc is not None:   # 720 scores per frame (330 ms in Python) – only for the screenshot check
            s = _grid_scores(gf, G, self.bright)
            j = int(round(self.omega * t / (2 * np.pi) * GRID))
            self.acc += np.roll(s, -j)  # acc[k] = fit of φ = grid k, i.e. angle k + j in this frame
        self.frames.append((gf, G, t))
        if self.n % self.every or self.omega * (t - self.frames[0][2]) < 2 * np.pi * 0.9:
            return None              # read only after about a turn, then every few frames
        self.hyp = self.candidates()
        readable = BEST_FACE > 0.2
        for phi0, pose0 in self.hyp:
            phi, pose, shift = fit_video(self.frames, phi0, self.omega, self.bright, pose0, self.shift)
            C, R, W = np.zeros(N), np.zeros(N), np.zeros(N)
            for fg, Gf0, tf in self.frames:
                Gf = posed(shifted(Gf0, *shift), pose)
                c, r, face = cell_features(fg, Gf, phi + self.omega * tf)
                w = np.clip((face - 0.6 * BEST_FACE) / (0.4 * np.maximum(BEST_FACE, 1e-3)), 0, 1) ** 2 * readable
                ok = ~np.isnan(c) & ~np.isnan(r) & (w > 0)
                C[ok] += w[ok] * c[ok]
                R[ok] += w[ok] * r[ok]
                W[ok] += w[ok]
            seen = W > 0
            if not seen.any():
                continue
            c = np.where(seen, C / np.maximum(W, 1e-9), np.nan)
            r = np.where(seen, R / np.maximum(W, 1e-9), np.nan)
            c = np.where(seen, c, np.nanmedian(c))   # never seen: a neutral guess, Reed-Solomon corrects it
            r = np.where(seen, r, np.nanmedian(r))
            out = decode_band(c, r, self.bright)
            if out is not None:
                self.pose, self.shift = pose, shift
                return out
        return None


def fit_video(frames, phi, omega, bright, pose=(0.0, 0.0, 0.0), shift=(0.0, 0.0), sample=None):
    """φ and the phone's pose for the whole video: coordinate descent on the marks' fit summed over a sample of the
    frames (a hand holds the phone nearly still – the pose barely changes, the angle advances at the known speed).
    -> (φ, (roll, px, py, exact), (dx, dy)) – shift in pixels at the first frame's size; exact: the outline model."""
    sample = sample or SAMPLE
    if not EXACT_OUTLINE:
        return _fit_video(frames, phi, omega, bright, pose, shift, sample, False)[1:]
    a = _fit_video(frames, phi, omega, bright, pose, shift, sample, True)
    if not BOTH_MODELS:
        return a[1:]
    b = _fit_video(frames, phi, omega, bright, pose, shift, sample, False)
    return (a if a[0] >= b[0] else b)[1:]


def _fit_video(frames, phi, omega, bright, pose, shift, sample, exact):
    """fit_video for one outline model -> (fit, φ, pose, shift)."""
    pick = frames[:: max(1, len(frames) // sample)]
    lim = MAX_SHIFT * float(np.sqrt(abs(np.linalg.det(pick[0][1][2])))) / 150 * 1.5
    cur = [float(phi), float(pose[0]), float(pose[1]), float(pose[2]), float(shift[0]), float(shift[1])]
    bounds = [None, MAX_ROLL, MAX_PERSP, MAX_PERSP, lim, lim]

    def fit(v):
        return float(np.nanmean([_score(fg, posed(shifted(G, v[4], v[5]), (v[1], v[2], v[3], exact)), v[0] + omega * t,
                                        bright) for fg, G, t in pick]))
    best = fit(cur)
    if exact:
        # the outline is kept exactly: no centre shift left to fit; the slant first on a coarse grid (from 0 the
        # descent stops at a local fit for slants of 15–25°)
        bounds[4] = bounds[5] = 0.0
        cur[4] = cur[5] = 0.0
        best = fit(cur)
        for qx in PERSP_GRID:
            for qy in PERSP_GRID:
                v = list(cur)
                v[2], v[3] = qx, qy
                sc_ = fit(v)
                if sc_ > best:
                    best, cur = sc_, v
    for steps in ((np.radians(3), np.radians(3), 0.05, 0.05, 2.0, 2.0),
                  (np.radians(1), np.radians(1), 0.015, 0.015, 0.7, 0.7),
                  (np.radians(0.3), np.radians(0.3), 0.005, 0.005, 0.3, 0.3)):
        for _ in range(4):
            moved = False
            for i, st in enumerate(steps):
                for d in (-st, st):
                    v = list(cur)
                    v[i] = v[i] + d if bounds[i] is None else float(np.clip(v[i] + d, -bounds[i], bounds[i]))
                    sc_ = fit(v)
                    if sc_ > best:
                        best, cur, moved = sc_, v, True
            if not moved:
                break
    return best, cur[0], (cur[1], cur[2], cur[3], exact), (cur[4], cur[5])


def run(p, rng, fps, period, max_s=12.0):
    """One reading: random code, random start angle, theme. -> seconds until read (or None), frames used."""
    payload = bytes([2]) + bytes(rng.integers(0, 256, 7, dtype=np.uint8).tolist())
    tex = texture(payload)
    dark = rng.random() < 0.5
    fg, bg = (230, 24) if dark else (30, 245)
    rot0 = rng.uniform(0, 2 * np.pi)
    if not p.get("perframe"):   # one phone pose per video (the stress set draws a new one every frame)
        p = dict(p, _pose=rng.uniform(-p.get("tilt", 0), p.get("tilt", 0), (4, 2)))
    if p.get("angles"):
        p["_angles"] = [rng.uniform(-a, a) for a in p["angles"]]
    rd = Reader(period)
    t = 0.0
    while t < max_s:
        screen = render(tex, rot0 + 2 * np.pi * t / period, fg=fg, bg=bg)
        img, _ = photo(rng, screen, p)
        out = rd.add(img, t)
        if out is not None:
            return (t if out == payload else -1), rd.n
        t += 1 / fps
    return None, rd.n


def single_frame(p, rng):
    """A screenshot: everything one frame shows -> does it read? (it must not) – read at its own best angles, the
    hidden slots guessed as gaps."""
    payload = bytes([2]) + bytes(rng.integers(0, 256, 7, dtype=np.uint8).tolist())
    tex = texture(payload)
    screen = render(tex, rng.uniform(0, 2 * np.pi))
    rd = Reader(acc=True)
    img, _ = photo(rng, screen, dict(SETS["clean"], **{k: v for k, v in BASE.items() if k not in SETS["clean"]}))
    rd.add(img, 0.0)
    if not rd.frames:
        return False, 0, 0
    fg, G, _t = rd.frames[0]
    hit, most, whole = False, 0, 0
    for phi in rd.phi_peaks():
        c, r, face = cell_features(fg, G, phi)
        seen = ~np.isnan(c) & ~np.isnan(r) & (face > 0.3)
        if not seen.any():
            continue
        c = np.where(seen, c, np.nanmin(c[seen]) if rd.bright else np.nanmax(c[seen]))
        r = np.where(seen, r, np.nanmin(r[seen]) if rd.bright else np.nanmax(r[seen]))
        hit |= decode_band(c, r, rd.bright) == payload
        most = max(most, int(seen.sum()))
        whole = max(whole, sum(all(seen[ORDER[b * 4 + k]] for k in range(4)) for b in range(18)))
    return hit, most, whole


def main():
    args = sys.argv[1:]
    n = int(args[args.index("--n") + 1]) if "--n" in args else 10
    only = args[args.index("--only") + 1] if "--only" in args else None
    fps = float(args[args.index("--fps") + 1]) if "--fps" in args else 30.0
    period = float(args[args.index("--period") + 1]) if "--period" in args else 4.0
    rng = np.random.default_rng(7)
    print(f"band: {N} cells, length {LENGTH:.2f} radii, cell {PITCH:.3f} radii; turn {period:.1f} s at {fps:.0f} fps")
    for name, ov in SETS.items():
        if only and name != only:
            continue
        p = dict(BASE, **ov)
        res = [run(p, rng, fps, period) for _ in range(n)]
        ok = [t for t, _f in res if t is not None and t >= 0]
        wrong = sum(1 for t, _f in res if t is not None and t < 0)
        frames = [f for t, f in res if t is not None and t >= 0]
        med = f"median {np.median(ok):.2f} s ({np.median(frames):.0f} frames), max {max(ok):.2f} s" if ok else "-"
        print(f"{name:11} read {len(ok)}/{n}  wrong {wrong}  {med}", flush=True)
    shots = [single_frame(dict(BASE), rng) for _ in range(n)]
    print(f"screenshot: read {sum(s[0] for s in shots)}/{n}, slots in view {np.mean([s[1] for s in shots]):.0f}/{N}, "
          f"whole bytes in view {np.mean([s[2] for s in shots]):.1f}/18 (max {max(s[2] for s in shots)})")


if __name__ == "__main__":
    main()
