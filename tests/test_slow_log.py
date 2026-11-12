"""The slow-card line in the local log (lead 07.11.2026): a card counted after more than SLOW_LOG seconds – or gone
uncounted after that long – gets ONE line with what its frames were (counts only, no pictures); fast cards and a
counted card lying there get none, and what counts stays the same. Runs the real loop (test_count_guard.Sim)."""
import logging
import unittest

from scanner import recognizer
from tests.test_count_guard import Sim


def slow_lines(frames):
    sim = Sim()
    with unittest.TestCase().assertLogs(recognizer.log, logging.INFO) as cm:
        recognizer.log.info("start")
        got = sim.run(frames)
    return got, [r.getMessage() for r in cm.records if r.getMessage().startswith("Slow card")]


class SlowCardLine(unittest.TestCase):
    def test_slow_card_counted(self):
        got, lines = slow_lines([("MAT", None, None, 1), ("A", None, None, 4), ("A", "A", "left", 1),
                                 ("MAT", None, None, 1)])
        self.assertEqual(got, ["A"])   # counting unchanged
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^Slow card: tst #1 counted after 4\.\d s · frames: nothing \d+")

    def test_reasons_from_the_search(self):
        sim = Sim()
        sim.rec._slow_note("blurry")
        sim.rec._slow_frame({"status": "none", "how": "Image match close, fingerprint disagrees", "sim": 0.71})
        sim.rec._slow_frame({"status": "none", "how": "Loading reference images …"})
        sim.rec._slow_frame({"status": "none", "how": "Card at the edge (not the top one)", "sim": 0.64})
        sim.rec._slow_frame({"status": "ask", "how": "x", "sim": 0.7})
        with self.assertLogs(recognizer.log, logging.INFO) as cm:
            sim.rec._slow_line("x counted", 5.0)
        self.assertEqual(cm.output[0].split(":", 2)[2], "Slow card: x counted after 5.0 s · frames: blurry 1, close 1, "
                                                       "loading 1, edge 1, print unclear 1 · best fingerprint 0.71")

    def test_fast_card_no_line(self):
        got, lines = slow_lines([("MAT", None, None, 1), ("A", None, None, 1), ("A", "A", "left", 1),
                                 ("MAT", None, None, 1)])
        self.assertEqual((got, lines), (["A"], []))

    def test_counted_card_lying_long_no_line(self):
        got, lines = slow_lines([("MAT", None, None, 1), ("A", "A", "left", 30), ("MAT", None, None, 1)])
        self.assertEqual((got, lines), (["A"], []))

    def test_gone_without_counting(self):
        got, lines = slow_lines([("MAT", None, None, 1), ("A", None, None, 5), ("MAT", None, None, 1)])
        self.assertEqual(got, [])
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^Slow card: gone without counting after 5\.\d s · frames: nothing \d+ · best "
                                   r"fingerprint 0\.00$")

    def test_stack_next_card_measured_from_the_count(self):
        # A counted fast, B right after it at the same place (no empty frame), found only after 4 s: one line for B
        got, lines = slow_lines([("A", "A", "left", 1), ("B", None, None, 4), ("B", "B", "left", 1)])
        self.assertEqual(got, ["A", "B"])
        self.assertEqual(len(lines), 1)
        self.assertIn("counted after 5.", lines[0])
