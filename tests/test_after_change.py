"""Review 08.11. (M11): a key change that went through is never reported as failed because a step AFTER it failed
(friends' notes, the rescue envelope): the notes stay pending for the next start, a missing envelope is marked.

    python -m unittest tests.test_after_change
"""
import unittest
from unittest import mock

from net import devices_ctl, rekey, relay, vault


def offline(*a, **kw):
    raise vault.VaultError(0, "offline")


class AfterChange(unittest.TestCase):
    def test_failures_are_reported_not_raised(self):
        with mock.patch("net.rekey.finish", side_effect=relay.RelayError("x", 0)), \
                mock.patch("net.vault.rescue_put", offline):
            self.assertEqual(rekey.after_change({}, "CODE"), {"rescued": False, "after_failed": ["friends", "rescue"]})

    def test_all_good(self):
        with mock.patch("net.rekey.finish"), mock.patch("net.vault.rescue_put"):
            self.assertEqual(rekey.after_change({}, "CODE"), {"rescued": True, "after_failed": []})
            self.assertEqual(rekey.after_change({}, None), {"rescued": False, "after_failed": []})

    def test_remove_counts_as_done(self):
        c = mock.Mock()
        c.sync_status = {}
        c._rekey_n = 0
        c._rid_of = lambda dev: "dB"
        c.guard_on.return_value = True
        c.sync_devices.return_value = []
        got = {}
        c._sync_bg = lambda step, fn: got.update(fn=fn)
        with mock.patch("collection.syncrun.available", lambda: True), \
                mock.patch("net.rekey.remove_one", lambda *a: {"old": "O", "new": "N", "gone": ["dB"]}), \
                mock.patch("net.rekey.finish", side_effect=relay.RelayError("x", 0)), \
                mock.patch("net.vault.rescue_put", offline):
            devices_ctl.DevicesControl.sync_remove(c, "x", guard="CODE")
            res = got["fn"]()
        self.assertEqual(res["new"], "N")
        self.assertEqual(res["after_failed"], ["friends", "rescue"])


if __name__ == "__main__":
    unittest.main()
