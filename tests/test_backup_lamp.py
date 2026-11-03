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
