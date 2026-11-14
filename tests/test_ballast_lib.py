"""Ballast round after review 0.9.7 (lead 10.11.): one list reader for the wishlist, one file list for backup ZIP and
checksum, one price rule and one "not issued to you" in the trade view. Throwaway folders only.

    python -m unittest tests/test_ballast_lib.py
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_autobackup import _Home  # noqa: E402


class WishLinesTest(unittest.TestCase):
    def test_read_like_a_deck_list(self):
        from ui.importview import wish_lines
        text = "Deck\n1 Sol Ring [Ramp]\n4 Arcane Signet (CMM) 412 *F*\nLlanowar Elves\n99999999 Island\nSideboard\n"
        self.assertEqual(wish_lines(text), [(1, "Sol Ring", ""), (4, "Arcane Signet", "cmm"), (1, "Llanowar Elves", ""),
                                            (99_999, "Island", "")])


class PersonalFilesTest(_Home):
    def test_zip_and_checksum_walk_the_same_files(self):
        from system import autobackup, datastore
        for rel in ("data/my-data/collection.json", "data/my-data/trash/x.json", "data/my-data/a.tmp",
                    "data/collectibles/x.partial", "data/collectibles/t/a.json", "settings.json"):
            self.write(rel, "{}")
        got = [(name, rel) for _f, name, rel in datastore.personal_files()]
        self.assertEqual(got, [("my-data", "collection.json"), ("collectibles", "t/a.json"), ("settings.json", "")])
        before = autobackup.content_sum()
        self.write("data/my-data/trash/y.json", "{}")   # the trash never changes the sum
        self.assertEqual(autobackup.content_sum(), before)


class TradeHelpersTest(unittest.TestCase):
    def test_price_rule(self):
        from ui.tradeview import _price
        self.assertIsNone(_price(None, True))
        self.assertEqual(_price({"eur": 1.0, "eur_foil": 3.0}, True), 3.0)
        self.assertEqual(_price({"eur": 1.0, "eur_foil": None}, True), 1.0)
        self.assertEqual(_price({"eur": 1.0, "eur_foil": 3.0}, False), 1.0)


if __name__ == "__main__":
    unittest.main()
