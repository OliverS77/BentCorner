"""Review 08.11.2026 (Prüfkette Schritt 1; Gordon B3/B8): lists and files from outside.
H2-1: a deck/text list line of „1 a“ + many spaces never freezes the app (it took 8 s at 400 spaces); H2-2: counts are
capped (one entry per copy – never millions); H2-4: a file and its unpacked .bentcorner content have size limits.
In memory and throwaway files only.

    python -m unittest tests/test_review_import.py
"""
import json
import pathlib
import tempfile
import time
import unittest
import zlib
from unittest import mock

from collection import decks, trade


class ListTest(unittest.TestCase):
    def test_no_freeze_on_long_space_runs(self):
        for line in ("1 a" + " " * 20000 + "b", "1 a" + " " * 2000 + "\x00b", "1 " + "a " * 5000 + "("):
            t = time.time()
            decks.parse_text(line)
            self.assertLess(time.time() - t, 0.5, line[:10])

    def test_normal_lines_unchanged(self):
        self.assertEqual(decks.parse_text("4 Lightning Bolt (2X2) 117 *F*"), [(4, "Lightning Bolt", "2x2", "117", "main")])
        self.assertEqual(decks.parse_text("2   Counterspell"), [(2, "Counterspell", "", "", "main")])

    def test_counts_capped(self):
        self.assertEqual(decks.parse_text("99999999 Bolt")[0][0], decks.MAX_COUNT)
        self.assertEqual(trade.parse_text("1000000000 Bolt")[0][4], decks.MAX_COUNT)
        rows = trade.parse_csv("name,count\nBolt,1e9\nShock,inf\n")
        self.assertEqual([r[4] for r in rows], [99_999, 1])
        self.assertEqual(trade.parse_csv("name,count\nIsland,2500\n")[0][4], 2500)   # real bulk stays (lead)


class FileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_too_large(self):
        f = self.root / "big.txt"
        f.write_text("1 Bolt\n" * 1000, "utf-8")
        with mock.patch.object(trade, "FILE_MAX", 100):
            with self.assertRaises(ValueError):
                trade.read_file(f)

    def test_bentcorner_bomb(self):
        f = self.root / "bomb.bentcorner"
        body = json.dumps({"app": "BentCorner", "id": "x", "pad": "0" * 200_000}).encode()
        f.write_bytes(trade.MAGIC + zlib.compress(body))
        with mock.patch.object(trade, "UNPACKED_MAX", 50_000):
            with self.assertRaises(ValueError):
                trade.read_file(f)
        self.assertEqual(trade.read_file(f)["kind"], "bentcorner")              # within the limit: as before

    def test_bentcorner_not_an_object(self):
        f = self.root / "list.bentcorner"
        f.write_bytes(trade.MAGIC + zlib.compress(b"[1, 2]"))
        with self.assertRaises(ValueError):
            trade.read_file(f)


if __name__ == "__main__":
    unittest.main()
