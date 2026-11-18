"""InlineAsk – the name field that grows in place (no dialog). With fill: true it fills a tile: „+ New list“ and renaming
under Lists & Orbit, „+ New binder“. Since 0.9.2 accept() closed it first and then called the field, which with fill
is already gone: the call broke off before accepted() and nothing was created (Oliver 17.11.2026).

Plays the real InlineAsk.qml offscreen in the same shape as the tiles (fill, an extra row of toggles) and as the
growing field of the list bar: open, type, OK (button and Enter) → accepted(mode, ident, text) arrives, no QML error.

    python -m unittest tests/test_inline_ask.py
"""
import os
import pathlib
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtQml  # noqa: E402

from ui import quickui, setupui  # noqa: E402

QML = quickui.qml_dir()

HOST = """
import QtQuick
import "%s"
Item {
    id: root
    width: 240; height: 320
    property string got: ""
    property int cancels: 0
    property bool fillMode: true
    InlineAsk {
        id: ask
        anchors.fill: fillMode ? parent : undefined
        fill: root.fillMode; z: 5
        placeholder: "Name"
        onAccepted: function (mode, ident, text) { root.got = mode + "|" + ident + "|" + text }
        onCanceled: root.cancels += 1
        extra: Component { Column { spacing: 8   // like the tiles: game / private-shared toggles below the field
            Rectangle { width: 80; height: 24 } Rectangle { width: 80; height: 24 } } }
    }
    function open_(mode, ident, text) { ask.start(mode, ident, "Title", text, "Create") }
    function type_(t) { ask.field.text = t }
    function ok() { ask.accept() }
    function enter() { ask.field.accepted() }
    function cancel() { ask.cancel() }
    function isOpen() { return ask.open }
}
"""


def _app():
    return QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])


class InlineAskAccepts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.shell = setupui._MiniShell()   # keep a reference – the context does not own it
        cls.T = quickui.palette()

    def setUp(self):
        self.msgs = []
        self._old = QtCore.qInstallMessageHandler(lambda t, c, m: self.msgs.append(m))
        self.engine = QtQml.QQmlEngine()
        ctx = self.engine.rootContext()
        ctx.setContextProperty("T", self.T)
        ctx.setContextProperty("shell", self.shell)
        comp = QtQml.QQmlComponent(self.engine)
        comp.setData((HOST % (QML / "components").as_uri()).encode("utf-8"),
                     QtCore.QUrl.fromLocalFile(str(QML / "components" / "_host.qml")))
        self.comp = comp
        self.root = comp.create()
        self.assertIsNotNone(self.root, "; ".join(e.toString() for e in comp.errors()))
        QtQml.QQmlEngine.setObjectOwnership(self.root, QtQml.QQmlEngine.CppOwnership)   # not the JS collector's

    def tearDown(self):
        QtCore.qInstallMessageHandler(self._old)
        self.root.deleteLater()
        self.spin()
        del self.engine

    def spin(self, n=12):
        for _ in range(n):
            self.app.processEvents()
            QtCore.QThread.msleep(10)

    def call(self, name, *args):
        QtCore.QMetaObject.invokeMethod(self.root, name, *[QtCore.Q_ARG("QVariant", a) for a in args])
        self.spin()

    def play(self, fill, mode, ident, how="ok"):
        self.root.setProperty("fillMode", fill)
        self.spin()
        self.call("open_", mode, ident, "old name" if mode == "rename" else "")
        self.call("type_", "Testliste")
        self.call("ok" if how == "ok" else "enter")
        errors = [m for m in self.msgs if "InlineAsk.qml" in m]
        return self.root.property("got"), errors

    def test_tile_new_list(self):   # Lists & Orbit: „+ New list“ tile
        got, errors = self.play(True, "new", "")
        self.assertEqual(got, "new||Testliste")
        self.assertEqual(errors, [])

    def test_tile_rename_list(self):   # Lists & Orbit: rename on the tile
        got, errors = self.play(True, "rename", "abc123")
        self.assertEqual(got, "rename|abc123|Testliste")
        self.assertEqual(errors, [])

    def test_tile_new_binder_by_enter(self):   # „+ New binder“ tile, confirmed with Enter in the field
        got, errors = self.play(True, "new", "", how="enter")
        self.assertEqual(got, "new||Testliste")
        self.assertEqual(errors, [])

    def test_growing_field_still_works(self):   # the library's list bar (fill: false)
        got, errors = self.play(False, "new", "custom")
        self.assertEqual(got, "new|custom|Testliste")
        self.assertEqual(errors, [])

    def test_closes_after_ok_and_empty_name_does_nothing(self):
        self.root.setProperty("fillMode", True)
        self.call("open_", "new", "", "")
        self.call("type_", "   ")
        self.call("ok")
        self.assertEqual(self.root.property("got"), "")
        self.call("type_", "Testliste")
        self.call("ok")
        self.assertEqual(self.root.property("got"), "new||Testliste")
        self.call("cancel")   # already closed: no second „canceled“
        self.assertEqual(self.root.property("cancels"), 0)


class TilesUseIt(unittest.TestCase):
    """The tiles that fill themselves with the field – the places the bug hit – still hand the name on."""

    def test_tiles_with_fill_hand_the_name_on(self):
        want = {"pages/TradePage.qml": ("newListFull", "renameListTo"), "components/BinderGrid.qml": ("newBinder",)}
        for rel, calls in want.items():
            src = (QML / rel).read_text("utf-8")
            block = src[src.index("InlineAsk {"):]
            block = block[:block.index("extra:")]
            self.assertRegex(block, r"fill:\s*true", rel)
            for c in calls:
                self.assertIn(c, block, f"{rel}: {c}")

    def test_accept_reads_the_field_before_closing(self):
        src = (QML / "components" / "InlineAsk.qml").read_text("utf-8")
        body = re.search(r"function accept\(\) \{(.*?)\n    \}", src, re.S).group(1)
        code = "\n".join(ln.split("//")[0] for ln in body.splitlines())   # without the comments
        self.assertLess(code.index("dropFocus"), code.index("open = false"))
        self.assertLess(code.index("open = false"), code.index("accepted("))


if __name__ == "__main__":
    unittest.main()
