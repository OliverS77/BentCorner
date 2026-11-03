"""Automatic backup (system/autobackup.py) with the ZIP and restore of system/datastore.py: targets, when a backup is
due, what goes into the ZIP (all games, settings, collectibles – no trash, no half-written files), rotation of old
backups, restore round trip, corrupt or foreign ZIPs are refused. Everything lives in a temp folder: every path
constant of datastore/autobackup (and scanner.common.DATA, tempfile.gettempdir) is redirected there.

    python -m unittest tests/test_autobackup.py
"""
import datetime
import json
import os
import pathlib
import tempfile
import time
import unittest
import zipfile
from unittest import mock

from scanner import common
from system import autobackup, datastore, undo


def _files(root):
    """{relative posix path: bytes} of every file under root."""
    root = pathlib.Path(root)
    return {f.relative_to(root).as_posix(): f.read_bytes() for f in root.rglob("*") if f.is_file()}


class _Home(unittest.TestCase):
    """A throwaway data folder: <tmp>/home/{settings.json, data/…}, a backup target and a private temp dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.home = self.root / "home"
        self.data = self.home / "data"
        self.mine = self.data / "my-data"
        self.settings_file = self.home / "settings.json"
        self.stick = self.root / "stick"
        self.stick.mkdir()
        self.tmpdir = self.root / "systemp"
        self.tmpdir.mkdir()
        backups = self.data / "backups"
        self.p = [mock.patch.object(datastore, "DATA", self.data),
                  mock.patch.object(datastore, "MINE", self.mine),
                  mock.patch.object(datastore, "SETTINGS", self.settings_file),
                  mock.patch.object(datastore, "BACKUPS", backups),
                  mock.patch.object(datastore, "AUTO", backups / "auto"),
                  mock.patch.object(datastore, "TRASH", self.mine / "trash"),
                  mock.patch.object(common, "DATA", self.data),
                  mock.patch.object(undo, "LAST_WRITE", [0.0]),
                  mock.patch.object(tempfile, "gettempdir", lambda: str(self.tmpdir))]
        for p in self.p:
            p.start()
        self.s = {}

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        self._tmp.cleanup()

    def write(self, rel, text):
        f = self.home / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, "utf-8")
        return f

    def fill(self):
        """Personal data of two games plus things that must NOT go into a backup."""
        self.write("settings.json", json.dumps({"game": "mtg", "lang": "en"}))
        self.write("data/my-data/collection.json", json.dumps({"items": [{"uid": "a", "count": 3}]}))
        self.write("data/my-data/sessions/s1.json", json.dumps({"id": "s1"}))
        self.write("data/my-data/trash/1-deck.json", "{}")                  # trash: not backed up
        self.write("data/my-data/decks.tmp", "half written")                  # unfinished write
        self.write("data/my-data/lists.json.partial", "aborted")
        self.write("data/games/pokemon/my-data/collection.json", json.dumps({"items": []}))
        self.write("data/games/yugioh/readme.txt", "no my-data here")         # not a personal root
        self.write("data/collectibles/tickets/mtg/x/x.json", "{}")
        self.write("data/card-data/cards.sqlite", "re-downloadable")          # card data: not personal


class Targets(_Home):
    def test_defaults_and_add_remove(self):
        c = autobackup.cfg(self.s)
        self.assertEqual((c["on"], c["every"], c["targets"]), (True, "change", []))   # new setups: after each change
        old = {"autobackup": {"every": "daily"}}
        self.assertEqual(autobackup.cfg(old)["every"], "daily")                       # existing ones keep theirs
        self.assertTrue(autobackup.add_target(self.s, self.stick))
        self.assertFalse(autobackup.add_target(self.s, str(self.stick).upper()))   # same folder, other case
        self.assertTrue(autobackup.add_target(self.s, self.root / "b"))
        self.assertTrue(autobackup.add_target(self.s, self.root / "c"))
        self.assertFalse(autobackup.add_target(self.s, self.root / "d"))           # at most three
        autobackup.remove_target(self.s, os.path.normpath(str(self.root / "b")))
        self.assertEqual(len(autobackup.cfg(self.s)["targets"]), 2)

    def test_kind(self):
        self.assertEqual(autobackup.kind(r"C:\Users\x\OneDrive\Backup"), "cloud")
        self.assertEqual(autobackup.kind(self.stick), "same")   # temp folder sits on the data folder's drive
        drive = os.path.splitdrive(str(self.data))[0].upper()
        other = "Y:\\" if drive == "Z:" else "Z:\\"
        self.assertEqual(autobackup.kind(other + "BentCorner"), "other")

    def test_available_creates_subfolder_only_if_target_exists(self):
        self.assertFalse(autobackup.available(self.root / "not-plugged-in"))
        self.assertFalse((self.root / "not-plugged-in").exists())
        self.assertTrue(autobackup.available(self.stick))
        self.assertTrue((self.stick / autobackup.FOLDER).is_dir())

    def test_due(self):
        autobackup.cfg(self.s)["every"] = "daily"
        self.assertFalse(autobackup.due(self.s, 0))                     # no target
        autobackup.add_target(self.s, self.root / "missing")
        self.assertFalse(autobackup.due(self.s, 0))                     # stick not plugged in: not due
        autobackup.add_target(self.s, self.stick)
        self.assertTrue(autobackup.due(self.s, 0))                      # never backed up there
        t = autobackup.cfg(self.s)["targets"][1]
        now = time.time()
        t["ok"] = now - 60
        self.assertFalse(autobackup.due(self.s, now))                   # interval not over yet
        t["ok"] = now - autobackup.EVERY["daily"] - 1
        self.assertTrue(autobackup.due(self.s, now))                    # over, and changed since
        self.assertFalse(autobackup.due(self.s, t["ok"] - 10))          # over, but nothing changed since
        self.assertTrue(autobackup.due(self.s, 0))                      # change time unknown: back up
        autobackup.cfg(self.s)["on"] = False
        self.assertFalse(autobackup.due(self.s, 0))

    def test_due_after_each_change_waits_for_quiet(self):
        autobackup.add_target(self.s, self.stick)
        t = autobackup.cfg(self.s)["targets"][0]
        now = time.time()
        t["ok"] = now - 3600
        self.assertFalse(autobackup.due(self.s, now - 30))                 # changed 30 s ago: still busy
        self.assertTrue(autobackup.due(self.s, now - autobackup.QUIET - 1))  # quiet for 2 minutes: now
        self.assertFalse(autobackup.due(self.s, now - 7200))               # last change before the last backup


class RunAndZip(_Home):
    def test_zip_contains_everything_personal_and_nothing_else(self):
        self.fill()
        autobackup.add_target(self.s, self.stick)
        out = autobackup.run(self.s)
        self.assertEqual(len(out), 1)
        path, ok, name = out[0]
        self.assertTrue(ok, out)
        z = self.stick / autobackup.FOLDER / name
        with zipfile.ZipFile(z) as zf:
            names = set(zf.namelist())
            self.assertEqual(json.loads(zf.read("settings.json"))["lang"], "en")
        self.assertEqual(names, {"settings.json", "README.txt", "manifest.json", "my-data/collection.json",
                                 "my-data/sessions/s1.json", "games/pokemon/my-data/collection.json",
                                 "collectibles/tickets/mtg/x/x.json"})
        with zipfile.ZipFile(z) as zf:
            man = json.loads(zf.read("manifest.json"))
        self.assertEqual(man["sum"], autobackup.content_sum())
        self.assertEqual((man["v"], man["address"]), (1, None))   # no identity yet: none is created for it
        self.assertNotIn("relay", self.s)
        t = autobackup.cfg(self.s)["targets"][0]
        self.assertGreater(t["ok"], 0)
        self.assertEqual(t["error"], "")
        self.assertEqual(list(self.tmpdir.iterdir()), [])                         # packed copy cleaned up
        self.assertEqual([f.name for f in (self.stick / autobackup.FOLDER).iterdir()], [name])   # no .partial left

    def test_nothing_written_outside_target_and_temp(self):
        self.fill()
        before = _files(self.home)
        autobackup.add_target(self.s, self.stick)
        autobackup.run(self.s)
        self.assertEqual(_files(self.home), before)            # the data folder is only read
        top = {p.name for p in self.root.iterdir()}
        self.assertEqual(top, {"home", "stick", "systemp"})

    def test_unreachable_target_skipped_others_written(self):
        self.fill()
        autobackup.add_target(self.s, self.root / "missing")
        autobackup.add_target(self.s, self.stick)
        out = autobackup.run(self.s)
        self.assertEqual([ok for _, ok, _ in out], [False, True])
        missing, stick = autobackup.cfg(self.s)["targets"]
        self.assertEqual((missing["ok"], missing["error"]), (0, "nicht erreichbar"))
        self.assertGreater(missing["tried"], 0)
        self.assertGreater(stick["ok"], 0)
        self.assertFalse((self.root / "missing").exists())     # never created

    def test_same_content_is_not_backed_up_again(self):
        self.fill()
        autobackup.add_target(self.s, self.stick)
        self.assertTrue(autobackup.run(self.s, force=True)[0][1])
        self.assertEqual(autobackup.run(self.s, force=True), [])            # nothing changed: nothing written
        self.write("settings.json", json.dumps({"game": "mtg", "lang": "de"}))
        self.assertEqual(autobackup.run(self.s, force=True), [])            # settings alone don't count
        self.assertEqual(len(autobackup.run(self.s, force=True, only_changed=False)), 1)   # "Back up now"
        self.write("data/my-data/collection.json", json.dumps({"items": [{"uid": "a", "count": 4}]}))
        self.assertTrue(autobackup.run(self.s, force=True)[0][1])          # real change: backed up

    def test_not_due_is_skipped_unless_forced(self):
        self.fill()
        autobackup.add_target(self.s, self.stick)
        autobackup.cfg(self.s)["targets"][0]["ok"] = time.time() - 60
        self.assertEqual(autobackup.run(self.s), [])
        self.assertEqual(len(autobackup.run(self.s, force=True)), 1)

    def test_prune_keeps_last_five_one_per_hour(self):
        folder = self.stick / autobackup.FOLDER
        folder.mkdir()
        now = time.time()
        files = []
        for d in range(40):                                    # one backup per day for 40 days
            f = folder / f"BentCorner backup {d:02d}.zip"
            f.write_bytes(b"x")
            ts = now - d * 86400
            os.utime(f, (ts, ts))
            files.append(f)
        old_part = folder / "x.zip.partial"
        old_part.write_bytes(b"x")
        os.utime(old_part, (now - 7200, now - 7200))
        fresh_part = folder / "y.zip.partial"                  # maybe still being written by another run
        fresh_part.write_bytes(b"x")
        other = folder / "notes.txt"
        other.write_text("mine")
        autobackup._prune(folder)
        self.assertEqual(set(folder.glob("BentCorner backup *.zip")), set(files[:5]))
        self.assertFalse(old_part.exists())
        self.assertTrue(fresh_part.exists())
        self.assertTrue(other.exists())                        # foreign files are never touched

    def test_prune_one_per_hour_newest_wins(self):
        folder = self.stick / autobackup.FOLDER
        folder.mkdir()
        hour = (int(time.time()) // 3600) * 3600               # a whole hour: the slots are exact
        files = []
        for m in range(0, 10 * 60, 20):                        # every 20 minutes for 10 hours
            f = folder / f"BentCorner backup {m:05d}.zip"
            f.write_bytes(b"x")
            ts = hour + 3599 - m * 60
            os.utime(f, (ts, ts))
            files.append(f)
        autobackup._prune(folder)
        left = sorted(folder.glob("BentCorner backup *.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
        self.assertEqual(len(left), autobackup.KEEP)
        self.assertEqual(left[0], files[0])                    # the newest always stays
        slots = {int(f.stat().st_mtime) // 3600 for f in left}
        self.assertEqual(len(slots), autobackup.KEEP)          # five different hours, one each


class Restore(_Home):
    def backup(self):
        autobackup.add_target(self.s, self.stick)
        (path, ok, name), = autobackup.run(self.s)
        self.assertTrue(ok)
        return self.stick / autobackup.FOLDER / name

    def test_round_trip(self):
        self.fill()
        z = self.backup()
        info = datastore.backup_info(str(z))
        self.assertEqual((info["cards"], info["sessions"]), (3, 1))
        self.assertEqual([g.name for g in info["games"]], ["pokemon"])
        original = {k: v for k, v in _files(self.home).items()
                    if k.startswith(("data/my-data/collection", "data/my-data/sessions", "data/games/", "settings"))}
        # things go wrong after the backup
        self.write("data/my-data/collection.json", json.dumps({"items": []}))
        (self.mine / "sessions" / "s1.json").unlink()
        self.write("data/my-data/sessions/new.json", "{}")
        self.write("data/games/pokemon/my-data/collection.json", "broken")
        self.write("data/games/pokemon/my-data/trash/1-deck.json", "{}")
        self.write("settings.json", "{}")
        self.assertTrue(datastore.restore_backup(str(z)))
        now = _files(self.home)
        for k, v in original.items():
            self.assertEqual(now.get(k), v, k)
        self.assertNotIn("data/my-data/sessions/new.json", now)                # exactly the backed-up state
        self.assertIn("data/my-data/trash/1-deck.json", now)                   # trash is kept, not replaced
        self.assertIn("data/games/pokemon/my-data/trash/1-deck.json", now)
        self.assertFalse((self.data / "restore-zip").exists())
        self.assertFalse((self.data / "restore-tmp").exists())
        snaps = datastore.snapshots()                                          # state before the restore is kept
        self.assertEqual(len(snaps), 1)
        self.assertEqual((snaps[0] / "reason.txt").read_text("utf-8"), "before-restore")
        self.assertEqual(json.loads((snaps[0] / "my-data" / "collection.json").read_text("utf-8")), {"items": []})

    def test_corrupt_zip_refused(self):
        self.fill()
        before = _files(self.home)
        bad = self.stick / "BentCorner backup broken.zip"
        bad.write_bytes(b"PK\x03\x04 this is not really a zip")
        self.assertIsNone(datastore.backup_info(str(bad)))
        self.assertFalse(datastore.restore_backup(str(bad)))
        now = _files(self.home)
        self.assertEqual({k: v for k, v in now.items() if not k.startswith("data/restore-zip")}, before)
        self.assertFalse((self.data / "backups").exists())                    # not even a snapshot was needed

    def test_truncated_zip_refused(self):
        self.fill()
        z = self.backup()
        half = self.stick / "half.zip"
        half.write_bytes(z.read_bytes()[: z.stat().st_size // 2])
        before = _files(self.home / "data" / "my-data")
        self.assertFalse(datastore.restore_backup(str(half)))
        self.assertEqual(_files(self.home / "data" / "my-data"), before)

    def test_zip_without_my_data_refused(self):
        self.fill()
        before = _files(self.data / "my-data")
        foreign = self.stick / "other.zip"
        with zipfile.ZipFile(foreign, "w") as zf:
            zf.writestr("photos/cat.jpg", b"meow")
        self.assertFalse(datastore.restore_backup(str(foreign)))
        self.assertEqual(_files(self.data / "my-data"), before)

    def test_unpack_ignores_paths_leading_outside(self):
        z = self.stick / "evil.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("my-data/collection.json", "{}")
            zf.writestr("../escaped.txt", "x")
            zf.writestr("../../escaped2.txt", "x")
        out = datastore.unpack_zip(str(z))
        self.assertTrue((out / "my-data" / "collection.json").exists())
        self.assertFalse((self.data / "escaped.txt").exists())
        self.assertFalse((self.home / "escaped2.txt").exists())

    # finding: system/datastore.py unpack_zip checks str(target).startswith(str(out)) – a ZIP entry
    # "../restore-zip-x/f" resolves to data/restore-zip-x/f, which shares the prefix and is written outside the
    # unpack folder. Fixed 2026-10-26: unpack_zip checks with Path.is_relative_to.
    def test_unpack_sibling_prefix_escape(self):
        z = self.stick / "evil.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("../restore-zip-evil/f.txt", "x")
        datastore.unpack_zip(str(z))
        self.assertFalse((self.data / "restore-zip-evil" / "f.txt").exists())


class Attention(_Home):
    def test_messages(self):
        self.fill()
        self.assertIn("Noch keine", autobackup.attention(self.s))
        autobackup.add_target(self.s, self.stick)                   # same drive as the data
        self.assertIn("derselben Festplatte", autobackup.attention(self.s))
        cloud = self.root / "OneDrive"
        cloud.mkdir()
        autobackup.add_target(self.s, cloud)
        self.assertIn("noch keine Sicherung", autobackup.attention(self.s))
        t = autobackup.cfg(self.s)["targets"][1]
        t["ok"] = time.time() - autobackup.STALE - 10
        self.assertIn("14 Tagen", autobackup.attention(self.s))
        t["ok"] = time.time()
        self.assertEqual(autobackup.attention(self.s), "")
        self.s["backup_risk_ok"] = True
        autobackup.cfg(self.s)["targets"] = []
        self.assertEqual(autobackup.attention(self.s), "")         # "I know the risk"

    def test_new_data_since_last_backup(self):
        self.fill()
        cloud = self.root / "OneDrive"
        cloud.mkdir()
        autobackup.add_target(self.s, cloud)
        t = autobackup.cfg(self.s)["targets"][0]
        t["ok"] = time.time() - 3 * 3600
        old = time.time() - 4 * 3600
        for f in self.home.rglob("*"):
            if f.is_file():
                os.utime(f, (old, old))
        self.assertEqual(autobackup.attention(self.s), "")
        f = self.mine / "sessions" / "s2.json"
        f.write_text("{}", "utf-8")
        ts = time.time() - autobackup.UNSAVED_GRACE - 60          # new session, grace time over
        os.utime(f, (ts, ts))
        self.assertIn("Neues", autobackup.attention(self.s))
        ts = time.time() - 60                                      # still within the grace time
        os.utime(f, (ts, ts))
        self.assertEqual(autobackup.attention(self.s), "")

    def test_last_change_ignores_trash_and_settings(self):
        self.fill()
        old = time.time() - 86400
        for f in self.home.rglob("*"):
            if f.is_file():
                os.utime(f, (old, old))
        base = autobackup.last_change()
        self.assertAlmostEqual(base, old, delta=2)
        for rel in ("settings.json", "data/my-data/trash/1-deck.json"):
            os.utime(self.home / rel, None)                        # touched now
        self.assertEqual(autobackup.last_change(), base)
        os.utime(self.mine / "collection.json", None)
        self.assertGreater(autobackup.last_change(), base + 3600)


if __name__ == "__main__":
    unittest.main()
