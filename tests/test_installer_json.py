"""Setup 0.9.9, app side (lead 13.11./14.11.2026, PLAN labs/_library/setup099): the Inno installer leaves
%APPDATA%\\BentCorner\\installer.json ({"v": 1, "lang", "home"}) on a NEW installation. The first start takes the
language and the folder and opens at the games („Step 1 of 3“); a folder that can't be used or a collection found on
this PC → the storage step as before; the file goes once the setup is done; an existing user deletes it unread;
a portable copy never reads it. Temp folders only – never the real %APPDATA%.

    python -m unittest tests.test_installer_json
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from system import datahome, i18n


def _collection(folder):
    (folder / "data" / "my-data").mkdir(parents=True, exist_ok=True)
    (folder / "data" / "my-data" / "collection.json").write_text(json.dumps({"items": [{"count": 2}]}), "utf-8")
    (folder / "settings.json").write_text("{}", "utf-8")


class Base(unittest.TestCase):
    """An installed copy (FROZEN, PORTABLE None) whose installer.json lies in a temp folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.file = self.root / "roaming" / "BentCorner" / "installer.json"
        self.file.parent.mkdir(parents=True)
        self.lang = i18n.LANG
        self.p = [mock.patch.object(datahome, "INSTALLER", self.file),
                  mock.patch.object(datahome, "FROZEN", True), mock.patch.object(datahome, "TEST", False),
                  mock.patch.object(datahome, "PORTABLE", None), mock.patch.object(datahome, "INSTALLED", True),
                  mock.patch.object(datahome, "APP_DIR", self.root / "prog"),
                  mock.patch.object(datahome, "_local_home", lambda: self.root / "local")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        i18n.set_language(self.lang)
        self.tmp.cleanup()

    def write(self, lang="de", home=None, enc="utf-8", **more):
        d = {"v": 1, "lang": lang, "home": str(home if home is not None else self.root / "Local" / "BentCorner"), **more}
        self.file.write_bytes(json.dumps(d, ensure_ascii=False).encode(enc))

    def backend(self, found=()):
        from ui import setupui
        with mock.patch.object(datahome, "existing", lambda: list(found)):
            return setupui.FirstRunBackend()


class Reading(Base):
    def test_utf8_bom_and_ansi(self):
        home = self.root / "Jürgen" / "BentCorner"
        for enc in ("utf-8", "utf-8-sig", "cp1252"):
            with self.subTest(enc=enc):
                self.write(home=home, enc=enc)
                self.assertEqual(datahome.read_installer(), {"lang": "de", "home": home})

    def test_only_language_and_path(self):
        self.write(lang="en", extra="ignored", t=123)
        self.assertEqual(set(datahome.read_installer()), {"lang", "home"})

    def test_bad_values(self):
        self.write(lang="xx", home="relative\\folder")
        self.assertEqual(datahome.read_installer(), {"lang": None, "home": None})
        self.file.write_bytes(b"\xff\xfe not json")
        self.assertIsNone(datahome.read_installer())
        self.file.write_text("[1, 2]", "utf-8")
        self.assertIsNone(datahome.read_installer())
        self.file.unlink()
        self.assertIsNone(datahome.read_installer())

    def test_whose_business(self):
        self.assertTrue(datahome.installer_ours())
        with mock.patch.object(datahome, "PORTABLE", self.root / "stick"):
            self.assertFalse(datahome.installer_ours())         # portable: never
        with mock.patch.object(datahome, "FROZEN", False):
            self.assertFalse(datahome.installer_ours())         # a source start: never the real file


class FirstStart(Base):
    def test_taken_opens_at_the_games(self):
        home = self.root / "Local" / "BentCorner"
        self.write(lang="de", home=home)
        b = self.backend()
        self.assertEqual((b.page, b.stepNo, b.steps, b.canBack), (2, 1, 3, False))
        self.assertEqual((b.lang, i18n.LANG), ("de", "de"))
        self.assertTrue(home.is_dir())                              # checked by writing (the test file is gone again)
        self.assertEqual(list(home.iterdir()), [])
        self.assertTrue(self.file.exists())                         # only read – deleted once the setup is done
        b.back()
        self.assertEqual(b.page, 2)                                 # nothing before the games
        b.toggleGame("pokemon")
        b.go()
        self.assertTrue(b.accepted)
        self.assertEqual((b.result_home, b.result_lang, b.result_games, b.result_steps), (home, "de", ["pokemon"], 3))

    def test_english(self):
        self.write(lang="en")
        b = self.backend()
        self.assertEqual((b.page, b.lang, i18n.LANG), (2, "en", "en"))

    def test_folder_not_usable_storage_step(self):
        blocker = self.root / "a-file"
        blocker.write_text("x", "utf-8")
        for home in (blocker / "BentCorner", self.root / "prog" / "data"):   # can't be created / in the program folder
            with self.subTest(home=home):
                self.write(lang="de", home=home)
                b = self.backend()
                self.assertEqual((b.page, b.stepNo, b.steps, b.canBack), (1, 1, 4, False))
                self.assertEqual((b.lang, b.choice), ("de", "docs"))   # the preset, as without the file
                b.next()
                self.assertEqual((b.page, b.stepNo), (2, 2))
                b.back()
                self.assertEqual(b.page, 1)

    def test_collection_found_storage_step(self):
        old = self.root / "alt"
        _collection(old)
        home = self.root / "Local" / "BentCorner"
        self.write(lang="de", home=home)
        b = self.backend([{"path": old, "cards": 2, "changed": 0, "reachable": True}])
        self.assertEqual((b.page, b.steps, b.customise, b.choice), (1, 4, True, ""))   # nothing preselected
        self.assertEqual(b.other, str(home))                        # the installer's folder under „another folder“

    def test_no_language_asks_it(self):
        self.write(lang=None)
        b = self.backend()
        self.assertEqual((b.page, b.steps), (0, 4))
        b.next()
        self.assertEqual(b.page, 2)                                 # the storage step stays skipped

    def test_without_file_as_before(self):
        b = self.backend()
        self.assertEqual((b.page, b.steps, b.choice), (0, 5, "docs"))

    def test_portable_never_reads_it(self):
        self.write(lang="en")
        with mock.patch.object(datahome, "PORTABLE", self.root / "stick"):
            b = self.backend()
        self.assertEqual((b.page, b.steps), (0, 4))
        self.assertTrue(self.file.exists())


class Startup(Base):
    """startup.py: after the setup the file goes; closed without finishing it stays; an existing user drops it."""

    def test_drop(self):
        self.write()
        datahome.drop_installer()
        self.assertFalse(self.file.exists())
        datahome.drop_installer()                                   # nothing there: no error

    def test_startup_wiring(self):
        src = pathlib.Path(datahome.__file__).with_name("startup.py").read_text("utf-8")
        first = src.index("if datahome.FIRST_RUN:")
        accepted = src.index("if not dlg.accepted:", first)
        drop1 = src.index("datahome.drop_installer()", first)
        relaunch = src.index("setupui.relaunch()", first)
        self.assertLess(accepted, drop1)                            # aborted: stays for the next first start
        self.assertLess(drop1, relaunch)
        drop2 = src.index("datahome.drop_installer()", relaunch)    # existing user (no first start): removed unread
        self.assertLess(drop2, src.index("setup_logging()", relaunch))

    def test_existing_user_has_no_first_start(self):
        home = self.root / "Documents" / "BentCorner"
        _collection(home)
        pointer = self.root / "roaming" / "BentCorner" / "datenordner.json"
        pointer.write_text(json.dumps({"home": str(home)}), "utf-8")
        self.write(lang="en")
        with mock.patch.object(datahome, "INSTALLED", True), mock.patch.object(datahome, "POINTER", pointer), \
                mock.patch.object(datahome, "_selftest_home", lambda: None):
            self.assertEqual(datahome._resolve(), (home, False))   # the setup never opens → only dropped


if __name__ == "__main__":
    unittest.main()
