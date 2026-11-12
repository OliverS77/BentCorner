"""tools/ticket_snapshot.py (performance's find 03.11.2026): since 0.9.7.33 the build step aborted hard and left orphan
folders. A format's code is "flattened" ("from ui import brand" -> "import brand"); that name has to reach ui.brand
while the archived code draws – else the import fails mid-drawing and the open QPainter takes Qt down. And a sample
that doesn't draw for the current version writes nothing (exit with an error, build.ps1 stops).

    python -m unittest tests/test_ticket_snapshot.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ticket_snapshot_t", ROOT / "tools" / "ticket_snapshot.py")
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)


class FlatImports(unittest.TestCase):
    def test_flattened_name_reaches_the_package_module_and_goes_again(self):
        from ui import brand
        before = sys.modules.get("brand")
        saved = ts._aliases({"offer_image.py": "def f():\n    import brand\n    return brand.WORD\n",
                             "ticket.py": "import rscode\n"})
        try:
            self.assertIs(sys.modules["brand"], brand)
            self.assertNotIn("ticket", saved)     # those two come from the format itself
            self.assertNotIn("rscode", saved)
        finally:
            for k, m in saved.items():
                if m is not None:
                    sys.modules[k] = m
                else:
                    sys.modules.pop(k, None)
        self.assertIs(sys.modules.get("brand"), before)

    def test_the_current_format_flattens_and_still_draws_its_imports(self):
        src = ts.sources_now()
        self.assertIn("import brand", src["offer_image.py"])   # the reason – if it moves, this test can go
        saved = ts._aliases(src)
        try:
            from ui import brand
            self.assertIs(sys.modules["brand"], brand)
        finally:
            for k, m in saved.items():
                if m is not None:
                    sys.modules[k] = m
                else:
                    sys.modules.pop(k, None)


class NothingHalfWritten(unittest.TestCase):
    def test_a_sample_that_does_not_draw_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            man = {"current": "", "formats": {}, "versions": []}
            with mock.patch.object(ts, "OUT", out), \
                    mock.patch.object(ts, "render", side_effect=AttributeError("module 'brand' has no attribute 'WORD'")):
                with self.assertRaises(SystemExit):
                    ts.snapshot({"ticket.py": "VERSION = 1\n", "rscode.py": "", "offer_image.py": "x"}, "9.9.9", "", man)
            self.assertEqual(list(out.iterdir()), [], "no formats/ or versions/ folder")
            self.assertEqual(man["versions"], [])

    def test_history_keeps_the_note_for_old_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            man = {"current": "", "formats": {}, "versions": []}
            with mock.patch.object(ts, "OUT", out), mock.patch.object(ts, "render", side_effect=ImportError("old")):
                self.assertTrue(ts.snapshot({"ticket.py": "VERSION = 1\n", "rscode.py": "", "offer_image.py": "x"},
                                            "0.1", "", man, strict=False))
            about = json.loads((out / "versions" / "0.1" / "about.json").read_text("utf-8"))
            self.assertIn("Muster nicht zeichenbar", about["note"])


if __name__ == "__main__":
    unittest.main()
