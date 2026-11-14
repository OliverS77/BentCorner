"""The data folder after the installer (lead 06.11.2026): an installed program never keeps data in its own folder (the
uninstaller deletes it), the first start finds collections already on this PC instead of silently starting empty,
and the uninstaller leaves a folder alone that holds a collection.

    python -m unittest tests/test_datafolder_safe.py
"""
import json
import os
import pathlib
import re
import tempfile
import time
import unittest
from unittest import mock

from system import datahome

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _collection(folder, counts, game=None):
    mine = folder / "data" / ("games/" + game if game else "") / "my-data"
    mine.mkdir(parents=True, exist_ok=True)
    (mine / "collection.json").write_text(json.dumps({"version": 1, "items": [{"count": c} for c in counts]}), "utf-8")
    (folder / "settings.json").write_text("{}", "utf-8")


class Installed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = pathlib.Path(self.tmp.name) / "Programs" / "Bent°Corner"
        self.app.mkdir(parents=True)
        self.patches = [mock.patch.object(datahome, "INSTALLED", True), mock.patch.object(datahome, "APP_DIR", self.app),
                        mock.patch.object(datahome, "FROZEN", True), mock.patch.object(datahome, "TEST", False),
                        mock.patch.object(datahome, "POINTER", pathlib.Path(self.tmp.name) / "roaming" / "datenordner.json")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_program_folder_is_never_a_data_folder(self):
        self.assertTrue(datahome.in_program(self.app))
        self.assertTrue(datahome.in_program(self.app / "data"))
        self.assertFalse(datahome.in_program(pathlib.Path(self.tmp.name) / "Documents" / "BentCorner"))
        with self.assertRaises(ValueError):
            datahome.set_home(self.app)
        self.assertFalse(datahome.POINTER.exists())

    def test_data_next_to_an_installed_program_is_not_taken(self):
        _collection(self.app, [1])
        home, first = datahome._resolve()
        self.assertNotEqual(home, self.app)
        self.assertTrue(first)

    def test_pointer_into_the_program_folder_is_ignored(self):
        datahome.POINTER.parent.mkdir(parents=True)
        datahome.POINTER.write_text(json.dumps({"home": str(self.app)}), "utf-8")
        self.assertNotEqual(datahome._resolve()[0], self.app)

    def test_portable_copy_unchanged(self):
        with mock.patch.object(datahome, "INSTALLED", False):
            _collection(self.app, [1])
            self.assertEqual(datahome._resolve(), (self.app, False))


class Existing(unittest.TestCase):
    """Where 0.9.6 users' collections lie: remembered folder, Documents, next to the old starter (its notes), Desktop."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.docs, self.local, self.desk, self.down = t / "Documents" / "BentCorner", t / "local", t / "Desktop", t / "Downloads"
        for d in (self.local, self.desk, self.down):
            d.mkdir(parents=True)
        self.pointer = t / "roaming" / "datenordner.json"
        self.patches = [mock.patch.object(datahome, "POINTER", self.pointer), mock.patch.object(datahome, "DEFAULT", self.docs),
                        mock.patch.object(datahome, "_local_home", lambda: self.local),
                        mock.patch.object(datahome, "_known_folder", lambda guid, fb: self.desk if guid == datahome._DESKTOP else self.down),
                        mock.patch.object(datahome, "TEST", False), mock.patch.object(datahome, "ISOLATED", False),
                        mock.patch.object(datahome, "INSTALLED", False)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def paths(self):
        return [e["path"] for e in datahome.existing()]

    def test_nothing_there(self):
        self.assertEqual(datahome.existing(), [])

    def test_a_documents(self):
        _collection(self.docs, [2, 3])
        _collection(self.docs, [5], game="pokemon")
        found = datahome.existing()
        self.assertEqual([e["path"] for e in found], [self.docs])
        self.assertEqual(found[0]["cards"], 10)

    def test_b_own_folder_remembered_but_not_reachable(self):
        gone = pathlib.Path(self.tmp.name) / "X-Drive" / "Sammlung"
        self.pointer.parent.mkdir(parents=True)
        self.pointer.write_text(json.dumps({"home": str(gone)}), "utf-8")
        _collection(self.docs, [1])
        found = datahome.existing()
        self.assertEqual(found[0]["path"], gone)          # the remembered one first …
        self.assertFalse(found[0]["reachable"])          # … even though it can't be reached
        self.assertEqual(found[1]["path"], self.docs)

    def test_c_portable_next_to_the_old_starter(self):
        """0.9.6 portable: data next to the starter exe; the starter noted where its "Essentials" lie (right next to
        the data) and in them installation.txt names the starter's folder."""
        stick = pathlib.Path(self.tmp.name) / "E" / "BentCorner-portabel"
        _collection(stick, [7])
        ess = stick / "Bent°Corner Essentials"
        ess.mkdir()
        (ess / "installation.txt").write_text(str(stick), "utf-8")
        (self.local / "essentials-1a2b3c4d.txt").write_text(str(ess), "utf-8")
        found = datahome.existing()
        self.assertEqual([e["path"] for e in found], [stick])
        self.assertEqual(found[0]["cards"], 7)

    def test_desktop_and_downloads_one_level(self):
        a, b, deep = self.desk / "BentCorner", self.down / "Bent°Corner 0.9.6", self.desk / "x" / "y"
        for f in (a, b, deep):
            _collection(f, [1])
        os.utime(b / "settings.json", (time.time() + 60, time.time() + 60))
        self.assertEqual(self.paths(), [b, a])            # most recently used first, nothing deeper than one level

    def test_test_copies_never_look_at_the_real_desktop(self):
        _collection(self.desk / "BentCorner", [1])
        with mock.patch.object(datahome, "ISOLATED", True):
            self.assertEqual(self.paths(), [])

    def test_installed_program_folder_never_offered(self):
        app = pathlib.Path(self.tmp.name) / "Programs" / "Bent°Corner"
        _collection(app, [1])
        (self.local / "essentials-x.txt").write_text(str(app / "Bent°Corner Essentials"), "utf-8")
        with mock.patch.object(datahome, "INSTALLED", True), mock.patch.object(datahome, "APP_DIR", app):
            self.assertEqual(self.paths(), [])


class Setup(unittest.TestCase):
    """First-run page: nothing preselected when collections were found; choosing one keeps it (no games page)."""

    def setUp(self):   # firstrun.log goes to a test folder, never to the real %LOCALAPPDATA%\BentCorner
        self.tmp = tempfile.TemporaryDirectory()
        self.local = pathlib.Path(self.tmp.name) / "local"
        self.patch = mock.patch.object(datahome, "_local_home", lambda: self.local)
        self.patch.start()
        # an installed copy: a portable one skips the storage step since 0.9.8 (tests/test_setup98.py)
        self.portable = mock.patch.object(datahome, "PORTABLE", None)
        self.portable.start()

    def tearDown(self):
        self.portable.stop()
        self.patch.stop()
        self.tmp.cleanup()

    def backend(self, found):
        from ui import setupui
        with mock.patch.object(datahome, "existing", lambda: found):
            return setupui.FirstRunBackend()

    def log(self):
        return (self.local / "firstrun.log").read_text("utf-8")

    def test_nothing_found_documents_as_before(self):
        b = self.backend([])
        self.assertEqual(b.choice, "docs")

    def test_found_nothing_preselected_and_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = pathlib.Path(tmp) / "alt"
            _collection(old, [4])
            b = self.backend([{"path": old, "cards": 4, "changed": time.time(), "reachable": True}])
            b._page = 1
            self.assertEqual(b.choice, "")
            self.assertFalse(b.canGoOn)
            self.assertEqual(len(b.found), 1)
            b.setChoice("found:0")
            self.assertTrue(b.canGoOn)
            b.next()                                       # straight to the end: an existing collection keeps its games
            self.assertTrue(b.accepted)
            self.assertEqual(b.result_home, old)
            self.assertIn(f"found: {old} (4 cards)", self.log())
            self.assertIn(f"chosen: {old} (existing collection)", self.log())

    def test_unreachable_cannot_be_taken(self):
        b = self.backend([{"path": pathlib.Path("Z:/weg"), "cards": 0, "changed": 0, "reachable": False}])
        b._page = 1
        b.setChoice("found:0")
        b.next()
        self.assertFalse(b.accepted)
        self.assertNotEqual(b.error, "")


class Uninstaller(unittest.TestCase):
    def test_never_deletes_a_folder_with_a_collection(self):
        iss = (ROOT / "installer" / "bentcorner.iss").read_text("utf-8")
        self.assertIsNone(re.search(r"(?m)^\[UninstallDelete\][^\[]*\{app\}", iss))
        step = re.search(r"procedure CurUninstallStepChanged.*?end;\s*$", iss, re.S | re.M).group(0)
        self.assertIn("settings.json", step)
        self.assertIn("\\data", step)
        self.assertLess(step.index("settings.json"), step.index("DelTree"))


if __name__ == "__main__":
    unittest.main()
