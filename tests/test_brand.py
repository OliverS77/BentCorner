"""The brand in brand/ (ui/brand.py, legal 03.11.2026 P6): all rights reserved, not GPL – so the program must build and
run without it, with neutral placeholders (plain grey card, the name as text, a random first loading card). And our
servers' names live only in system/contacts.py (forks change them there), apart from legal texts.

    python -m unittest tests/test_brand.py
"""
import ast
import pathlib
import re
import tempfile
import unittest
from unittest import mock

from PySide6 import QtCore, QtGui, QtQml

from ui import brand, iconkit

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["test", "-platform", "offscreen"])


class WithBrand(unittest.TestCase):
    def test_logo_icons_and_load_card(self):
        self.assertTrue(brand.present())
        for name in ("icon.ico", "icon.png", "loadcard.json", "BRAND.md"):
            self.assertTrue((brand.folder() / name).is_file(), name)
        self.assertEqual(brand.load_card(), {"corner": 1, "fold": 21.0, "tilt": -7.0})
        self.assertEqual(brand.info(), {"logo": True, "name": "Bent°Corner", "word": "BENT°CORNER",
                                        "loadCard": [1, 21.0, -7.0, 1.0]})

    def test_nothing_points_to_the_old_places(self):
        for p in ("icon.ico", "assets/icon.png", "assets/logo"):
            self.assertFalse((ROOT / p).exists(), p)


class WithoutBrand(unittest.TestCase):
    """A fork without brand/: everything still works, with placeholders."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(brand, "folder", lambda: pathlib.Path(self.tmp.name) / "brand")
        p.start()
        self.addCleanup(p.stop)

    def test_info_neutral(self):
        self.assertFalse(brand.present())
        self.assertIsNone(brand.load_card())
        self.assertEqual(brand.info(), {"logo": False, "name": "Bent°Corner", "word": "BENT°CORNER",
                                        "loadCard": [0.0, 0.0, 0.0, 0.0]})

    def test_icons_are_a_plain_card(self):
        for size in iconkit.SIZES:
            img = iconkit.pixel_image(size)
            self.assertEqual(img.shape, (size, size, 4))
            self.assertEqual(img[size // 2, size // 2, 3], 255)      # the card in the middle
            self.assertEqual(img[0, 0, 3], 0)                        # transparent around it
        ico = pathlib.Path(self.tmp.name) / "icon.ico"
        iconkit.write_ico(ico)
        self.assertGreater(ico.stat().st_size, 1000)

    def test_lockup_is_the_name_alone(self):
        _img, w_none, _h = iconkit.lockup_image(21)
        mock.patch.stopall()
        _img, w_brand, _h = iconkit.lockup_image(21)
        self.assertLess(w_none, w_brand)                             # no card in front of the name

    def test_qml_lockup_and_loading_load(self):
        for name in ("Lockup.qml", "Loading.qml"):
            engine = QtQml.QQmlEngine()
            from ui import quickui
            engine.rootContext().setContextProperty("T", quickui.palette())
            brand.expose(engine.rootContext())
            comp = QtQml.QQmlComponent(engine, QtCore.QUrl.fromLocalFile(str(ROOT / "qml" / "components" / name)))
            obj = comp.create()
            self.assertIsNotNone(obj, comp.errorString())


class DisplayNameOnce(unittest.TestCase):
    """legal 03.11.2026: the name as text may stay without brand/, but it is ONE constant (ui/brand.NAME) that the
    lockup, the window title and the launcher read – a fork changes it in one place. The GPL attribution is separate."""
    READERS = ["qml/components/Lockup.qml", "qml/Main.qml", "qml/components/BootShuffle.qml", "ui/iconkit.py",
               "launcher/Launcher.cs"]

    def test_trade_ticket_header(self):
        self.assertIn("brand.WORD, 30, ink, display=True", (ROOT / "collection" / "tradelib.py").read_text("utf-8"))

    def test_readers_use_the_constant(self):
        for rel in self.READERS:
            if rel.endswith(".py"):
                code = "\n".join(_strings(ROOT / rel))
            else:   # without // comments
                code = "\n".join(line.split("//")[0] for line in (ROOT / rel).read_text("utf-8-sig").splitlines())
            self.assertNotRegex(code, r"(?i)bent°corner(?! essentials)", rel)

    def test_attribution_stays_apart(self):
        from ui import qsetpages
        self.assertEqual(qsetpages.GPL_ATTRIBUTION, "Based on Bent°Corner – https://bentcorner.app")
        with mock.patch.object(brand, "NAME", "Fork"):
            self.assertEqual(qsetpages.GPL_ATTRIBUTION, "Based on Bent°Corner – https://bentcorner.app")


HOSTS = re.compile(r"bentcorner\.app|oliver-schunn\.tech")
# legal texts and history may name the server – they describe it, they don't use it
ALLOWED = {"system/contacts.py", "app.py", "version.py", "patchnotes.py", "games/extras.py"}
CODE = ["cards", "collection", "games", "launcher", "net", "scanner", "system", "ui", "qml"]


def _strings(path):
    """String constants of a Python file that aren't docstrings."""
    tree = ast.parse(path.read_text("utf-8"))
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs]


class HostsOnlyInContacts(unittest.TestCase):
    def test_code_names_no_server_of_ours(self):
        from ui import qsetpages
        found = []
        for d in CODE:
            for f in sorted((ROOT / d).rglob("*")):
                rel = f.relative_to(ROOT).as_posix()
                if rel in ALLOWED or "/locales/" in f"/{rel}" or not f.is_file():
                    continue
                if f.suffix == ".py":
                    hits = [s for s in _strings(f) if HOSTS.search(s) and s != qsetpages.GPL_ATTRIBUTION]
                elif f.suffix in (".qml", ".cs", ".js"):
                    hits = [line for line in f.read_text("utf-8").splitlines()
                            if HOSTS.search(line.split("//", 1)[0] if "://" not in line else line.replace("://", ""))]
                else:
                    continue
                found += [f"{rel}: {h[:80]}" for h in hits]
        self.assertEqual(found, [], "use system/contacts.py (SERVER, SERVER_OLD, SITE, MAIL)")


if __name__ == "__main__":
    unittest.main()
