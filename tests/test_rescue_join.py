"""Review 08.11. (M10): after a restore with the protection code, the device registration uses that code once – the
device joins at once instead of a 14-day request that a stolen device could decline. The code stays in memory only.

    python -m unittest tests.test_rescue_join
"""
import unittest
from unittest import mock

from net import devices_ctl, sync_ctl, vault


def _ctl():
    c = mock.Mock()
    c.sync_status = {}
    c.settings = {"relay": {"on": True}}
    c._dev_busy = False
    c._dev_cooldown = 0
    c._join_invite = None
    c.sync_engine.on.return_value = True
    c.sync_engine.meta = {"seeded": True}
    return c


class RescueJoin(unittest.TestCase):
    def _flow(self, register):
        c = _ctl()
        with mock.patch("collection.syncrun.available", lambda: True):
            sync_ctl.SyncControl.sync_rescue_restore(c, "ABCD-EFGH")
            sync_ctl.SyncControl._rescue_done(c, "rescue_restore", "c2VlZA==", None)
            self.assertNotIn("ABCD", str(c.settings), "the code is never stored in the settings")
            got = {}
            c._sync_bg = lambda step, fn: got.update(step=step, fn=fn)
            with mock.patch("net.devkeys.registered", lambda s: False), mock.patch("net.devkeys.unreadable", lambda: False), \
                    mock.patch("net.devkeys.mine", lambda create=True: None), \
                    mock.patch("net.devkeys.register", side_effect=register) as reg:
                devices_ctl.DevicesControl._dev_ensure(c)
                res = got["fn"]()
        return c, reg, res

    def test_joins_with_the_code(self):
        c, reg, res = self._flow(lambda s, inv=None, guard=None: "ok")
        self.assertEqual(res, "ok")
        self.assertEqual(reg.call_args_list[0].args[1:], (None, "ABCD-EFGH"))
        self.assertIsNone(c._rescue_guard, "used once")

    def test_code_refused_asks_instead(self):
        def register(s, inv=None, guard=None):
            if guard:
                raise vault.VaultError(403, "main_required", {"main_required": True})
            return {"pending": True, "until": 1}
        c, reg, res = self._flow(register)
        self.assertEqual(res, {"pending": True, "until": 1})
        self.assertEqual(len(reg.call_args_list), 2)

    def test_wrong_code_forgotten(self):
        c = _ctl()
        with mock.patch("collection.syncrun.available", lambda: True):
            sync_ctl.SyncControl.sync_rescue_restore(c, "ABCD-EFGH")
            sync_ctl.SyncControl._rescue_done(c, "rescue_restore", None, vault.VaultError(404, "nope"))
        self.assertIsNone(c._rescue_typed)


    def test_own_backup_with_the_code_no_foreign_line(self):
        """lead 09.11.: own backup back (rescue code), a code is set, the right code typed -> registered at once (the
        M10 way), and NO „another device is signed in“ line – that is only for a plain registration."""
        c, reg, res = self._flow(lambda s, inv=None, guard=None: "ok")
        self.assertFalse(c._dev_add_plain, "with the code it is no plain registration")
        from net import devices_ctl
        devices_ctl.DevicesControl._dev_done(c, "dev_add", res, None)
        self.assertNotIn("foreign_device", c.sync_status)
        self.assertNotIn("join_wait", c.sync_status)


if __name__ == "__main__":
    unittest.main()
