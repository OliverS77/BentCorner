"""Data next to the code goes into the package (13.11.2026: 0.9.7 shipped without system/nicknames.json – PyInstaller only
collects the .py of a package – and every first sync failed). Every non-Python file in the app's packages must be
added by build.ps1 (--add-data) and be one of tools/check_package.REQUIRED, which stops a build without it.

    python -m unittest tests/test_package_data.py
"""
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_package  # noqa: E402

PACKAGES = ("collection", "net", "system", "ui", "cards", "scanner", "games", "locales")


def data_files():
    out = []
    for pkg in PACKAGES:
        for f in (ROOT / pkg).rglob("*"):
            if f.is_file() and f.suffix not in (".py", ".pyc") and "__pycache__" not in f.parts:
                out.append(f.relative_to(ROOT).as_posix())
    return sorted(out)


class PackageData(unittest.TestCase):
    def test_every_data_file_is_added_and_checked(self):
        build = (ROOT / "build.ps1").read_text("utf-8-sig")
        files = data_files()
        self.assertIn("system/nicknames.json", files)
        for rel in files:
            win = rel.replace("/", "\\")
            folder = win.rsplit("\\", 1)[0]
            self.assertIn(f'--add-data "{win};{folder}"', build, f"build.ps1 doesn't add {rel}")
            self.assertIn(rel, check_package.REQUIRED, f"check_package.REQUIRED misses {rel}")

    def test_check_package_stops_without_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = pathlib.Path(tmp) / "app-stage" / "0.9.7-2611122159" / "system"
            stage.mkdir(parents=True)
            (stage / "nicknames.pyc").write_bytes(b"x")
            self.assertEqual(check_package.missing_entries(pathlib.Path(tmp) / "app-stage"), ["system/nicknames.json"])
            (stage / "nicknames.json").write_text("{}", "utf-8")
            self.assertEqual(check_package.missing_entries(pathlib.Path(tmp) / "app-stage"), [])


if __name__ == "__main__":
    unittest.main()
