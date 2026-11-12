"""A2 (Oliver 08.11.): adding a device needs the protection code – typed on the NEW device; the showing device offers no
code without one set. The joining PC becomes the ID only after the server took the code; a wrong one changes nothing.
Plus: a first code only while the ID has a single device (box 8597915: 409 guard_first_only_alone).

    python -m unittest tests.test_a2_join_guard
"""
import base64
import unittest
from unittest import mock

from net import pairing, sync_ctl, vault

SEED = base64.b64encode(b"\x11" * 32).decode()


def _ctl():
    c = mock.Mock()
    c.sync_status = {}
    c.settings = {"relay": {"seed": base64.b64encode(b"\x22" * 32).decode(), "url": "https://example.invalid"}}
    jobs = []
    c._sync_bg = lambda step, fn: jobs.append((step, fn))
    return c, jobs


class ShowingSide(unittest.TestCase):
    def test_no_code_no_pairing_code(self):
        c, jobs = _ctl()
        c.sync_on.return_value = True
        c.sync_orbit_ok.return_value = True
        c.guard_on.return_value = False
        c.pair = {}
        sync_ctl.SyncControl.pair_show(c)
        self.assertTrue(c.pair["need_guard"])
        self.assertEqual(jobs, [])

    def test_guard_optional_by_the_registry(self):
        c, _ = _ctl()
        c._dev_reg = {"list": [{"dev_id": "a"}]}
        self.assertTrue(sync_ctl.SyncControl.guard_optional(c))
        c._dev_reg = {"list": [{"dev_id": "a"}, {"dev_id": "b"}]}
        self.assertFalse(sync_ctl.SyncControl.guard_optional(c))
        c._dev_reg = None
        c.sync_has_others.return_value = True
        self.assertFalse(sync_ctl.SyncControl.guard_optional(c))

    def test_first_code_only_alone_with_the_generated_code(self):
        """library 09.11.: the same answer on the rescue path (sync_rescue_confirm -> rescue_put) – not „couldn't be set
        up“ but legal's line."""
        c, _ = _ctl()
        c._rescue_missing = lambda err: None
        err = vault.VaultError(409, "nur allein", {"guard_first_only_alone": True})
        sync_ctl.SyncControl._rescue_done(c, "rescue_put", None, err)
        self.assertEqual((c.sync_status["rescue"], c.sync_status["text"]), ("first_alone", ""))

    def test_first_code_only_alone(self):
        c, _ = _ctl()
        c._rescue_missing = lambda err: None
        sync_ctl.SyncControl._guard_done(c, vault.VaultError(409, "nur allein", {"guard_first_only_alone": True}))
        self.assertEqual(c.sync_status["guard"], "first_alone")


class JoiningSide(unittest.TestCase):
    def _taken(self):
        c, jobs = _ctl()
        mine = c.settings["relay"]["seed"]
        payload = {"seed": SEED, "extra": {"device": "pc", "invite": {"by": "dA", "nonce": "n"},
                                           "guard_salt": pairing.new_salt()}}
        sync_ctl.SyncControl._join_take_done(c, payload, None)
        self.assertEqual(c.sync_status["join"], "need_guard")
        self.assertEqual(c.settings["relay"]["seed"], mine, "not this ID yet – only after the code was taken")
        c._join_payload = payload
        return c, jobs, mine, payload

    def test_right_code_then_the_id(self):
        c, jobs, mine, payload = self._taken()
        calls = []
        with mock.patch("collection.syncrun.available", lambda: True), \
                mock.patch("net.devkeys.register", lambda s, inv, code: calls.append((s, inv, code)) or "ok"):
            sync_ctl.SyncControl.sync_join_guard(c, "MEIN-CODE")
            step, fn = jobs.pop()
            res = fn()
        self.assertEqual(step, "join_guard")
        s, inv, code = calls[0]
        self.assertEqual((s["relay"]["seed"], inv, code), (SEED, payload["extra"]["invite"], "MEIN-CODE"))
        self.assertEqual(s["relay"]["guard_salt"], payload["extra"]["guard_salt"], "the ID's salt from the payload")
        c._join_apply = lambda res, salt=None: c.applied.append((res, salt))
        c.applied = []
        sync_ctl.SyncControl._join_guard_done(c, res, None)
        self.assertEqual(c.applied, [(payload, payload["extra"]["guard_salt"])])
        self.assertIsNone(c._join_payload)

    def test_wrong_code_changes_nothing(self):
        c, jobs, mine, payload = self._taken()
        err = vault.VaultError(403, "Schutz-Code falsch", {"guard_wrong": True, "main_required": True})
        sync_ctl.SyncControl._join_guard_done(c, None, err)
        self.assertEqual((c.sync_status["join"], c.sync_status["guard"]), ("need_guard", "wrong"))
        self.assertEqual(c.settings["relay"]["seed"], mine)
        self.assertIs(c._join_payload, payload, "kept: the next try needs no new pairing code")
        err = vault.VaultError(429, "warten", {"main_required": True, "retry_after": 4})
        sync_ctl.SyncControl._join_guard_done(c, None, err)
        self.assertEqual((c.sync_status["guard"], c.sync_status["guard_wait"]), ("wait", 4))


    def test_info_and_drop(self):
        c, jobs, mine, payload = self._taken()
        step, fn = jobs.pop()
        self.assertEqual(step, "join_info")
        del payload["extra"]["guard_salt"]
        sync_ctl.SyncControl._join_info_done(c, {"guard": {"set": True, "salt": "S" * 24}, "guard_request": {"until": 1}},
                                             None)
        self.assertEqual(payload["extra"]["guard_salt"], "S" * 24, "an older showing device: the salt from the server")
        self.assertTrue(c.sync_status["join_request"])
        sync_ctl.SyncControl.sync_join_drop(c)
        self.assertIsNone(c._join_payload)
        self.assertNotIn("join", c.sync_status)
        self.assertEqual(c.settings["relay"]["seed"], mine)


if __name__ == "__main__":
    unittest.main()
