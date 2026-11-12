"""Bent°Corner only once per Windows user (ui/tray.py, Oliver/lead 03.11.2026): a second start brings the running window
to the front and quits; the server listens from the start, a request during the start waits for the main window.
Test runs get a name per test folder (BC_HOME, set by tests/__init__) – never the real program's.

    python -m unittest tests/test_single_instance.py
"""
import os
import pathlib
import subprocess
import sys
import textwrap
import time
import unittest
from unittest import mock

from PySide6 import QtCore

from ui import tray

APP = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication(["test"])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the running instance: claim() at once, the main window (listen) only after `late` seconds
CHILD = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {root!r})
    from PySide6 import QtCore
    app = QtCore.QCoreApplication([])
    from ui import tray
    assert tray.acquire()
    tray.claim()
    print("READY", flush=True)
    def shown():
        print("SHOWN", flush=True)
        QtCore.QTimer.singleShot(100, app.quit)
    QtCore.QTimer.singleShot(int({late} * 1000), lambda: tray.listen(shown))
    QtCore.QTimer.singleShot(15000, app.quit)
    # the venv's python.exe is only a redirector: when the test stops it, this (the real) process must end too
    import ctypes, os
    k32 = ctypes.windll.kernel32
    parent = k32.OpenProcess(0x00100000, False, os.getppid())
    watch = QtCore.QTimer(interval=200, timeout=lambda: app.quit() if parent and k32.WaitForSingleObject(parent, 0) == 0 else None)
    watch.start()
    app.exec()
""")


class Name(unittest.TestCase):
    def test_per_user_outside_tests(self):
        with mock.patch.dict(os.environ, {"BC_HOME": "", "USERNAME": "Oliver"}), \
                mock.patch.object(tray.datahome, "ISOLATED", False):
            a = tray._server_name()
            with mock.patch.object(tray.datahome, "HOME", "D:/somewhere/else"):
                self.assertEqual(tray._server_name(), a)          # any data folder: the same lock
        with mock.patch.dict(os.environ, {"BC_HOME": "", "USERNAME": "Max"}), \
                mock.patch.object(tray.datahome, "ISOLATED", False):
            self.assertNotEqual(tray._server_name(), a)           # another user: another lock

    def test_test_runs_have_their_own(self):
        with mock.patch.dict(os.environ, {"BC_HOME": "x", "USERNAME": "Oliver"}):
            with mock.patch.object(tray.datahome, "HOME", "C:/t1"):
                t1 = tray._server_name()
            with mock.patch.object(tray.datahome, "HOME", "C:/t2"):
                t2 = tray._server_name()
        with mock.patch.dict(os.environ, {"BC_HOME": "", "USERNAME": "Oliver"}), \
                mock.patch.object(tray.datahome, "ISOLATED", False):
            real = tray._server_name()
        self.assertNotEqual(t1, t2)
        self.assertNotIn(real, (t1, t2))

    def test_built_exe_ignores_bc_home(self):
        """The exe doesn't follow BC_HOME for its data (datahome) – so it must not split the lock either (lead 06.11.):
        otherwise a second instance could run on the same real data."""
        with mock.patch.dict(os.environ, {"BC_HOME": "", "USERNAME": "Oliver"}), \
                mock.patch.object(tray.datahome, "ISOLATED", False), mock.patch.object(tray.datahome, "FROZEN", True):
            real = tray._server_name()
        with mock.patch.dict(os.environ, {"BC_HOME": "x", "USERNAME": "Oliver"}), \
                mock.patch.object(tray.datahome, "ISOLATED", False), mock.patch.object(tray.datahome, "FROZEN", True), \
                mock.patch.object(tray.datahome, "HOME", "C:/t1"):
            self.assertEqual(tray._server_name(), real)


class SecondStart(unittest.TestCase):
    def run_child(self, late):
        child = subprocess.Popen([sys.executable, "-c", CHILD.format(root=ROOT, late=late)], stdout=subprocess.PIPE,
                                 text=True, env=dict(os.environ))
        self.addCleanup(self.gone)
        self.addCleanup(lambda: (child.kill() if child.poll() is None else None, child.wait(), child.stdout.close()))
        self.assertEqual(child.stdout.readline().strip(), "READY")
        return child

    def gone(self):
        """The real child process ends ~0.2 s after its redirector (see CHILD) – wait until nobody answers."""
        end = time.time() + 3
        while time.time() < end and tray.other_instance():
            time.sleep(0.1)

    def test_second_start_shows_the_running_one(self):
        child = self.run_child(late=0)
        time.sleep(0.3)
        self.assertTrue(tray.other_instance())
        self.assertEqual(child.stdout.readline().strip(), "SHOWN")

    def test_request_during_the_start_waits_for_the_window(self):
        child = self.run_child(late=1.5)   # still "in the first-run setup"
        self.assertTrue(tray.other_instance())
        t = time.time()
        self.assertEqual(child.stdout.readline().strip(), "SHOWN")
        self.assertGreater(time.time() - t, 0.8)    # only once the main window took over

    def test_nobody_running(self):
        self.assertFalse(tray.other_instance())

    @unittest.skipUnless(sys.platform == "win32", "Windows mutex")
    def test_lock_is_atomic_and_released(self):
        self.run_child(late=5)   # holds the lock (acquire) and listens
        self.assertFalse(tray.acquire())
        self.assertTrue(tray.show_other(2))


class Restart(unittest.TestCase):
    def test_restart_and_relaunch_hand_over(self):
        """Before starting the next instance the server is released and the new one waits (--after=<pid>)."""
        src = (pathlib.Path(ROOT) / "app.py").read_text("utf-8")
        self.assertIn('args.append(f"--after={os.getpid()}")', src)
        self.assertNotIn("tray.server.close()", src)
        setup = (pathlib.Path(ROOT) / "ui" / "setupui.py").read_text("utf-8")
        self.assertEqual(setup.count('[f"--after={os.getpid()}"]'), 2)
        start = (pathlib.Path(ROOT) / "system" / "startup.py").read_text("utf-8")
        self.assertLess(start.index("tray.acquire()"), start.index("if datahome.FIRST_RUN:"))


if __name__ == "__main__":
    unittest.main()
