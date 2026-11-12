"""Review 08.11.2026 (Gordon B2/B5/B6): set packages and font ZIPs from outside.
B2: an image path in a set's card list never leads out of card-images/ (a UNC path would make Windows send its login
hash) – one bad path and the whole package is refused, nothing written; B5: entries have sane sizes, also while
reading; B6: a font from a ZIP lands only as a plain file name in the font folder, never overwriting one.
Throwaway folders only.

    python -m unittest tests/test_review_setpack.py
"""
import json
import pathlib
import tempfile
import unittest
import zipfile
from unittest import mock

from cards import library


def pack(path, img="data/card-images/neo/12.jpg", big=0):   # as real card lists store it
    cards = [{"name": "A", "img": img}]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("recognition/neo.json", json.dumps({"code": "neo", "cards": cards}))
        z.writestr("recognition/neo.npz", b"x")
        z.writestr("card-images/neo/12.jpg", b"j" * (big or 3))


class SetPackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.data = self.root / "data"
        self.p = mock.patch.object(library, "DATA", self.data)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self._tmp.cleanup()

    def test_a_normal_package(self):
        z = self.root / "ok.zip"
        pack(z)
        self.assertEqual(library.import_sets(z), ["neo"])
        self.assertTrue((self.data / "card-images/neo/12.jpg").exists())

    def test_unsafe_image_paths_refuse_the_whole_package(self):
        for bad in ("//attacker/share/a.jpg", "\\\\attacker\\share\\a.jpg", "C:/Windows/a.jpg",
                    "card-images/../../x.jpg", "../a.jpg", "card-images/neo/12.png", "data/../x/card-images/a.jpg"):
            z = self.root / "bad.zip"
            pack(z, img=bad)
            with self.assertRaises(RuntimeError, msg=bad):
                library.import_sets(z)
            self.assertFalse(self.data.exists(), bad)                     # nothing written

    def test_entries_have_a_size_limit(self):
        z = self.root / "big.zip"
        pack(z, big=2048)
        with mock.patch.dict(library.PACK_MAX, {".jpg": 1024}):
            with self.assertRaises(RuntimeError):
                library.import_sets(z)


class FontTest(unittest.TestCase):
    def setUp(self):
        from ui import look
        self.look = look
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.fonts = self.root / "fonts"
        self.fonts.mkdir()
        self.p = mock.patch.object(look, "FONT_DIR", self.fonts)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self._tmp.cleanup()

    def test_only_plain_names_in_the_font_folder(self):
        self.assertIsNotNone(self.look._font_target("Inter Regular.ttf"))
        for bad in ("D:evil.ttf", "..\\x.ttf", "a/b.ttf", "x.ttf.exe", "C:\\evil.otf"):
            self.assertIsNone(self.look._font_target(bad), bad)
        (self.fonts / "Mine.ttf").write_bytes(b"old")
        self.assertIsNone(self.look._font_target("Mine.ttf"))             # never overwritten

    def test_zip_import_skips_bad_and_big(self):
        z = self.root / "f.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("D:evil.ttf", b"x")
            zf.writestr("ok/Good.ttf", b"x" * 10)
            zf.writestr("Big.ttf", b"x" * 2048)
        with mock.patch.object(self.look, "FONT_MAX", 1024), \
                mock.patch("PySide6.QtGui.QFontDatabase.addApplicationFont", return_value=-1):
            self.look.import_fonts([z])
        self.assertEqual(sorted(p.name for p in self.fonts.iterdir()), ["Good.ttf"])


if __name__ == "__main__":
    unittest.main()
