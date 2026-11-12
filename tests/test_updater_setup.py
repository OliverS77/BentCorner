"""Updates since the installer (net/updater.py, labs/installer/PLAN.md): which file each kind of copy takes, the setup
runs silently and the program quits, a portable folder never replaces itself.

    python -m unittest tests/test_updater_setup.py
"""
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

from net import updater

M = {"latest": "9.9.9", "platforms": {"windows": {"file": "BentCorner-9.9.9.exe"},
                                       "windows_setup": {"file": "BentCorner-Setup-9.9.9.exe"},
                                       "windows_portable": {"file": "BentCorner-9.9.9-portable.zip"}}}


class Kind(unittest.TestCase):
    def test_entry_per_kind(self):
        self.assertEqual(updater.entry_key(M, "installed"), "windows_setup")
        self.assertEqual(updater.entry_key(M, "starter"), "windows_setup")     # the move to the installer
        self.assertEqual(updater.entry_key(M, "portable"), "windows_portable")
        old = {"platforms": {"windows": {"file": "x.exe"}}}
        self.assertEqual(updater.entry_key(old, "starter"), "windows")         # before any setup is offered
        # data next to the starter: the installed program would not find it – stays on the single exe
        self.assertEqual(updater.entry_key(M, "starter-portable"), "windows")

    def test_distribution(self):
        from system import datahome
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as starter_dir:
            exe = pathlib.Path(tmp) / "BentCorner.exe"
            exe.write_bytes(b"")
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", str(exe)), \
                    mock.patch.object(updater, "platform_key", lambda: "windows"), \
                    mock.patch.object(datahome, "APP_DIR", pathlib.Path(starter_dir)), \
                    mock.patch.dict(os.environ, {"BENTCORNER_EXE": ""}):
                self.assertEqual(updater.distribution(), "portable")
                with mock.patch.dict(os.environ, {"BENTCORNER_EXE": "C:/x/BentCorner.exe"}):
                    self.assertEqual(updater.distribution(), "starter")
                    (pathlib.Path(starter_dir) / "settings.json").write_text("{}")
                    self.assertEqual(updater.distribution(), "starter-portable")
                (pathlib.Path(tmp) / "unins000.exe").write_bytes(b"")
                self.assertEqual(updater.distribution(), "installed")
        self.assertEqual(updater.distribution(), "source")


class WithoutStarter(unittest.TestCase):
    """The first installer release offers no single exe any more (Oliver 06.11.2026: no bridge starter, windows = null):
    every copy still finds its file – only a starter with its data next to it finds none and stays as it is."""
    NEW = {"latest": "9.9.9", "platforms": {"windows": None,
                                            "windows_setup": {"file": "BentCorner-Setup-9.9.9.exe", "size": 1, "sha256": "0"},
                                            "windows_portable": {"file": "BentCorner-9.9.9-portable.zip", "size": 1, "sha256": "0"}}}

    def check(self, dist):
        u = updater.Updater(base="http://127.0.0.1:9/dl", news=lambda: False)
        with mock.patch.object(updater, "fetch_manifest", lambda base: dict(self.NEW)), \
                mock.patch.object(updater, "distribution", lambda: dist), \
                mock.patch.object(updater, "platform_key", lambda: "windows"):
            u.check(auto_download=False)
            for _ in range(200):
                if u.state not in ("idle", "checking"):
                    break
                time.sleep(0.01)
        return u

    def test_each_kind(self):
        for dist, key in (("installed", "windows_setup"), ("starter", "windows_setup"), ("portable", "windows_portable")):
            u = self.check(dist)
            self.assertEqual((u.key, u.state), (key, "available"), dist)
        u = self.check("starter-portable")
        self.assertEqual((u.key, u.state, u.entry), ("windows", "none", None))


class Install(unittest.TestCase):
    def test_setup_runs_silently_and_the_program_quits(self):
        u = updater.Updater()
        u.key, u.entry, u.state = "windows_setup", {"file": "BentCorner-Setup-9.9.9.exe", "sha256": "x"}, "ready"
        started = []
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(u, "_sha_ok", lambda p: True), \
                mock.patch.object(updater, "platform_key", lambda: "windows"), \
                mock.patch("subprocess.Popen", lambda cmd, **kw: started.append(cmd)):
            self.assertEqual(u.install(), "setup")
        self.assertTrue(started[0][0].endswith("BentCorner-Setup-9.9.9.exe"))
        self.assertEqual(started[0][1:], updater.SETUP_ARGS)
        self.assertIn("/RESTARTAPP=1", updater.SETUP_ARGS)

    def test_portable_never_installs(self):
        u = updater.Updater()
        u.key, u.entry, u.state = "windows_portable", {"file": "z.zip"}, "ready"
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(updater, "platform_key", lambda: "windows"):
            self.assertTrue(u.manual)
            self.assertFalse(u.can_install())
        self.assertTrue(u.download_url().endswith("/windows_portable/z.zip"))


if __name__ == "__main__":
    unittest.main()
