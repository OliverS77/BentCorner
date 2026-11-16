"""Converted euro prices get "≈" and the day of the exchange rate (legal/lead 14.11.2026): table price_est(sid, rate_day)
of the card database, Game.price_estimated / price_rate_day, written by the Yu-Gi-Oh! price job, the Pokémon price job
("untrusted" prints) and the Yu-Gi-Oh! data pack; kept prices keep their mark when a newer pack database comes.

    python -m unittest tests.test_price_est
"""
import json
import pathlib
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from cards import carddb, currency
from games import base, yugioh
from tests.test_ygo_prices import Resp, make_db


class Currency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = pathlib.Path(self.tmp.name) / "exchange-rates.json"
        p = mock.patch.object(currency, "FILE", self.file)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_day_from_the_source_kept_with_the_rates(self):
        body = {"amount": 1.0, "base": "EUR", "date": "2026-11-13", "rates": {"USD": 1.1052}}
        r = mock.Mock(**{"json.return_value": body, "raise_for_status.return_value": None})
        with mock.patch.object(currency.netpolite, "get", return_value=r), \
                mock.patch.object(currency, "_stamp", 0.0), mock.patch.object(currency, "_failed", 0.0):
            self.assertTrue(currency.refresh(max_age=0))
            self.assertEqual(currency.rate_day(), "2026-11-13")
        self.assertEqual(json.loads(self.file.read_text("utf-8"))["date"], "2026-11-13")
        currency.load()
        self.assertEqual(currency.rate_day(), "2026-11-13")

    def test_older_file_without_date_uses_the_fetch_day(self):
        t = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
        self.file.write_text(json.dumps({"rates": {"USD": 1.1}, "fetched": t}), "utf-8")
        currency.load()
        self.assertEqual(currency.rate_day(), time.strftime("%Y-%m-%d", time.gmtime(t)))


class Table(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        make_db(self.db)
        p = mock.patch.object(carddb, "DB_PATH", self.db)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        base.price_est_changed()
        self.addCleanup(base.price_est_changed)

    def test_older_table_gets_the_column_and_the_api_answers(self):
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE price_est (sid TEXT PRIMARY KEY)")   # as written up to 0.9.9.103
        con.execute("INSERT INTO price_est VALUES ('lob-001')")
        con.commit()
        g = yugioh.GAME
        self.assertTrue(g.price_estimated("lob-001"))
        self.assertIsNone(g.price_rate_day("lob-001"))   # converted, day unknown (older database)
        base.ensure_price_est(con)
        con.execute("UPDATE price_est SET rate_day = '2026-11-13'")
        con.commit()
        con.close()
        base.price_est_changed()
        self.assertEqual(g.price_rate_day("lob-001"), "2026-11-13")
        self.assertFalse(g.price_estimated("lart-en001"))
        self.assertIsNone(g.price_rate_day("lart-en001"))

    def test_no_table_no_mark(self):
        for g in ("mtg", "pokemon", "yugioh"):
            game = __import__("games").load(g)
            self.assertFalse(game.price_estimated("lob-001"))
            self.assertIsNone(game.price_rate_day("lob-001"))


class YgoJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        make_db(self.db)
        for p in (mock.patch.object(carddb, "DB_PATH", self.db),
                  mock.patch("cards.currency.load", lambda: None),
                  mock.patch("cards.currency.from_usd", lambda u: u * 0.9 if u else None),
                  mock.patch("cards.currency.rate_day", lambda: "2026-11-13"),
                  mock.patch("games.base.write_hist", lambda hist, day: None)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(base.price_est_changed)

    def test_converted_price_marked_with_the_day(self):
        with mock.patch("net.netpolite.get", lambda *a, **k: Resp({"v": 1, "p": {
                "lob-001": [0.02, 125.94], "lart-en001": [3.1, 4.2]}})):
            yugioh.GAME.update_prices()
        g = yugioh.GAME
        self.assertTrue(g.price_estimated("lob-001"))
        self.assertEqual(g.price_rate_day("lob-001"), "2026-11-13")
        self.assertFalse(g.price_estimated("lart-en001"))   # real Cardmarket € – no sign


class YgoHistory(YgoJob):
    """library 14.11.: a converted euro is no Cardmarket point – only the TCGplayer point ("tn") is written."""

    def test_converted_euro_not_on_the_cardmarket_line(self):
        got = {}
        with mock.patch("games.base.write_hist", lambda hist, day: got.update(hist)), \
                mock.patch("net.netpolite.get", lambda *a, **k: Resp({"v": 1, "p": {
                    "lob-001": [0.02, 125.94], "lart-en001": [3.1, 4.2]}})):
            yugioh.GAME.update_prices()
        self.assertNotIn("cn", got["lob-001"])
        self.assertEqual(got["lob-001"]["tn"][0][1], 125.94)
        self.assertEqual(got["lart-en001"]["cn"][0][1], 3.1)   # real Cardmarket € stays a Cardmarket point

    def test_old_converted_points_removed_once_with_backup(self):
        from cards import pricehist
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(pricehist, "DB", pathlib.Path(tmp) / "price-history.sqlite"):
            hc = pricehist._connect()
            recs = {"lob-001": {"e": 9, "cn": [[5, 113.0], [9, 113.3]], "tn": [[5, 125.0]]},
                    "lart-en001": {"e": 9, "cn": [[5, 3.0]]}}
            hc.executemany("INSERT INTO hist VALUES (?, ?)", [(s, pricehist._pack(r)) for s, r in recs.items()])
            hc.commit()
            hc.close()
            yugioh._clean_converted_cn({"lob-001"})
            hc = pricehist._connect()
            got = {s: pricehist._unpack(b) for s, b in hc.execute("SELECT sid, data FROM hist")}
            hc.execute("INSERT OR REPLACE INTO hist VALUES ('lob-001', ?)", (pricehist._pack(recs["lob-001"]),))
            hc.commit()
            hc.close()
            self.assertEqual(got["lob-001"], {"e": 9, "tn": [[5, 125.0]]})
            self.assertEqual(got["lart-en001"], recs["lart-en001"])
            self.assertTrue((pathlib.Path(tmp) / "price-history.before-cn-conv-fix.sqlite").exists())
            yugioh._clean_converted_cn({"lob-001"})   # second time: nothing
            hc = pricehist._connect()
            again = pricehist._unpack(hc.execute("SELECT data FROM hist WHERE sid = 'lob-001'").fetchone()[0])
            hc.close()
            self.assertEqual(again, recs["lob-001"])


class PokemonJob(unittest.TestCase):
    """Pokémon converts only the "untrusted" prints (ambiguous Cardmarket number, cm_fix.json) – those are marked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        con = sqlite3.connect(self.db)
        con.executescript(carddb.SCHEMA)
        cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
        for sid in ("sv1-1", "sv1-2"):
            row = dict(id=sid, name="Pika", set_code="sv1", number=sid[-1], lang="en", layout="normal", booster=1)
            con.execute(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        tuple(row.get(c) for c in cols))
        con.execute("CREATE TABLE ext (sid TEXT, variant TEXT, cm INTEGER, tcg INTEGER)")
        con.execute("CREATE TABLE set_ext (set_code TEXT PRIMARY KEY, cm INTEGER, tcg INTEGER, abbr TEXT, official INTEGER)")
        con.executemany("INSERT INTO ext VALUES (?, 'normal', ?, ?)", [("sv1-1", 1, 5001), ("sv1-2", 2, 5002)])
        con.execute("INSERT INTO set_ext VALUES ('sv1', NULL, 100, NULL, NULL)")
        con.execute("CREATE TABLE variants (sid TEXT, type TEXT)")
        con.commit()
        con.close()
        from games import pokemon
        tcg = {"100": {"5001": {"Normal": 10.0}, "5002": {"Normal": 4.0}}}
        guide = {2: {"trend": 3.5}}   # sv1-2 has its own Cardmarket price
        for p in (mock.patch.object(carddb, "DB_PATH", self.db),
                  mock.patch.object(pokemon, "cardmarket_guide", lambda url, progress: guide),
                  mock.patch.object(pokemon, "tcgplayer_table", lambda *a, **k: (tcg, False)),
                  mock.patch.object(pokemon.Pokemon, "market_fix", lambda self: {"untrusted": ["sv1-1"]}),
                  mock.patch.object(pokemon, "write_hist", lambda hist, day: None),
                  mock.patch("cards.currency.from_usd", lambda u: round(u * 0.9, 2) if u else None),
                  mock.patch("cards.currency.rate_day", lambda: "2026-11-13")):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(base.price_est_changed)
        self.game = pokemon.GAME

    def test_untrusted_converted_and_marked_others_not(self):
        self.game.update_prices()
        con = sqlite3.connect(self.db)
        eur = dict(con.execute("SELECT id, eur FROM cards"))
        con.close()
        self.assertEqual(eur["sv1-1"], 9.0)   # from TCGplayer
        self.assertTrue(self.game.price_estimated("sv1-1"))
        self.assertEqual(self.game.price_rate_day("sv1-1"), "2026-11-13")
        self.assertFalse(self.game.price_estimated("sv1-2"))   # real Cardmarket €


class PackUpgrade(unittest.TestCase):
    """A newer pack database replaces the user's one but keeps the user's prices: their mark comes along."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.user, self.pack = self.tmp / "user" / "cards.sqlite", self.tmp / "pack" / "cards.sqlite"
        for p, build, est in ((self.user, "1", [("lob-001", "2026-11-01")]), (self.pack, "2", [("sdk-001", "2026-11-14")])):
            p.parent.mkdir()
            make_db(p)
            con = sqlite3.connect(p)
            base.ensure_price_est(con)
            con.executemany("INSERT INTO price_est VALUES (?, ?)", est)
            con.execute("INSERT OR REPLACE INTO meta VALUES ('pk_build', ?)", (build,))
            con.commit()
            con.close()
        for p in (mock.patch.object(carddb, "DB_PATH", self.user),
                  mock.patch.object(carddb, "_bundle_src", lambda: self.pack)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(base.price_est_changed)

    def test_kept_prices_keep_their_mark(self):
        self.assertTrue(carddb._from_bundle(upgrade=True))
        con = sqlite3.connect(self.user)
        est = dict(con.execute("SELECT sid, rate_day FROM price_est"))
        con.close()
        # every print of make_db has a user price -> all kept with the user's marks; the pack's sdk-001 mark is gone
        self.assertEqual(est, {"lob-001": "2026-11-01"})
        self.assertEqual(yugioh.GAME.price_rate_day("lob-001"), "2026-11-01")



class MagicScryfall(unittest.TestCase):
    """Magic's euros come from Scryfall (in the card database from its bulk data), not from MTGJSON's Cardmarket values
    (Oliver/legal 16.11.2026). The MTGJSON price job brings only TCGplayer; a print without any Scryfall euro gets the
    TCGplayer price converted (≈, price_est)."""

    ROWS = {   # id: (eur, eur_foil, usd, usd_foil) as the Scryfall bulk left them
        "a": (5.0, None, 6.0, None),     # real Scryfall euro: stays, no mark
        "b": (None, None, 10.0, 20.0),   # no euro at all: converted, marked
        "c": (None, 7.0, 3.0, 8.0),      # a Scryfall foil euro: real, nothing converted
        "d": (None, None, None, None),   # no price at all: none
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        con = sqlite3.connect(self.db)
        con.executescript(carddb.SCHEMA)
        cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
        for sid, (eur, eur_foil, usd, usd_foil) in self.ROWS.items():
            row = dict(id=sid, name=sid.upper(), set_code="x", number="1", lang="en", layout="normal", booster=1,
                       eur=eur, eur_foil=eur_foil, usd=usd, usd_foil=usd_foil)
            con.execute(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        tuple(row.get(c) for c in cols))
        con.commit()
        con.close()
        self.rate = 0.9
        for q in (mock.patch.object(carddb, "DB_PATH", self.db),
                  mock.patch("cards.currency.from_usd", lambda u: round(u * self.rate, 2) if u else None),
                  mock.patch("cards.currency.rate_day", lambda: "2026-11-16")):
            q.start()
            self.addCleanup(q.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(base.price_est_changed)

    def prices(self):
        con = sqlite3.connect(self.db)
        try:
            return ({r[0]: r[1:] for r in con.execute("SELECT id, eur, eur_foil, usd, usd_foil FROM cards")},
                    dict(con.execute("SELECT sid, rate_day FROM price_est")))
        finally:
            con.close()

    def apply(self, prices):
        import app
        with mock.patch.object(app.library, "installed_sets", lambda: []):
            app.MainWindow.apply_prices(prices)

    def test_mtgjson_euros_ignored_scryfall_kept(self):
        self.apply({"a": {"eur": 99.0, "eur_foil": 98.0, "usd": 6.5, "usd_foil": 9.0},
                    "b": {"eur": 55.0, "usd": 11.0}})
        rows, est = self.prices()
        self.assertEqual(rows["a"], (5.0, None, 6.5, 9.0))      # MTGJSON's € never lands, its $ does
        self.assertEqual(rows["b"], (9.9, 18.0, 11.0, 20.0))    # converted from the new $ (and the kept foil $)
        self.assertEqual(rows["c"], (None, 7.0, 3.0, 8.0))
        self.assertEqual(rows["d"], (None, None, None, None))
        self.assertEqual(est, {"b": "2026-11-16"})

    def test_next_job_recomputes_with_the_new_rate(self):
        self.apply({"a": {"usd": 6.0}})
        self.rate = 0.5
        self.apply({"a": {"usd": 6.0}})
        rows, est = self.prices()
        self.assertEqual(rows["b"][:2], (5.0, 10.0))
        self.assertEqual(set(est), {"b"})
        self.assertEqual(base.price_est_map().get("b"), "2026-11-16")   # what the ≈ display reads
        self.assertNotIn("a", base.price_est_map())

    def test_job_without_news_still_fills(self):   # MTGJSON had nothing new: jobqueue calls scryfall_euros itself
        from games import mtg
        with carddb.connection() as con:
            out = mtg.scryfall_euros(con)
        self.assertEqual(out["b"], (9.0, 18.0))
        self.assertEqual(self.prices()[1], {"b": "2026-11-16"})


if __name__ == "__main__":
    unittest.main()
