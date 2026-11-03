"""Every .qml file of the program compiles (offscreen, no window): syntax errors, unknown types, broken imports and
property typos in bindings show up here instead of as an empty page in the app. Context values the program sets
(shell, T, the page backends) are only needed at run time – the tours check those.

    python -m unittest tests/test_qml_load.py
"""
import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtQml  # noqa: E402

from ui import quickui  # noqa: E402

QML = quickui.qml_dir()


def _app():
    return QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])


class QmlCompiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.engine = QtQml.QQmlEngine()

    def test_every_file_compiles(self):
        files = sorted(QML.rglob("*.qml"))
        self.assertGreater(len(files), 50)
        bad = []
        for f in files:
            comp = QtQml.QQmlComponent(self.engine, QtCore.QUrl.fromLocalFile(str(f)))
            while comp.status() == QtQml.QQmlComponent.Loading:
                self.app.processEvents()
            if comp.status() != QtQml.QQmlComponent.Ready:
                bad.append(f"{f.relative_to(QML).as_posix()}: " + "; ".join(e.toString() for e in comp.errors()))
        self.assertEqual(bad, [], "\n".join(bad))

    def test_every_page_the_shell_registers_exists(self):
        import re
        src = (QML.parent / "ui" / "quickshell.py").read_text("utf-8")
        pages = set(re.findall(r'"(\w+Page\.qml)"', src)) | set(re.findall(r'"(\w+\.qml)"', src))
        missing = sorted(p for p in pages if not (QML / "pages" / p).exists() and not (QML / p).exists())
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
