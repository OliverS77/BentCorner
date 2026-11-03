"""Several cards chosen in the Library (ui/qselect.py), only through the "Select" button: a click toggles,
Shift+click takes the range, the lasso replaces (or adds with Ctrl), rows that are no longer shown drop out, and
the grid hears only about changed keys.
No UI window, no data.

    python -m unittest tests/test_select.py
"""
import unittest

from PySide6 import QtCore

from ui import qselect

CTRL, SHIFT = QtCore.Qt.ControlModifier.value, QtCore.Qt.ShiftModifier.value


class _Model(QtCore.QObject):
    reset = QtCore.Signal()

    def __init__(self, rows):
        super().__init__()
        self.rows = rows


class _Grid:
    def __init__(self):
        self.told = []

    def picked_changed(self, keys):
        self.told.append(set(keys))


class _Host(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.grid = _Grid()


class Select(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])

    def setUp(self):
        self.rows = [{"key": f"k{i}", "name": f"C{i}", "count": 1, "price": 1.0} for i in range(10)]
        self.lib = type("Lib", (), {})()
        self.lib.model = _Model(self.rows)
        self.lib.mode = "mine"
        self.host = _Host()
        self.s = qselect.SelectBackend(None, self.lib, self.host)

    def test_nothing_chooses_without_the_button(self):
        """Oliver, after 0.9.3: Ctrl/Shift+click, the frame and Ctrl+A start no choice – a click opens the card."""
        self.s.click(2, CTRL)
        self.s.click(5, SHIFT)
        self.s.lassoStart()
        self.s.lasso([1, 2], False)
        self.s.all()
        self.assertEqual(self.s.keys, set())
        self.assertFalse(self.s.active)

    def test_click_and_shift_range_while_choosing(self):
        self.s.toggleChoosing()
        self.s.click(2, 0)
        self.s.click(5, SHIFT)
        self.assertEqual(self.s.keys, {"k2", "k3", "k4", "k5"})
        self.s.click(3, 0)
        self.assertNotIn("k3", self.s.keys)
        self.assertEqual(self.host.grid.told[-1], {"k3"})            # only the changed tile is told

    def test_select_button_keeps_choosing_until_done(self):
        self.s.toggleChoosing()
        self.assertTrue(self.s.active)                                # on, nothing chosen yet
        self.s.click(2, 0)
        self.s.click(2, 0)
        self.assertEqual(self.s.keys, set())
        self.assertTrue(self.s.active)                                # still choosing at 0 ("None" too)
        self.s.click(4, 0)
        self.s.none()
        self.assertTrue(self.s.active)
        self.s.end()                                                  # "Done" / ✕ / Esc / another page
        self.assertFalse(self.s.active)
        self.assertEqual(self.s.keys, set())

    def test_after_every_kind_of_choice_the_next_click_opens(self):
        """Every way out leaves nothing behind: afterwards the next plain click opens the card (choose does nothing)."""
        ways = [lambda: self.s.end(), lambda: self.s.toggleChoosing()]
        for way in ways:
            self.s.toggleChoosing()
            self.s.click(1, 0)
            self.s.lassoStart()
            self.s.lasso([3, 4], True)
            self.s.all()
            way()
            self.assertFalse(self.s.active)
            self.s.click(6, 0)
            self.assertEqual(self.s.keys, set())

    def test_lasso_replaces_or_adds(self):
        self.s.toggleChoosing()
        self.s.click(0, 0)
        self.s.lassoStart()
        self.s.lasso([3, 4, 99], False)
        self.assertEqual(self.s.keys, {"k3", "k4"})
        self.s.lassoStart()
        self.s.lasso([7], True)
        self.assertEqual(self.s.keys, {"k3", "k4", "k7"})

    def test_rows_no_longer_shown_drop_out(self):
        self.s.toggleChoosing()
        self.s.all()
        self.lib.model.rows = self.rows[:3]
        self.lib.model.reset.emit()
        self.assertEqual(self.s.keys, {"k0", "k1", "k2"})
        self.s.end()
        self.assertFalse(self.s.active)


if __name__ == "__main__":
    unittest.main()
