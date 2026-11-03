"""Price alerts (collection/alarms.py): report once when the limit is crossed, again only after the price went back;
"below" and "above"; other games' alerts stay untouched; which price counts (source, finish, average); list alerts
in percent against the price when the alert was set.

    python -m unittest tests/test_price_alarms.py
"""
import unittest
from unittest import mock

from collection import alarms
from system import i18n


class _Prices:
    """Stands in for alarms.current_prices: {key_of(alert): price} from a dict by card name."""
    def __init__(self):
        self.now = {}

    def __call__(self, lst):
        return {alarms.key_of(a): self.now.get(a["name"]) for a in lst}


class CardAlerts(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")   # texts are compared in English (app import may set another)
        self.prices = _Prices()
        self.p = [mock.patch.object(alarms, "_game", lambda: "mtg"),
                  mock.patch.object(alarms, "current_prices", self.prices)]
        for p in self.p:
            p.start()
        self.s = {}

    def tearDown(self):
        for p in self.p:
            p.stop()

    def check(self, **now):
        self.prices.now = now
        return alarms.check(self.s)

    def test_below_reports_once_then_again_after_recovery(self):
        alarms.put(self.s, {"kind": "wish", "name": "Sol Ring"}, 2.0, None)
        self.assertEqual(self.check(**{"Sol Ring": 2.5}), [])
        hit = self.check(**{"Sol Ring": 1.99})
        self.assertEqual(len(hit), 1)
        self.assertIn("below your limit", hit[0][1])
        self.assertEqual(self.check(**{"Sol Ring": 1.5}), [])          # still below: not again every day
        self.assertEqual(self.check(**{"Sol Ring": 2.2}), [])          # back above: armed again
        self.assertEqual(len(self.check(**{"Sol Ring": 2.0})), 1)      # exactly at the limit counts

    def test_above_for_trade_card(self):
        alarms.put(self.s, {"kind": "trade", "name": "Ragavan", "sid": "r1", "foil": True}, None, 50.0)
        self.assertEqual(self.check(Ragavan=49.99), [])
        hit = self.check(Ragavan=50.0)
        self.assertEqual(hit[0][0], "Price alert – trade card")
        self.assertIn("above your limit", hit[0][1])

    def test_no_price_no_alert_and_last_price_kept(self):
        alarms.put(self.s, {"kind": "wish", "name": "Unknown"}, 5.0, None)
        self.assertEqual(self.check(), [])
        self.check(Unknown=4.0)
        self.assertEqual(alarms.find(self.s, "wish", name="Unknown")["last"], 4.0)

    def test_delete_and_other_game_untouched(self):
        self.s["price_alarms"] = [{"kind": "wish", "name": "Pikachu", "below": 1.0, "game": "pokemon", "hit": False}]
        alarms.put(self.s, {"kind": "wish", "name": "Sol Ring"}, 2.0, None)
        self.assertEqual(self.check(Pikachu=0.1, **{"Sol Ring": 9.0}), [])   # Pokémon alert: not checked in Magic
        self.assertEqual(len(self.s["price_alarms"]), 2)
        alarms.put(self.s, {"kind": "wish", "name": "Sol Ring"}, None, None)   # both None = delete
        self.assertEqual([a["name"] for a in self.s["price_alarms"]], ["Pikachu"])

    def test_old_alert_without_kind_is_a_wish(self):
        self.s["price_alarms"] = [{"name": "Opt", "below": 0.5}]
        self.assertEqual(len(self.check(Opt=0.4)), 1)


class WhichPrice(unittest.TestCase):
    ROW = {"eur": 2.0, "eur_foil": 6.0, "usd": 1.0, "usd_foil": None}
    HIST = {"cn": [["d1", 1.0], ["d2", 2.0], ["d3", 3.0]]}

    def setUp(self):
        self.p = mock.patch.object(alarms.currency, "from_usd", lambda v: v * 0.9)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def v(self, **o):
        return alarms._value(self.ROW, self.HIST, dict({"src": "cm", "basis": "day", "finish": "any"}, **o))

    def test_sources_and_finish(self):
        self.assertEqual(self.v(), 2.0)                          # any: normal first
        self.assertEqual(self.v(finish="f"), 6.0)
        self.assertAlmostEqual(self.v(src="tcg"), 0.9)            # TCGplayer $ converted to €
        self.assertIsNone(self.v(src="tcg", finish="f"))
        self.assertAlmostEqual(self.v(src="both", dir="down"), 0.9)   # drop: the cheaper source counts
        self.assertEqual(self.v(src="both", dir="up"), 2.0)           # rise: the more expensive one

    def test_average(self):
        self.assertEqual(self.v(basis="avg7"), 2.0)
        self.assertIsNone(self.v(basis="avg30", finish="f"))

    def test_defaults_per_kind(self):
        self.assertEqual(alarms.opts_of({"kind": "trade", "sid": "x", "foil": True})["finish"], "f")
        o = alarms.opts_of({"kind": "wish", "name": "x"})
        self.assertEqual((o["src"], o["basis"], o["finish"], o["dir"]), ("cm", "day", "any", "down"))


class ListAlerts(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")   # texts are compared in English (app import may set another)
        self.now = {}
        self.p = [mock.patch.object(alarms, "_game", lambda: "mtg"),
                  mock.patch.object(alarms, "list_prices", lambda *a, **k: dict(self.now)),
                  mock.patch("collection.trade.lists", lambda kind: [{"id": "L1", "name": "Wants"}])]
        for p in self.p:
            p.start()
        self.s = {"list_alarms": [{"lkind": "wish", "lid": "L1", "drop": 20, "rise": None, "base": {"A": 10.0},
                                   "hit": {}, "game": "mtg"}]}

    def tearDown(self):
        for p in self.p:
            p.stop()

    def run_check(self, **now):
        self.now = now
        return alarms.check_lists(self.s, coll=object())

    def test_drop_percent_once(self):
        self.assertEqual(self.run_check(A=8.01), [])
        hit = self.run_check(A=8.0)                      # -20 % exactly
        self.assertEqual(len(hit), 1)
        self.assertIn("-20 %", hit[0][1])
        self.assertEqual(self.run_check(A=7.0), [])      # still down: not again

    def test_new_card_gets_base_price(self):
        self.run_check(A=10.0, B=4.0)
        self.assertEqual(self.s["list_alarms"][0]["base"]["B"], 4.0)
        self.assertEqual(len(self.run_check(A=10.0, B=3.0)), 1)


if __name__ == "__main__":
    unittest.main()
