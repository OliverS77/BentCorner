"""From a tester log (0.9.2, OneDrive folder): the previous start's program log is kept, and a form names only the
building blocks whose values changed (QML re-reads just those – each read is a call into Python that needs the GIL).

    python -m unittest tests/test_ui_blockers.py
"""
import pathlib
import tempfile
import unittest

from PySide6 import QtWidgets

from system import startup
from ui import qform

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])   # a full app: later tests draw


class PreviousLog(unittest.TestCase):
    def test_the_last_log_is_kept_one_generation(self):
        with tempfile.TemporaryDirectory() as d:
            base = pathlib.Path(d)
            (base / startup.LOG).write_text("first start", "utf-8")
            startup.keep_previous_log(base)
            self.assertFalse((base / startup.LOG).exists())
            self.assertEqual((base / startup.PREVIOUS_LOG).read_text("utf-8"), "first start")
            (base / startup.LOG).write_text("second start", "utf-8")
            startup.keep_previous_log(base)
            self.assertEqual((base / startup.PREVIOUS_LOG).read_text("utf-8"), "second start")

    def test_no_log_yet_is_fine(self):
        with tempfile.TemporaryDirectory() as d:
            startup.keep_previous_log(pathlib.Path(d))
            self.assertFalse((pathlib.Path(d) / startup.PREVIOUS_LOG).exists())


class ChangedKeys(unittest.TestCase):
    def test_only_the_changed_block_is_named(self):
        vals = {"a": "one", "b": "two"}
        form = qform.Form(lambda ui: ui.col([ui.label(vals["a"]), ui.label(vals["b"])]))
        got = []
        form.valsChanged.connect(lambda keys: got.append(set(keys)))
        vals["b"] = "three"
        form.refresh()
        self.assertEqual(len(got), 1)
        (key,) = got[0]
        self.assertEqual(form.val(key)["html"], "three")
        form.refresh()   # nothing changed: no signal
        self.assertEqual(len(got), 1)


if __name__ == "__main__":
    unittest.main()
