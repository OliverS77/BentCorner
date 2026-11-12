"""The lamp on "Backup" (Oliver, 29.10.): outside Full Orbit it stays on – also after a look – until a backup in a
second place is set up and fresh (addition, switch LOCAL_OK_CLEARS); the online-backup rule for Full Orbit waits
for the sync plan (ONLINE_BACKUP). No UI, no network.

    python -m unittest tests/test_backup_lamp.py
"""
import time
import unittest
from unittest import mock

from system import autobackup


class Lamp(unittest.TestCase):
    def test_no_target_lights_it(self):
        self.assertTrue(autobackup.lamp({"autobackup": {"on": True, "targets": []}}))

    def test_set_up_puts_it_out_even_on_the_same_drive(self):
        now = time.time()
        s = {"autobackup": {"on": True, "targets": [{"path": "C:\\Backup", "ok": 0, "error": "", "tried": 0, "added": now}]}}
        with mock.patch.object(autobackup, "kind", lambda p: "same"):
            self.assertFalse(autobackup.lamp(s))            # just set up, same drive: out (only a hint)
            self.assertTrue(autobackup.attention(s))        # … the hint is still there
            with mock.patch.object(autobackup, "LOCAL_OK_CLEARS", False):
                self.assertTrue(autobackup.lamp(s))

    def test_fourteen_days_without_a_backup_light_it_again(self):
        old = time.time() - 15 * 86400
        s = {"autobackup": {"on": True, "targets": [{"path": "E:\\", "ok": old, "error": "", "tried": old}]}}
        self.assertTrue(autobackup.lamp(s))
        s["autobackup"]["targets"][0]["ok"] = time.time()
        self.assertFalse(autobackup.lamp(s))
        s = {"autobackup": {"on": True, "targets": [{"path": "E:\\", "ok": 0, "error": "", "tried": 0, "added": old}]}}
        self.assertTrue(autobackup.lamp(s))                 # set up 15 days ago, never worked (stick never plugged in)

    def test_online_rule_only_with_the_sync_plan(self):
        s = {"autobackup": {"on": True, "targets": []}, "orbit": "near"}
        from net import relay
        relay.state(s)["on"] = True   # Full Orbit
        self.assertTrue(autobackup.lamp(s))   # no online backup yet: like Near/Core
        with mock.patch.object(autobackup, "ONLINE_BACKUP", True):
            self.assertTrue(autobackup.lamp(s))
            s["backup_online_seen"] = True
            self.assertFalse(autobackup.lamp(s))


if __name__ == "__main__":
    unittest.main()


class OneIsEnough(unittest.TestCase):
    """PLAN-EINFACH C (Oliver 07.11.): the lamp goes out as soon as any backup exists – one is enough."""

    def test_a_file_by_hand_puts_it_out(self):
        s = {"autobackup": {"on": True, "targets": []}, "orbit": "near"}
        self.assertTrue(autobackup.lamp(s))
        s["last_backup"] = time.time()
        self.assertFalse(autobackup.lamp(s))

    def test_the_online_backup_puts_it_out(self):
        from net import relay
        s = {"autobackup": {"on": True, "targets": []}, "orbit": "near", "sync_backup": True}
        self.assertTrue(autobackup.lamp(s))   # not in Full Orbit: no online backup
        relay.state(s)["on"] = True
        self.assertFalse(autobackup.lamp(s))
        s["sync_backup"] = False
        self.assertTrue(autobackup.lamp(s))

    def test_a_failing_target_still_lights_it(self):
        old = time.time() - 15 * 86400
        s = {"autobackup": {"on": True, "targets": [{"path": "E:\\", "ok": old, "error": "", "tried": old}]},
             "last_backup": old}
        self.assertTrue(autobackup.lamp(s))   # an error, not a missing set-up (Oliver 29.10.)


class RestoreFolded(unittest.TestCase):
    """lead 07.11.: „Mit Schutz-Code wiederherstellen“ open only while this device has no online backup – set up, it
    sits folded as „Auf einem neuen Gerät wiederherstellen ›“."""

    def test_folded_when_on_open_when_off(self):
        import types
        from collection import syncrun
        from system import orbit
        from tests.test_backup_ui import UI, texts
        from tests.test_guard_request_ui import ctrl
        from ui import backupui
        with mock.patch.object(syncrun, "available", return_value=True):
            orbit.bind(None)
            c = ctrl()[0]
            c.sync_engine = types.SimpleNamespace(on=lambda: False, meta={})
            t = texts(backupui.settings_items(UI(), c, types.SimpleNamespace(form=None), lambda: None))
            self.assertIn(backupui.RESTORE_NEW + " ›", t)
            self.assertNotIn(backupui.RESTORE, t)
            c.settings["sync_backup"] = False
            t = texts(backupui.settings_items(UI(), c, types.SimpleNamespace(form=None), lambda: None))
            self.assertNotIn(backupui.RESTORE_NEW + " ›", t)

    def test_after_deleting_folded(self):
        # lead 08.11. (step 10): after the online backup was deleted, restoring isn't offered open any more
        import types
        from collection import syncrun
        from system import orbit
        from tests.test_backup_ui import UI, texts
        from tests.test_guard_request_ui import ctrl
        from ui import backupui
        with mock.patch.object(syncrun, "available", return_value=True):
            orbit.bind(None)
            c = ctrl()[0]
            c.settings["sync_backup"] = False
            c.sync_engine = types.SimpleNamespace(on=lambda: False, meta={})
            c.sync_status["deleted"] = True
            t = texts(backupui.settings_items(UI(), c, types.SimpleNamespace(form=None), lambda: None))
            self.assertNotIn(backupui.RESTORE, t)
            self.assertIn(backupui.RESTORE_NEW + " ›", t)
            c.sync_status.pop("deleted")                       # a device that never had one: open as before
            t = texts(backupui.settings_items(UI(), c, types.SimpleNamespace(form=None), lambda: None))
            self.assertNotIn(backupui.RESTORE_NEW + " ›", t)

