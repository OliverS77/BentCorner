"""Review 08.11.2026 (Prüfkette Schritt 1, library's area): restoring a backup and the automatic backup.
F1: a backup's settings never bring this device's targets/paths/server address along (the identity does – the move);
F2: a settings.json that isn't an object never crashes the start; F3: a ZIP bomb is refused before anything is
written, a cancelled question leaves nothing behind; F4: without the safety copy nothing happens, an error halfway
puts it back; F5: planted „backups“ from the future never make new ones vanish; F8: the tickets come back too;
Gordon B1: a ticket is never archived outside its folder. Throwaway folders only.

    python -m unittest tests/test_review_backup.py
"""
import json
import os
import time
import unittest
import zipfile
from unittest import mock

from collection import collectibles
from system import autobackup, datastore
from tests.test_autobackup import _Home, _files


class SettingsTest(unittest.TestCase):
    def test_device_settings_stay_this_devices(self):
        backup = {"game": "mtg", "relay": {"seed": "SEED-B", "url": "http://evil.example"},
                  "autobackup": {"on": True, "targets": [{"path": "\\\\attacker\\share"}]},
                  "last_backup_path": "\\\\attacker\\x", "last_backup": 1}
        cur = {"relay": {"seed": "SEED-A", "url": "https://bentcorner.app/relay"},
               "autobackup": {"on": True, "targets": [{"path": "E:\\"}]}}
        new = datastore.restorable_settings(json.dumps(backup), cur)
        self.assertEqual(new["relay"]["seed"], "SEED-B")                       # the identity moves – that's the point
        self.assertEqual(new["relay"]["url"], "https://bentcorner.app/relay")  # never the backup's server
        self.assertEqual(new["autobackup"], cur["autobackup"])                 # never the backup's targets
        self.assertNotIn("last_backup_path", new)
        new = datastore.restorable_settings(json.dumps(backup), {})
        self.assertNotIn("url", new["relay"])
        self.assertNotIn("autobackup", new)

    def test_not_an_object(self):
        for text in ("[1]", "3", "null", "nope"):
            self.assertIsNone(datastore.restorable_settings(text, {}))

    def test_start_never_crashes_on_a_bad_settings_file(self):
        from system import startup
        with mock.patch.object(startup, "SETTINGS_FILE") as f:
            f.exists.return_value = True
            f.read_text.return_value = "[1]"
            self.assertEqual(startup._saved(), {})
            self.assertEqual(startup.saved_language(), "de")
        import app
        with mock.patch.object(app, "SETTINGS_FILE") as f:
            f.read_text.return_value = "[1]"
            s = app.MainWindow.load_settings(None)
        self.assertEqual(s["price_update"], app.DEFAULTS["price_update"])


class RestoreTest(_Home):
    def fill2(self):
        self.fill()
        self.write("data/collectibles/tickets/mtg/x/x.json", '{"mine": 1}')

    def backup(self):
        autobackup.add_target(self.s, self.stick)
        (path, ok, name), = autobackup.run(self.s)
        self.assertTrue(ok)
        return self.stick / autobackup.FOLDER / name

    def test_zip_bomb_refused_before_writing(self):
        z = self.root / "bomb.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("my-data/collection.json", "{}")
            zf.writestr("my-data/big.bin", b"\0" * (2 * 1024 * 1024))
        with mock.patch.object(datastore, "ZIP_MAX_BYTES", 1024 * 1024):
            self.assertIsNone(datastore.backup_info(str(z)))
        self.assertFalse((self.data / "restore-zip").exists())
        with mock.patch.object(datastore, "ZIP_MAX_FILES", 1):
            self.assertIsNone(datastore.backup_info(str(z)))

    def test_cancel_leaves_nothing_and_unpacks_once(self):
        self.fill2()
        z = self.backup()
        calls = []
        real = datastore._unzip
        with mock.patch.object(datastore, "_unzip", lambda *a: (calls.append(1), real(*a))):
            datastore.backup_info(str(z))
            datastore.backup_info(str(z))
        self.assertEqual(len(calls), 1)                                        # the same ZIP: unpacked once
        datastore.drop_unpacked()
        self.assertFalse((self.data / "restore-zip").exists())

    def test_without_safety_copy_nothing_changes(self):
        self.fill2()
        z = self.backup()
        self.write("data/my-data/collection.json", '{"items": []}')
        before = _files(self.home / "data" / "my-data")
        with mock.patch.object(datastore, "snapshot", lambda reason="auto": None):
            with self.assertRaises(datastore.RestoreError):
                datastore.restore_backup(str(z))
        self.assertEqual(_files(self.home / "data" / "my-data"), before)

    def test_error_halfway_puts_it_back(self):
        self.fill2()
        z = self.backup()
        self.write("data/my-data/collection.json", '{"items": [{"uid": "now", "count": 1}]}')
        real, n = datastore._apply, []

        def flaky(info, own):
            n.append(own)
            if not own:
                real(info, own)
                raise OSError("disk full")   # after the swap: the safety copy must come back
            real(info, own)
        with mock.patch.object(datastore, "_apply", flaky):
            with self.assertRaises(OSError):
                datastore.restore_backup(str(z))
        self.assertEqual(n, [False, True])
        self.assertIn(b'"now"', (self.mine / "collection.json").read_bytes())

    def test_tickets_come_back(self):
        self.fill2()
        z = self.backup()
        self.write("data/collectibles/tickets/mtg/x/x.json", '{"changed": 1}')
        self.assertTrue(datastore.restore_backup(str(z)))
        self.assertEqual(json.loads((self.data / "collectibles/tickets/mtg/x/x.json").read_text("utf-8")), {"mine": 1})


class IdentityTest(_Home):
    """F1 with performance' helpers (08.11.): a backup with ANOTHER identity takes it over, and this device's keys and
    sync state of the old one go; the same identity keeps them. device_name stays this device's."""

    def setup_identity(self, mine_seed, backup_seed):
        import base64
        self.fill()
        seed = lambda b: base64.b64encode(bytes([b]) * 32).decode()   # noqa: E731
        self.write("settings.json", json.dumps({"game": "mtg", "device_name": "Laptop",
                                                "relay": {"seed": seed(backup_seed), "registered": True}}))
        autobackup.add_target(self.s, self.stick)
        (path, ok, name), = autobackup.run(self.s)
        z = self.stick / autobackup.FOLDER / name
        self.write("settings.json", json.dumps({"game": "mtg", "device_name": "PC 2",
                                                "relay": {"seed": seed(mine_seed), "registered": True}}))
        self.write("devkey.json", "{}")
        self.write("sync/meta.json", "{}")
        return z

    def test_other_identity_drops_the_device_state(self):
        z = self.setup_identity(1, 2)
        self.assertTrue(datastore.restore_backup(str(z)))
        s = json.loads(self.settings_file.read_text("utf-8"))
        self.assertNotIn("registered", s["relay"])
        self.assertEqual(s["device_name"], "PC 2")
        self.assertFalse((self.home / "devkey.json").exists())
        self.assertFalse((self.home / "sync").exists())

    def test_same_identity_keeps_it(self):
        z = self.setup_identity(1, 1)
        self.assertTrue(datastore.restore_backup(str(z)))
        self.assertTrue((self.home / "devkey.json").exists())
        self.assertTrue((self.home / "sync").exists())


class DeclinedLineTest(unittest.TestCase):
    def test_server_date_on_the_waiting_device(self):
        import types
        from tests.test_device_switch import UI
        from ui import qsync
        until = int(time.time()) + 7 * 86400
        c = types.SimpleNamespace(sync_status={"join_wait": {"declined": True, "cooldown_until": until}})
        line = qsync.join_wait_items(UI(), c)[0][1][0]
        self.assertEqual(line, qsync.JOIN_DECLINED_UNTIL.format(date=time.strftime("%d.%m.%Y", time.localtime(until))))
        c.sync_status["join_wait"] = {"declined": True}
        self.assertEqual(qsync.join_wait_items(UI(), c)[0][1][0], qsync.JOIN_DECLINED)


class PruneTest(_Home):
    def test_future_files_never_delete_new_backups(self):
        folder = self.stick / autobackup.FOLDER
        folder.mkdir()
        for y in range(5):                                                     # planted, „from 2099“
            f = folder / f"BentCorner backup 209{y}-01-01 00-00.zip"
            f.write_bytes(b"x")
            os.utime(f, (4102444800 + y, 4102444800 + y))
        new = folder / time.strftime("BentCorner backup %Y-%m-%d %H-%M.zip")
        new.write_bytes(b"x")
        autobackup._prune(folder)
        self.assertTrue(new.exists())


class TicketPathTest(unittest.TestCase):
    def test_never_outside_the_archive(self):
        with self.assertRaises(ValueError):
            collectibles._path({"g": "mtg", "x": "a", "id": "../../../../x/evil"})
        self.assertTrue(str(collectibles._path({"g": "mtg", "x": "ab12", "id": "ab12"})).endswith("ab12.json"))


if __name__ == "__main__":
    unittest.main()
