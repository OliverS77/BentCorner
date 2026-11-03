"""Menus as a light page in the window (qmenu.Menu.sheet → qdialogs.menu): entries with brightness for checkable ones,
a submenu lies over its menu ("←" back), choosing an entry closes the menu and every menu it came from, then runs it.

    python -m unittest discover -t . -s tests -p test_menu_sheet.py
"""
import unittest
from unittest import mock

from ui import qdialogs, qmenu


class FakeDialog:
    def __init__(self, title, items, on_pick, parent, at=None):
        self.title, self.items, self.pick, self.parent_menu, self.at = title, items, on_pick, parent, at
        self.closed = False

    def close(self, result=None):
        self.closed = True


class MenuSheet(unittest.TestCase):
    def setUp(self):
        self.opened = []

        def menu(title, items, on_pick, *, parent=None, at=None):
            d = FakeDialog(title, items, on_pick, parent, at)
            self.opened.append(d)
            return d
        self.p = mock.patch.object(qdialogs, "menu", menu)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_entries_brightness_and_order(self):
        ran = []
        m = qmenu.Menu()
        m.addAction("Open", lambda: ran.append("open"))
        m.addSeparator()
        built = m.addAction("Built", lambda: ran.append("built"))
        built.setCheckable(True)
        built.setChecked(True)
        off = m.addAction("Delete", lambda: ran.append("del"))
        off.setEnabled(False)
        m.sheet("Deck")
        d = self.opened[-1]
        self.assertEqual(d.title, "Deck")
        self.assertEqual([i["text"] for i in d.items], ["Open", "", "Built", "Delete"])
        self.assertTrue(d.items[1]["sep"])
        self.assertEqual((d.items[2]["checkable"], d.items[2]["on"]), (True, True))
        self.assertFalse(d.items[3]["enabled"])
        d.pick(3)   # disabled: nothing
        d.pick(1)   # separator: nothing
        self.assertEqual(ran, [])
        self.assertFalse(d.closed)
        d.pick(0)
        self.assertTrue(d.closed)
        self.assertEqual(ran, ["open"])

    def test_opens_where_it_was_asked(self):
        """exec(pos) like QMenu: the card goes to that point (P1 – not the middle of the window any more)."""
        from PySide6 import QtCore
        m = qmenu.Menu()
        m.addAction("Open")
        m.exec(QtCore.QPoint(120, 340))
        self.assertEqual(self.opened[-1].at, QtCore.QPoint(120, 340))

    def test_checkable_entry_toggles(self):
        got = []
        m = qmenu.Menu()
        a = m.addAction("Built")
        a.setCheckable(True)
        a.toggled.connect(lambda on: got.append(on))
        m.sheet("Deck")
        self.opened[-1].pick(0)
        self.assertEqual(got, [True])

    def test_submenu_lies_over_its_menu_and_closes_all(self):
        ran = []
        m = qmenu.Menu()
        sub = m.addMenu("Move to folder")
        sub.addAction("Commander", lambda: ran.append("cmd"))
        m.sheet("Deck")
        top = self.opened[-1]
        self.assertTrue(top.items[0]["sub"])
        top.pick(0)
        self.assertFalse(top.closed)          # the menu stays under its submenu
        inner = self.opened[-1]
        self.assertIs(inner.parent_menu, top)
        self.assertEqual(inner.title, "Move to folder")
        inner.pick(0)
        self.assertTrue(inner.closed and top.closed)
        self.assertEqual(ran, ["cmd"])


class MultiMenu(unittest.TestCase):
    """qdialogs.menu(multi=True): every switch reports, the sheet stays open until done; free text when nothing fits."""

    def setUp(self):
        class Host:
            def __init__(self):
                self.open_, self.closed_ = [], []

            def open(self, d):
                self.open_.append(d)

            def closed(self, d):
                self.closed_.append(d)
        self.host = Host()
        self.old = qdialogs.host()
        qdialogs.set_host(self.host)

    def tearDown(self):
        qdialogs.set_host(self.old)

    def test_switches_stay_open_and_close_keeps(self):
        got, texts, closed = [], [], []
        d = qdialogs.menu("Sets", [{"text": "OTJ", "on": True}, {"text": "MKM"}], got.append, multi=True,
                          on_text=texts.append, on_close=lambda r: closed.append(r))
        self.assertTrue(d.multi)
        d.pick(1)
        d.pick(0)
        self.assertEqual(got, [1, 0])
        self.assertFalse(d.done)          # still open
        d.take_text("Final Fantasy")
        self.assertEqual(texts, ["Final Fantasy"])
        d.back()                          # Enter / Done / Esc / a click beside
        self.assertTrue(d.done)
        self.assertEqual(closed, [None])


if __name__ == "__main__":
    unittest.main()


class MenuPoint(unittest.TestCase):
    """qdialogs.menu: where the card opens (the sheet's "at", a point on the screen)."""

    def test_default_is_the_mouse_and_a_submenu_follows_its_menu(self):
        from PySide6 import QtCore, QtGui
        with mock.patch.object(QtGui.QCursor, "pos", return_value=QtCore.QPoint(40, 50)), \
                mock.patch.object(qdialogs, "_host", None):
            top = qdialogs.menu("Deck", [], lambda i: None)
            self.assertEqual(top.at, (40, 50))
            sub = qdialogs.menu("Folder", [], lambda i: None, parent=top)
            self.assertEqual(sub.at, (40, 50))
            given = qdialogs.menu("Deck", [], lambda i: None, at=QtCore.QPoint(7, 8))
            self.assertEqual(given.at, (7, 8))
