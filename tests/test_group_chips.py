"""Group by – chips and switch (Oliver, 30.10.): × removes only that level, a level switched off stays in the path but
doesn't filter, the switch keeps the path but shows the normal list, "Ungroup" really resets; the chips carry the
numbers of the tree and appear only when the grouping filters something. No UI.

    python -m unittest tests/test_group_chips.py
"""
import unittest
from types import SimpleNamespace
from unittest import mock

from PySide6 import QtCore

from tests.test_grouping import GAME, ROWS
from ui import grouping, qgroup


class _Sig(QtCore.QObject):
    reset = QtCore.Signal()
    changed = QtCore.Signal()


class FakeLib:
    mode = "mine"

    def __init__(self):
        self.model = _Sig()
        self.sort = SimpleNamespace(currentData=lambda: None)
        self.group_chain, self.group_path, self.group_base = [], [], list(ROWS)

    def refresh(self):
        self.group_base = list(ROWS)   # (the rows before the branch – mine_rows keeps them for the tree)


class Chips(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(grouping.games, "current", lambda: GAME)   # (qgroup.games is the same module)
        self.p.start()
        self.p3 = mock.patch.object(qgroup, "_euro", lambda v: f"{v:.2f} €")
        self.p3.start()
        self.ctrl = SimpleNamespace(settings={}, settings_changed=lambda: None)
        self.lib = FakeLib()
        self.host = _Sig()
        self.g = qgroup.GroupBackend(self.ctrl, self.lib, self.host)

    def tearDown(self):
        self.p3.stop()
        self.p.stop()

    def grouped(self):
        for k in ("set", "rarity", "color"):
            self.g.addLevel(k)
        self.g.pick(0, "OLD")
        self.g.pick(1, "rare")
        self.g.pick(2, "M")   # C is white and blue: multicoloured
        return self.g

    def test_button_text_is_always_just_group_by(self):
        g = self.grouped()
        self.assertEqual(g.buttonText, "Group by")

    def test_chips_with_numbers_only_when_filtering(self):
        self.g.addLevel("set")
        self.assertEqual(self.g.chips, [])   # a chain without a picked branch filters nothing: no category
        g = self.grouped()
        self.assertEqual([(c["label"], c["cards"]) for c in g.chips],
                         [("OLD Set", "4"), ("Rare", "3"), (g.chips[2]["label"], "3")])
        self.assertEqual(self.lib.group_path, ["OLD", "rare", "M"])

    def test_cross_removes_only_this_level(self):
        g = self.grouped()
        g.removeLevel(1)   # OLD › rare › M  ->  OLD › M
        self.assertEqual(self.lib.group_chain, ["set", "color"])
        self.assertEqual(self.lib.group_path, ["OLD", "M"])

    def test_switched_off_level_stays_but_does_not_filter(self):
        g = self.grouped()
        g.toggleLevel(1)
        self.assertEqual(self.lib.group_chain, ["set", "color"])
        self.assertEqual(self.lib.group_path, ["OLD", "M"])
        self.assertEqual([c["grey"] for c in g.chips], [False, True, False])
        g.toggleLevel(1)   # on again: the path as before
        self.assertEqual(self.lib.group_path, ["OLD", "rare", "M"])

    def test_switch_off_keeps_the_path_ungroup_resets(self):
        g = self.grouped()
        g.setOn(False)
        self.assertEqual((self.lib.group_chain, self.lib.group_path), ([], []))
        self.assertTrue(all(c["grey"] for c in g.chips) and len(g.chips) == 3)
        g.setOn(True)
        self.assertEqual(self.lib.group_path, ["OLD", "rare", "M"])
        g.clear()
        self.assertEqual((self.lib.group_chain, g.chips, g.active), ([], [], False))

    def test_chip_click_goes_back_to_that_level(self):
        g = self.grouped()
        g.toLevel(0)
        self.assertEqual(self.lib.group_path, ["OLD"])
        self.assertEqual(len(g.chips), 1)

    def test_remembered_with_switched_off_levels(self):
        self.grouped().toggleLevel(2)
        again = qgroup.GroupBackend(self.ctrl, FakeLib(), _Sig())
        self.assertEqual([c["disabled"] for c in again.chips], [False, False, True])
        self.assertEqual(again.lib.group_path, ["OLD", "rare"])


if __name__ == "__main__":
    unittest.main()
