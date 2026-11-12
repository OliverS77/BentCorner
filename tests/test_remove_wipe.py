"""D (Oliver/lead 12.11.2026): a device that leaves a group that goes on empties itself – after a 30-day copy that holds
everything that goes (set aside, the trash, Studio photos, earlier copies, the settings without codes/keys). Without the
copy nothing is deleted. A deleted group (plain 410 gone) keeps everything. Temp folders only – never real data.

    python -m unittest tests/test_remove_wipe.py
"""
import json
import os
import pathlib
import tempfile
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from system import datastore  # noqa: E402


class Home:
    """A throw-away data home with the datastore paths pointed at it."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        data = base / "data"
        self.p = [mock.patch.object(datastore, "DATA", data), mock.patch.object(datastore, "SETTINGS", base / "settings.json"),
                  mock.patch.object(datastore, "BACKUPS", data / "backups"),
                  mock.patch.object(datastore, "AUTO", data / "backups" / "auto"),
                  mock.patch.object(datastore, "REMOVED", data / "backups" / "before-remove")]
        for x in self.p:
            x.start()
        (data / "my-data" / "trash").mkdir(parents=True)
        (data / "my-data" / "collection.json").write_text(json.dumps({"items": [{"id": "a", "count": 3}]}), "utf-8")
        (data / "my-data" / "trash" / "deck-1.json").write_text("{}", "utf-8")
        (data / "games" / "pokemon" / "my-data").mkdir(parents=True)
        (data / "games" / "pokemon" / "my-data" / "collection.json").write_text("{}", "utf-8")
        (data / "beiseite").mkdir()
        (data / "beiseite" / "set-aside.json").write_text("{}", "utf-8")
        (data / "studio").mkdir()
        (data / "studio" / "foto.jpg").write_bytes(b"jpg")
        (data / "backups" / "auto" / "2026-11-01_10-00-00").mkdir(parents=True)
        (base / "settings.json").write_text(json.dumps({
            "relay": {"seed": "SECRET"}, "sync_backup": True, "sync_rescue_ok": True, "phone_token": "T",
            "profile": {"name": "Oliver"}, "device_name": "Küche", "look": "dark"}), "utf-8")
        self.base, self.data = base, data
        return self

    def __exit__(self, *a):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()


class CopyAndWipeTest(unittest.TestCase):
    def test_copy_holds_everything_without_secrets(self):
        with Home() as h:
            dest = datastore.remove_copy(now=1000.0)
            self.assertIsNotNone(dest)
            self.assertTrue((dest / "my-data" / "collection.json").exists())
            self.assertTrue((dest / "games" / "pokemon" / "my-data" / "collection.json").exists())
            self.assertTrue((dest / "extra" / "trash" / "my-data" / "deck-1.json").exists())    # the trash
            self.assertTrue((dest / "extra" / "beiseite" / "set-aside.json").exists())          # set aside
            self.assertTrue((dest / "extra" / "studio" / "foto.jpg").exists())                 # own photos
            self.assertTrue((dest / "earlier" / "auto" / "2026-11-01_10-00-00").is_dir())       # earlier state
            s = json.loads((dest / "settings.json").read_text("utf-8"))
            self.assertNotIn("relay", s)                                                       # no codes/keys
            self.assertNotIn("phone_token", s)
            self.assertFalse([k for k in s if k.startswith("sync_")])
            self.assertEqual(s["look"], "dark")
            self.assertEqual(datastore.removed_copies(now=1000.0)[0]["until"], 1000.0 + 30 * 86400)

    def test_wipe_then_restore(self):
        with Home() as h:
            dest = datastore.remove_copy()
            settings = json.loads((h.base / "settings.json").read_text("utf-8"))
            datastore.wipe_personal(settings)
            self.assertFalse((h.data / "my-data" / "collection.json").exists())
            self.assertFalse((h.data / "beiseite").exists())
            self.assertFalse((h.data / "studio").exists())
            self.assertFalse((h.data / "games" / "pokemon" / "my-data").exists())
            self.assertNotIn("profile", settings)
            self.assertEqual(settings["look"], "dark")
            settings["relay"] = {"seed": "NEW"}   # the emptied device's new identity
            (h.base / "settings.json").write_text(json.dumps(settings), "utf-8")
            self.assertTrue(datastore.restore_backup(dest))
            self.assertTrue((h.data / "my-data" / "collection.json").exists())
            self.assertTrue((h.data / "beiseite" / "set-aside.json").exists())
            self.assertTrue((h.data / "studio" / "foto.jpg").exists())
            self.assertTrue((h.data / "my-data" / "trash" / "deck-1.json").exists())
            back = json.loads((h.base / "settings.json").read_text("utf-8"))
            self.assertEqual(back["relay"]["seed"], "NEW")          # the copy has no keys: this device keeps its own
            self.assertEqual(back["profile"]["name"], "Oliver")

    def test_the_rest_of_datastore_still_there(self):
        # desk-geraete3 box run 12.11.: the patch had swallowed „def personal_size():“ – the Backup page crashed
        with Home():
            self.assertGreater(datastore.personal_size(), 0)

    def test_prune_after_30_days(self):
        with Home():
            datastore.remove_copy(now=1000.0)
            self.assertEqual(datastore.prune_removed(now=1000.0 + 29 * 86400), 0)
            self.assertEqual(datastore.prune_removed(now=1000.0 + 31 * 86400), 1)
            self.assertEqual(datastore.removed_copies(now=1000.0 + 31 * 86400), [])

    def test_copy_fails_nothing_left(self):
        with Home():
            with mock.patch.object(datastore, "_copy_personal", side_effect=OSError("disk full")):
                self.assertIsNone(datastore.remove_copy())
            self.assertFalse(list(datastore.REMOVED.iterdir()) if datastore.REMOVED.exists() else [])


class CtrlTest(unittest.TestCase):
    """The sign-out (others remain) and the removal from outside – copy first, then empty and restart."""

    def ctrl(self, others=True):
        from net import sync_ctl
        cls = next(v for v in vars(sync_ctl).values() if isinstance(v, type) and hasattr(v, "_empty_device"))
        c = cls.__new__(cls)
        c.settings = {"relay": {"seed": "OLD"}, "sync_backup": True}
        c.sync_status = {}
        c.sync_engine = types.SimpleNamespace(on=lambda: True, meta={"seeded": True}, switch_off=lambda: None,
                                              drop_self=lambda: None, push=lambda: None, devices=lambda: [{}, {}])
        c.settings_changed = c._sync_changed = c.sync_setup = lambda: None
        c.sync_has_others = lambda: others
        c.bg = []
        c._sync_bg = lambda step, fn: c.bg.append(step)
        c.restarts = []
        c.restart_after_restore = lambda: c.restarts.append(1)
        c.save_settings = lambda: None
        return c

    def test_no_copy_nothing_happens(self):
        c = self.ctrl()
        with mock.patch.object(datastore, "remove_copy", return_value=None), \
                mock.patch.object(datastore, "wipe_personal") as wipe:
            c.sync_leave()
        self.assertEqual(c.bg, [])                          # not even left
        self.assertEqual(c.sync_status.get("wipe"), "failed")
        wipe.assert_not_called()
        self.assertEqual(c.settings["relay"]["seed"], "OLD")

    def test_copy_then_leave_then_empty(self):
        c = self.ctrl()
        dest = pathlib.Path(tempfile.gettempdir()) / "bc-test-copy"
        with mock.patch.object(datastore, "remove_copy", return_value=dest), \
                mock.patch.object(datastore, "wipe_personal") as wipe, mock.patch("net.devkeys.forget"), \
                mock.patch("net.devkeys.drop_device_state"):
            c.sync_leave()
            self.assertEqual(c.bg, ["leave"])               # pending changes go up first (drop_self + push), then out
            wipe.assert_not_called()
            c._leave_done({"registry": True}, None)
            wipe.assert_called_once()
        self.assertNotEqual(c.settings["relay"]["seed"], "OLD")   # the new identity only after the copy
        self.assertEqual(c.restarts, [1])
        self.assertEqual(c.settings["sync_wiped"]["copy"], "bc-test-copy")

    def test_last_device_keeps_its_data(self):
        c = self.ctrl(others=False)
        c.sync_switch_plan = lambda: "ask"
        with mock.patch.object(datastore, "remove_copy") as copy:
            c.sync_leave()
        copy.assert_not_called()


class RelayMarkTest(unittest.TestCase):
    """Removed (per_device without an envelope, or gone WITH by) empties; a deleted group (plain gone) never."""

    def mark(self, data, fwd=None):
        from net import relay
        s = {"relay": {"seed": "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWY="}}
        with mock.patch.object(relay, "changing", return_value=False), mock.patch("net.devkeys.forget"), \
                mock.patch("net.devkeys.fetch_fwd", return_value=fwd), mock.patch.object(relay, "my_code", return_value="C"), \
                mock.patch("net.pairing.vault_open", return_value={"name": "PC 1"}):
            relay.moved_away(s, dict(data))
        return bool(s["relay"].get("removed_here"))

    def test_cases(self):
        self.assertTrue(self.mark({"moved": True, "per_device": True}))     # removed: no envelope for this device
        self.assertTrue(self.mark({"gone": True, "by": "x"}))               # removed by an own device (old way)
        self.assertTrue(self.mark({"gone": True, "removed": True}))          # the box's mark (2 devices, box patch A)
        self.assertFalse(self.mark({"gone": True}))                          # the group / identity deleted
        self.assertFalse(self.mark({"moved": True, "per_device": True}, fwd={"seed": "N", "code": "D"}))   # followed


if __name__ == "__main__":
    unittest.main()
