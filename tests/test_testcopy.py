"""A test copy stays a test copy (Oliver 05.11.2026): bc-testkopie.txt next to the exe isolates a double click on the
test starter or on the program in "Bent°Corner Essentials"; test copies never stay in the tray; closing the first-run
setup window really ends the setup (before: TypeError in the closing slot, the program stayed on invisibly)."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from system import datahome

ROOT = pathlib.Path(__file__).resolve().parents[1]
STARTER = datahome.STARTER_KEYS


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


class Marker(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in datahome.MARKER_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.t = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def good(self, extra=""):
        t = self.t
        return (f"BC_STARTER_LOCAL={t / 'local'}\nBC_STARTER_ROAMING={t / 'roaming'}\n"
                f"BC_STARTER_DOCUMENTS={t / 'docs'}\n" + extra)

    def test_read_keeps_only_known_keys(self):
        f = self.t / "m.txt"
        _write(f, self.good("BC_CHECK=1\nHTTPS_PROXY=http://127.0.0.1:9\nPATH=C:\\evil\nBENTCORNER_EXE=x\n"))
        got = datahome.read_marker(f)
        self.assertEqual(set(got), set(STARTER) | {"BC_CHECK", "HTTPS_PROXY"})

    def test_read_refuses_relative_or_missing_folders(self):
        f = self.t / "m.txt"
        _write(f, self.good().replace(str(self.t / "docs"), "docs"))
        self.assertIsNone(datahome.read_marker(f))
        _write(f, f"BC_STARTER_LOCAL={self.t / 'local'}\n")
        self.assertIsNone(datahome.read_marker(f))
        self.assertIsNone(datahome.read_marker(self.t / "missing.txt"))

    def test_applies_next_to_the_exe_and_one_folder_up(self):
        ess = self.t / "local" / "Bent°Corner Essentials"
        _write(ess / datahome.TEST_MARKER, self.good("BC_CHECK=1\n"))
        for exe in (ess / "BentCorner.exe", ess / "0.9.7.42-x" / "BentCorner.exe"):
            for k in datahome.MARKER_KEYS:
                os.environ.pop(k, None)
            self.assertEqual(datahome.apply_marker(exe), ess / datahome.TEST_MARKER)
            self.assertEqual(os.environ["BC_STARTER_LOCAL"], str(self.t / "local"))
            self.assertEqual(os.environ["BC_CHECK"], "1")

    def test_switches_already_set_win(self):
        _write(self.t / datahome.TEST_MARKER, self.good())
        os.environ["BC_STARTER_LOCAL"] = str(self.t / "other")
        self.assertIsNone(datahome.apply_marker(self.t / "BentCorner.exe"))
        self.assertEqual(os.environ["BC_STARTER_LOCAL"], str(self.t / "other"))
        self.assertNotIn("BC_STARTER_ROAMING", os.environ)

    def test_no_marker_nothing_changes(self):
        self.assertIsNone(datahome.apply_marker(self.t / "app" / "BentCorner.exe"))
        self.assertFalse(any(k in os.environ for k in datahome.MARKER_KEYS))

    def test_source_run_never_reads_a_marker(self):
        self.assertIn("MARKER = apply_marker(", (ROOT / "system" / "datahome.py").read_text("utf-8"))
        self.assertIsNone(datahome.MARKER)   # not frozen: the line is skipped

    def test_frozen_double_click_on_the_program_is_isolated(self):
        """The real import path: a 'frozen' process whose exe sits next to the marker comes up ISOLATED, with its
        single-instance lock keyed to the test folder, not to the Windows user."""
        ess = self.t / "local" / "Bent°Corner Essentials"
        _write(ess / datahome.TEST_MARKER, self.good())
        code = ("import sys; sys.frozen = True; sys.executable = sys.argv[1]\n"
                "from system import datahome\n"
                "from ui import tray\n"
                "print(datahome.ISOLATED, datahome.MARKER is not None, tray._server_name())\n")
        env = {k: v for k, v in os.environ.items() if k not in datahome.MARKER_KEYS and k != "BENTCORNER_EXE"}
        env["QT_QPA_PLATFORM"] = "offscreen"
        run = lambda exe: subprocess.run([sys.executable, "-c", code, str(exe)], cwd=ROOT, env=env, capture_output=True,
                                         text=True, timeout=120).stdout.split()
        test = run(ess / "BentCorner.exe")
        real = run(self.t / "real" / "BentCorner.exe")
        self.assertEqual(test[:2], ["True", "True"])
        self.assertEqual(real[:2], ["False", "False"])
        self.assertNotEqual(test[2], real[2])   # different lock: the test copy can't block the real program


class LauncherSource(unittest.TestCase):
    """Launcher.cs reads the same file with the same keys and copies it into Essentials (only in a test run)."""

    def test_same_keys_and_order(self):
        src = (ROOT / "launcher" / "Launcher.cs").read_text("utf-8-sig")
        self.assertIn('TEST_MARKER = "' + datahome.TEST_MARKER + '"', src)
        keys = ", ".join(f'"{k}"' for k in datahome.MARKER_KEYS)
        self.assertIn(" ".join(keys.split()), " ".join(src.split()))
        main = src[src.index("static int Main"):]
        self.assertLess(main.index("ApplyTestMarker("), main.index("ApplyTestEnv()"))
        self.assertLess(main.index("Activate(essentials, id)"), main.index("CopyTestMarker(essentials)"))
        copy = src[src.index("internal static void CopyTestMarker"):]
        self.assertLess(copy.index("if (!IsTestRun()) return;"), copy.index("File.WriteAllText"))


class Tray(unittest.TestCase):
    def test_isolated_copies_never_stay_in_the_tray(self):
        from ui import tray
        ctrl = mock.Mock(settings={"tray_mode": True})
        with mock.patch.object(tray.QtWidgets.QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
            obj = mock.Mock(ctrl=ctrl)
            with mock.patch.object(datahome, "ISOLATED", True):
                self.assertFalse(tray.Tray.enabled.fget(obj))
            with mock.patch.object(datahome, "ISOLATED", False):
                self.assertTrue(tray.Tray.enabled.fget(obj))


class SetupWindowClose(unittest.TestCase):
    def test_closing_the_setup_window_ends_the_setup(self):
        """In its own process (Qt Quick, offscreen): the window is closed with X after 1 s -> quick_first_run comes
        back not accepted, nothing keeps running."""
        code = ("import sys, faulthandler\n"
                "faulthandler.dump_traceback_later(60, exit=True)\n"
                "from PySide6 import QtCore, QtGui, QtWidgets\n"
                "app = QtWidgets.QApplication(sys.argv)\n"
                "from ui import setupui\n"
                "QtCore.QTimer.singleShot(1000, lambda: [w.close() for w in QtGui.QGuiApplication.topLevelWindows()])\n"
                "b = setupui.quick_first_run()\n"
                "print('RESULT', b is not None, b is not None and b.accepted)\n")
        with tempfile.TemporaryDirectory() as t:
            env = {k: v for k, v in os.environ.items() if k not in datahome.MARKER_KEYS}
            env.update(QT_QPA_PLATFORM="offscreen", BC_STARTER_LOCAL=str(pathlib.Path(t) / "local"),
                       BC_STARTER_ROAMING=str(pathlib.Path(t) / "roaming"),
                       BC_STARTER_DOCUMENTS=str(pathlib.Path(t) / "docs"))
            r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                               timeout=120)
        self.assertIn("RESULT True False", r.stdout, r.stderr[-2000:])
        self.assertNotIn("TypeError", r.stderr)


if __name__ == "__main__":
    unittest.main()
