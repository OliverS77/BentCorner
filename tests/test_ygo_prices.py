"""Yu-Gi-Oh! daily prices (games/yugioh.update_prices): YGOPRODeck's Cardmarket € is per card (its cheapest print) and
only counts for a card with exactly one print – otherwise every print showed it (Blue-Eyes LOB-001 at 0.02 €). Then €
from the print's TCGplayer price (≈) or none; old per-card prices of prints missing from a full list are cleared.

    python -m unittest tests/test_ygo_prices.py
"""
import gzip
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

from cards import carddb
from games import yugioh


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    rows = [dict(id="lob-001", name="Blue-Eyes White Dragon", set_code="lob", number="001", eur=0.02, usd=125.94),
            dict(id="sdk-001", name="Blue-Eyes White Dragon", set_code="sdk", number="001", eur=0.02, usd=76.59),
            dict(id="dds-001", name="Blue-Eyes White Dragon", set_code="dds", number="001", eur=0.02, usd=1450.0),
            dict(id="lart-en001", name="Only Once Dragon", set_code="lart", number="EN001", eur=3.0, usd=4.0)]
    con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(dict(r, lang="en", layout="normal", booster=1).get(c) for c in cols) for r in rows])
    con.commit()
    con.close()


class Resp:
    def __init__(self, data):
        self.content = gzip.compress(json.dumps(data).encode())

    def raise_for_status(self):
        pass


class YgoPrices(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        make_db(self.db)
        for p in (mock.patch.object(carddb, "DB_PATH", self.db),
                  mock.patch("cards.currency.load", lambda: None),
                  mock.patch("cards.currency.from_usd", lambda u: u * 0.9 if u else None),
                  mock.patch("games.base.write_hist", lambda hist, day: None)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, prices):
        with mock.patch("net.netpolite.get", lambda *a, **k: Resp({"v": 1, "p": prices})):
            yugioh.GAME.update_prices()
        con = sqlite3.connect(self.db)
        try:
            return {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, eur, usd FROM cards")}, \
                {r[0] for r in con.execute("SELECT sid FROM price_est")}
        finally:
            con.close()

    def test_per_card_price_only_for_single_print(self):
        got, est = self.run_with({"lob-001": [0.02, 125.94], "sdk-001": [0.02, None], "lart-en001": [3.1, 4.2]})
        self.assertEqual(got["lob-001"], (113.35, 125.94))   # ≈ from TCGplayer, not 0.02
        self.assertEqual(got["sdk-001"], (None, None))       # rather no price than a wrong one
        self.assertEqual(got["lart-en001"], (3.1, 4.2))      # the card's only print: Cardmarket counts
        self.assertEqual(got["dds-001"], (0.02, 1450.0))     # short list: missing prints untouched
        self.assertEqual(est, {"lob-001"})

    def test_full_list_clears_stale_multi_print_prices(self):
        prices = {f"x-{i}": [None, 1.0] for i in range(1001)}   # unknown prints: just a full-size list
        prices["lob-001"] = [None, 125.94]
        got, _ = self.run_with(prices)
        self.assertEqual(got["dds-001"], (None, None))       # stale 0.02 € from the data pack is gone
        self.assertEqual(got["lart-en001"], (3.0, 4.0))      # single print keeps its price


class CmHistoryCleanup(unittest.TestCase):
    """Once: Cardmarket points from before the fix go for multi-print cards; TCGplayer and single prints stay."""

    def test_once_with_backup(self):
        from cards import pricehist
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(pricehist, "DB", pathlib.Path(tmp) / "price-history.sqlite"):
            hc = pricehist._connect()
            recs = {"lob-001": {"e": 9, "cn": [[5, 0.02], [9, 0.02]], "tn": [[5, 125.0]]},
                    "lart-en001": {"e": 9, "cn": [[5, 3.0]]}}
            hc.executemany("INSERT INTO hist VALUES (?, ?)", [(s, pricehist._pack(r)) for s, r in recs.items()])
            hc.commit()
            hc.close()
            yugioh._clean_cm_history({"lob-001"}, 9)
            hc = pricehist._connect()
            got = {s: pricehist._unpack(b) for s, b in hc.execute("SELECT sid, data FROM hist")}
            hc.execute("INSERT OR REPLACE INTO hist VALUES ('lob-001', ?)", (pricehist._pack(recs["lob-001"]),))
            hc.commit()
            hc.close()
            self.assertEqual(got["lob-001"], {"e": 9, "cn": [[9, 0.02]], "tn": [[5, 125.0]]})
            self.assertEqual(got["lart-en001"], recs["lart-en001"])
            self.assertTrue((pathlib.Path(tmp) / "price-history.before-cm-fix.sqlite").exists())
            yugioh._clean_cm_history({"lob-001"}, 9)   # second time: nothing
            hc = pricehist._connect()
            again = pricehist._unpack(hc.execute("SELECT data FROM hist WHERE sid = 'lob-001'").fetchone()[0])
            hc.close()
            self.assertEqual(again, recs["lob-001"])


if __name__ == "__main__":
    unittest.main()
