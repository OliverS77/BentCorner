""""Delete my collection and settings on this PC" in the portable setup (lead 03.11.2026): the data folder IS the program
folder (datahome: APP_DIR when the data lies next to the exe – Oliver's app\\). system/wipe.py must then delete exactly
settings.json, data\\ and the two AppData folders – never the program (BentCorner.exe, "Bent°Corner Essentials") and
never anything else in that folder; the folder itself stays because it isn't empty. Only temp folders here.

    python -m unittest tests/test_wipe_portable.py
"""
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from system import datahome, wipe


class PortableWipe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.app = root / "app"                       # program AND data folder (portable)
        (self.app / "data" / "my-data").mkdir(parents=True)
        (self.app / "data" / "my-data" / "collection.json").write_text("{}", "utf-8")
        (self.app / "data" / "backups").mkdir()
        (self.app / "settings.json").write_text("{}", "utf-8")
        (self.app / "BentCorner.exe").write_bytes(b"MZ")
        ess = self.app / "Bent°Corner Essentials" / "0.9.7.35-x"
        ess.mkdir(parents=True)
        (ess / "BentCorner.exe").write_bytes(b"MZ")
        (self.app / "Meine Notizen.txt").write_text("fremd", "utf-8")
        self.roam = root / "roaming" / "BentCorner"
        self.roam.mkdir(parents=True)
        (self.roam / "home.json").write_text("{}", "utf-8")
        self.local = root / "local"
        self.local.mkdir()
        (self.local / "starter.log").write_text("x", "utf-8")
        for p in (mock.patch.object(wipe, "BASE", self.app),
                  mock.patch.object(datahome, "_config_dir", lambda: self.roam),
                  mock.patch.dict(os.environ, {"BC_STARTER_LOCAL": str(self.local)})):
            p.start()
            self.addCleanup(p.stop)

    def test_plan_names_only_ours(self):
        p = wipe.plan({})
        self.assertEqual(sorted(pathlib.Path(x).resolve() for x in p.delete),
                         sorted(x.resolve() for x in (self.app / "settings.json", self.app / "data", self.roam,
                                                      self.local / "starter.log")))
        self.assertEqual(p.tidy, [str(self.local)], "the redirected local folder only goes when empty afterwards")
        self.assertNotIn(str(self.app), p.delete, "never the program/data folder itself")

    def test_the_program_and_foreign_files_stay(self):
        errors = wipe.wipe(wipe.plan({}))
        self.assertEqual(errors, [])
        self.assertFalse((self.app / "settings.json").exists())
        self.assertFalse((self.app / "data").exists())
        self.assertFalse(self.roam.exists())
        self.assertFalse(self.local.exists())
        self.assertTrue((self.app / "BentCorner.exe").exists(), "the program stays")
        self.assertTrue((self.app / "Bent°Corner Essentials" / "0.9.7.35-x" / "BentCorner.exe").exists())
        self.assertTrue((self.app / "Meine Notizen.txt").exists(), "nothing foreign goes")
        self.assertTrue(self.app.is_dir(), "the folder stays – it isn't empty")

    def test_a_backup_in_the_data_folder_is_said_to_go(self):
        b = self.app / "data" / "backups" / "BentCorner backup 2026-11-03.zip"
        b.write_bytes(b"PK")
        with mock.patch.object(wipe, "latest_backup", lambda s: (str(b), b.stat().st_mtime)):
            self.assertTrue(wipe.plan({}).backup_goes)

    def test_env_pointing_at_a_foreign_folder_deletes_nothing_foreign(self):
        """lead 06.11.: BC_STARTER_LOCAL set from outside (e.g. at "Documents") – only our own entries go."""
        docs = pathlib.Path(self.tmp.name) / "Dokumente"
        (docs / "Fotos").mkdir(parents=True)
        (docs / "Fotos" / "urlaub.jpg").write_bytes(b"jpg")
        (docs / "Brief.docx").write_bytes(b"doc")
        (docs / "starter.log").write_text("x", "utf-8")
        (docs / "essentials-0123456789abcdef.txt").write_text("x", "utf-8")
        (docs / "essentials-kaputt.txt").write_text("x", "utf-8")   # not a starter note name: stays
        with mock.patch.dict(os.environ, {"BC_STARTER_LOCAL": str(docs)}):
            p = wipe.plan({})
            self.assertNotIn(str(docs), p.delete)
            self.assertEqual(wipe.wipe(p), [])
        self.assertTrue((docs / "Fotos" / "urlaub.jpg").exists())
        self.assertTrue((docs / "Brief.docx").exists())
        self.assertTrue((docs / "essentials-kaputt.txt").exists())
        self.assertFalse((docs / "starter.log").exists())
        self.assertFalse((docs / "essentials-0123456789abcdef.txt").exists())
        self.assertTrue(docs.is_dir(), "the folder stays – it isn't empty")

    def test_a_planted_plan_file_deletes_only_what_the_program_plans_itself(self):
        foreign = pathlib.Path(self.tmp.name) / "Fremd"
        foreign.mkdir()
        (foreign / "wichtig.txt").write_text("x", "utf-8")
        planned = wipe.plan({})
        evil = wipe.Plan(folder=str(foreign), delete=[str(foreign), *planned.delete], tidy=[str(foreign)])
        f = pathlib.Path(self.tmp.name) / "plan.json"
        f.write_text(evil.to_json(), "utf-8")
        with mock.patch.object(wipe.sys, "argv", ["BentCorner.exe", "--wipe-local", str(f), "0"]), \
                mock.patch.object(wipe, "_wait_for", lambda pid: True), \
                mock.patch.object(wipe.tempfile, "gettempdir", lambda: self.tmp.name):
            with self.assertRaises(SystemExit) as ended:
                wipe.main()
        self.assertEqual(ended.exception.code, 0)
        self.assertTrue((foreign / "wichtig.txt").exists(), "a path the program didn't plan stays")
        self.assertFalse((self.app / "settings.json").exists(), "what the program plans itself still goes")


if __name__ == "__main__":
    unittest.main()
