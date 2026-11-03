"""Counting a card that stays lying there exactly once (Oliver, live 0.9.2: cards counted twice when they stay in the
picture). Runs the real recognizer loop (Recognizer._run_ai) and the real session on made-up camera frames – a mat, two
cards, a hand, a black frame – with only the image search stubbed (it says which card and where it lies).

    python -m unittest tests/test_count_guard.py
"""
import types
import unittest
from unittest import mock

import cv2
import numpy as np

from scanner import aiscan, core, recognizer

FW, FH = 1280, 720
ZONE = [0.5, 0.5, 0.3]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def monotonic(self):
        return self.t

    def sleep(self, s):
        pass


def _texture(seed):
    rng = np.random.default_rng(seed)
    img = (rng.random((FH, FW)) * 255).astype(np.uint8)
    return cv2.cvtColor(cv2.resize(cv2.resize(img, (160, 90)), (FW, FH), interpolation=cv2.INTER_NEAREST),
                        cv2.COLOR_GRAY2BGR)


MAT = np.full((FH, FW, 3), 70, np.uint8)
MAT[:] = cv2.GaussianBlur((np.random.default_rng(1).random((FH, FW, 3)) * 12 + 64).astype(np.uint8), (31, 31), 0)
HAND = np.full((FH, FW, 3), (120, 150, 205), np.uint8)   # skin, close to the lens: smooth, few edges
DARK = np.full((FH, FW, 3), 6, np.uint8)                  # the camera waking up
CARDS = {"A": _texture(11), "B": _texture(12), "A2": _texture(11)}   # A2: the second copy of A (same picture)
BOX = {"left": (200, 150, 380, 530), "right": (700, 150, 380, 530)}


def entry(name):
    return {"id": f"{name}-id_0", "name": name, "set": "tst", "number": "1", "img": "", "eur": 1.0, "eur_foil": None,
            "finishes": ["nonfoil"], "lang": "en"}


class Sim:
    """frames: [(scene, card name or None, box key or None, seconds)] – scene = MAT/HAND/DARK or a card key."""

    def __init__(self):
        self.clock = Clock()
        self.frame, self.seq, self.result = None, 0, None
        cam = types.SimpleNamespace(latest=lambda: (self.frame, self.seq),
                                    recent_frames=lambda: [(self.seq, self.frame)])
        sess = core.Session()
        sess.info["active"] = True
        with mock.patch.object(recognizer.threading, "Thread"):
            self.rec = recognizer.Recognizer(cam, sess, {"zone": ZONE, "scan_data": False, "scan_mode": "ai",
                                                         "card_lang": "en", "hit": 0.5})
        self.rec.fp_index = object()
        self.rec._set_lang_checked = lambda *a: None
        self.rec.live = types.SimpleNamespace(step=lambda *a, **k: self.result, prior=None, _foot_reads=[])

    def run(self, frames):
        patches = [mock.patch.object(recognizer, "time", self.clock), mock.patch.object(core, "time", self.clock),
                   mock.patch.object(aiscan, "sure_print", lambda frame, res, index: res),
                   mock.patch("net.anonstats.mark", lambda *a, **k: None)]
        for p in patches:
            p.start()
        try:
            last = -1
            for scene, name, box, secs in frames:
                img = {"MAT": MAT, "HAND": HAND, "DARK": DARK}.get(scene)
                if img is None:   # a card: its picture in the scan zone, on the mat
                    img = MAT.copy()
                    x, y, w, h = core.zone_rect(ZONE, FW, FH)
                    shift = 6 if scene == "A2" else 0
                    img[y:y + h, x + shift:x + w] = CARDS[scene][y:y + h, x:x + w - shift]
                if name is None:
                    self.result = {"status": "none", "how": "test"}
                else:
                    self.result = {"status": "ok", "entry": entry(name), "box": BOX[box],
                                   "strength": aiscan.STRONG + 10, "how": "test", "lang": "en", "img": None}
                for _ in range(max(1, round(secs * 30))):
                    self.seq += 1
                    self.frame = img
                    self.clock.t += 1 / 30
                    last = self.rec._run_ai(last)
        finally:
            for p in patches:
                p.stop()
        return [e["name"] for p in self.rec.session.packs for e in p["cards"]]


class LyingCardCountsOnce(unittest.TestCase):
    def test_lying_card_beside_hop_hand_and_shift(self):
        """A lies there, B beside it, the tracking hops back to A, a hand covers 2 s, A moved a little: A and B 1× each."""
        got = Sim().run([("MAT", None, None, 1), ("A", "A", "left", 30), ("B", "B", "right", 5),
                         ("A", "A", "left", 15), ("HAND", None, None, 2), ("A2", "A", "left", 5)])
        self.assertEqual(got, ["A", "B"])

    def test_camera_waking_up_black(self):
        """Back on the scan page: the camera wakes up with black frames – the card lying there doesn't count again."""
        got = Sim().run([("MAT", None, None, 1), ("A", "A", "left", 5), ("DARK", None, None, 3), ("A", "A", "left", 5)])
        self.assertEqual(got, ["A"])

    def test_stack_in_the_hand(self):
        """A stack in the hand: A, B, A at the same place, never an empty frame – three cards."""
        got = Sim().run([("A", "A", "left", 2), ("B", "B", "left", 4), ("A2", "A", "left", 12)])
        self.assertEqual(got, ["A", "B", "A"])

    def test_two_copies_swapped_quickly(self):
        """Two identical commons: A away, A' at once – the mat shows for a moment: two cards."""
        got = Sim().run([("MAT", None, None, 1), ("A", "A", "left", 3), ("MAT", None, None, 0.1),
                         ("A2", "A", "left", 3)])
        self.assertEqual(got, ["A", "A"])

    def test_quick_hop_keeps_the_card_beside(self):
        """The tracking hops back to A within 3 s: B lies beside it (another place) – it stays, A doesn't count again."""
        got = Sim().run([("MAT", None, None, 1), ("A", "A", "left", 3), ("B", "B", "right", 1.5),
                         ("A", "A", "left", 3)])
        self.assertEqual(got, ["A", "B"])


def _room(seed):
    """Scanning in the hand in front of the webcam: the room behind, out of focus – few edges, but light and dark."""
    rng = np.random.default_rng(seed)
    big = (rng.random((9, 16)) * 200 + 30).astype(np.uint8)
    img = cv2.GaussianBlur(cv2.resize(big, (FW, FH), interpolation=cv2.INTER_CUBIC), (151, 151), 0)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


ROOMS = [_room(s) for s in range(20, 26)]


class WithoutAMat(unittest.TestCase):
    """No mat: the card held up in the hand, the room behind (moving with the hand) – nothing counts twice, nothing
    real is swallowed."""
    def test_two_copies_in_the_hand(self):
        """A held up, the room for half a second, A' held up: two cards."""
        self.assertEqual(_run_rooms([("A", "A", "left", 2), ("ROOM", None, None, 0.5), ("A2", "A", "left", 2)]),
                         ["A", "A"])

    def test_a_card_held_still(self):
        """A held up for 20 s (the room never shows): one card."""
        self.assertEqual(_run_rooms([("ROOM", None, None, 1), ("A", "A", "left", 20)]), ["A"])

    def test_room_then_hand_over_lens(self):
        """The room, A, a hand right over the lens for 2 s, A again: one card."""
        self.assertEqual(_run_rooms([("ROOM", None, None, 1), ("A", "A", "left", 3), ("HAND", None, None, 2),
                                     ("A", "A", "left", 3)]), ["A"])


def _run_rooms(frames):
    """Like Sim.run, the scene "ROOM" being a changing out-of-focus room instead of the mat."""
    sim = Sim()
    expanded = []
    for scene, name, box, secs in frames:
        if scene == "ROOM":
            for k in range(max(1, round(secs * 10))):
                expanded.append(("ROOM", k, None, 0.1))
        else:
            expanded.append((scene, name, box, secs))
    orig = sim.run

    def run(fr):
        global MAT
        keep = MAT
        try:
            out = []
            for scene, name, box, secs in fr:
                if scene == "ROOM":
                    MAT = ROOMS[name % len(ROOMS)]
                    out = orig([("MAT", None, None, secs)])
                else:
                    out = orig([(scene, name, box, secs)])
            return out
        finally:
            MAT = keep
    return run(expanded)
