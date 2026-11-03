"""Search by year and artist (library and the card search while scanning), the card search's details, the card search
offered in the status line instead of opening by itself, and no language image asked for a print that doesn't
exist in that language.

    python -m unittest tests/test_search_year.py
"""
import types
import unittest
from unittest import mock

from cards import carddb
from scanner.scan_ctl import ScanControl
from tests.test_lorcana import _LorcanaDB
from ui import searchbox
from ui.panels import CardPanel


class YearInTheText(_LorcanaDB):
    def test_split(self):
        self.assertEqual(searchbox.split_year("stitch 2025"), (2025, "stitch"))
        self.assertEqual(searchbox.split_year("2023"), (2023, ""))
        self.assertEqual(searchbox.split_year("hades 5"), (None, "hades 5"))
        self.assertEqual(searchbox.split_year("hades 3000"), (None, "hades 3000"))   # not a year: as before
        self.assertEqual(searchbox.split_year("7 2025"), (None, "7 2025"))          # next to a set code: a number

    def test_scan_search_filters_by_year_and_syntax(self):
        names = lambda q: sorted({e["name"] for e, _u in CardPanel.search_db(q)})   # noqa: E731
        self.assertEqual(names("hades 2023"), ["Hades - King of Olympus"])
        self.assertEqual(names("hades 2025"), [])
        self.assertIn("Stitch - Rock Star", names("year>=2025"))
        self.assertNotIn("Hades - King of Olympus", names("year>=2025"))
        self.assertIn("Hades - King of Olympus", names('a:"test artist" hades'))

    def test_library_filters(self):
        f = {}
        searchbox.apply_criterion(f, "year", "2024", False, "<=")
        self.assertEqual(f["ranges"]["year"], (None, 2024.0))
        rows = carddb.search("", **f)
        self.assertTrue(rows and all(r["released"][:4] <= "2024" for r in rows))


class Details(_LorcanaDB):
    def test_set_name_year_artist_rules(self):
        card = carddb.entry_from_row(carddb.card(carddb.search("be prepared")[0]["id"]))
        meta, details, rules = CardPanel.card_details(card)
        self.assertIn("The First Chapter", meta)
        self.assertIn("2023", meta)
        self.assertIn("Test Artist", details)
        self.assertEqual(rules, "Banish all characters.")

    def test_unknown_card_only_set_and_number(self):
        meta, details, rules = CardPanel.card_details({"id": "nope_0", "set": "XX", "number": "1", "rarity": ""})
        self.assertEqual((meta, details, rules), ("XX #1", "", ""))


class LanguageImages(_LorcanaDB):
    def test_known_languages_only(self):
        self.assertFalse(carddb.lacks_language("1", "5", "de"))   # Hades exists in German
        self.assertFalse(carddb.lacks_language("1", "5", "en"))
        self.assertTrue(carddb.lacks_language("7", "2", "de"))    # Mulan: only English in the data – don't ask
        self.assertFalse(carddb.lacks_language("9", "99", "de"))  # no language data for it (new set): ask as before


class OfferInTheStatusLine(unittest.TestCase):
    def ctrl(self):
        panel = types.SimpleNamespace(hidden=True, searched=None, question=None)
        panel.isHidden = lambda: panel.hidden
        panel.set_search = lambda t: setattr(panel, "searched", t)
        stream = types.SimpleNamespace(card_panel=panel, edit_index=None, opened=0)

        def open_add():
            stream.opened += 1
            panel.hidden = False
        stream.open_add = open_add
        stream.close_card_panel = lambda: setattr(panel, "hidden", True)
        rec = types.SimpleNamespace(unknown_offer=None, unknown_gone=False, offer_open=False, counted=[], pending=None,
                                    lang_ask=None)
        rec.counted_by_hand = rec.counted.append
        c = types.SimpleNamespace(recognizer=rec, stream=stream, question_wait=None)
        for name in ("unknown_card_check", "open_offered_search", "add_card", "added_by_hand", "open_question"):
            setattr(c, name, getattr(ScanControl, name).__get__(c))
        return c

    def test_nothing_opens_by_itself(self):
        c = self.ctrl()
        c.recognizer.unknown_offer = {"name": "Stitch"}
        c.unknown_card_check()
        self.assertEqual(c.stream.opened, 0)
        self.assertEqual(c.search_offer, {"name": "Stitch"})

    def test_k_opens_with_the_name_and_counts_once(self):
        c = self.ctrl()
        c.recognizer.unknown_offer = {"name": "Stitch"}
        c.unknown_card_check()
        c.add_card()   # key K
        self.assertEqual((c.stream.opened, c.stream.card_panel.searched), (1, "Stitch"))
        self.assertIsNone(c.search_offer)
        self.assertTrue(c.recognizer.offer_open)
        c.added_by_hand({"name": "Stitch - Rock Star"})
        self.assertEqual(c.recognizer.counted, ["Stitch - Rock Star"])   # not counted a second time by the scanner

    def test_gone_or_recognized_leaves_no_trace(self):
        c = self.ctrl()
        c.recognizer.unknown_offer = {"name": "Stitch"}
        c.unknown_card_check()
        c.recognizer.unknown_gone = True
        c.unknown_card_check()
        self.assertIsNone(c.search_offer)
        c.add_card()   # K now: the plain search, nothing counted by hand
        self.assertEqual((c.stream.opened, c.stream.card_panel.searched), (1, None))
        c.added_by_hand({"name": "Other"})
        self.assertEqual(c.recognizer.counted, [])


if __name__ == "__main__":
    unittest.main()


class NameHitsFirst(unittest.TestCase):
    """Oliver's case: "Energy Switch 75" put Klink (BW5 #75, energy and switch only in its rules text) on top."""

    def test_rank(self):
        self.assertEqual(carddb.name_rank({"name": "Energy Switch"}, "energy switch"), 0)
        self.assertEqual(carddb.name_rank({"name": "Energy Switch"}, "energy sw"), 1)
        self.assertEqual(carddb.name_rank({"name": "Rainbow Energy Switch"}, "energy switch"), 2)
        self.assertEqual(carddb.name_rank({"name": "Klink"}, "energy switch"), 3)

    def test_scan_search_puts_the_name_first(self):
        def row(i, name, set_code, img):
            return {"id": i, "name": name, "set_code": set_code, "number": "75", "rarity": "common", "booster": 1,
                    "finishes": "", "eur": None, "eur_foil": None, "img_small": img, "faces": None, "lang": "en"}
        rows = [row("bw5-75", "Klink", "bw5", "https://img/klink.png"), row("ex16-75", "Energy Switch", "ex16", "")]
        game = types.SimpleNamespace(image_url=None, card_url=lambda s, n: "")
        with mock.patch.object(carddb, "exists", lambda: True), mock.patch.object(carddb, "search", lambda *a, **k: rows), \
                mock.patch("ui.searchbox.split_print_query", lambda t: (None, "75", "Energy Switch")), \
                mock.patch("ui.searchbox.split_year", lambda t: (None, t)), \
                mock.patch("games.current", lambda: game), mock.patch("scanner.hybrid.image_url", lambda r: r["img_small"] or None):
            got = [e["name"] for e, _u in CardPanel.search_db("Energy Switch 75")]
        self.assertEqual(got, ["Energy Switch", "Klink"])


class PrintedNumber(_LorcanaDB):
    """"slowbro 43": which print is mine? The row says set, set name, year, "#43/62" where the data knows the size."""

    def test_row_with_year_and_set_size(self):
        import sqlite3
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE set_ext (set_code TEXT PRIMARY KEY, cm INTEGER, tcg INTEGER, abbr TEXT, official INTEGER)")
        con.execute("INSERT INTO set_ext VALUES ('1', NULL, NULL, NULL, 204)")
        con.commit()
        con.close()
        carddb._TOTALS.clear()
        CardPanel._rows.clear()
        card = carddb.entry_from_row(carddb.card(carddb.search("be prepared")[0]["id"]))
        panel = CardPanel.__new__(CardPanel)
        _name, sub = panel.row_text(card, True)
        self.assertIn("The First Chapter", sub)
        self.assertIn("2023", sub)
        self.assertIn("#128/204", sub)
        self.assertNotIn("online", sub)
        self.assertEqual(CardPanel.number_text(dict(card, number="205")), "#205")   # beyond the printed size
        self.assertEqual(CardPanel.number_text(dict(card, set="7")), "#128")         # no size known: none shown
        carddb._TOTALS.clear()
