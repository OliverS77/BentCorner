"""Orbit's Core shows no card prices anywhere (Oliver/legal 06.11.): every price helper is empty in Core and unchanged
from Near Orbit on; what the user typed himself (spent on packs, money between friends) stays; the CSV exports keep
their price columns, empty. The sweep over all pages (offscreen) is labs\\_library\\kernpreise\\kern2.py. Only temporary
files, never the real settings.

    python -m unittest tests/test_core_prices.py
"""
import csv
import pathlib
import tempfile
import unittest

from system import orbit

GROUP = {"id": "aaaa-1_0", "sid": "aaaa-1", "name": "Lightning Bolt", "set": "2X2", "number": "117", "lang": "en",
         "foil": False, "rarity": "uncommon", "eur": 12.5, "eur_foil": None, "count": 2, "last": 1700000000}


def settings(level):
    return {"orbit": "near" if level == "full" else level, "relay": {"on": level == "full"}}


class LevelTest(unittest.TestCase):
    def tearDown(self):
        orbit.bind(None)

    def test_unbound_shows(self):   # tools and tests without the app: as before
        orbit.bind(None)
        self.assertTrue(orbit.prices_shown())

    def test_only_core_hides(self):
        for lv, shown in (("core", False), ("near", True), ("full", True)):
            orbit.bind(settings(lv))
            self.assertEqual(orbit.prices_shown(), shown, lv)
            self.assertEqual(orbit.level(settings(lv)), lv)

    def test_follows_the_settings_live(self):
        s = settings("near")
        orbit.bind(s)
        self.assertTrue(orbit.prices_shown())
        s["orbit"] = "core"
        self.assertFalse(orbit.prices_shown())


class HelpersTest(unittest.TestCase):
    def tearDown(self):
        orbit.bind(None)

    def helpers(self):
        from cards import completion
        from collection import alarms, deckcore, tradelib
        from ui import librarycore, scanlook, searchbox
        return {"librarycore": librarycore.eur, "scanlook": scanlook.eur, "signed": scanlook.signed,
                "searchbox": searchbox.eur, "deckcore": deckcore.eur, "completion": completion.eur,
                "alarms": alarms.eur, "tradelib.value": tradelib.value}

    def test_core_empty_near_and_full_as_before(self):
        for lv in ("core", "near", "full"):
            orbit.bind(settings(lv))
            for name, fn in self.helpers().items():
                got = fn(12.5)
                if lv == "core":
                    self.assertEqual(got, "", (lv, name))
                else:
                    self.assertIn("12,5", got, (lv, name))

    def test_own_money_stays_in_core(self):
        from collection import tradelib
        from ui import scanlook
        orbit.bind(settings("core"))
        self.assertEqual(scanlook.money(29.94), "29,94 €")   # spent on packs
        self.assertEqual(tradelib.eur(5), "5,00 €")         # money between friends (trade ticket)

    def test_signed_leaves_no_sign_alone(self):
        from ui import scanlook
        orbit.bind(settings("core"))
        self.assertEqual(scanlook.signed(-4.0), "")
        orbit.bind(settings("near"))
        self.assertEqual(scanlook.signed(-4.0), "−4,00 €")


class SortLabelTest(unittest.TestCase):
    """lead 06.11.: the sort key never empty – the chosen sort is always one the list offers, in every level, also
    with a saved price sort (it rests in Core, the setting stays)."""

    def tearDown(self):
        orbit.bind(None)

    def test_chosen_sort_is_always_offered(self):
        import types
        from ui import qlibrary
        for saved in ("price", "name", "relevance"):
            fake = types.SimpleNamespace(lib=types.SimpleNamespace(sort=types.SimpleNamespace(currentData=lambda s=saved: s)))
            for lv in ("core", "near", "full", "core", "near"):   # back and forth, as the level changes
                orbit.bind(settings(lv))
                keys = [x["key"] for x in qlibrary.LibraryBackend.sorts.fget(fake)]
                chosen = qlibrary.LibraryBackend.sort.fget(fake)
                self.assertIn(chosen, keys, (saved, lv))
                self.assertEqual("price" in keys, lv != "core", lv)

    def test_level_change_asks_every_view_again(self):
        from ui import qlibrary
        hits = []

        class B:
            changed = type("S", (), {"emit": lambda self: hits.append(1)})()
        b = B()
        qlibrary.ALL.add(b)
        try:
            qlibrary.orbit_changed()
        finally:
            qlibrary.ALL.discard(b)
        self.assertEqual(hits, [1])


class ExportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        orbit.bind(None)
        self._tmp.cleanup()

    def read(self, p, delim):
        with open(p, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f, delimiter=delim))

    def test_collection_csv_keeps_columns_empty_in_core(self):
        from collection import collection as coll
        for lv in ("core", "near"):
            orbit.bind(settings(lv))
            p = self.dir / f"x-{lv}.csv"
            coll.export_csv([GROUP], p, "excel", {})
            head, row = self.read(p, ";")
            self.assertIn("Preis (€)", head)
            want = "" if lv == "core" else "12,50"
            self.assertEqual(row[head.index("Preis (€)")], want, lv)
            self.assertEqual(row[head.index("Wert (€)")], "" if lv == "core" else "25,00", lv)
            p = self.dir / f"m-{lv}.csv"
            coll.export_csv([GROUP], p, "manabox", {})
            head, row = self.read(p, ",")
            self.assertEqual(row[head.index("Purchase price")], "" if lv == "core" else "12.50", lv)

    def test_trade_csv_price_empty_in_core(self):
        from collection import trade
        for lv in ("core", "near"):
            orbit.bind(settings(lv))
            p = self.dir / f"t-{lv}.csv"
            trade.export_custom([GROUP], p, ["name", "price"])
            head, row = self.read(p, ";")
            self.assertEqual(row[head.index("Preis")], "" if lv == "core" else "12,50", lv)


if __name__ == "__main__":
    unittest.main()
