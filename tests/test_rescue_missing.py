"""T2 07.11.: protection code set, envelope missing (guard without rescue). Like the web (ports): the envelope is tried
twice; still missing -> settings["sync_rescue_missing"]; the next try with the same code needs no „previous code“ –
only the envelope goes up, signed with the typed code, and the server takes it only for THE code (else need_old).

    python -m unittest tests.test_rescue_missing
"""
import unittest
from unittest import mock

from collection import syncrescue, syncrun
from net import guard, pairing, sync_ctl, vault

CODE, OTHER = pairing.new_rescue_code(), pairing.new_rescue_code()   # made here, never written down


def ctl(meta=None, settings=None):
    c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
    c.settings = dict(settings or {})
    c.sync_status = {"busy": False}
    c.sync_engine = mock.Mock()
    c.sync_engine.meta = dict(meta or {})
    for n in ("_sync_changed", "settings_changed", "sync_now", "sync_setup"):
        setattr(c, n, mock.Mock())
    c.ran = []
    c._sync_bg = lambda step, fn: c.ran.append((step, fn))
    return c


def run(c, step_done):
    (step, fn), = c.ran
    c.ran.clear()
    try:
        res, err = fn(), None
    except Exception as e:  # noqa: BLE001
        res, err = None, e
    with mock.patch.object(sync_ctl, "tr", lambda s: s), mock.patch.object(sync_ctl, "problem_text", str):
        step_done(c, step, res, err)
    return err


def rescue_done(c, step, res, err):
    sync_ctl.SyncControl._rescue_done(c, step, res, err)


def guard_done(c, step, res, err):
    sync_ctl.SyncControl._guard_done(c, err)


class Envelope(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(syncrun, "available", lambda: True),
                  mock.patch.object(syncrescue, "last5_ok", lambda code, last5: True),
                  mock.patch("time.sleep")):
            p.start()
            self.addCleanup(p.stop)

    def test_second_try_suffices(self):
        c = ctl()
        put = mock.Mock(side_effect=[vault.VaultError(500, "down"), {"ok": True}])
        with mock.patch.object(guard, "set_code") as setc, mock.patch.object(vault, "rescue_put", put):
            sync_ctl.SyncControl.sync_rescue_confirm(c, CODE, CODE[-5:])
            self.assertIsNone(run(c, rescue_done))
        setc.assert_called_once()
        self.assertEqual(put.call_count, 2)
        self.assertTrue(c.settings["sync_rescue_ok"])
        self.assertNotIn("sync_rescue_missing", c.settings)

    def test_first_code_envelope_fails_nothing_set(self):
        """lead 12.11. (bug 1): a FIRST code sends its envelope before the code – failing twice, NOTHING is set: no
        protection code on the server, no „envelope missing“ mark; the page's „couldn't be set up“ is then true."""
        c = ctl()
        down = vault.VaultError(500, "down")
        with mock.patch.object(guard, "set_code") as setc, \
                mock.patch.object(vault, "rescue_put", side_effect=[down, down]):
            sync_ctl.SyncControl.sync_rescue_confirm(c, CODE, CODE[-5:])
            err = run(c, rescue_done)
        self.assertFalse(getattr(err, "rescue_missing", False))
        setc.assert_not_called()
        self.assertNotIn("sync_rescue_missing", c.settings)
        self.assertFalse(c.sync_engine.meta.get("guard"))
        self.assertEqual(c.sync_status["rescue"], "error")

    def test_change_envelope_fails_mark_then_same_code_without_the_old_one(self):
        """A change: the code first (the envelope needs its signature) – the envelope failing twice leaves the mark
        („half“); the next try sends only the envelope, the code is not set again."""
        c = ctl(meta={"guard": True})
        down = vault.VaultError(500, "down")
        with mock.patch.object(guard, "set_code") as setc, \
                mock.patch.object(vault, "rescue_put", side_effect=[down, down]):
            sync_ctl.SyncControl.sync_rescue_confirm(c, CODE, CODE[-5:], old="OLD-CODE")
            err = run(c, rescue_done)
        self.assertTrue(err.rescue_missing)
        setc.assert_called_once()
        self.assertTrue(c.settings["sync_rescue_missing"])
        self.assertEqual(c.sync_status["rescue"], "half")
        with mock.patch.object(guard, "set_code") as setc2, mock.patch.object(vault, "rescue_put") as put:
            sync_ctl.SyncControl.sync_rescue_confirm(c, CODE, CODE[-5:])
            self.assertIsNone(run(c, rescue_done))
        setc2.assert_not_called()
        put.assert_called_once()
        self.assertNotIn("sync_rescue_missing", c.settings)
        self.assertTrue(c.settings["sync_rescue_ok"])

    def test_one_key_derivation_for_code_and_envelope(self):
        c = ctl()
        real = pairing.code_keys
        with mock.patch.object(pairing, "code_keys", side_effect=real) as kdf,                 mock.patch.object(guard, "_post"), mock.patch.object(vault, "_post"),                 mock.patch.object(vault, "_me", return_value=("ME", 1)),                 mock.patch("net.relay.my_code", return_value="ME"), mock.patch("net.relay._signed", return_value="s"),                 mock.patch("net.relay._signing"):
            c.settings["relay"] = {"seed": "c2VlZHNlZWRzZWVkc2VlZHNlZWRzZWVkc2VlZHNlZWQ="}
            sync_ctl.SyncControl.sync_rescue_confirm(c, CODE, CODE[-5:])
            self.assertIsNone(run(c, rescue_done))
        self.assertEqual(kdf.call_count, 1)

    def test_another_code_is_refused_by_the_server(self):
        """The mark never skips the server's check: rescue/put carries sig_main of the TYPED code; the server answers
        403 main_required for any other – then the old code is asked for, nothing changed."""
        c = ctl(meta={"guard": True}, settings={"sync_rescue_missing": True})
        refused = vault.VaultError(403, "Schutz-Code nötig", {"main_required": True})
        with mock.patch.object(guard, "set_code") as setc, \
                mock.patch.object(vault, "rescue_put", side_effect=refused) as put:
            sync_ctl.SyncControl.sync_rescue_confirm(c, OTHER, OTHER[-5:])
            run(c, rescue_done)
        setc.assert_not_called()
        self.assertEqual(put.call_count, 1)   # no retry of a refusal
        self.assertEqual(c.sync_status["rescue"], "need_old")
        self.assertTrue(c.settings["sync_rescue_missing"])

    def test_without_the_mark_a_set_code_needs_the_old_one(self):
        c = ctl(meta={"guard": True})
        with mock.patch.object(vault, "rescue_put") as put:
            sync_ctl.SyncControl.sync_rescue_confirm(c, CODE, CODE[-5:])
        self.assertEqual(c.sync_status["rescue"], "need_old")
        self.assertEqual(c.ran, [])
        put.assert_not_called()

    def test_rescue_put_signs_with_the_typed_code(self):
        from net import pairing
        salt = pairing.new_salt()
        settings = {"relay": {"guard_salt": salt}}
        with mock.patch.object(vault, "_post") as post, mock.patch.object(vault, "_me", return_value=("ME", 1)):
            vault.rescue_put(settings, CODE)
        body = post.call_args[0][2]
        msg = f"rescue_put|ME|{body['rid']}|" + __import__("hashlib").sha256(body["data"].encode()).hexdigest() + "|1"
        self.assertEqual(body["sig_main"], guard.sign(CODE, msg, salt=salt))
        self.assertNotEqual(body["sig_main"], guard.sign(OTHER, msg, salt=salt))

    def test_guard_set_path_the_same(self):
        c = ctl()
        down = vault.VaultError(500, "down")
        with mock.patch.object(guard, "set_code") as setc, \
                mock.patch.object(vault, "rescue_put", side_effect=[down, down]), \
                mock.patch.object(sync_ctl.SyncControl, "guard_strength", lambda self, t: {"ok": True}):
            sync_ctl.SyncControl.guard_set(c, CODE)
            run(c, guard_done)
        setc.assert_not_called()                                    # a first code: nothing set (lead 12.11.)
        self.assertNotIn("sync_rescue_missing", c.settings)
        c = ctl(meta={"guard": True})
        with mock.patch.object(guard, "set_code"), mock.patch.object(vault, "rescue_put", side_effect=[down, down]), \
                mock.patch.object(sync_ctl.SyncControl, "guard_strength", lambda self, t: {"ok": True}):
            sync_ctl.SyncControl.guard_set(c, CODE, old="OLD-CODE")   # a change: the code is set, its envelope not
            run(c, guard_done)
        self.assertTrue(c.settings["sync_rescue_missing"])
        self.assertEqual(c.sync_status["guard"], "half")
        with mock.patch.object(guard, "set_code") as setc, mock.patch.object(vault, "rescue_put"):
            sync_ctl.SyncControl.guard_set(c, CODE)
            run(c, guard_done)
        setc.assert_not_called()
        self.assertNotIn("sync_rescue_missing", c.settings)
        self.assertEqual(c.sync_status["guard"], "ok")


if __name__ == "__main__":
    unittest.main()
