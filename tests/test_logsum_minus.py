"""logsum.migration / close_gap with a minus on a copy added by hand (03.11.2026): "+1 by hand"
taken back with Undo – the copy is gone, its line by hand stays. Before, the minus was skipped: a gap of 1 stayed and
every logs check warned. Now a minus line with the card as its line had it closes it; log cards still go to "gone"."""
import unittest

from collection import logsum

LINE = {"id": "c0de", "name": "Sol Ring", "set": "c21", "number": "263", "lang": "en", "foil": False, "uid": "u1",
        "delta": 1, "price": 1.5, "added": 100.0, "finish": "etched", "cond": "NM"}
HAND = {"id": "manual_2026-11-03", "info": {"kind": "manual"}, "ended": 100.0, "packs": [{"cards": [dict(LINE)]}]}


class MinusByHand(unittest.TestCase):
    def test_undone_plus_one_becomes_a_minus_line(self):
        self.assertEqual(logsum.diff([], [HAND], []), {"uid:u1": (1, 0)})
        mig = logsum.migration([], [HAND], [], 200.0)
        lines = mig["packs"][0]["cards"]
        self.assertEqual(len(lines), 1)
        ln = lines[0]
        self.assertEqual((ln["uid"], ln["delta"], ln["name"], ln["set"], ln["finish"], ln["price"]),
                         ("u1", -1, "Sol Ring", "c21", "etched", 1.5))
        self.assertNotIn("gone", mig)
        # with the minus line the library (empty) is exactly the sum of its logs again
        hand = dict(HAND, packs=[{"cards": [dict(LINE), dict(ln)]}])
        self.assertEqual(logsum.diff([], [hand], []), {})

    def test_log_cards_still_go_to_gone(self):
        scan = {"id": "s1", "ended": 50.0, "collection": True, "info": {}, "packs": [{"cards": [{"added": 1.0, "name": "X"}]}]}
        mig = logsum.migration([], [scan], [], 200.0)
        self.assertEqual(mig["gone"], ["s1/1.0"])
        self.assertEqual(mig["packs"][0]["cards"], [])


if __name__ == "__main__":
    unittest.main()
