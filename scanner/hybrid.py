"""Hybrid recognition: text recognition supplies candidates (similar names, read set/number); their images are
loaded in steps of ten (the most likely first, then the next ten …) and compared with the camera image via image
features. If several prints stay equally good, the read collector line decides – and if that doesn't help
either, the program asks.
"""
import collections
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from cards import carddb
from cards import imgcache
from scanner.common import BASE, features, image_rel, make_orb, prep

BATCH = 10          # images per loading step
MAX_BATCHES = 4     # at most 40 images per card
MIN_INLIERS = 18    # from here an image counts as "fits"
CLOSE = 0.5         # other prints with >= 50 % of the best match: same artwork (different artwork: mostly < 10 %)
OVERLAY_GAP = 0.06  # a print must be this much better in the whole-card comparison to count without asking
ASK_MAX = 6         # at most this many candidates in the ask window

_local = threading.local()
_feat = collections.OrderedDict()  # image path -> (keypoints, descriptors), the last 600
_feat_lock = threading.Lock()
_pool = ThreadPoolExecutor(6, thread_name_prefix="bilder")
_prefetch_pool = ThreadPoolExecutor(3, thread_name_prefix="vorladen")  # separate pool: doesn't slow down recognition
_bf = cv2.BFMatcher(cv2.NORM_HAMMING)


def _orb():
    if not hasattr(_local, "orb"):
        _local.orb = make_orb(800)
    return _local.orb


def image_url(row):
    """Image URL of the front face (double-faced cards have one per face)."""
    if row.get("img_normal"):
        return row["img_normal"]
    try:
        faces = json.loads(row.get("faces") or "[]")
        return faces[0].get("img_normal") if faces else None
    except ValueError:
        return None


def image_path(row):
    return BASE / image_rel(row["set_code"], row["number"], 0)


def _ref(row):
    """Features of the candidate image (downloads it if needed). None = image not available."""
    path = image_path(row)
    key = str(path)
    with _feat_lock:
        if key in _feat:
            _feat.move_to_end(key)
            return _feat[key]
    if not imgcache.fetch(path, image_url(row)):
        return None
    img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    f = features(_orb(), prep(img))
    with _feat_lock:
        _feat[key] = f
        while len(_feat) > _feat_max:
            _feat.popitem(last=False)
    return f


FEAT_KEEP = 600          # reference features kept in RAM (~40 KB each) …
FEAT_FILTERED = 1500     # … plus up to this many of the filtered scan's sets (preload_features, ~60 MB at most)
_feat_max = FEAT_KEEP


def preload_features(paths, stop=lambda: False, progress=None):
    """Filtered scan: the features of these stored reference images computed now and kept in RAM, so the image
    match doesn't read and compute them first (at most FEAT_FILTERED; missing images are skipped) -> how many.
    progress(done, total): every 25 images."""
    global _feat_max
    paths = list(paths)[:FEAT_FILTERED]
    _feat_max = FEAT_KEEP + len(paths)
    n = 0
    for i, path in enumerate(paths):
        if stop():
            break
        if progress and i % 25 == 0:
            progress(i, len(paths))
        if _ref_path(path) is not None:
            n += 1
    with _feat_lock:
        while len(_feat) > _feat_max:
            _feat.popitem(last=False)
    return n


def _ref_path(path):
    """Features of a stored card image (no download) or None."""
    key = str(path)
    with _feat_lock:
        if key in _feat:
            _feat.move_to_end(key)
            return _feat[key]
    if not path.exists():
        return None
    img = cv2.imdecode(np.fromfile(key, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    f = features(_orb(), prep(img))
    with _feat_lock:
        _feat[key] = f
        while len(_feat) > _feat_max:
            _feat.popitem(last=False)
    return f


_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def verify(frame, rect, path):
    """Is the already recognised card (image at path) still in the area around the scan frame? -> inliers (0 = no).
    ~15 ms instead of a new text recognition."""
    ref = _ref_path(path)
    if ref is None:
        return 0
    x, y, w, h = rect
    fh, fw = frame.shape[:2]
    mx, my = int(w * 0.5), int(h * 0.3)
    region = frame[max(0, y - my):min(fh, y + h + my), max(0, x - mx):min(fw, x + w + mx)]
    scale = min(1.0, 720 / max(region.shape[:2]))
    gray = cv2.cvtColor(cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
                        cv2.COLOR_BGR2GRAY)
    return _inliers(features(make_orb(1200), _clahe.apply(gray)), ref)


def query_features(img):
    return features(make_orb(1000), prep(img))


def _inliers(q, ref):
    qp, qd = q
    rp, rd = ref
    if len(qd) < 10 or len(rd) < 10:
        return 0
    good = [m[0] for m in _bf.knnMatch(qd, rd, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
    if len(good) < 10:
        return 0
    _, mask = cv2.findHomography(qp[[m.queryIdx for m in good]], rp[[m.trainIdx for m in good]], cv2.RANSAC, 6.0)
    return int(mask.sum()) if mask is not None else 0


def _overlay_score(img, row):
    """Lay the camera image exactly onto the candidate image (homography) and compare the whole card (correlation).
    Tells apart prints with the same artwork but a different frame (borderless, showcase, promo …). -> -1..1"""
    ref_img = cv2.imdecode(np.fromfile(str(image_path(row)), np.uint8), cv2.IMREAD_COLOR)
    if ref_img is None:
        return -1.0
    qg, rg = prep(img), prep(ref_img)
    (qp, qd), (rp, rd) = features(_orb(), qg), features(_orb(), rg)
    if len(qd) < 10 or len(rd) < 10:
        return -1.0
    good = [m[0] for m in _bf.knnMatch(qd, rd, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
    if len(good) < 10:
        return -1.0
    hm, mask = cv2.findHomography(qp[[m.queryIdx for m in good]], rp[[m.trainIdx for m in good]], cv2.RANSAC, 5.0)
    if hm is None:
        return -1.0
    h, w = rg.shape
    warped = cv2.warpPerspective(qg, hm, (w, h))
    valid = cv2.warpPerspective(np.full(qg.shape, 255, np.uint8), hm, (w, h)) > 0
    if valid.mean() < 0.5:
        return -1.0
    a = cv2.GaussianBlur(warped, (5, 5), 0)[valid].astype(np.float32)
    b = cv2.GaussianBlur(rg, (5, 5), 0)[valid].astype(np.float32)
    a -= a.mean()
    b -= b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))


def _num(n):
    return carddb.norm_number(n, "")


def decide(imgs, rows, r, prefer_sets=()):
    """Camera images of the card (straightened, then the area around the frame as fallback) + candidates (best first)
    + what was read -> {"status": "ok" | "ask" | "none", "row": row, "cands": [(row, inliers)], "loaded", "inliers"}"""
    imgs = [i for i in imgs if i is not None]
    q = query_features(imgs[0])
    scored, loaded = [], []   # scored: (row, inliers); loaded: (row, features)
    best_name = None
    for start in range(0, min(len(rows), BATCH * MAX_BATCHES), BATCH):
        batch = rows[start:start + BATCH]
        if start and best_name is not None:
            # hit found: only load further prints of the same card (they could share the artwork)
            batch = [b for b in batch if b["name"] == best_name]
            if not batch:
                break
        for row, ref in zip(batch, _pool.map(_ref, batch)):
            if ref is not None:
                loaded.append((row, ref))
                scored.append((row, _inliers(q, ref)))
        if not scored:
            if imgcache.offline():
                break
            continue
        top = max(scored, key=lambda t: t[1])
        if top[1] >= MIN_INLIERS:
            best_name = top[0]["name"]
            # collector line confirms the hit -> done, no further prints needed
            if r.get("set") and top[0]["set_code"] == r["set"] and (not r.get("number")
                                                                      or _num(top[0]["number"]) == r["number"]):
                break
            if not any(b["name"] == best_name for b in rows[start + BATCH:]):
                break
    if len(imgs) > 1 and loaded and max(i for _, i in scored) < MIN_INLIERS:
        # straightened image fits nowhere (wrong outline caught): compare the area around the frame
        q2 = query_features(imgs[1])
        scored = [(row, _inliers(q2, ref)) for row, ref in loaded]
    scored.sort(key=lambda t: -t[1])
    out = {"status": "none", "row": None, "cands": scored, "loaded": len(loaded),
           "inliers": scored[0][1] if scored else 0}
    if not scored or scored[0][1] < MIN_INLIERS:
        return out
    best = scored[0][1]
    close = [t for t in scored if t[1] >= CLOSE * best]
    pick = _tiebreak(close, r, prefer_sets, imgs[0]) if len(close) > 1 else close[0]
    if pick is not None:
        out.update(status="ok", row=pick[0])
    else:
        out.update(status="ask", cands=close[:ASK_MAX])
    return out


def _tiebreak(close, r, prefer_sets, img=None):
    """Several prints equally good: the read number/set, sets confirmed in this session or the exact
    whole-card comparison decide. None = genuinely unclear (ask)."""
    if r.get("set"):
        same = [t for t in close if t[0]["set_code"] == r["set"]]
        if len(same) == 1:
            return same[0]
        if same and r.get("number"):
            same = [t for t in same if _num(t[0]["number"]) == r["number"]]
            if len(same) == 1:
                return same[0]
    if r.get("number"):
        same = [t for t in close if _num(t[0]["number"]) == r["number"]]
        if len(same) == 1:
            return same[0]
    if prefer_sets:
        same = [t for t in close if t[0]["set_code"] in prefer_sets]
        if len(same) == 1:
            return same[0]
    if img is not None:
        ranked = sorted(((_overlay_score(img, t[0]), t) for t in close), key=lambda x: -x[0])
        if ranked[0][0] > 0.5 and ranked[0][0] - ranked[1][0] >= OVERLAY_GAP:
            return ranked[0][1]
    return None


def _prefetch_one(r):
    from net import netpolite
    with netpolite.mirror_only():   # in advance only via our mirror – the source sees no bulk downloads
        return imgcache.fetch(image_path(r), image_url(r))


def prefetch_sets(codes, stop=lambda: False, progress=None):
    """Preload the images of all cards in these sets (scan mode "All cards" with known session sets):
    then nothing has to be downloaded while scanning. -> number of newly loaded images. progress(done, total)."""
    import games
    codes = [c.lower() for c in codes if c]
    if not codes or not carddb.exists() or not games.current().bulk_images:   # Lorcana: never whole sets
        return 0
    with carddb.connection() as con:
        rows = [dict(r) for r in con.execute(
            f"SELECT set_code, number, img_normal, faces FROM cards WHERE set_code IN ({','.join('?' * len(codes))})"
            " AND layout NOT IN ('art_series', 'token', 'double_faced_token', 'emblem')", codes)]
    todo = [r for r in rows if not image_path(r).exists()]
    done = 0
    for i in range(0, len(todo), 8):
        if stop() or imgcache.offline():
            break
        if progress:
            progress(i, len(todo))
        part = todo[i:i + 8]
        done += sum(_prefetch_pool.map(_prefetch_one, part))
        time.sleep(0.2)  # go easy on Scryfall, recognition has priority
    return done


def confirm(img, row):
    """Fast path: does the camera image match exactly this card? -> inliers (loads only this one image)."""
    ref = _ref(row)
    if ref is None:
        return 0
    return _inliers(query_features(img), ref)


def row_by_print(set_code, number):
    """Set + number (typed in by the user) -> row or None."""
    with carddb.connection() as con:
        row = con.execute("SELECT * FROM cards WHERE set_code = ? AND (number = ? OR ltrim(number, '0') = ?)",
                          (set_code.lower(), number, carddb.norm_number(number, ""))).fetchone()
        return dict(row) if row else None
