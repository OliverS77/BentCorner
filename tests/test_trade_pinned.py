"""0.9.7.21 – pinned wants in the trade proposal (03.11.2026): the wanted count is used up across the friend's
versions – the exact version first, other versions only for what is still missing, never twice."""
import unittest

from ui.tradeview import pinned_rows


def row(name, set_, number, count):
    return {"name": name, "set": set_, "number": number, "count": count, "price": 1.0}


class PinnedWants(unittest.TestCase):
    def test_exact_version_first_then_the_rest(self):
        pinned = {("Bolt", "lea", "161"): 2}
        rows = [row("Bolt", "M10", "146", 3), row("Bolt", "LEA", "161", 1)]
        out = pinned_rows(rows, pinned)
        self.assertEqual([(r["set"], r["count"], r["pinned_match"]) for r in out],
                         [("LEA", 1, True), ("M10", 1, False)])

    def test_other_versions_share_the_count(self):
        pinned = {("Bolt", "lea", "161"): 2}
        rows = [row("Bolt", "M10", "146", 3), row("Bolt", "2X2", "117", 3)]
        self.assertEqual(sum(r["count"] for r in pinned_rows(rows, pinned)), 2)

    def test_exact_covers_everything(self):
        pinned = {("Bolt", "lea", "161"): 1}
        rows = [row("Bolt", "M10", "146", 3), row("Bolt", "LEA", "161", 4)]
        out = pinned_rows(rows, pinned)
        self.assertEqual([(r["set"], r["count"]) for r in out], [("LEA", 1)])

    def test_any_version_already_in_trade(self):
        pinned = {("Bolt", "lea", "161"): 1}
        self.assertEqual(pinned_rows([row("Bolt", "LEA", "161", 1)], pinned, {"Bolt"}), [])


if __name__ == "__main__":
    unittest.main()
