"""„Bent°Corner löschen“ on this PC (system/wipe.py) – only ever in temporary folders: exactly our files go, other
files in the data folder stay, backups outside stay; legal 03.11.2026: whether the latest backup goes along is known
before (the text says "will be kept" only when it really stays).

    python -m unittest tests/test_wipe.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from system import autobackup, datastore, wipe


class Wipe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = pathlib.Path(self.tmp.name)
        self.base, self.roaming, self.local, self.target = t / "Docs" / "BentCorner", t / "Roaming", t / "Local", t / "Stick"
        (self.base / "data" / "my-data").mkdir(parents=True)
        (self.base / "data" / "my-data" / "collection.json").write_text("{}", "utf-8")
        (self.base / "settings.json").write_text("{}", "utf-8")
        for d in (self.roaming, self.local):
            d.mkdir(parents=True)
            (d / "note.txt").write_text("x", "utf-8")
        for p in (mock.patch.object(wipe, "BASE", self.base),
                  mock.patch.object(datastore, "BACKUPS", self.base / "data" / "backups"),
                  mock.patch.object(wipe.datahome, "_config_dir", lambda: self.roaming),
                  mock.patch.object(wipe, "_local_home", lambda: self.local)):
            p.start()
            self.addCleanup(p.stop)
        self.settings = {}

    def backup(self, folder, name, age=0):
        folder.mkdir(parents=True, exist_ok=True)
        f = folder / name
        f.write_bytes(b"zip")
        os.utime(f, (time.time() - age, time.time() - age))
        return f

    def test_plan_names_exactly_our_paths(self):
        p = wipe.plan(self.settings)
        self.assertEqual(sorted(p.delete), sorted(str(x) for x in (self.base / "settings.json", self.base / "data",
                                                                   self.roaming, self.local)))
        self.assertEqual(p.folder, str(self.base))
        self.assertEqual(p.backup, "")

    def test_latest_backup_inside_goes_along(self):
        f = self.backup(self.base / "data" / "backups" / "auto", "BentCorner backup 1.zip")
        p = wipe.plan(self.settings)
        self.assertEqual(p.backup, str(f))
        self.assertTrue(p.backup_goes)

    def test_backup_on_a_target_stays(self):
        self.backup(self.base / "data" / "backups" / "auto", "BentCorner backup 1.zip", age=3600)
        autobackup.add_target(self.settings, self.target)
        f = self.backup(self.target / autobackup.FOLDER, "BentCorner backup 2.zip")
        p = wipe.plan(self.settings)
        self.assertEqual(p.backup, str(f))
        self.assertFalse(p.backup_goes)
        self.assertEqual(wipe.wipe(p), [])
        self.assertTrue(f.exists())

    def test_backup_made_by_hand_counts_while_it_exists(self):
        self.backup(self.base / "data" / "backups" / "auto", "BentCorner backup 1.zip", age=3600)
        hand = pathlib.Path(self.tmp.name) / "Somewhere" / "BentCorner backup 2026-11-03 09-00"
        hand.mkdir(parents=True)
        wipe.remember_backup(self.settings, hand)
        p = wipe.plan(self.settings)
        self.assertEqual(p.backup, str(hand))
        self.assertFalse(p.backup_goes)                 # outside the data folder: it stays
        hand.rmdir()                                    # gone (moved, deleted): no longer counted
        self.assertNotEqual(wipe.plan(self.settings).backup, str(hand))

    def test_backup_made_by_hand_inside_the_data_folder_goes(self):
        hand = self.base / "data" / "BentCorner backup 2026-11-03 09-00"
        hand.mkdir(parents=True)
        wipe.remember_backup(self.settings, hand)
        self.assertTrue(wipe.plan(self.settings).backup_goes)

    def test_wipe_keeps_other_files_and_the_folder_with_them(self):
        (self.base / "my notes.txt").write_text("mine", "utf-8")
        self.assertEqual(wipe.wipe(wipe.plan(self.settings)), [])
        self.assertEqual(sorted(x.name for x in self.base.iterdir()), ["my notes.txt"])
        self.assertFalse(self.roaming.exists() or self.local.exists())

    def test_empty_data_folder_goes(self):
        self.assertEqual(wipe.wipe(wipe.plan(self.settings)), [])
        self.assertFalse(self.base.exists())

    def test_waits_for_the_program_to_end(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
        self.assertTrue(wipe._wait_for(child.pid, 10))
        child.wait()
        self.assertFalse(wipe._wait_for(os.getpid(), 0.3))   # still running: not ended (and nothing sent to it)


if __name__ == "__main__":
    unittest.main()
