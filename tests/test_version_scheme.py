"""Work-in-progress builds count after the LAST ship (Oliver/Gordon 13.11.2026): 0.9.8.100 comes after the 0.9.8 hotfix
and before 0.9.9. The old builds of the history (0.9.2.115, 0.9.7.58, 0.9.8.0) keep counting towards their ship.

    python -m unittest tests.test_version_scheme
"""
import unittest
from unittest import mock

import version
from net import updater


class Scheme(unittest.TestCase):
    def test_release_of(self):
        self.assertEqual(version.release_of("0.9.8.100"), "0.9.9")
        self.assertEqual(version.release_of("0.9.8.107"), "0.9.9")
        self.assertEqual(version.release_of("0.9.9.100"), "0.9.10")
        self.assertEqual(version.release_of("0.9.7.58"), "0.9.7")    # old style
        self.assertEqual(version.release_of("0.9.8.0"), "0.9.8")     # old style (the 13.11. test build)
        self.assertEqual(version.release_of("0.9.2.115"), "0.9.2")   # old style, even above 100
        self.assertEqual(version.release_of("0.9.8"), "0.9.8")

    def test_current_is_a_work_build_of_the_next_ship(self):
        # pinned to a work build: the release commit sets VERSION to three digits (ship 0.9.9, export tests)
        with mock.patch.object(version, "VERSION", "0.9.8.100"):
            self.assertFalse(version.is_release())
            self.assertTrue(version._after_ship([int(x) for x in version.VERSION.split(".")]))
            self.assertEqual(version.release_of(), "0.9.9")

    def test_order(self):
        order = ["0.9.2.115", "0.9.2", "0.9.7.58", "0.9.7", "0.9.8.0", "0.9.8", "0.9.8.100", "0.9.8.101", "0.9.9",
                 "0.9.9.100", "0.9.10"]
        self.assertEqual(sorted(order, key=version._vkey), order)

    def test_work_build_older_than_the_next_ship(self):
        for v in ("0.9.8.100", "0.9.8.250"):
            self.assertLess(version._vkey(v), version._vkey(version.release_of(v)))
            self.assertTrue(updater.newer(version.release_of(v), v), v)   # 0.9.9 is offered to 0.9.8.100
            self.assertFalse(updater.newer("0.9.8", v), v)                # its own ship is not

    def test_highlights_of_the_last_ship_count_as_seen(self):
        with mock.patch.dict(version.HIGHLIGHTS, {"0.9.8": ["fix"], "0.9.9": ["next"]}, clear=False):
            self.assertEqual(version.highlights_since("0.9.8", "0.9.8.100")[1], [])
            self.assertEqual(version.highlights_since("0.9.7", "0.9.8.100")[1][:1], ["fix"])
            self.assertNotIn("next", version.highlights_since("0.9.7", "0.9.8.100")[1])

    def test_publish_refuses_four_digits(self):
        src = (version.pathlib.Path(version.__file__).parent / "tools" / "publish_release.py")
        if src.exists():
            self.assertIn("if not version.is_release():", src.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
