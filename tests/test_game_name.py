"""The mini game's name (lead 13.11.2026, Gordon + legal): from 0.9.8 on it lives ONLY in ui/scalper.py TITLE – the
settings page, the game's start picture and the web (tools/export_web_scalper.py) take it from there. The old name
is nowhere in the code any more; only the patch history keeps it (what was shipped back then).
"""
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OLD = "Scalper " + "Invaders"            # put together: this file must not match itself
CODE = {".py", ".qml", ".js", ".mjs", ".css", ".html", ".json", ".txt", ".md", ".ps1", ".sh"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "data", "build", "dist", "__pycache__", "labs"}
HISTORY = {"patchnotes.py", "CHANGELOG.md"}   # what was shipped under the old name stays as it was


class GameName(unittest.TestCase):
    def test_one_place(self):
        from ui import scalper
        self.assertTrue(scalper.TITLE)
        self.assertNotEqual(scalper.TITLE.lower(), OLD.lower())
        import app
        self.assertIn(("game", "game", scalper.TITLE), [p[:3] for p in app.SETTINGS_PAGES])

    def test_old_name_gone(self):
        hits = []
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                p = pathlib.Path(folder) / f
                if p.suffix.lower() not in CODE or f in HISTORY:
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if OLD.lower() in line.lower() or OLD.upper().replace(" ", "") in line.replace(" ", "").upper():
                        hits.append(f"{p.relative_to(ROOT)}:{n}")
        self.assertEqual(hits, [], "old game name still in the code – use ui/scalper.py TITLE")

    def test_never_uppercase(self):
        # legal 14.11.2026: the name is never shown in capitals (no "SCALPERS"-like wordmark) – as written in TITLE
        from ui import scalper
        self.assertNotEqual(scalper.TITLE, scalper.TITLE.upper())
        qml = (ROOT / "qml" / "components" / "ScalperGame.qml").read_text(encoding="utf-8")
        self.assertRegex(qml, r"text: root\.title(?!\.)")   # the start picture shows TITLE as written
        for bad in ("title.toUpperCase", "Font.AllUppercase", "Font.SmallCaps"):
            self.assertNotIn(bad, qml)


class GameNode(unittest.TestCase):
    def test_title_done_go(self):
        from ui import scalper

        class Ui:
            n = 0

            def _id(self, fn):
                self.fn = fn
                return "g1"
        ui, went = Ui(), []
        orig = scalper.ship_url, scalper.sprites
        scalper.ship_url, scalper.sprites = (lambda back: ""), (lambda: {})
        try:
            node = scalper.node(ui, {}, done=True, on_go=lambda: went.append(1))
        finally:
            scalper.ship_url, scalper.sprites = orig
        self.assertEqual(node["title"], scalper.TITLE)
        self.assertTrue(node["done"] and node["go"])
        ui.fn(["go"])
        self.assertEqual(went, [1])
        scalper.ship_url, scalper.sprites = (lambda back: ""), (lambda: {})
        try:
            plain = scalper.node(Ui(), {})
        finally:
            scalper.ship_url, scalper.sprites = orig
        self.assertFalse(plain["done"] or plain["go"])   # Settings → Game: never a strip


if __name__ == "__main__":
    unittest.main()
