"""The camera message without a picture ("No camera found …") on the scan page: wrapped inside the free gap between the
tiles that ScanPage.qml (msgBox) hands over – never into a tile (lead 14.11.2026, after 0.9.9)."""
import pathlib
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class MessageBox(unittest.TestCase):
    def test_slot_sets_and_clears(self):
        from PySide6 import QtCore
        from ui.qscan import ScanBackend
        me = types.SimpleNamespace(view=types.SimpleNamespace(msg_box=None), _dirty=False)
        ScanBackend.setMessageBox(me, 400.0, 400.0, 600.0, 130.0)
        self.assertEqual(me.view.msg_box, QtCore.QRectF(400, 400, 600, 130))
        self.assertTrue(me._dirty)
        ScanBackend.setMessageBox(me, 0.0, 0.0, 0.0, 0.0)   # no gap: the old column in the middle
        self.assertIsNone(me.view.msg_box)

    def test_wired(self):
        qml = (ROOT / "qml" / "pages" / "ScanPage.qml").read_text(encoding="utf-8")
        self.assertIn("onMsgBoxChanged: sp.setMessageBox(", qml)
        self.assertIn("sp.setMessageBox(msgBox.x", qml.split("Component.onCompleted: { scanTiles.setActive(visible);")[1][:80])
        view = (ROOT / "ui" / "scanview.py").read_text(encoding="utf-8")
        self.assertIn("self.msg_box = None", view)
        self.assertIn("if self.stream and self.msg_box is not None:", view)


if __name__ == "__main__":
    unittest.main()
