"""lead 09.11. (guide run, step 8): sign out -> add again -> the code field stays open -> joining works – on the PC logic
level (library has the UI test). The earlier join's "ok" must be gone after signing out, the pairing code goes through,
the protection code is asked for, and with it the device is this ID again.

    python -m unittest tests.test_rejoin_after_leave
"""
import base64
import unittest
from unittest import mock

from net import pairing, sync_ctl

SEED = base64.b64encode(b"\x11" * 32).decode()


def _ctl():
    c = mock.Mock()
    c.sync_status = {"join": "ok", "join_n": 2}   # PC 2 was added before (step 2)
    c.settings = {"relay": {"seed": base64.b64encode(b"\x22" * 32).decode(), "url": "https://example.invalid"}}
    c.sync_engine.meta = {}
    c.sync_engine.lock = mock.MagicMock()
    jobs = []
    c._sync_bg = lambda step, fn: jobs.append((step, fn))
    c._join_apply = lambda res, salt=None: sync_ctl.SyncControl._join_apply(c, res, salt)
    return c, jobs


class RejoinAfterLeave(unittest.TestCase):
    def test_sign_out_then_join_again(self):
        c, jobs = _ctl()
        sync_ctl.SyncControl._leave_done(c, {"registry": True}, None)   # 7: signed out
        self.assertTrue(c.sync_status["left"])
        self.assertNotIn("join", c.sync_status, "the earlier join is over – the field won't close at once")
        with mock.patch("collection.syncrun.available", lambda: True):
            sync_ctl.SyncControl.sync_join_code(c, "ABCDE-FGHJK")       # 8: the pairing code again
        step, fn = jobs.pop()
        self.assertEqual((step, c.sync_status["join"]), ("join_take", "busy"))
        salt = pairing.new_salt()
        payload = {"seed": SEED, "extra": {"device": "pc", "invite": {"by": "dA", "nonce": "n"}, "guard_salt": salt}}
        sync_ctl.SyncControl._join_take_done(c, payload, None)
        self.assertEqual(c.sync_status["join"], "need_guard", "the protection code is asked for – the field stays")
        jobs.clear()
        with mock.patch("collection.syncrun.available", lambda: True):
            sync_ctl.SyncControl.sync_join_guard(c, "MEIN-CODE")
        step, fn = jobs.pop()
        with mock.patch("net.devkeys.register", return_value="ok"):
            res = fn()
        sync_ctl.SyncControl._join_guard_done(c, res, None)
        self.assertEqual(c.settings["relay"]["seed"], SEED, "this ID again")
        self.assertEqual(c.settings["relay"]["guard_salt"], salt)
        self.assertNotIn("left", c.sync_status, "back in: the „leaves the sync“ line is over")


if __name__ == "__main__":
    unittest.main()
