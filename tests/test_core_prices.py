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


class NetGateTest(unittest.TestCase):
    """Orbit's Core fetches no price and no exchange rate (legal 15.11., R2/R3). Network mocked, never real."""

    def tearDown(self):
        orbit.bind(None)

    def test_fetch_gate(self):   # prices_on of the bound settings, read live; unbound fails closed
        orbit.bind(None)
        self.assertFalse(orbit.prices_fetch_ok())
        s = settings("core")
        orbit.bind(s)
        self.assertFalse(orbit.prices_fetch_ok())
        s["orbit"] = "near"   # level change at runtime (set_level changes the same dict)
        self.assertTrue(orbit.prices_fetch_ok())
        s["orbit"] = "core"
        self.assertFalse(orbit.prices_fetch_ok())
        s["relay"] = {"on": True}   # Full Orbit
        self.assertTrue(orbit.prices_fetch_ok())

    def _price_later(self, lv):
        from unittest import mock
        from scanner.core import Session
        orbit.bind(settings(lv))
        look = mock.Mock(return_value=(1.0, 2.0))
        threads = []

        class Thread:
            def __init__(self, target, daemon=None):
                threads.append(target)

            def start(self):
                pass

        with mock.patch("games.current", return_value=mock.Mock(price_lookup=look)), \
                mock.patch("scanner.core.threading.Thread", Thread):
            Session._price_later(mock.MagicMock(), {"id": "sv1-1_0", "foil": False})
        for t in threads:
            t()
        return look

    def test_scan_price_later(self):
        self.assertFalse(self._price_later("core").called)
        self.assertTrue(self._price_later("near").called)
        self.assertTrue(self._price_later("full").called)

    def _lookup(self, lv):
        import contextlib
        from unittest import mock
        from games import pokemon
        orbit.bind(settings(lv))
        con = mock.Mock()
        con.execute.return_value.fetchone.return_value = None   # not in the card database (or without a price)

        @contextlib.contextmanager
        def connection(*a, **k):
            yield con

        rest = mock.Mock(return_value={"pricing": {"cardmarket": {"trend": 3.5, "trend-holo": None}}})
        with mock.patch("cards.carddb.connection", connection), mock.patch.object(pokemon, "_rest", rest):
            res = pokemon.Pokemon.price_lookup(mock.Mock(), "sv1-1_0")
        return res, rest

    def test_pokemon_lookup(self):   # E1a (16.11.): no TCGdex price request in any level, only the card database
        for lv in ("core", "near", "full"):
            res, rest = self._lookup(lv)
            self.assertIsNone(res, lv)
            rest.assert_not_called()

    def _currency(self, lv, code):
        import collections
        from unittest import mock
        from ui import qsetpages
        s = collections.defaultdict(str, settings(lv))
        s["currency"] = "EUR"
        ctrl = mock.MagicMock()
        ctrl.settings = s
        picked = []

        def choice(ui, options, current, fn, **k):
            if options is not None and fn.__name__ == "set_currency":
                picked.append(fn)
            return mock.MagicMock()

        ran = []
        with mock.patch.object(qsetpages, "_choice", choice), mock.patch.object(qsetpages, "_set"), \
                mock.patch.object(qsetpages.currency, "set_current"), \
                mock.patch("ui.librarycore.run_async", lambda parent, fn, cb: ran.append(fn)):
            qsetpages.page_collection(mock.MagicMock(), mock.MagicMock(ctrl=ctrl))
            self.assertEqual(len(picked), 1)
            picked[0](code)
        return [f for f in ran if f is qsetpages.currency.refresh]

    def test_currency_switch(self):
        self.assertEqual(self._currency("core", "USD"), [])
        self.assertEqual(len(self._currency("near", "USD")), 1)
        self.assertEqual(len(self._currency("full", "USD")), 1)
        self.assertEqual(self._currency("near", "EUR"), [])   # euros need no rate fetch

    def test_friends_text(self):   # R4: the new wording, with its German line
        from locales import de
        src = pathlib.Path(__file__).resolve().parents[1] / "ui" / "qshared.py"
        key = "Friends only exist in Full Orbit – until then you share nothing."
        self.assertIn(key, src.read_text("utf-8"))
        self.assertEqual(de.TEXTS[key], "Freunde gibt es erst im Ganzen Orbit – bis dahin teilst du nichts.")
        self.assertNotIn("until then everything stays on this computer", src.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
