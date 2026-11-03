"""A count resting on a weak image match asks instead (aiscan.COUNT_NEEDS – "not sure -> ask"); the unambiguous
fingerprint and the collector line are untouched.

    python -m unittest tests/test_weak_match.py
"""
import unittest

from scanner import aiscan


def res(how, strength):
    e = {"id": "x_0", "name": "Bronzong", "set": "me05", "number": "64", "img": ""}
    return {"status": "ok", "entry": e, "how": how, "strength": strength, "img": None, "box": None}


class WeakMatch(unittest.TestCase):
    def test_weak_image_match_asks(self):
        r = aiscan.sure_print(None, res("SCAN° fingerprint (0.76) + image match (92)", 92))
        self.assertEqual(r["status"], "ask")
        self.assertEqual(r["cands"][0][0]["name"], "Bronzong")
        self.assertIn("image match weak", r["how"])

    def test_strong_and_other_paths_unchanged(self):
        self.assertFalse(aiscan._weak_match(res("SCAN° fingerprint (0.81) + image match (140)", 140)))
        self.assertFalse(aiscan._weak_match(res("SCAN° fingerprint unambiguous (gap 0.12 / 0.12)", 0)))
        self.assertFalse(aiscan._weak_match(res("SCAN° fingerprint (0.70) + collector line", 60)))
        self.assertTrue(aiscan._weak_match(res("SCAN° fingerprint + image match (70, similar print 50)", 70)))
