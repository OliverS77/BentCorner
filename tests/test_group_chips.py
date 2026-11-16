"""Group by – chips and switch (Oliver, 30.10.): × removes only that level, a level switched off stays in the path but
doesn't filter, the switch keeps the path but shows the normal list, "Ungroup" really resets; the chips carry the
numbers of the tree and appear only when the grouping filters something. No UI – except ChipRowPlace: since 05.11.
(Oliver) the chips stand as the LAST chip of the filter row (left, after the others; before: at the right end); checked
offscreen on ChipBar's tail with plain boxes.

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
        self.p3 = mock.patch.object(qgroup, "_euro", lambda v, est=False: ("≈ " if est else "") + f"{v:.2f} €")
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


QML_ROW = """
import QtQuick
import "file:///%s"
Window {
    width: 900; height: 300; visible: true
    ChipBar {
        objectName: "bar"
        width: 700
        tail: Rectangle { objectName: "tail"; width: 220; height: 30; visible: width > 0 }
    }
}
"""


def _group(key, values):
    return {"key": key, "id": key, "title": key.title(), "titleId": "", "coverId": "", "grey": False, "clear": False,
            "collapsing": False, "values": [{"cid": f"{key}:{v}", "text": v, "kind": "", "neg": False,
                                             "collapsing": False} for v in values]}


class ChipRowPlace(unittest.TestCase):
    """Group by is the tail of the chip row: after the last filter chip, wraps with the row, nothing reserved at the
    right edge any more."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import shiboken6
        from PySide6 import QtGui, QtQml, QtQuick
        from ui import quickui
        cls.app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
        cls.engine = QtQml.QQmlEngine()
        cls.engine.rootContext().setContextProperty("T", quickui.palette())
        comp = QtQml.QQmlComponent(cls.engine)
        comp.setData((QML_ROW % quickui.qml_dir().joinpath("components").as_posix()).encode("utf-8"), QtCore.QUrl())
        cls.obj = comp.create()   # (Python owns it: keep the reference, else the window goes away mid-test)
        assert cls.obj is not None, [e.toString() for e in comp.errors()]
        cls.win = shiboken6.wrapInstance(shiboken6.getCppPointer(cls.obj)[0], QtQuick.QQuickWindow)
        found = {}
        todo = [cls.win.contentItem()]
        while todo:   # QML items hang in the visual tree
            it = todo.pop()
            found[it.objectName()] = it
            todo.extend(it.childItems())
        cls.bar, cls.tail = found["bar"], found["tail"]

    @classmethod
    def tearDownClass(cls):
        cls.win = cls.bar = cls.tail = None
        del cls.obj

    def settle(self, groups, ms=900):
        import time
        self.bar.setProperty("groups", groups)
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)

    def boxes(self):
        flow = self.tail.parentItem().parentItem()   # tail > tail slot > Flow
        return [(round(it.x()), round(it.y()), round(it.width())) for it in flow.childItems()
                if it.isVisible() and it.width() > 0]

    def test_tail_alone_starts_at_the_left(self):
        self.settle([])
        self.assertEqual(self.boxes(), [(0, 0, 220)])
        self.assertGreater(self.bar.height(), 0)   # the row is there for "Group by" alone

    def test_tail_comes_right_after_the_last_chip(self):
        self.settle([_group("sets", ["UNH", "UNF"])])
        b = self.boxes()
        self.assertEqual(len(b), 2)
        (x0, y0, w0), (x1, y1, w1) = b
        self.assertEqual((y1, x1), (y0, x0 + w0 + 8))   # same line, one gap (Flow spacing 8) – not at the right end
        self.assertLess(x1 + w1, 700 - 50)

    def test_tail_wraps_and_stays_last(self):
        self.settle([_group("sets", ["UNH", "UNF", "UST", "AFR", "UNK", "PCEL", "WC97", "WC98", "WC99"]),
                     _group("colors", ["W", "U"]), _group("types", ["Land"])])
        b = self.boxes()
        self.assertEqual(len(b), 4)
        last_line = max(y for _, y, _ in b[:-1])
        x, y, _ = b[-1]
        self.assertGreaterEqual(y, last_line)         # never above or before a filter chip
        self.assertTrue(y > b[0][1])                   # here the row wraps
        before = [bx for bx in b[:-1] if bx[1] == y]
        if before:
            self.assertEqual(x, before[-1][0] + before[-1][2] + 8)

    def test_hidden_tail_takes_no_place(self):
        self.tail.setProperty("width", 0)
        try:
            self.settle([])
            self.assertEqual(self.bar.height(), 0)
            self.settle([_group("sets", ["UNH"])])
            self.assertEqual(len(self.boxes()), 1)
        finally:
            self.tail.setProperty("width", 220)
            self.settle([])

    def test_library_view_puts_group_by_into_the_tail(self):
        from ui import quickui
        src = (quickui.qml_dir() / "components" / "LibraryView.qml").read_text("utf-8")
        self.assertIn("tail: GroupChips {", src)


if __name__ == "__main__":
    unittest.main()
