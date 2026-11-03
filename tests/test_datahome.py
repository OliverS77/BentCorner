"""Where the data lives (system/datahome.py): development (BC_HOME), portable next to the .exe, the folder chosen at
first start (pointer file), first start, and the test start "like the first time". Everything in temp folders – the
real pointer file and the user's data are never touched (the module's paths are redirected).

    python -m unittest tests/test_datahome.py
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from system import datahome


class Resolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.app, self.chosen, self.default = t / "app", t / "chosen", t / "Documents" / "BentCorner"
        self.app.mkdir()
        self.pointer = t / "config" / "datenordner.json"
        self.patches = [mock.patch.object(datahome, "APP_DIR", self.app),
                        mock.patch.object(datahome, "POINTER", self.pointer),
                        mock.patch.object(datahome, "DEFAULT", self.default),
                        mock.patch.object(datahome, "TEST_ROOT", t / "first-run-test"),
                        mock.patch.object(datahome, "TEST", False),
                        mock.patch.dict(os.environ, {}, clear=False)]
        for p in self.patches:
            p.start()
        os.environ.pop("BC_HOME", None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def frozen(self, on=True):
        return mock.patch.object(datahome, "FROZEN", on)

    def test_development_next_to_the_scripts_or_bc_home(self):
        with self.frozen(False):
            self.assertEqual(datahome._resolve(), (self.app, False))
            os.environ["BC_HOME"] = str(self.chosen)
            self.assertEqual(datahome._resolve(), (self.chosen, False))   # e.g. a test copy for measuring

    def test_bc_home_has_no_effect_in_the_exe(self):
        os.environ["BC_HOME"] = str(self.chosen)
        with self.frozen():
            self.assertEqual(datahome._resolve(), (self.default, True))

    def test_portable_when_data_sits_next_to_the_exe(self):
        (self.app / "settings.json").write_text("{}", "utf-8")
        with self.frozen():
            self.assertEqual(datahome._resolve(), (self.app, False))
        (self.app / "settings.json").unlink()
        (self.app / "data").mkdir()
        with self.frozen():
            self.assertEqual(datahome._resolve(), (self.app, False))

    def test_chosen_folder_is_remembered(self):
        self.chosen.mkdir()
        datahome.set_home(self.chosen)
        self.assertEqual(json.loads(self.pointer.read_text("utf-8"))["home"], str(self.chosen.resolve()))
        with self.frozen():
            self.assertEqual(datahome._resolve(), (self.chosen.resolve(), False))

    def test_first_start_without_or_with_a_broken_pointer(self):
        with self.frozen():
            self.assertEqual(datahome._resolve(), (self.default, True))
            datahome.set_home(self.chosen)               # folder doesn't exist (any more)
            self.assertEqual(datahome._resolve(), (self.default, True))
            self.pointer.write_text("{broken", "utf-8")
            self.assertEqual(datahome._resolve(), (self.default, True))

    def test_has_data(self):
        self.assertFalse(datahome.has_data(self.app))
        (self.app / "data").mkdir()
        self.assertTrue(datahome.has_data(self.app))

    def test_first_run_test_starts_from_scratch_and_can_continue(self):
        root = datahome.TEST_ROOT
        old = root / "old-run"
        old.mkdir(parents=True)
        datahome.set_home(old)
        with mock.patch.object(datahome, "TEST", True), mock.patch.object(sys, "argv", ["app.py", "--first-run-test"]):
            self.assertEqual(datahome._resolve(), (self.default, True))   # new test start: everything from last time
            self.assertFalse(root.exists())                               # is gone
            self.assertFalse(self.pointer.exists())
        old.mkdir(parents=True)
        datahome.set_home(old)
        with mock.patch.object(datahome, "TEST", True), \
                mock.patch.object(sys, "argv", ["app.py", "--first-run-test", "--continue-test"]):
            self.assertEqual(datahome._resolve(), (old.resolve(), False))   # restart in the middle of setup

    def test_restart_stays_in_the_test(self):
        with mock.patch.object(datahome, "TEST", True):
            self.assertEqual(datahome.restart_args(), ["--first-run-test", "--continue-test"])
        self.assertEqual(datahome.restart_args(), [])
        with self.frozen(False):
            self.assertEqual(datahome.program(), sys.executable)


class IsolatedRun(unittest.TestCase):
    """Test run of the exe with BC_STARTER_* (same switches as launcher/Launcher.cs): config and "Documents" come from
    the given folders, the registry autostart is off; without the variables nothing changes."""
    VARS = ("BC_STARTER_LOCAL", "BC_STARTER_ROAMING", "BC_STARTER_DOCUMENTS")

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for v in self.VARS:
            os.environ.pop(v, None)

    def tearDown(self):
        self.env.stop()

    def test_switches_redirect_config_and_documents(self):
        with tempfile.TemporaryDirectory() as t:
            os.environ["BC_STARTER_ROAMING"] = str(pathlib.Path(t) / "roaming")
            os.environ["BC_STARTER_DOCUMENTS"] = " " + str(pathlib.Path(t) / "docs") + " "
            self.assertEqual(datahome._config_dir(), pathlib.Path(t) / "roaming" / "BentCorner")
            self.assertEqual(datahome.documents(), pathlib.Path(t) / "docs")

    def test_without_switches_nothing_changes(self):
        os.environ["BC_STARTER_ROAMING"] = "  "   # empty counts as unset
        if sys.platform == "win32":
            self.assertEqual(datahome._config_dir(),
                             pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home() / "AppData" / "Roaming") / "BentCorner")
        self.assertNotEqual(datahome.documents(), pathlib.Path("  "))

    def test_no_registry_autostart_when_isolated(self):
        from ui import tray
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "win32"):
            with mock.patch.object(datahome, "TEST", False), mock.patch.object(datahome, "ISOLATED", True):
                self.assertFalse(tray.autostart_possible())   # set_autostart() then returns before touching winreg


if __name__ == "__main__":
    unittest.main()
