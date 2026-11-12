"""The move from the old starter to the installer (system/installinfo.py): Essentials goes only when it holds nothing
but the starter's own files; the note comes once, only to those who came from the starter. Temp folders only.

    python -m unittest tests/test_installinfo.py
"""
import pathlib
import tempfile
import unittest
from unittest import mock

from system import installinfo


class Move(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name) / "Docs" / "BentCorner"
        self.ess = self.home / installinfo.ESSENTIALS
        (self.ess / "0.9.7.20-2611011200").mkdir(parents=True)
        (self.ess / "0.9.7.20-2611011200" / "BentCorner.exe").write_bytes(b"x")
        for n in ("BentCorner.exe", "current.txt", "installation.txt"):
            (self.ess / n).write_text("x", "utf-8")
        for p in (mock.patch.object(installinfo.datahome, "HOME", self.home),
                  mock.patch.object(installinfo, "installed", lambda: True),
                  mock.patch.dict("os.environ", {"BC_STARTER_LOCAL": str(pathlib.Path(self.tmp.name) / "Local")})):
            p.start()
            self.addCleanup(p.stop)

    def test_only_ours_goes(self):
        self.assertEqual(installinfo.tidy_essentials(), [str(self.ess)])
        self.assertFalse(self.ess.exists())
        self.assertTrue(self.home.exists())   # the data folder itself is never touched

    def test_anything_else_keeps_it(self):
        (self.ess / "my notes.txt").write_text("mine", "utf-8")
        self.assertEqual(installinfo.tidy_essentials(), [])
        self.assertTrue((self.ess / "my notes.txt").exists())

    def test_note_once_and_only_after_a_move(self):
        s = {}
        self.assertTrue(installinfo.after_move(s))
        self.assertFalse(installinfo.after_move(s))          # once
        fresh = {}
        self.assertFalse(installinfo.after_move(fresh))      # a fresh install (no Essentials): no note

    def test_not_installed_does_nothing(self):
        with mock.patch.object(installinfo, "installed", lambda: False):
            self.assertFalse(installinfo.after_move({}))
        self.assertTrue(self.ess.exists())


if __name__ == "__main__":
    unittest.main()
