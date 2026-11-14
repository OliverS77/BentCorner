"""Joining with and without a protection code (Oliver 13.11.: A2 of 08.11. taken back). The joining PC first asks the
server whether the arrived ID has a code: with one, the NEW device types it (as before); without one, the invitation is
enough and it registers at once. It becomes the ID only after the server took it; a wrong code, offline or an older box
change nothing. The showing device offers a pairing code with or without a code; a first code with more than one device
gets legal's note (guard_note_all); an older box's 409 guard_first_only_alone stays handled.

    python -m unittest tests.test_a2_join_guard
"""
import base64
import unittest
from unittest import mock

from net import pairing, sync_ctl, vault

SEED = base64.b64encode(b"\x11" * 32).decode()
S = sync_ctl.SyncControl


def _ctl():
    c = mock.Mock()
    c.sync_status = {}
    c.settings = {"relay": {"seed": base64.b64encode(b"\x22" * 32).decode(), "url": "https://example.invalid"}}
    jobs = []
    c._sync_bg = lambda step, fn: jobs.append((step, fn))
    c._join_ask = lambda: S._join_ask(c)
    c._join_register = lambda code: S._join_register(c, code)
    return c, jobs


class ShowingSide(unittest.TestCase):
    def test_pairing_code_also_without_a_protection_code(self):
        c, jobs = _ctl()
        c.sync_on.return_value = True
        c.sync_orbit_ok.return_value = True
        c.guard_on.return_value = False
        c.sync_status = {}
        c.pair = {}
        S.pair_show(c)
        self.assertNotIn("need_guard", c.pair)

    def test_guard_optional_always(self):
        c, _ = _ctl()
        c._dev_reg = {"list": [{"dev_id": "a"}, {"dev_id": "b"}]}
        self.assertTrue(S.guard_optional(c))

    def test_note_before_the_first_code_with_more_devices(self):
        c, _ = _ctl()
        c.guard_on.return_value = False
        c._dev_reg = {"list": [{"dev_id": "a"}]}
        self.assertFalse(S.guard_note_all(c))
        c._dev_reg = {"list": [{"dev_id": "a"}, {"dev_id": "b"}]}
        self.assertTrue(S.guard_note_all(c))
        c._dev_reg = None
        c.sync_has_others.return_value = True
        self.assertTrue(S.guard_note_all(c))
        c.guard_on.return_value = True   # changing an existing code: no note
        self.assertFalse(S.guard_note_all(c))

    def test_first_code_only_alone_with_the_generated_code(self):
        """An older box (before 13.11.): the same answer on the rescue path (sync_rescue_confirm -> rescue_put) – not
        „couldn't be set up“ but legal's line."""
        c, _ = _ctl()
        c._rescue_missing = lambda err: None
        err = vault.VaultError(409, "nur allein", {"guard_first_only_alone": True})
        S._rescue_done(c, "rescue_put", None, err)
        self.assertEqual((c.sync_status["rescue"], c.sync_status["text"]), ("first_alone", ""))

    def test_first_code_only_alone(self):
        c, _ = _ctl()
        c._rescue_missing = lambda err: None
        S._guard_done(c, vault.VaultError(409, "nur allein", {"guard_first_only_alone": True}))
        self.assertEqual(c.sync_status["guard"], "first_alone")


class JoiningSide(unittest.TestCase):
    def _taken(self, salt=True):
        c, jobs = _ctl()
        mine = c.settings["relay"]["seed"]
        payload = {"seed": SEED, "extra": {"device": "pc", "invite": {"by": "dA", "nonce": "n"}}}
        if salt:
            payload["extra"]["guard_salt"] = pairing.new_salt()
        S._join_take_done(c, payload, None)
        self.assertEqual(c.sync_status["join"], "busy", "first the ID's state from the server")
        self.assertEqual(c.settings["relay"]["seed"], mine, "not this ID yet – only after the server took it")
        step, _fn = jobs.pop()
        self.assertEqual(step, "join_info")
        return c, jobs, mine, payload

    def _register(self, c, jobs, reply="ok"):
        calls = []
        with mock.patch("collection.syncrun.available", lambda: True), \
                mock.patch("net.devkeys.register", lambda s, inv, code: calls.append((s, inv, code)) or reply):
            step, fn = jobs.pop()
            res = fn()
        self.assertEqual(step, "join_guard")
        return calls[0], res

    def _applied(self, c, res):
        c.applied = []
        c._join_apply = lambda r, salt=None: c.applied.append((r, salt))
        S._join_guard_done(c, res, None)
        return c.applied

    def test_with_a_code_the_new_device_types_it(self):
        c, jobs, mine, payload = self._taken()
        S._join_info_done(c, {"guard": {"set": True}, "guard_request": None}, None)
        self.assertEqual(c.sync_status["join"], "need_guard")
        self.assertEqual(jobs, [], "nothing registered before the code is typed")
        with mock.patch("collection.syncrun.available", lambda: True):
            S.sync_join_guard(c, "MEIN-CODE")
        (s, inv, code), res = self._register(c, jobs)
        self.assertEqual((s["relay"]["seed"], inv, code), (SEED, payload["extra"]["invite"], "MEIN-CODE"))
        self.assertEqual(s["relay"]["guard_salt"], payload["extra"]["guard_salt"], "the ID's salt from the payload")
        self.assertEqual(self._applied(c, res), [(payload, payload["extra"]["guard_salt"])])
        self.assertIsNone(c._join_payload)

    def test_without_a_code_the_invitation_is_enough(self):
        c, jobs, mine, payload = self._taken(salt=False)
        with mock.patch("collection.syncrun.available", lambda: True):
            S._join_info_done(c, {"guard": None, "guard_request": None}, None)
        self.assertEqual(c.sync_status["join"], "busy")
        (s, inv, code), res = self._register(c, jobs)
        self.assertEqual((s["relay"]["seed"], inv, code), (SEED, payload["extra"]["invite"], None))
        self.assertEqual(self._applied(c, res), [(payload, None)])

    def test_wrong_code_changes_nothing(self):
        c, jobs, mine, payload = self._taken()
        S._join_info_done(c, {"guard": {"set": True}}, None)
        with mock.patch("collection.syncrun.available", lambda: True):
            S.sync_join_guard(c, "FALSCH")
        err = vault.VaultError(403, "Schutz-Code falsch", {"guard_wrong": True, "main_required": True})
        S._join_guard_done(c, None, err)
        self.assertEqual((c.sync_status["join"], c.sync_status["guard"]), ("need_guard", "wrong"))
        self.assertEqual(c.settings["relay"]["seed"], mine)
        self.assertIs(c._join_payload, payload, "kept: the next try needs no new pairing code")
        S._join_guard_done(c, None, vault.VaultError(429, "warten", {"main_required": True, "retry_after": 4}))
        self.assertEqual((c.sync_status["guard"], c.sync_status["guard_wait"]), ("wait", 4))

    def test_a_code_set_meanwhile_asks_for_it(self):
        """No code when asked, but one at registering (set on another device in between): the field, no "wrong"."""
        c, jobs, mine, payload = self._taken()
        with mock.patch("collection.syncrun.available", lambda: True):
            S._join_info_done(c, {"guard": None}, None)
        S._join_guard_done(c, None, vault.VaultError(403, "Schutz-Code nötig", {"main_required": True}))
        self.assertEqual(c.sync_status["join"], "need_guard")
        self.assertNotIn("guard", c.sync_status)

    def test_older_box_still_wanting_a_code(self):
        c, jobs, mine, payload = self._taken()
        with mock.patch("collection.syncrun.available", lambda: True):
            S._join_info_done(c, {"guard": None}, None)
        S._join_guard_done(c, None, vault.VaultError(409, "erst einen Schutz-Code", {"guard_required": True}))
        self.assertEqual((c.sync_status["join"], c.sync_status["join_error"]), ("error", "guard_required"))
        self.assertEqual(c.settings["relay"]["seed"], mine)
        self.assertIs(c._join_payload, payload)

    def test_offline_then_try_again(self):
        c, jobs, mine, payload = self._taken()
        with mock.patch.object(sync_ctl, "problem_text", lambda e: "offline"):
            S._join_info_done(c, None, vault.VaultError(0, "Server unreachable"))
        self.assertEqual((c.sync_status["join"], c.sync_status["text"]), ("error", "offline"))
        self.assertIs(c._join_payload, payload)
        self.assertEqual(jobs, [])
        S.sync_join_retry(c)
        self.assertEqual(c.sync_status["join"], "busy")
        self.assertEqual(jobs.pop()[0], "join_info")

    def test_info_salt_request_and_drop(self):
        c, jobs, mine, payload = self._taken(salt=False)
        S._join_info_done(c, {"guard": {"set": True, "salt": "S" * 24}, "guard_request": {"until": 1}}, None)
        self.assertEqual(payload["extra"]["guard_salt"], "S" * 24, "an older showing device: the salt from the server")
        self.assertTrue(c.sync_status["join_request"])
        S.sync_join_drop(c)
        self.assertIsNone(c._join_payload)
        self.assertNotIn("join", c.sync_status)
        self.assertEqual(c.settings["relay"]["seed"], mine)


if __name__ == "__main__":
    unittest.main()
