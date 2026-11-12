"""Guide run 09.11.: a mistyped protection code (the check character catches it) is „wrong code“ like the server's
answer – joining keeps the field (join "need_guard", guard "wrong"), nothing is sent.

    python -m unittest tests.test_guard_typo
"""
import base64
import unittest
from unittest import mock

from net import guard, pairing, sync_ctl, vault

TYPO = "ZZZZZ-ZZZZZ-ZZZZZ-ZZZZZ-ZZZZZ"


class Typo(unittest.TestCase):
    def test_sign_with_a_typo_is_a_wrong_code(self):
        with self.assertRaises(vault.VaultError) as cm:
            guard.sign(TYPO, "msg", salt=pairing.new_salt())
        self.assertEqual(cm.exception.status, 403)
        self.assertTrue(cm.exception.data["main_required"])

    def test_joining_keeps_the_field(self):
        c = mock.Mock()
        c.sync_status = {"join": "busy"}
        c._join_payload = {"seed": base64.b64encode(b"\x11" * 32).decode(), "extra": {"guard_salt": pairing.new_salt()}}
        jobs = []
        c._sync_bg = lambda step, fn: jobs.append(fn)
        c.sync_status["join"] = "need_guard"
        c.settings = {"relay": {}}
        with mock.patch("collection.syncrun.available", lambda: True), \
                mock.patch("net.vault._post", side_effect=AssertionError("sent")):
            sync_ctl.SyncControl.sync_join_guard(c, TYPO)
            try:
                res, err = jobs[0](), None
            except Exception as e:  # noqa: BLE001 – what _sync_bg does
                res, err = None, e
        sync_ctl.SyncControl._join_guard_done(c, res, err)
        self.assertEqual((c.sync_status["join"], c.sync_status["guard"]), ("need_guard", "wrong"))


if __name__ == "__main__":
    unittest.main()
