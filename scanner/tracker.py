"""Track the card in the camera frame – for the scan overlay in the preview.

Two stages:
  gefunden (found)   – card still unknown: outline in card format (63:88) in the area around the scan frame
  erfasst (locked)   – card recognized: its reference image is searched in the camera frame via image features
                       (homography). Precise, even with fingers and a dark background, and the orientation is known
                       (top/bottom)
quad: 4 corners in the camera frame (pixels); for "erfasst" in card order top left, top right, bottom right,
bottom left.
"""
import collections
import threading
import time

import cv2
import numpy as np

from scanner.common import BASE, features, make_orb, prep
from scanner.core import zone_rect

HZ = 20
LOST_AFTER = 0.6   # how long (s) the frame stays when the card is briefly not found


class CardTracker:
    def __init__(self, camera, settings, recognizer):
        self.camera, self.settings, self.recognizer = camera, settings, recognizer
        self.quad, self.state, self.seen = None, None, 0.0
        self.running = True
        self._orb_q = make_orb(1200)
        self._orb_r = make_orb(800)
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._refs = collections.OrderedDict()  # image path -> (points, features, width, height)
        threading.Thread(target=self._run, daemon=True, name="verfolgen").start()

    # ---------- main loop ----------
    def _run(self):
        last_seq = -1
        while self.running:
            t0 = time.time()
            frame, seq = self.camera.latest()
            if frame is None or seq == last_seq or not self.active():
                if frame is None or not self.active():
                    self.quad, self.state = None, None
                time.sleep(0.02)
                continue
            last_seq = seq
            try:
                self._step(frame)
            except Exception:
                pass
            time.sleep(max(0.0, 1 / HZ - (time.time() - t0)))

    def active(self):
        """Only compute while the preview is visible (set by the main window)."""
        return getattr(self, "visible", True)

    def _step(self, frame):
        fh, fw = frame.shape[:2]
        rect = zone_rect(self.settings["zone"], fw, fh)
        q, state = None, None
        entry = getattr(self.recognizer, "current", None)
        if entry is not None:
            q = self._locate(frame, rect, BASE / entry["img"])
            state = "erfasst" if q is not None else None
        if q is None:
            q = contour_quad(frame, rect)
            state = "gefunden" if q is not None else None
        now = time.time()
        if q is None:
            if now - self.seen > LOST_AFTER:
                self.quad, self.state = None, None
            return
        self.quad = self._smooth(self.quad, q, state == "erfasst" and self.state == "erfasst")
        self.state, self.seen = state, now

    # ---------- known card via its image ----------
    def _ref(self, path):
        key = str(path)
        if key in self._refs:
            self._refs.move_to_end(key)
            return self._refs[key]
        img = cv2.imdecode(np.fromfile(key, np.uint8), cv2.IMREAD_COLOR) if path.exists() else None
        if img is None:
            return None
        g = prep(img)
        pts, des = features(self._orb_r, g)
        ref = (pts, des, g.shape[1], g.shape[0])
        self._refs[key] = ref
        while len(self._refs) > 20:
            self._refs.popitem(last=False)
        return ref

    def _locate(self, frame, rect, path):
        ref = self._ref(path)
        if ref is None or len(ref[1]) < 10:
            return None
        rp, rd, rw, rh = ref
        x, y, w, h = rect
        fh, fw = frame.shape[:2]
        mx, my = int(w * 0.5), int(h * 0.3)
        x0, y0, x1, y1 = max(0, x - mx), max(0, y - my), min(fw, x + w + mx), min(fh, y + h + my)
        region = frame[y0:y1, x0:x1]
        scale = min(1.0, 720 / max(region.shape[:2]))
        gray = cv2.cvtColor(cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
                            cv2.COLOR_BGR2GRAY)
        qp, qd = features(self._orb_q, gray)
        if len(qd) < 10:
            return None
        good = [m[0] for m in self._bf.knnMatch(rd, qd, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if len(good) < 12:
            return None
        hm, mask = cv2.findHomography(rp[[m.queryIdx for m in good]], qp[[m.trainIdx for m in good]], cv2.RANSAC, 5.0)
        if hm is None or mask is None or mask.sum() < 12:
            return None
        corners = np.float32([[0, 0], [rw, 0], [rw, rh], [0, rh]]).reshape(-1, 1, 2)
        q = cv2.perspectiveTransform(corners, hm).reshape(4, 2) / scale + np.array([x0, y0], np.float32)
        return q if plausible(q, w * h) else None

    # ---------- smoothing ----------
    @staticmethod
    def _smooth(old, new, same_order):
        if old is None:
            return new
        if not same_order:  # rotate the corners of the new solution so they match the old ones
            new = min((np.roll(new, k, axis=0) for k in range(4)), key=lambda n: np.linalg.norm(n - old, axis=1).sum())
        size = np.linalg.norm(old[0] - old[2])
        if np.linalg.norm(new - old, axis=1).mean() > 0.25 * size:
            return new  # jump (different card, fast movement): take it over immediately
        return (old * 0.45 + new * 0.55).astype(np.float32)


def plausible(q, zone_area):
    """Quadrilateral looks like a card: convex, aspect ratio roughly 63:88, sensible size."""
    if not cv2.isContourConvex(q.astype(np.float32).reshape(-1, 1, 2)):
        return False
    a = (np.linalg.norm(q[0] - q[1]) + np.linalg.norm(q[2] - q[3])) / 2
    b = (np.linalg.norm(q[1] - q[2]) + np.linalg.norm(q[3] - q[0])) / 2
    if min(a, b) < 20:
        return False
    ratio = min(a, b) / max(a, b)
    area = cv2.contourArea(q.astype(np.float32))
    return 0.5 <= ratio <= 0.95 and 0.08 * zone_area <= area <= 4 * zone_area


def contour_quad(frame, rect):
    """Outline in card format near the scan frame (corners clockwise) or None."""
    x, y, w, h = rect
    fh, fw = frame.shape[:2]
    mx, my = int(w * 0.4), int(h * 0.25)
    x0, y0, x1, y1 = max(0, x - mx), max(0, y - my), min(fw, x + w + mx), min(fh, y + h + my)
    region = frame[y0:y1, x0:x1]
    scale = 480 / max(region.shape[:2])
    small = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    zone_area = w * h * scale * scale
    zc = np.array([(x - x0 + w / 2) * scale, (y - y0 + h / 2) * scale])
    best = None
    for c in cnts:
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        if min(rw, rh) < 1:
            continue
        ratio = min(rw, rh) / max(rw, rh)
        area = rw * rh
        if not (0.62 <= ratio <= 0.80 and 0.25 * zone_area <= area <= 2.5 * zone_area):
            continue
        if cv2.contourArea(cv2.convexHull(c)) < 0.88 * area:
            continue
        score = abs(np.log(area / zone_area)) + np.linalg.norm(np.array([cx, cy]) - zc) / np.sqrt(zone_area)
        if best is None or score < best[0]:
            best = (score, cv2.boxPoints(((cx, cy), (rw * 1.03, rh * 1.02), ang)))
    if best is None:
        return None
    q = best[1] / scale + np.array([x0, y0], np.float32)
    c = q.mean(0)
    order = np.argsort([np.arctan2(p[1] - c[1], p[0] - c[0]) for p in q])  # clockwise from top left
    return q[order].astype(np.float32)
