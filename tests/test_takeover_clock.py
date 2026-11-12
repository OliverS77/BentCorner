"""Review 08.11. (M13): „keep this device's state“ (takeover) is ordered by the hybrid clock, not the PC clock. Before,
a PC whose clock ran two days ahead kept winning: a later takeover from a correct device was ignored there and its
data stayed different without asking.

    python -m unittest tests.test_takeover_clock
"""
import tempfile
import unittest

from tests.test_syncrun import Device, FakeVault, deck

DAY = 86400 * 1000


class TakeoverClock(unittest.TestCase):
    def test_later_takeover_wins_although_the_other_clock_runs_ahead(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = [1793600000000]
            vault = FakeVault()
            a = Device(tmp, "a", vault, lambda: t[0] + 2 * DAY)   # this PC's clock runs two days ahead
            b = Device(tmp, "b", vault, lambda: t[0])
            a.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)])]})
            a.eng.switch_on()
            a.sync()
            t[0] += 1000
            b.eng.switch_on()
            b.sync()
            # A keeps its state first (stamped two days ahead) …
            a.save_decks([deck("d1", "Burn A", [("s1", 3)])])
            a.eng.keep_mine()
            a.sync()
            t[0] += 1000
            b.sync()
            self.assertEqual(b.decks()["d1"]["name"], "Burn A")
            # … then B, later in reality, keeps its own: A must take it
            t[0] += 60_000
            b.save_decks([deck("d1", "Burn B", [("s1", 3)])])
            b.eng.keep_mine()
            b.sync()
            t[0] += 1000
            a.sync()
            self.assertEqual(a.decks()["d1"]["name"], "Burn B", "the later takeover counts, whatever the PC clocks say")


if __name__ == "__main__":
    unittest.main()
