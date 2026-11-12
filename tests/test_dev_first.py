"""ports 08.11.: an unregistered device (restored backup, old install) of an ID that has a device list gets 403
dev_required on every sync write. The registration used to come only after a GOOD run – so it never came: no join
request, the error line for ever. Now the 403 asks to join at once, and the sync waits while the request is open.

    python -m unittest tests.test_dev_first
"""
import unittest
from unittest import mock

from net import devices_ctl, sync_ctl, vault


def _ctl():
    c = mock.Mock()
    c.sync_status = {"busy": True}
    c._rekey_n = 0
    c.settings = {"relay": {"on": True}}
    return c


class DevFirst(unittest.TestCase):
    def test_403_dev_required_asks_to_join(self):
        c = _ctl()
        err = vault.VaultError(403, "Gerät nicht eingetragen", {"dev_required": True})
        with mock.patch("net.devkeys.registered", lambda s: False), mock.patch.object(sync_ctl, "QtCore"):
            sync_ctl.SyncControl._sync_done(c, "push", None, err)
        c._dev_ensure.assert_called_once_with(force=True)
        self.assertFalse(c.sync_status["busy"])
        self.assertFalse(c.sync_status.get("text"), "no error line – the join request is the answer")

    def test_force_registers_before_a_good_run(self):
        c = mock.Mock()
        c.sync_status = {}
        c._dev_busy = False
        c._dev_cooldown = 0
        c._join_invite = None
        c.settings = {"relay": {"on": True}}
        c.sync_engine.on.return_value = True
        c.sync_engine.meta = {}   # never seeded: no good run yet
        with mock.patch("collection.syncrun.available", lambda: True), \
                mock.patch("net.devkeys.unreadable", lambda: False), \
                mock.patch("net.devkeys.registered", lambda s: False), \
                mock.patch("net.devkeys.mine", lambda create=True: None):
            devices_ctl.DevicesControl._dev_ensure(c)
            c._sync_bg.assert_not_called()
            devices_ctl.DevicesControl._dev_ensure(c, force=True)
            self.assertEqual(c._sync_bg.call_args.args[0], "dev_add")

    def test_no_sync_while_the_request_waits(self):
        c = _ctl()
        c.sync_status = {"busy": False, "join_wait": {"until": 5}}
        c.pair = {}   # no code being shown (sync_now also waits for that – desk-light)
        c.sync_on.return_value = True
        c.sync_orbit_ok.return_value = True
        with mock.patch("net.devkeys.registered", lambda s: False):
            sync_ctl.SyncControl.sync_now(c)
        c._sync_bg.assert_not_called()
        with mock.patch("net.devkeys.registered", lambda s: True):
            sync_ctl.SyncControl.sync_now(c)
        c._sync_bg.assert_called_once()


if __name__ == "__main__":
    unittest.main()
