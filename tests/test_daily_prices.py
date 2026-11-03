"""Daily prices shared by the games (games/base.py, CLEANUP line 40): Cardmarket guide + TCGplayer from our price server
-> card database + price history. Temp card database and temp price history, no network.

    python -m unittest tests/test_daily_prices.py
"""
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

from cards import carddb, pricehist
from games import base

GUIDE = {"priceGuides": [{"idProduct": 11, "trend": 2.5, "trend-holo": 7.0, "avg30": 2.0, "avg7": 2.2, "avg1": 2.4},
                         {"idProduct": 12, "trend": 0.3}]}
TCG = {"500": {"901": {"Normal": 1.1, "Cold Foil": 4.4, "Holofoil": 9.9}, "902": {"Normal": None, "Foil": 3.3}}}
EXT = [("c1", 11, 901), ("c2", 12, 902), ("c3", None, None)]


class DailyPrices(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        con = sqlite3.connect(d / "cards.sqlite")
        con.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, eur REAL, eur_foil REAL, usd REAL, usd_foil REAL)")
        con.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?)", [("c1", None, None, None, None),
                                                                     ("c2", None, None, None, None),
                                                                     ("c3", 9.0, None, None, None)])
        con.commit()
        con.close()
        self.downloads = 0

        def get_large(url, **kw):
            self.downloads += 1
            return json.dumps(GUIDE).encode()
        self.p = [mock.patch.object(carddb, "DB_PATH", d / "cards.sqlite"),
                  mock.patch.object(pricehist, "DB", d / "price-history.sqlite"),
                  mock.patch.object(base, "tcgplayer_table", lambda net, cache, name: (TCG, False)),
                  mock.patch("net.netpolite.get_large", get_large)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def card(self, sid):
        con = sqlite3.connect(carddb.DB_PATH)
        try:
            return con.execute("SELECT eur, eur_foil, usd, usd_foil FROM cards WHERE id = ?", (sid,)).fetchone()
        finally:
            con.close()

    def test_prices_and_foil_preference(self):
        n = base.daily_prices(EXT, "https://cm/x.json", "lorcana-tcgplayer.json.gz", ("Cold Foil", "Holofoil"))
        self.assertEqual(n, (2, 1))   # c2 has only "Foil" – not a Lorcana foil key
        self.assertEqual(self.card("c1"), (2.5, 7.0, 1.1, 4.4))     # Cold Foil before Holofoil
        self.assertEqual(self.card("c2"), (0.3, None, None, None))   # TCGplayer: no "Cold Foil"/"Holofoil", no Normal
        self.assertEqual(self.card("c3"), (9.0, None, None, None))   # no product: old price stays

    def test_foil_key_of_the_game(self):   # a game whose TCGplayer foil is called just "Foil"
        base.daily_prices(EXT, "https://cm/x.json", "game-tcgplayer.json.gz", ("Foil",))
        self.assertEqual(self.card("c2"), (0.3, None, None, 3.3))

    def test_history_averages_only_first_time(self):
        base.daily_prices(EXT, "https://cm/x.json", "x.json.gz")
        first = pricehist.series("c1")
        base.daily_prices(EXT, "https://cm/x.json", "x.json.gz")   # same day again: guide from the local copy
        self.assertEqual(self.downloads, 1)
        self.assertEqual(pricehist.series("c1"), first)              # nothing doubled
        self.assertTrue(first)

    def test_entry_shape(self):
        p, e = base.cardmarket_entry(GUIDE["priceGuides"][0], 1000)
        self.assertEqual(p, {"eur": 2.5, "eur_foil": 7.0})
        self.assertEqual(e["cn"], [[970, 2.0], [993, 2.2], [999, 2.4], [1000, 2.5]])
        self.assertEqual(e["cf"], [[1000, 7.0]])
        self.assertEqual(base.cardmarket_entry({"idProduct": 1}, 1000), ({"eur": None, "eur_foil": None}, None))


class PriceSource(unittest.TestCase):
    def test_hook(self):
        import games
        for key, ready in ((k, r) for k, _n, r in games.GAMES):
            if not ready:
                continue
            g = games.load(key)
            self.assertIn(g.price_source, ("daily", "mtgjson"), key)
            if g.price_source == "daily":
                self.assertTrue(hasattr(g, "update_prices"), key)   # a daily game must bring its own prices
        self.assertEqual(games.load("mtg").price_source, "mtgjson")

    def test_no_game_key_checks_left_for_prices(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for path in ("cards/pricehist.py", "cards/valuehist.py"):
            self.assertNotIn('key != "mtg"', (root / path).read_text("utf-8"), path)
            self.assertNotIn('key == "mtg"', (root / path).read_text("utf-8"), path)
        src = (root / "ui" / "qsetpages.py").read_text("utf-8")
        self.assertEqual(src.count('price_source == "daily"'), 2)   # price tiles and the data overview


if __name__ == "__main__":
    unittest.main()
