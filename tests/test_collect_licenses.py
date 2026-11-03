"""licenses/ for the exe (tools/collect_licenses.py, legal 03.11.2026 P4): the LGPL texts for Qt, FFmpeg and GEOS, and
every file THIRD_PARTY_NOTICES.md points to under licenses/ must really be there – the notices name nothing that isn't.

    python -m unittest tests/test_collect_licenses.py
"""
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import collect_licenses  # noqa: E402

# the public notices (overlay) where the private source still has them, else the exported ones at the top
NOTICES = [p for p in (ROOT / "tools" / "public" / "overlay" / "THIRD_PARTY_NOTICES.md", ROOT / "THIRD_PARTY_NOTICES.md")
           if p.exists()][0]


class CollectLicenses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = pathlib.Path(cls.tmp.name) / "licenses"
        cls.count = collect_licenses.collect(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_lgpl_and_gpl_texts(self):
        for name in ("GPL-3.0.txt", "LGPL-3.0.txt", "LGPL-2.1.txt", "Apache-2.0.txt"):
            self.assertTrue((self.out / name).is_file(), name)
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", (self.out / "LGPL-2.1.txt").read_text("utf-8"))
        self.assertIn("Version 2.1, February 1999", (self.out / "LGPL-2.1.txt").read_text("utf-8"))
        self.assertIn("Version 3, 29 June 2007", (self.out / "LGPL-3.0.txt").read_text("utf-8"))

    def test_every_file_the_notices_name_is_there(self):
        named = set(re.findall(r"`licenses/([\w.-]+)`", NOTICES.read_text("utf-8")))
        self.assertTrue(named, "the notices name files under licenses/")
        for name in named:
            self.assertTrue((self.out / name).is_file(), f"THIRD_PARTY_NOTICES names licenses/{name}")

    def test_package_licenses_without_build_tools_and_qt_commercial(self):
        names = {p.name.rsplit("-", 1)[0] for p in (self.out / "packages").iterdir()}
        self.assertIn("numpy", names)
        self.assertIn("onnxruntime-directml", names)   # its LICENSE sits in the package folder, not the .dist-info
        self.assertFalse(names & collect_licenses.BUILD_ONLY)
        self.assertFalse(list(self.out.rglob("LicenseRef-Qt-Commercial.txt")))
        self.assertGreater(self.count, 20)

    def test_every_package_has_its_line_in_the_notices(self):
        text = NOTICES.read_text("utf-8")
        for p in (self.out / "packages").iterdir():
            name = re.sub(r"-[\d.]+$", "", p.name)
            pattern = r"(?<![a-z])(" + re.escape(name) + "|" + re.escape(name.replace("-", " ")) + r")(?![a-z])"
            self.assertRegex(text.lower(), pattern, f"licenses/packages/{p.name} – no line in {NOTICES.name}")
        self.assertFalse({re.sub(r"-[\d.]+$", "", p.name) for p in (self.out / "packages").iterdir()}
                         & collect_licenses.NOT_BUNDLED)

    def test_same_venv_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            again = pathlib.Path(tmp) / "licenses"
            collect_licenses.collect(again)
            a = {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
            b = {p.relative_to(again).as_posix(): p.read_bytes() for p in again.rglob("*") if p.is_file()}
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
