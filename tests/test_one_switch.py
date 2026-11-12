"""One switch (lead/Oliver 07.11.): a paired device always syncs; the only switch is „Online-Sicherung und Abgleich“
(off = the online backup goes, and with it the sync for ALL devices); one device leaves by „Dieses Gerät abmelden“
(only it stops, the others go on). The UI asks first with sync_backup_plan / sync_leave_plan.

    python -m unittest tests.test_one_switch
"""
import base64
import unittest
from unittest import mock

from net import sync_ctl

SEED = base64.b64encode(b"\x07" * 32).decode()


def ctl(others=False, guard=False, seeded=True):
    c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
    c.settings, c.sync_status = {"relay": {}, "sync_backup": True}, {"busy": False}
    for n in ("_sync_changed", "settings_changed", "sync_setup", "sync_now", "vault_delete"):
        setattr(c, n, mock.Mock())
    state = {"on": True}
    e = mock.Mock()
    e.meta = {"seeded": seeded, "guard": guard}
    e.lock = mock.MagicMock()
    e.on = lambda: state["on"]
    e.switch_on = lambda: state.update(on=True)
    e.switch_off = lambda: state.update(on=False)
    e.devices = lambda: [{"dev": "a", "me": True}] + ([{"dev": "b", "me": False}] if others else [])
    c.sync_engine = e
    return c


class PairingSwitchesOn(unittest.TestCase):
    def test_joining_switches_on(self):
        c = ctl()
        c.sync_engine.switch_off()
        c.settings["sync_backup"] = False
        sync_ctl.SyncControl._join_apply(c, {"seed": SEED, "extra": {"device": "pc"}})   # A2: after the code
        self.assertTrue(c.sync_engine.on())
        self.assertTrue(c.settings["sync_backup"])
        c.sync_now.assert_called()


class Leave(unittest.TestCase):
    def test_with_others_only_this_device_goes(self):
        c = ctl(others=True)
        self.assertEqual(c.sync_leave_plan(), "leave")
        steps = []
        c._sync_bg = lambda step, fn: (steps.append(step), fn(), sync_ctl.SyncControl._sync_done(c, step, None, None))
        c._gate_state = lambda: None
        c.sync_leave()
        self.assertEqual(steps, ["leave"])
        c.sync_engine.drop_self.assert_called_once()
        c.sync_engine.push.assert_called_once()
        self.assertFalse(c.sync_engine.on())
        self.assertFalse(c.settings["sync_backup"])
        self.assertTrue(c.sync_status["left"])
        c.vault_delete.assert_not_called()

    def test_joining_again_clears_the_left_line(self):
        """Guide run 08.11.: after signing out and adding the device again it still said „leaves the sync“."""
        c = ctl(others=True)
        c.sync_status["left"] = True
        sync_ctl.SyncControl._join_apply(c, {"seed": SEED, "extra": {"device": "pc"}})   # A2: after the code
        self.assertNotIn("left", c.sync_status)

    def test_last_device_asks_first_and_deletes_only_on_the_answer(self):
        c = ctl(guard=True)
        self.assertEqual(c.sync_leave_plan(), "ask")
        c.sync_leave()
        self.assertEqual(c.sync_status["switch_off"], "ask")
        self.assertTrue(c.sync_engine.on(), "nothing happens before the answer")
        c.vault_delete.assert_not_called()
        c.sync_leave(delete=True, guard="code")
        c.vault_delete.assert_called_once_with("code")

    def test_last_device_keeps_the_backup(self):
        c = ctl(guard=True)
        c.sync_leave(delete=False)
        self.assertFalse(c.sync_engine.on())
        self.assertTrue(c.sync_status["left"])
        c.vault_delete.assert_not_called()


class DropSelf(unittest.TestCase):
    def test_the_others_stop_listing_it(self):
        import tempfile
        from tests import test_syncrun as ts
        with tempfile.TemporaryDirectory() as tmp:
            t = [1_790_000_000_000]
            vault = ts.FakeVault()
            a = ts.Device(tmp, "a", vault, lambda: t[0])
            b = ts.Device(tmp, "b", vault, lambda: t[0])
            for d in (a, b):
                d.eng.switch_on()
                d.sync()
            t[0] += 1000
            a.sync()
            self.assertEqual(len(a.eng.devices()), 2)
            b.eng.drop_self()
            b.eng.push()
            a.sync()
            self.assertEqual([d["me"] for d in a.eng.devices()], [True])


class BackupOffForAll(unittest.TestCase):
    def test_off_deletes_the_online_backup_for_all(self):
        """Off = vault + envelope deleted on the server; the other devices get VaultDeleted at their next run and go
        off (DeletedAndBackedUpAgain in test_syncrun)."""
        c = ctl(others=True)
        with mock.patch("collection.syncrun.available", lambda: True):
            sync_ctl.SyncControl.sync_backup_set(c, False, guard="code")
        c.vault_delete.assert_called_once_with("code")

    def test_the_others_go_off_when_it_is_deleted(self):
        from collection import syncrun
        c = ctl()
        c.sync_engine.deleted_elsewhere = lambda: c.sync_engine.switch_off()
        c.guard_on = lambda: False
        sync_ctl.SyncControl._sync_done(c, "fetch", None, syncrun.VaultDeleted(1793600000))
        self.assertFalse(c.sync_engine.on())
        self.assertFalse(c.settings["sync_backup"])


if __name__ == "__main__":
    unittest.main()
