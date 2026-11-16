"""Name read confirms a fingerprint candidate (aiscan.LiveScanner._name_pick, real photos 14.11.2026): two reads must
agree, the card must be among the fingerprint's first five, the print is never guessed.
Run: python -m unittest discover -t . -s tests -p "test_name_pick.py" """
import unittest
from unittest import mock

import numpy as np

from scanner import aiscan


def _e(name, cid, set_="abc", num="1"):
    return {"id": cid, "name": name, "set": set_, "number": num, "img": ""}


A, B = _e("Galaxy Cyclone", "a1_0"), _e("Storm", "b1_0")
LISTS = [[(A, 0.70), (B, 0.60)], [(B, 0.65)]]
ROW = {"id": "a1", "name": "Galaxy Cyclone", "set_code": "abc", "number": "1"}
ROW2 = {"id": "a2", "name": "Galaxy Cyclone", "set_code": "xyz", "number": "9"}


class NamePick(unittest.TestCase):
    def setUp(self):
        self.ls = aiscan.LiveScanner()
        self.ls.TEXT_GAP = 0.0
        self.frame = np.zeros((40, 40, 3), np.uint8)
        self.boxed = [(self.frame, (0, 0, 40, 40))]

    def _pick(self, reads, rows):
        """Run _name_pick once per read (each read finishes before the next frame) -> last result."""
        out = None
        with mock.patch.object(aiscan.LiveScanner, "_read_name", side_effect=reads), \
                mock.patch.object(aiscan.LiveScanner, "_prints_of", return_value=rows), \
                mock.patch("cards.carddb.print_likeliness", return_value=0):
            for _ in range(len(reads) + 1):
                out = self.ls._name_pick(self.frame, self.boxed, (0, 0, 40, 40), LISTS)
                if self.ls._name_job is not None:
                    self.ls._name_job.join()
        return out

    def test_two_agreeing_reads_count_a_single_print(self):
        got = self._pick([(A, None), (A, None)], [ROW])
        self.assertEqual(got["status"], "ok")
        self.assertEqual(got["entry"]["name"], "Galaxy Cyclone")
        self.assertIn("name read", got["how"])

    def test_one_read_is_never_enough(self):
        got = self._pick([(A, None)], [ROW])
        self.assertNotIn("status", got or {})

    def test_reads_that_disagree_count_nothing(self):
        got = self._pick([(A, None), (B, None)], [ROW])
        self.assertNotIn("status", got or {})

    def test_several_prints_ask_unless_the_line_names_one(self):
        asked = self._pick([(A, None), (A, None)], [ROW, ROW2])
        self.assertEqual(asked["status"], "ask")
        self.assertEqual({r["id"] for r, _ in asked["cands"]}, {"a1", "a2"})
        self.ls = aiscan.LiveScanner()
        self.ls.TEXT_GAP = 0.0
        with mock.patch.object(aiscan, "_row_entry", side_effect=lambda r, like=None: dict(like, id=r["id"])):
            got = self._pick([(A, ("xyz", "9")), (A, ("xyz", "9"))], [ROW, ROW2])
        self.assertEqual(got["status"], "ok")
        self.assertEqual(got["entry"]["id"], "a2")

    def test_a_stamped_twin_asks_even_with_the_line(self):
        """Bench 15.11. (prerelease-dsk/booster-fin): FIN 46 and its prerelease promo PFIN 46s share the line."""
        promo = {"id": "a3", "name": "Galaxy Cyclone", "set_code": "pabc", "number": "1s"}
        with mock.patch("games.current") as cur:
            cur.return_value.key = "mtg"
            got = self._pick([(A, ("abc", "1")), (A, ("abc", "1"))], [ROW, promo, ROW2])
        self.assertEqual(got["status"], "ask")
        self.assertEqual({r["id"] for r, _ in got["cands"]}, {"a1", "a3"})

    def test_unknown_prints_count_nothing(self):
        got = self._pick([(A, None), (A, None)], [])
        self.assertNotIn("status", got or {})

    def test_a_name_outside_the_top_five_is_not_taken(self):
        other = _e("Dark Hole", "c1_0")
        got = self._pick([(other, None), (other, None)], [ROW])
        self.assertNotIn("status", got or {})


class ReadName(unittest.TestCase):
    """_read_name: exactly one candidate's printed name fits (≥ NAME_SURE, every other < NAME_OTHER)."""

    def _read(self, text, cands):
        ls = aiscan.LiveScanner()
        with mock.patch("scanner.ocrscan.available", return_value=True), \
                mock.patch("scanner.ocrscan.find_card", return_value=[]), \
                mock.patch("scanner.ocrscan.read", return_value={"name": text, "set": None, "number": None}), \
                mock.patch("scanner.langcheck.printed_names", side_effect=lambda e: {"en": e["name"]}):
            return ls._read_name(np.zeros((40, 40, 3), np.uint8), (0, 0, 40, 40), None, cands)

    def test_clear_name(self):
        got = self._read("GALAXY CYCLONE", [(A, 0.7), (B, 0.6)])
        self.assertEqual(got[0]["name"], "Galaxy Cyclone")

    def test_two_similar_names_fit_nothing(self):
        dm, dmg = _e("Dark Magician", "d1_0"), _e("Dark Magician Girl", "d2_0")
        self.assertIsNone(self._read("DARK MAGICIAN", [(dm, 0.6), (dmg, 0.6)]))

    def test_unreadable(self):
        self.assertIsNone(self._read("XQZW", [(A, 0.7), (B, 0.6)]))


class OnlyWhereItIsOn(unittest.TestCase):
    def test_game_without_name_confirm_never_reads(self):
        ls = aiscan.LiveScanner()
        def one(*a, **k):   # a frame without a hit that did search (lists are there)
            ls._lists = [[(A, 0.7)]]
            return {"status": "none", "how": "", "entry": None}
        for on, calls in ((False, 0), (True, 1)):
            with mock.patch.object(aiscan.LiveScanner, "_try_one", side_effect=one), \
                    mock.patch.object(aiscan.LiveScanner, "_name_pick", return_value=None) as pick, \
                    mock.patch("games.current") as cur:
                cur.return_value.name_confirm = on
                ls._try(np.zeros((4, 4, 3), np.uint8), [], None, (), center=(0, 0, 4, 4))
                self.assertEqual(pick.call_count, calls)
                ls._try(np.zeros((4, 4, 3), np.uint8), [], None, ())   # the last card's place only: never
                self.assertEqual(pick.call_count, calls)


if __name__ == "__main__":
    unittest.main()
