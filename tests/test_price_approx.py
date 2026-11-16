"""„≈" on euro prices converted from dollars (legal 14.11.2026, lead: everywhere – detail, lists, sums, trade, value
history, scan page, logs, decks, set completion, alerts, search, stats; one converted price makes a sum „≈"; real
Cardmarket euros stay without a sign). A test collection with only converted prices: every price output checked.
Stand-ins only – no card database, no window, nothing real.

    python -m unittest tests.test_price_approx
"""
import os
import threading
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cards import currency  # noqa: E402

DAY = "2026-11-14"
A = "≈"


def converted(on=True, sids=None):
    """All prints converted (on) – or only those in sids. The rate day is DAY."""
    est = (lambda s, game=None: bool(s) and (sids is None or s in sids)) if on else (lambda s, game=None: False)
    return [mock.patch.object(currency, "estimated", est),
            mock.patch.object(currency, "rate_day_of", lambda s, game=None: DAY if est(s) else None),
            mock.patch("system.orbit.prices_shown", lambda *a: True),
            mock.patch("system.orbit.prices_on", lambda *a: True)]


class Base(unittest.TestCase):
    on, sids = True, None

    def setUp(self):
        self.p = converted(self.on, self.sids)
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()


ITEM = {"id": "s1_0", "name": "Blue-Eyes", "set": "lob", "number": "1", "lang": "en", "foil": False, "count": 2,
        "eur": 12.3, "eur_foil": None, "uid": "u1", "rarity": "rare"}
DBROW = {"id": "s1", "name": "Blue-Eyes", "set_code": "lob", "number": "1", "eur": 12.3, "eur_foil": None,
         "rarity": "rare", "type_line": "Monster", "mana_cost": "", "cmc": 0, "colors": "", "color_identity": "",
         "oracle_text": "", "legalities": "{}", "keywords": "", "layout": "normal"}
LINE = dict(ITEM, price=12.3, delta=1, added=1.0, pack=1, idx=0)


class Helpers(Base):
    def test_fmt_tip_sum(self):
        self.assertEqual(currency.fmt(12.3, True), "≈ 12,30 €")
        self.assertEqual(currency.fmt(12.3), "12,30 €")
        self.assertEqual(currency.approx_tip(DAY), "converted from the TCGplayer US price (ECB rate of 14.11.2026)")
        self.assertEqual(currency.approx_tip(None), "converted from the TCGplayer US price")
        self.assertEqual(currency.approx_sum([(10.0, "s1"), (2.3, "s2")]), (12.3, True, DAY))


class Library(Base):
    def test_rows_sums_tiles_links(self):
        from ui import librarycore
        self.assertTrue(librarycore.eur(5, True).startswith(A))
        self.assertEqual(librarycore.price_tip("s1"), (True, currency.approx_tip(DAY)))
        rows = [{"sid": "s1", "price": 2.0, "count": 3}, {"sid": "s2", "price": 1.0, "count": 1}]
        self.assertEqual(librarycore.rows_sum(rows), (7.0, True, DAY))
        self.assertIn("≈ 7,00 €", librarycore.approx_link(7.0, True, DAY))
        self.assertIn("approx:" + DAY, librarycore.approx_link(7.0, True, DAY))
        from ui import quickshell
        cls = next(v for v in vars(quickshell).values() if isinstance(v, type) and "approxTip" in vars(v))
        self.assertEqual(cls.approxTip(None, "value|approx:" + DAY), currency.approx_tip(DAY))
        self.assertEqual(cls.approxTip(None, "value"), "")

    def test_group_tree(self):
        from ui import grouping
        rows = [{"sid": "s1", "price": 2.0, "count": 1, "set": "lob", "name": "a"}]
        t = grouping.tree(rows, ["set"], [])
        self.assertTrue(t["root"]["est"])
        self.assertTrue(t["cols"][0]["nodes"][0]["est"])
        self.assertEqual(t["root"]["day"], DAY)

    def test_collection_summary(self):
        from collection import collection
        fake = types.SimpleNamespace(lock=threading.Lock(), items=[ITEM])
        s = collection.Collection.summary(fake)
        self.assertEqual((s["value"], s["value_est"], s["value_day"]), (24.6, True, DAY))


class Trade(Base):
    def test_rows_and_sums(self):
        from collection import tradelib
        rows = [{"db": {"id": "s1"}, "price": 3.0, "count": 1}]
        self.assertTrue(tradelib.rows_est(rows))
        self.assertTrue(tradelib.card_eur(3.0, tradelib.rows_est(rows)).startswith(A))
        self.assertTrue(tradelib.value(3.0, True).startswith(A))
        self.assertEqual(tradelib.rows_tip(rows), currency.approx_tip(DAY))
        self.assertFalse(tradelib.eur(5.0).startswith(A))           # cash a friend typed: never „≈"

    def test_offer_picture_rows(self):
        from collection import tradelib
        self.assertTrue(tradelib.row_est({"est": True}))
        self.assertFalse(tradelib.row_est({"est": False, "db": {"id": "s1"}}))   # another game's print


class ScanAndLogs(Base):
    def test_lines_packs_stats(self):
        from scanner import core
        self.assertTrue(core.entry_est(LINE))
        st = core.session_stats([{"cards": [LINE], "opened": 1}], {"kind": "packs"})
        self.assertEqual((st["est"], st["est_day"]), (True, DAY))
        self.assertEqual(core.session_est({"packs": [{"cards": [LINE]}]}), (True, DAY))
        from ui import scanlook, scantiles
        self.assertTrue(scanlook.eur(1.0, True).startswith(A))
        self.assertTrue(scanlook.signed(2.0, est=True).startswith(A))
        row = scantiles.card_row(LINE)
        self.assertTrue(row["price"].startswith(A) and row["priceShort"].startswith(A))
        self.assertEqual(row["priceTip"], currency.approx_tip(DAY))
        self.assertTrue(scantiles.pack_list([LINE], 1)[0]["total"].startswith(A))

    def test_search_and_classic_panels(self):
        from ui import panels
        cls = next(v for v in vars(panels).values() if isinstance(v, type) and hasattr(v, "price_text"))
        self.assertTrue(cls.price_text({"id": "s1_0", "eur": 4.0}).startswith(A))

    def test_share_picture_text(self):
        from collection import share
        self.assertTrue(share.eur(3.0, True).startswith(A))


class Decks(Base):
    def test_analyze_and_rows(self):
        from collection import deckcore, decks
        a = decks.analyze({"cards": [{"sid": "s1", "count": 2, "board": "main"}], "format": "casual"}, {"s1": DBROW})
        self.assertTrue(a["price_est"])
        self.assertTrue(deckcore.eur(a["price"], a["price_est"]).startswith(A))
        self.assertTrue(deckcore._price(DBROW).startswith(A))
        from collection import deckshare
        self.assertTrue(deckshare.eur(1.0, True).startswith(A))


class SetsAlertsHistory(Base):
    def test_completion(self):
        from cards import completion
        self.assertTrue(completion.est([DBROW]))
        self.assertTrue(completion.eur(5.0, True).startswith(A))

    def test_alerts(self):
        from collection import alarms
        self.assertTrue(alarms.eur(5.0, True).startswith(A))
        self.assertTrue(alarms.price_est({"src": "tcg", "kind": "wish", "name": "x"}, "s9", 1.0))
        self.assertTrue(alarms.price_est({"src": "cm", "kind": "wish", "name": "x"}, "s1", 1.0))
        self.assertFalse(alarms.eur(5.0).startswith(A))             # the user's own limit

    def test_value_history(self):
        from cards import valuehist
        with mock.patch("cards.pricehist.series_many", lambda sids: {}):
            res = valuehist.collection_series([ITEM], starts={})
        self.assertEqual(res["conv"], 2)
        spec = valuehist.chart_spec(res)
        self.assertIn(A, spec["sub"])
        self.assertTrue(any(A in line for tip in spec["body"]["tips"] for line in tip))

    def test_stats_charts(self):
        from ui import qcharts
        w = types.SimpleNamespace(rows=[("Blue-Eyes", 12.3, "LOB", True)], money=True, fmt=currency.fmt, color="#fff")
        self.assertTrue(qcharts._hbars(w)["rows"][0]["text"].startswith(A))


class RealCardmarket(Base):
    """Nothing converted: no „≈" anywhere (legal: real Cardmarket euros without a sign)."""
    on = False

    def test_no_sign(self):
        from ui import librarycore, scantiles
        from collection import decks, tradelib
        self.assertEqual(librarycore.rows_sum([{"sid": "s1", "price": 2.0, "count": 1}])[1], False)
        self.assertNotIn(A, scantiles.card_row(LINE)["price"])
        self.assertFalse(tradelib.rows_est([{"db": {"id": "s1"}, "price": 3.0}]))
        self.assertFalse(decks.analyze({"cards": [{"sid": "s1", "count": 1, "board": "main"}]}, {"s1": DBROW})["price_est"])


class MixedSum(Base):
    """One converted price among real ones: the sum gets „≈", the real row stays plain."""
    sids = {"s2"}

    def test_mixed(self):
        from ui import librarycore
        rows = [{"sid": "s1", "price": 5.0, "count": 1}, {"sid": "s2", "price": 1.0, "count": 1}]
        self.assertEqual(librarycore.rows_sum(rows), (6.0, True, DAY))
        self.assertEqual(librarycore.price_tip("s1"), (False, ""))


class OtherGame(unittest.TestCase):
    """A Yu-Gi-Oh! card in a Magic trade (lead 14.11.): its own game's card database decides."""

    def test_other_games_database(self):
        import games
        from games import base
        from collection import tradelib
        cur = games.current().key
        other = "yugioh" if cur != "yugioh" else "mtg"
        maps = {other: {"y1": DAY}}
        with mock.patch.object(base, "price_est_map", lambda game=None: maps.get(game, {})):
            self.assertTrue(currency.estimated("y1", other))
            self.assertEqual(currency.rate_day_of("y1", other), DAY)
            self.assertFalse(currency.estimated("y2", other))
            row = {"db": {"id": "y1"}, "game": other, "price": 3.0, "count": 1}
            self.assertTrue(tradelib.rows_est([row]))
            self.assertEqual(tradelib.rows_tip([row]), currency.approx_tip(DAY))

    def test_cache_per_file(self):
        from games import base
        base.price_est_changed()
        self.assertIsInstance(base.price_est_map(), dict)   # the open game: no file in tests -> {}


class Texts(unittest.TestCase):
    def test_converted_is_never_called_cardmarket(self):
        """legal 14.11. (lead): the detail's converted row reads „Price in € (converted from TCGplayer)"."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1] / "ui" / "librarycore.py").read_text("utf-8")
        self.assertIn('lab = (tr("Price in €") + fin', src)
        from locales import de
        self.assertEqual(de.TEXTS["Price in €"], "Preis in €")
        self.assertEqual(de.TEXTS["(converted from TCGplayer)"], "(umgerechnet aus TCGplayer)")

    def test_german_and_sources(self):
        from locales import de
        self.assertEqual(de.TEXTS["converted from the TCGplayer US price (ECB rate of {date})"],
                         "umgerechnet aus dem US-Preis von TCGplayer (Kurs EZB vom {date})")
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1] / "app.py").read_text("utf-8")
        self.assertIn("<b>Exchange rates:</b> European Central Bank (reference rates, via Frankfurter)", src)
        self.assertTrue(any("<b>Wechselkurse:</b> Europäische Zentralbank (Referenzkurse, über Frankfurter)" in v
                            for v in de.TEXTS.values()))

    def test_core_shows_nothing(self):
        with mock.patch("system.orbit.prices_shown", lambda *a: False):
            from ui import librarycore, scanlook
            self.assertEqual(librarycore.eur(5, True), "")
            self.assertEqual(scanlook.eur(5, True), "")


if __name__ == "__main__":
    unittest.main()
