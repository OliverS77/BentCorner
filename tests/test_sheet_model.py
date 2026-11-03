"""Dialog sheets as a list model (ui/qsheets.py): opening adds a row, a new title or closing changes only that row,
removing takes it out – the other dialogs are not rebuilt (a plain list as the model rebuilt all of them each time,
tester log 0.9.2: 300 ms per opening). After a removal the dialogs above know their new index.

    python -m unittest tests/test_sheet_model.py
"""
import types
import unittest

from PySide6 import QtWidgets

from ui import qsheets

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _dlg(title):
    return types.SimpleNamespace(title=title, form=None, side=False, kind="", tool="", wide=0, keys={})


class SheetModel(unittest.TestCase):
    def setUp(self):
        self.s = qsheets.Sheets()
        self.m = self.s.model
        self.log = []
        self.m.rowsInserted.connect(lambda _p, a, b: self.log.append(("insert", a, b)))
        self.m.rowsRemoved.connect(lambda _p, a, b: self.log.append(("remove", a, b)))
        self.m.dataChanged.connect(lambda a, b, _r: self.log.append(("change", a.row(), b.row())))
        self.m.modelReset.connect(lambda: self.log.append(("reset",)))

    def row(self, i):
        return self.m.data(self.m.index(i), qsheets._Model.ROLE)

    def test_open_retitle_close_touch_only_their_row(self):
        a, b = _dlg("A"), _dlg("B")
        self.s.open(a)
        self.s.open(b)
        self.assertEqual(self.log, [("insert", 0, 0), ("insert", 1, 1)])
        b.title = "B2"
        self.s.retitle(b)
        self.assertEqual(self.log[-1], ("change", 1, 1))
        self.assertEqual(self.row(1)["title"], "B2")
        self.s.closed(b)
        self.s._changed(b)          # (the timer's work)
        self.assertTrue(self.row(1)["closing"])
        self.assertNotIn(("reset",), self.log)

    def test_removal_renumbers_the_ones_above(self):
        a, b = _dlg("A"), _dlg("B")
        self.s.open(a)
        self.s.open(b)
        self.s._remove(a)
        self.assertIn(("remove", 0, 0), self.log)
        self.assertEqual(self.m.rowCount(), 1)
        self.assertEqual(self.row(0)["title"], "B")
        self.assertEqual(self.row(0)["i"], 0)   # back/key/pick go to the right dialog


if __name__ == "__main__":
    unittest.main()
