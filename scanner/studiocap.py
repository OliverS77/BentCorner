"""Scan studio: find the card in the camera frame (or in a file), straighten it, round the corners – and tell how good
the shot is. Image processing only (OpenCV), no UI; used by qstudio.py.

find_quad(img)        -> 4 corners (top left, top right, bottom right, bottom left) in image pixels or None
warp(img, corners)    -> card upright, the game's aspect ratio, as large as in the image (at most MAX_H tall)
rounded(card)         -> BGRA with rounded (transparent) corners – the way the card really looks
quality(img, corners) -> {"found", "sharp", "glare", "light", "size", "ok"} each 0..1 (+ text for the indicator lights)
best(frames)          -> (image, corners) of the sharpest shot out of several camera frames
"""
import cv2
import numpy as np

MAX_H = 2400        # larger gains nothing (scanner at 600 dpi: ~2100)
MIN_GOOD_H = 1000   # from here on the shot is large enough for the databases
SHARP_GOOD = 120.0  # variance of the Laplacian filter (at 700 px height) – above this it is sharp
GLARE_BAD = 0.012   # share of almost white pixels – above this something reflects


def _aspect():
    from scanner import common   # the game's card format (Magic/Pokémon 63 × 88, Yu-Gi-Oh! 59 × 86)
    return common.H / common.W


def _order(pts):
    """Order corners: top left, top right, bottom right, bottom left – long side vertical (portrait)."""
    pts = np.asarray(pts, np.float32).reshape(4, 2)
    c = pts.mean(0)
    pts = np.array(sorted(pts, key=lambda p: np.arctan2(p[1] - c[1], p[0] - c[0])), np.float32)
    # starts at the corner with the smallest angle (top left for an upright card)
    i = int(np.argmin(pts.sum(1)))
    pts = np.roll(pts, -i, axis=0)
    d01, d12 = np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[1] - pts[2])
    if d01 > d12:   # card lying sideways: short edge to the top
        pts = np.roll(pts, -1, axis=0)
    return pts


def find_quad(img):
    """Find the largest card-shaped outline (may be tilted and slightly in perspective)."""
    if img is None or not img.size:
        return None
    h, w = img.shape[:2]
    scale = 800 / max(h, w)
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img
    scale = min(scale, 1.0)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    cnts = []
    # two sensitivities: a black card border on a dark surface barely stands out – then only the fine level finds the
    # outer edge (otherwise you get the inner frame); the largest matching outline wins
    for lo, hi in ((30, 90), (8, 30)):
        edges = cv2.Canny(gray, lo, hi)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        cnts += list(cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0])
    area_img = small.shape[0] * small.shape[1]
    want = _aspect()
    best, best_score = None, 0.0
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 0.04 * area_img:
            continue
        hull = cv2.convexHull(c)
        peri = cv2.arcLength(hull, True)
        quad = cv2.approxPolyDP(hull, 0.02 * peri, True)
        if len(quad) != 4:
            (cx, cy), (rw, rh), ang = cv2.minAreaRect(hull)
            if cv2.contourArea(hull) < 0.9 * rw * rh:
                continue
            quad = cv2.boxPoints(((cx, cy), (rw, rh), ang))
        q = _order(quad)
        sw = (np.linalg.norm(q[0] - q[1]) + np.linalg.norm(q[3] - q[2])) / 2
        sh = (np.linalg.norm(q[1] - q[2]) + np.linalg.norm(q[0] - q[3])) / 2
        if sw < 1:
            continue
        ratio = sh / sw
        if not (want * 0.85 <= ratio <= want * 1.15):
            continue
        if cv2.contourArea(q) > 0.97 * area_img:
            continue   # image border, not a card
        score = cv2.contourArea(q) * (1 - 0.5 * abs(ratio - want) / want)
        if score > best_score:
            best, best_score = q, score
    if best is None:
        return None
    return best / scale


def size_of(quad):
    """Height of the card in the image (pixels)."""
    q = np.asarray(quad, np.float32)
    return float((np.linalg.norm(q[1] - q[2]) + np.linalg.norm(q[0] - q[3])) / 2)


def warp(img, quad, max_h=MAX_H):
    """Straighten the card – as large as it is in the image (not artificially enlarged)."""
    hh = int(min(max_h, max(200, size_of(quad))))
    ww = int(round(hh / _aspect()))
    dst = np.float32([[0, 0], [ww - 1, 0], [ww - 1, hh - 1], [0, hh - 1]])
    m = cv2.getPerspectiveTransform(np.asarray(quad, np.float32), dst)
    return cv2.warpPerspective(img, m, (ww, hh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def rounded(card, radius=0.045):
    """BGRA: transparent corners (radius as a share of the width, Magic/Pokémon ≈ 3 mm of 63 mm)."""
    h, w = card.shape[:2]
    r = max(2, int(round(w * radius)))
    k = 4   # soft edge: draw at four times the size, then scale down
    big = np.zeros((h * k, w * k), np.uint8)
    rr = r * k
    cv2.rectangle(big, (rr, 0), (w * k - rr, h * k), 255, -1)
    cv2.rectangle(big, (0, rr), (w * k, h * k - rr), 255, -1)
    for cx, cy in ((rr, rr), (w * k - rr, rr), (rr, h * k - rr), (w * k - rr, h * k - rr)):
        cv2.circle(big, (cx, cy), rr, 255, -1)
    alpha = cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA)
    out = cv2.cvtColor(card, cv2.COLOR_BGR2BGRA)
    out[:, :, 3] = alpha
    return out


def sharpness(card):
    g = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (int(700 / g.shape[0] * g.shape[1]), 700), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def quality(img, quad):
    """How good is the shot? Each point 0..1 (1 = good) and whether everything fits."""
    out = {"found": 0.0, "sharp": 0.0, "glare": 0.0, "light": 0.0, "size": 0.0, "ok": False, "px": 0}
    if quad is None:
        return out
    card = warp(img, quad, max_h=900)
    out["found"] = 1.0
    out["px"] = int(size_of(quad))
    out["size"] = min(1.0, size_of(quad) / MIN_GOOD_H)
    out["sharp"] = min(1.0, sharpness(card) / SHARP_GOOD)
    hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
    inner = hsv[int(card.shape[0] * 0.04):int(card.shape[0] * 0.96), int(card.shape[1] * 0.05):int(card.shape[1] * 0.95)]
    v = inner[:, :, 2]
    # glare: blown-out, colourless spots (camera maxed out) – "opened" first so that thin bright edges around text
    # don't count; white text boxes don't blow out with correct exposure
    spots = ((v >= 252) & (inner[:, :, 1] < 22)).astype(np.uint8)
    spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    glare = float(np.mean(spots))
    out["glare"] = max(0.0, 1.0 - glare / GLARE_BAD)
    # light: not too dark, not overexposed (mean brightness)
    mean = float(v.mean())
    out["light"] = max(0.0, min(1.0, (mean - 45) / 40, (235 - mean) / 30))
    out["ok"] = out["sharp"] >= 0.8 and out["glare"] >= 0.6 and out["light"] >= 0.6 and out["size"] >= 0.55
    return out


def best(frames):
    """Out of several camera frames the sharpest one with a found card -> (image, corners) or (None, None)."""
    pick, score = (None, None), -1.0
    for f in frames:
        q = find_quad(f)
        if q is None:
            continue
        s = sharpness(warp(f, q, max_h=700))
        if s > score:
            pick, score = (f, q), s
    return pick


def from_file(path):
    """Image from a file (scanner, phone photo): find the card in it and straighten it. If the image already is just
    the card (aspect ratio fits, no outline needed), it is taken as is. -> (card BGR, found?) or (None, …)"""
    data = np.fromfile(str(path), np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)   # rotates per EXIF and drops all metadata
    if img is None:
        return None, False
    q = find_quad(img)
    h, w = img.shape[:2]
    if q is not None and cv2.contourArea(q.astype(np.float32)) < 0.92 * w * h:
        return warp(img, q), True
    if h < w:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        h, w = w, h
    if abs(h / w - _aspect()) / _aspect() < 0.08:
        if h > MAX_H:
            img = cv2.resize(img, (int(MAX_H / h * w), MAX_H), interpolation=cv2.INTER_AREA)
        return img, True
    return img, False


def encode_png(bgra):
    ok, buf = cv2.imencode(".png", bgra, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    return buf.tobytes() if ok else b""


def encode_jpg(bgr, q=92):
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes() if ok else b""
