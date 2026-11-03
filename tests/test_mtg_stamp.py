"""Magic prerelease promos: same art and collector line as the normal print, only the gold date stamp differs
(games/mtg.py: date_stamp_in, Magic.stamped_twin; Recognizer._stamp_check uses both after counting).
The OCR texts below are what the scanner really read on the scan bench (stamp at the bottom right of the art).

    python -m unittest tests/test_mtg_stamp.py
"""
import sqlite3
import unittest

from cards import carddb
from games import mtg
from games.mtg import date_stamp_in


class DateStamp(unittest.TestCase):
    def test_stamps_read_by_ocr(self):
        for text in ("22-23 APRIL 2017", "22-23APRL2017", "-23APR12017 NA",   # Amonkhet, OCR running it together
                     "2019年4月27—28日 PY", "2019年4月27一28日"):                    # War of the Spark, Japanese walker
            self.assertTrue(date_stamp_in(text), text)

    def test_no_stamp(self):
        for text in ("", "NA", "ANA ZOMBIE CREATURE TOKEN.", "TM & © 2017 WIZARDS OF THE COAST",   # a year alone is no stamp
                     "MPR1205 NA", "-23AD612017 NA",                                                # stamp too garbled: no read (= as before)
                     "APRIL SHOWERS", "Draw a card."):
            self.assertFalse(date_stamp_in(text), text)


class Twin(unittest.TestCase):
    """The one date-stamped promo of a print: set "p" + set, same digits in the number, same artist."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript(carddb.SCHEMA)
        rows = [("akh", "97", "Liliana, Death's Majesty", "Chris Rallis", ""),
                ("pakh", "97s", "Liliana, Death's Majesty", "Chris Rallis", "setpromo,prerelease,datestamped"),
                ("pakh", "97p", "Liliana, Death's Majesty", "Chris Rallis", "setpromo,promopack,stamped"),
                ("war", "234", "Saheeli, Sublime Artificer", "Wisnu Tan", ""),
                ("war", "234★", "Saheeli, Sublime Artificer", "Ryota Murayama", "jpwalker"),
                ("pwar", "234s", "Saheeli, Sublime Artificer", "Wisnu Tan", "setpromo,prerelease,datestamped"),
                ("pwar", "234s★", "Saheeli, Sublime Artificer", "Ryota Murayama", "setpromo,prerelease,datestamped,jpwalker"),
                ("cmd", "260", "Skullclamp", "Luca Zontini", ""),
                ("m10", "5", "Twice", "A", ""),
                ("pm10", "5s", "Twice", "A", "datestamped"),
                ("pm10", "5d", "Twice", "A", "datestamped")]
        for i, (s, n, name, artist, promo) in enumerate(rows):
            self.con.execute("INSERT INTO cards (id, name, lang, set_code, number, artist, promo_types) "
                             "VALUES (?, ?, 'en', ?, ?, ?, ?)", (f"id{i}", name, s, n, artist, promo))

    def twin(self, s, n, name):
        row = mtg.GAME.stamped_twin(self.con, {"set": s, "number": n, "name": name})
        return row and (row["set_code"], row["number"])

    def test_the_one_prerelease_promo(self):
        self.assertEqual(self.twin("akh", "97", "Liliana, Death's Majesty"), ("pakh", "97s"))      # not the promo pack 97p
        self.assertEqual(self.twin("AKH", "97", "Liliana, Death's Majesty"), ("pakh", "97s"))

    def test_the_artist_separates_alternate_art(self):
        self.assertEqual(self.twin("war", "234", "Saheeli, Sublime Artificer"), ("pwar", "234s"))
        self.assertEqual(self.twin("war", "234★", "Saheeli, Sublime Artificer"), ("pwar", "234s★"))

    def test_none_or_several_change_nothing(self):
        self.assertIsNone(self.twin("cmd", "260", "Skullclamp"))
        self.assertIsNone(self.twin("m10", "5", "Twice"))   # two stamped prints: no guess


class StampAndLanguage(unittest.TestCase):
    """_stamp_check and the language check (_set_lang_checked) run in separate threads after counting and correct the
    same card. In either order the result is the stamped promo in the read language – the language check must not
    put the normal print back (print_in_lang would find it via the artist)."""

    NORMAL = {"id": "war-234j_0", "name": "Saheeli, Sublime Artificer", "set": "WAR", "number": "234★",
              "rarity": "uncommon", "finishes": ["nonfoil", "foil"], "eur": 1.0, "eur_foil": 3.0,
              "img": "data/card-images/war/234★_0.jpg"}
    PROMO = dict(NORMAL, id="pwar-234sj_0", set="PWAR", number="234s★", finishes=["foil"], eur=None, eur_foil=9.0,
                 img="data/card-images/pwar/234s★_0.jpg")

    def setUp(self):
        import threading
        from unittest import mock
        import numpy as np
        from scanner import core, recognizer
        self.session = core.Session()
        self.session.add_manual(dict(self.NORMAL))
        self.added = self.session.packs[-1]["cards"][-1]["added"]
        rec = recognizer.Recognizer.__new__(recognizer.Recognizer)   # no camera, no AI: only the two checks
        rec.session, rec.settings = self.session, {}
        rec._print_lock, rec._stamped = threading.Lock(), {}
        self.rec = rec
        self.patches = [mock.patch.object(recognizer.games, "current", return_value=mtg.GAME),
                        mock.patch.object(mtg.GAME, "stamped_twin", side_effect=lambda con, entry: dict(self.PROMO)),
                        mock.patch.object(mtg.GAME, "has_stamp", return_value=True),
                        mock.patch.object(recognizer.carddb, "connect"),
                        mock.patch.object(recognizer.carddb, "entry_from_row", side_effect=dict),
                        mock.patch.object(recognizer.hybrid, "image_url", return_value=""),
                        mock.patch.object(recognizer.langcheck, "card_view", return_value=np.zeros((8, 8, 3), np.uint8)),
                        # the dangerous case: the language check would pick the normal print again
                        mock.patch.object(recognizer.langcheck, "print_in_lang", return_value=dict(self.NORMAL))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def stamp(self):
        self.rec._stamp_check(dict(self.NORMAL), self.added, None, {"img": object(), "box": None})

    def language(self):
        self.rec._set_lang_checked(dict(self.NORMAL), self.added, "ja")

    def result(self):
        card = self.session.packs[-1]["cards"][-1]
        return card["set"], card["number"], card["lang"], card["foil"]

    def test_stamp_then_language(self):
        self.stamp()
        self.language()
        self.assertEqual(self.result(), ("PWAR", "234s★", "ja", True))

    def test_language_then_stamp(self):
        self.language()
        self.stamp()
        self.assertEqual(self.result(), ("PWAR", "234s★", "ja", True))

    def test_card_changed_meanwhile_is_left_alone(self):
        from scanner import recognizer
        other = dict(self.NORMAL, id="x_0", set="SLD", number="9")
        with mock_print_in_lang(recognizer, other):
            self.language()                     # the language check moved it to another print
        self.stamp()
        self.assertEqual(self.result()[:2], ("SLD", "9"))


def mock_print_in_lang(recognizer, row):
    from unittest import mock
    return mock.patch.object(recognizer.langcheck, "print_in_lang", return_value=dict(row))


if __name__ == "__main__":
    unittest.main()
