"""Online backup and the rescue code (library's pages call these; legal/Oliver 06.11.):
- the rescue code lives only in memory; the server only ever gets rid (derived) and the sealed seed;
- nothing goes up before the user typed the code's last 5 characters;
- „Online-Sicherung löschen“ deletes the vault AND the rescue envelope;
- behind the switch (syncrun.available): off = no network call at all.

    python -m unittest tests/test_syncrescue.py
"""
import base64
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

from collection import syncrescue, syncrun
from net import pairing, vault

SEED = base64.b64encode(b"\x05" * 32).decode()


class Code(unittest.TestCase):
    def test_new_code_and_last5(self):
        c = syncrescue.new_code()
        self.assertRegex(c, r"^[A-Z0-9]{5}(-[A-Z0-9]{5}){4}$")
        self.assertTrue(syncrescue.last5_ok(c, c[-5:].lower()))
        self.assertTrue(syncrescue.last5_ok(c, " " + c[-5:] + " "))
        self.assertFalse(syncrescue.last5_ok(c, c[-6:-1]))
        self.assertFalse(syncrescue.last5_ok(c, c[-4:]))
        self.assertFalse(syncrescue.last5_ok("kaputt", "AAAAA"))


class Network(unittest.TestCase):
    def setUp(self):
        self.settings = {"relay": {"seed": SEED, "registered": "x"}}
        self.sent = []

        def post(settings, path, payload):
            self.sent.append((path, payload))
            if path == "/v1/rescue/get":
                return {"data": self.stored}
            return {"ok": True}
        p = mock.patch.object(vault, "_post", post)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(vault, "_me", lambda s: ("ABCDEF1234", 1793600000))
        q.start()
        self.addCleanup(q.stop)

    def test_put_sends_only_rid_and_the_sealed_seed(self):
        code = syncrescue.new_code()
        vault.rescue_put(self.settings, code)
        path, payload = self.sent[-1]
        self.assertEqual(path, "/v1/rescue/put")
        self.assertEqual(payload["rid"], pairing.rescue_rid(code))
        self.assertNotIn(code.replace("-", ""), repr(payload).replace("-", ""), "the code itself never goes up")
        self.assertNotIn(SEED, repr(payload), "the seed only sealed")
        self.assertEqual(pairing.rescue_open(code, payload["data"])[0], SEED)
        self.assertEqual(payload["salt"] if "salt" in payload else self.settings["relay"]["guard_salt"],
                         pairing.rescue_header(payload["data"])["salt"], "the envelope carries the ID's salt")

    def test_fetch_opens_with_the_code_only(self):
        code = syncrescue.new_code()
        self.stored = pairing.rescue_seal(code, SEED, pairing.new_salt())
        restored = {}
        self.assertEqual(vault.rescue_fetch(restored, code), SEED)
        self.assertEqual(restored["relay"]["guard_salt"], pairing.rescue_header(self.stored)["salt"])
        with self.assertRaises(pairing.PairError):
            vault.rescue_fetch({}, syncrescue.new_code())

    def test_delete_takes_vault_and_envelope(self):
        vault.clear(self.settings)
        self.assertEqual([p for p, _ in self.sent], ["/v1/vault/del", "/v1/rescue/del"])
        self.assertFalse(any("sig_main" in d for _, d in self.sent), "no code: as before")

    def test_delete_with_the_code_signs_both(self):
        code = syncrescue.new_code()
        self.settings["relay"]["guard_salt"] = salt = pairing.new_salt()
        vault.clear(self.settings, code)
        pk = pairing.main_signing(code, salt).verify_key
        for path, d in self.sent:
            msg = f"{path.split('/')[2]}_del|ABCDEF1234|1793600000".encode()
            pk.verify(msg, base64.b64decode(d["sig_main"]))   # raises if not signed with the code
        self.assertEqual(len(self.sent), 2)


class Switch(unittest.TestCase):
    """lead 06.11.: in qtquick the switch is off – then nothing, not even a network call."""

    def test_wanted_needs_switch_full_orbit_and_backup_not_the_code(self):
        """Oliver 07.11.: the rescue/protection code is an offer, no longer a condition."""
        s = {"relay": {"on": True}, "sync_backup": True, "sync_rescue_ok": False}
        with mock.patch.object(syncrun, "available", lambda: True):
            self.assertTrue(syncrun.wanted(s))
            self.assertFalse(syncrun.wanted(dict(s, sync_backup=False)))
            self.assertFalse(syncrun.wanted(dict(s, relay={"on": False}, orbit="near")))
        with mock.patch.object(syncrun, "available", lambda: False):
            self.assertFalse(syncrun.wanted(s))

    def test_switch_off_no_calls(self):
        from net import sync_ctl
        ctl = type("C", (), {})()
        ctl.settings, ctl.sync_status = {}, {}
        ctl._sync_bg = mock.Mock()
        ctl._sync_changed = mock.Mock()
        ctl.settings_changed = mock.Mock()
        ctl.vault_delete = mock.Mock()
        env = {k: v for k, v in os.environ.items() if k != "BC_SYNC"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(syncrun, "SYNC_TEST", False):
            C = sync_ctl.SyncControl
            C.sync_rescue_confirm(ctl, "x", "y")
            C.sync_rescue_restore(ctl, "x")
            C.sync_offer_answer(ctl, False)
            C.sync_backup_set(ctl, False)
            # the protection code too (lead 07.11.): switch off = not one network call
            ctl.sync_engine = mock.Mock()
            ctl.sync_engine.meta = {}
            ctl.guard_strength = lambda c: {"ok": True}
            ctl.guard_on = lambda: True
            C.guard_set(ctl, "x", old="y")
            self.assertIsNone(C.guard_request_prepare(ctl))
            self.assertFalse(C.guard_request_confirm(ctl, "x", "y"))
            C.guard_decline(ctl, "x")
            C.sync_rekey(ctl, "remove", "x")
            C.vault_delete(ctl, "x")
        ctl._sync_bg.assert_not_called()
        ctl.vault_delete.assert_not_called()
        self.assertEqual(ctl.settings, {})

    def test_confirm_needs_the_last_5(self):
        from net import sync_ctl
        ctl = type("C", (), {})()
        ctl.settings, ctl.sync_status = {}, {}
        ctl._sync_bg = mock.Mock()
        ctl._sync_changed = mock.Mock()
        code = syncrescue.new_code()
        with mock.patch.object(syncrun, "available", lambda: True), mock.patch.object(sync_ctl, "tr", lambda s: s):
            sync_ctl.SyncControl.sync_rescue_confirm(ctl, code, "ZZZZZ" if not code.endswith("ZZZZZ") else "YYYYY")
            self.assertEqual(ctl.sync_status["rescue"], "mismatch")
            ctl._sync_bg.assert_not_called()
            sync_ctl.SyncControl.sync_rescue_confirm(ctl, code, code[-5:])
        self.assertEqual(ctl.sync_status["rescue"], "busy")
        self.assertEqual(ctl._sync_bg.call_args[0][0], "rescue_put")

    def test_a_new_code_needs_the_old_one(self):
        """A code is set: a new one without the old code is refused before anything is sent (guard and envelope stay
        one code); with old it goes through – both ways (generated and own)."""
        from net import sync_ctl
        ctl = type("C", (), {})()
        ctl.settings, ctl.sync_status = {}, {}
        ctl._sync_bg = mock.Mock()
        ctl._sync_changed = mock.Mock()
        ctl.sync_engine = type("E", (), {"meta": {"guard": True}})()
        ctl.guard_on = lambda: sync_ctl.SyncControl.guard_on(ctl)
        ctl.guard_strength = lambda t: {"ok": True}
        code, old = syncrescue.new_code(), syncrescue.new_code()
        with mock.patch.object(syncrun, "available", lambda: True), mock.patch.object(sync_ctl, "tr", lambda s: s):
            sync_ctl.SyncControl.sync_rescue_confirm(ctl, code, code[-5:])
            self.assertEqual(ctl.sync_status["rescue"], "need_old")
            sync_ctl.SyncControl.guard_set(ctl, code, own=True)
            self.assertEqual(ctl.sync_status["guard"], "need_old")
            ctl._sync_bg.assert_not_called()
            sync_ctl.SyncControl.sync_rescue_confirm(ctl, code, code[-5:], old=old)
            self.assertEqual(ctl._sync_bg.call_args[0][0], "rescue_put")
            sync_ctl.SyncControl.guard_set(ctl, code, own=True, old=old)
            self.assertEqual(ctl._sync_bg.call_args[0][0], "guard")



class DeviceSwitchOff(unittest.TestCase):
    """lead/legal 07.11.: others -> only this device leaves; alone without a protection code -> off + vault deleted;
    alone with a code or unclear -> ask (then the user's answer)."""

    def ctl(self, devices, guard=False, paired=False, seeded=True):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings = {"sync_paired": paired}
        c.sync_status = {}
        c._sync_changed = mock.Mock()
        c.sync_setup = mock.Mock()
        c.vault_delete = mock.Mock()
        c.sync_engine = mock.Mock()
        c.sync_engine.meta = {"seeded": seeded, "guard": guard}
        c.sync_engine.devices.return_value = [{"dev": d} for d in devices]
        return c

    def test_plans(self):
        self.assertEqual(self.ctl(["a", "b"]).sync_switch_plan(), "leave")
        self.assertEqual(self.ctl(["a"], paired=True).sync_switch_plan(), "leave")
        self.assertEqual(self.ctl(["a"]).sync_switch_plan(), "delete")
        self.assertEqual(self.ctl(["a"], guard=True).sync_switch_plan(), "ask")
        self.assertEqual(self.ctl([], seeded=False).sync_switch_plan(), "ask")

class RekeyKeepsTheCode(unittest.TestCase):
    """lead 07.11.: after „Gerät entfernen“ with the protection code, the new address has the code and the envelope
    again at once – the page must not ask for a code again (sync_rescue_ok stays True); without a code it is offered."""

    def run_rekey(self, guard):
        from net import guard as guardmod, rekey, sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings, c.sync_status = {"sync_rescue_ok": True}, {}
        c._sync_changed, c.settings_changed, c.sync_now, c.relay_rekey = (mock.Mock() for _ in range(4))
        c.sync_engine = mock.Mock()
        c.sync_engine.on.return_value = False
        jobs = []
        c._sync_bg = lambda step, fn: jobs.append((step, fn))
        set_code, put = mock.Mock(), mock.Mock()
        with (mock.patch.object(syncrun, "available", lambda: True),
              mock.patch.object(rekey, "change", lambda s, m, g=None: {"old": "A", "new": "B"}),
              mock.patch.object(rekey, "finish", lambda s: None),
              mock.patch.object(guardmod, "set_code", set_code), mock.patch.object(vault, "rescue_put", put)):
            c.sync_rekey("remove", guard)
            step, fn = jobs[0]
            res = fn()
        if guard:
            self.assertNotIn(guard, repr(res), "only a yes/no comes back, never the code")
        # Gordon 07.11.: the server carries the code over – a guard/set would be refused; the envelope goes up anew
        set_code.assert_not_called()
        self.assertEqual([c_[0][1] for c_ in put.call_args_list], [guard] if guard else [])
        sync_ctl.SyncControl._sync_done(c, step, res, None)
        return c

    def test_with_code_no_new_question(self):
        c = self.run_rekey(syncrescue.new_code())
        self.assertTrue(c.settings["sync_rescue_ok"])
        self.assertEqual(c.sync_status["rekey"], "ok")

    def test_without_code_offered_again(self):
        c = self.run_rekey(None)
        self.assertFalse(c.settings["sync_rescue_ok"])


class CodeLost(unittest.TestCase):
    """library/ports 07.11.: „Code verloren?“ in two steps like the web – the new code only shown, sent only after the
    last 5 are typed; the date is the server's; this device marks its own request."""

    def ctl(self):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings, c.sync_status = {}, {}
        c._sync_changed, c.settings_changed, c.sync_now = (mock.Mock() for _ in range(3))
        c._sync_bg = mock.Mock()
        c.sync_engine = mock.Mock()
        c.sync_engine.meta = {"seeded": True}
        return c

    def test_two_steps(self):
        from net import sync_ctl
        c = self.ctl()
        with mock.patch.object(syncrun, "available", lambda: True), mock.patch.object(sync_ctl, "tr", lambda s: s):
            code = sync_ctl.SyncControl.guard_request_prepare(c)
            self.assertTrue(code)
            self.assertNotIn(code, repr(c.settings) + repr(c.sync_status) + repr(vars(c)), "only returned, not kept")
            c._sync_bg.assert_not_called()
            wrong = "ZZZZZ" if not code.endswith("ZZZZZ") else "YYYYY"
            self.assertFalse(sync_ctl.SyncControl.guard_request_confirm(c, code, wrong))
            c._sync_bg.assert_not_called()
            self.assertTrue(sync_ctl.SyncControl.guard_request_confirm(c, code, code[-5:]))
            self.assertEqual(c._sync_bg.call_args[0][0], "guard_request")
            sync_ctl.SyncControl._sync_done(c, "guard_request", {"ok": True, "until": 1794000600}, None)
        self.assertEqual(c.sync_status["guard"], "ok")
        self.assertEqual(c.sync_status["request_until"], 1794000600)
        self.assertEqual(c.settings["sync_guard_mine"], {"until": 1794000600})
        self.assertNotIn(code, repr(c.settings) + repr(c.sync_status))

    def test_mark_goes_with_the_request(self):
        from net import sync_ctl
        c = self.ctl()
        c.settings["sync_guard_mine"] = {"until": 1}
        c.sync_engine.meta = {"seeded": True, "guard_request": {"since": 0, "until": 1}}
        self.assertEqual(sync_ctl.SyncControl.guard_request_info(c), {"since": 0, "until": 1})
        self.assertIn("sync_guard_mine", c.settings)
        c.sync_engine.meta = {"seeded": True}
        self.assertIsNone(sync_ctl.SyncControl.guard_request_info(c))
        self.assertNotIn("sync_guard_mine", c.settings)

    def test_switch_off(self):
        from net import sync_ctl
        c = self.ctl()
        with mock.patch.object(syncrun, "available", lambda: False):
            self.assertIsNone(sync_ctl.SyncControl.guard_request_prepare(c))
            self.assertFalse(sync_ctl.SyncControl.guard_request_confirm(c, syncrescue.new_code(), "AAAAA"))
        c._sync_bg.assert_not_called()


class DeleteAndRemoved(unittest.TestCase):
    """lead/ports 07.11.: deleting the online backup goes to the server FIRST – offline nothing changes; a removed
    device is a final state (kept, no error line), not „a backup of a removed identity“."""

    def setUp(self):
        p = mock.patch.object(syncrun, "available", lambda: True)   # the switch on (the off case: Switch)
        p.start()
        self.addCleanup(p.stop)

    def ctl(self):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings = {"sync_backup": True, "relay": {"removed_by": "Pixel 8"}}
        c.sync_status = {}
        c._sync_changed = mock.Mock()
        c.sync_setup = mock.Mock()
        c.settings_changed = mock.Mock()
        c._sync_bg = mock.Mock()
        c.sync_engine = mock.Mock()
        c.sync_engine.meta = {}   # no protection code (a Mock's .get would say „set“)
        return c

    def test_with_a_code_delete_needs_it(self):
        """lead 07.11. (Gordon faf6385): a protection code set – deleting the online backup only with it; without,
        nothing is sent; the server's 403/429 lead to asking for the code, never to an error line or switching off."""
        from net import sync_ctl
        from net.vault import VaultError
        c = self.ctl()
        c.sync_engine.meta = {"guard": True}
        c.vault_delete()
        c._sync_bg.assert_not_called()
        self.assertEqual(c.sync_status["delete_guard"], "need")
        code = syncrescue.new_code()
        with mock.patch.object(sync_ctl, "tr", lambda s: s):
            c.vault_delete(code)
            self.assertEqual(c._sync_bg.call_args[0][0], "vault_delete")
            sync_ctl.SyncControl._sync_done(c, "vault_delete", None,
                                            VaultError(403, "x", {"main_required": True}))
            self.assertEqual(c.sync_status["delete_guard"], "wrong")
            c.vault_delete(code)
            sync_ctl.SyncControl._sync_done(c, "vault_delete", None,
                                            VaultError(429, "x", {"main_required": True, "retry_after": 30}))
            self.assertEqual((c.sync_status["delete_guard"], c.sync_status["guard_wait"]), ("wait", 30))
            c.sync_engine.meta = {}   # set on another device meanwhile: the server asks, this PC didn't know
            c.vault_delete()
            sync_ctl.SyncControl._sync_done(c, "vault_delete", None,
                                            VaultError(429, "x", {"main_required": True}))
            self.assertEqual(c.sync_status["delete_guard"], "need")
        c.sync_engine.switch_off.assert_not_called()
        self.assertTrue(c.settings["sync_backup"])
        self.assertEqual(c.sync_status.get("text"), "")

    def test_the_typed_code_is_kept_nowhere(self):
        """lead 07.11.: the code goes only into the one background call – never into settings, sync_status, the log
        or an attribute of the control (only the yes/no „a code was typed“)."""
        import logging
        from net import sync_ctl
        from net.vault import VaultError
        c = self.ctl()
        c.sync_engine.meta = {"guard": True}
        code = syncrescue.new_code()
        bare = code.replace("-", "").upper()
        with mock.patch.object(sync_ctl, "tr", lambda s: s), self.assertLogs(level="DEBUG") as logs:
            logging.getLogger().debug("start")
            for err in (VaultError(403, "x", {"main_required": True}), VaultError(0, "offline"), None):
                c.vault_delete(code)
                c._sync_bg.reset_mock()   # the background call ran and is gone (the mock would keep its lambda)
                sync_ctl.SyncControl._sync_done(c, "vault_delete", None if err else {}, err)
        seen = repr(c.settings) + repr(c.sync_status) + repr(vars(c)) + " ".join(logs.output)
        self.assertNotIn(bare, seen.replace("-", "").upper())

    def test_offline_delete_changes_nothing(self):
        from net import sync_ctl
        from net.vault import VaultError
        c = self.ctl()
        c.vault_delete()
        c.sync_engine.switch_off.assert_not_called()
        with mock.patch.object(sync_ctl, "tr", lambda s: s):
            sync_ctl.SyncControl._sync_done(c, "vault_delete", None, VaultError(0, "unreachable"))
        c.sync_engine.switch_off.assert_not_called()
        self.assertTrue(c.settings["sync_backup"])
        self.assertFalse(c.sync_status["deleted"])

    def test_delete_then_off(self):
        from net import sync_ctl
        c = self.ctl()
        c.vault_delete()
        with mock.patch.object(sync_ctl, "tr", lambda s: s):
            sync_ctl.SyncControl._sync_done(c, "vault_delete", {}, None)
        c.sync_engine.switch_off.assert_called_once()
        self.assertFalse(c.settings["sync_backup"])
        self.assertTrue(c.sync_status["deleted"])

    def test_removed_is_final_and_kept(self):
        from net import sync_ctl
        from net.vault import VaultError
        c = self.ctl()
        c.sync_engine.meta = {}
        sync_ctl.SyncControl._sync_done(c, "fetch", None, VaultError(410, "gone", {"gone": True}))
        self.assertEqual(c.sync_status["removed"], {"by": "Pixel 8"})
        self.assertEqual(c.settings["relay"]["removed"]["by"], "Pixel 8")
        self.assertEqual(c.sync_status.get("text"), "")
        self.assertIsNot(c.sync_status.get("ok"), False, "no error line")

if __name__ == "__main__":
    unittest.main()


class JoinTaken(unittest.TestCase):
    """Teil-A run 07.11.: a PC joining names the other device right (the offer says "pc"/"phone"; old web: phone) and
    is in the online backup afterwards (Settings → Backup shows it on)."""

    def run_join(self, extra):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings, c.sync_status = {"relay": {}}, {}
        c._sync_changed, c.settings_changed, c.sync_setup, c.sync_now = (mock.Mock() for _ in range(4))
        c.sync_engine = mock.Mock()
        c.sync_engine.meta = {}
        c.sync_engine.lock = mock.MagicMock()
        sync_ctl.SyncControl._join_apply(c, {"seed": SEED, "extra": extra})   # A2: after the code was taken
        return c

    def test_the_other_device_and_the_backup(self):
        c = self.run_join({"device": "pc"})
        self.assertEqual(c.sync_engine.meta["join_other"], "pc")
        self.assertTrue(c.settings["sync_backup"])
        self.assertTrue(c.settings["sync_asked"])
        self.assertEqual(self.run_join({}).sync_engine.meta["join_other"], "phone", "old web: no field")
        self.assertEqual(self.run_join({"device": "toaster"}).sync_engine.meta["join_other"], "phone")

    def test_the_offer_says_pc(self):
        self.assertEqual(vault.pair_extra({})["device"], "pc")


class OnlyFullOrbit(unittest.TestCase):
    """Oliver/lead 07.11.: pairing and syncing only in Full Orbit. Core/Near: not one network call from the sync – the
    pairing stays, nothing is sent or deleted; back in Full Orbit it goes on."""

    def ctl(self, full):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings = {"relay": {"on": full, "seed": SEED}, "orbit": "near"}
        c.sync_status = {"ok": None, "text": "", "when": None, "busy": False}
        c.sync_engine = mock.Mock()
        c.sync_engine.on.return_value = True
        c.sync_engine.meta = {"seeded": True}
        c._sync_bg, c._sync_changed, c._pair_drop_images = mock.Mock(), mock.Mock(), mock.Mock()
        c._sync_t, c._sync_edit_t = mock.Mock(), mock.Mock()
        return c

    def test_core_no_network_call_from_the_sync(self):
        from net import sync_ctl
        c = self.ctl(full=False)
        with mock.patch.object(syncrun, "available", lambda: True), \
                mock.patch.object(sync_ctl.QtCore.QTimer, "singleShot") as later:
            sync_ctl.SyncControl.sync_setup(c)
            sync_ctl.SyncControl.sync_now(c, manual=True)
            sync_ctl.SyncControl.pair_show(c)
            sync_ctl.SyncControl.sync_join_code(c, "ABCDE-23456")
        c._sync_bg.assert_not_called()
        c._sync_t.start.assert_not_called()
        later.assert_not_called()
        self.assertEqual(c.sync_status["paused"], "orbit")
        self.assertEqual(c.sync_status["join"], "orbit")
        self.assertTrue(c.pair["orbit"])
        c.sync_engine.switch_off.assert_not_called()   # the pairing stays

    def test_back_in_full_orbit_it_goes_on(self):
        from net import sync_ctl
        c = self.ctl(full=False)
        with mock.patch.object(syncrun, "available", lambda: True), \
                mock.patch.object(sync_ctl.QtCore.QTimer, "singleShot"):
            sync_ctl.SyncControl.sync_setup(c)
            c.settings["relay"]["on"] = True
            sync_ctl.SyncControl.sync_setup(c)
            sync_ctl.SyncControl.sync_now(c, manual=True)
        c._sync_t.start.assert_called()
        self.assertEqual(c.sync_status["paused"], "")
        self.assertEqual(c._sync_bg.call_args[0][0], "fetch")


class DeletedElsewhereBackupOff(unittest.TestCase):
    """Teil-A run 07.11.: deleted on another device -> this device's backup shows OFF (no „request a new code“)."""

    def test_backup_off(self):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings = {"sync_backup": True, "sync_rescue_ok": True}
        c.sync_status = {"busy": True}
        c.sync_engine = mock.Mock()
        c.sync_engine.meta = {}
        for n in ("_sync_changed", "settings_changed", "sync_setup"):
            setattr(c, n, mock.Mock())
        with mock.patch.object(sync_ctl, "tr", lambda s: s):
            sync_ctl.SyncControl._sync_done(c, "fetch", None, syncrun.VaultDeleted(1793600000))
        c.sync_engine.deleted_elsewhere.assert_called_once()
        self.assertFalse(c.settings["sync_backup"])
        self.assertFalse(c.settings["sync_rescue_ok"])


class OwnKeyChangeNotDeleted(unittest.TestCase):
    """T2 07.11.: „Remove device“ on PC 1 – a fetch still running asked the OLD address, got „deleted“/410 and PC 1
    switched itself off. An answer from before this device's own key change counts for nothing."""

    def ctl(self):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings = {"sync_backup": True, "sync_rescue_ok": True, "relay": {"seed": SEED}}
        c.sync_status = {"busy": False, "ok": None, "text": ""}
        c.sync_engine = mock.Mock()
        c.sync_engine.meta = {}
        c.sync_engine.on.return_value = True
        for n in ("_sync_changed", "settings_changed", "sync_setup", "sync_on", "sync_orbit_ok"):
            setattr(c, n, mock.Mock(return_value=True))
        return c

    def fetch_error(self, c, err):
        """sync_now -> the background fetch raises err -> what _sync_done gets."""
        from net import sync_ctl
        got = []
        c._sync_bg = lambda step, fn: got.append((step, fn))
        sync_ctl.SyncControl.sync_now(c)
        (step, fn), = got
        c.sync_engine.fetch.side_effect = err
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            return step, e
        self.fail("no error")

    def done(self, c, step, err):
        from net import sync_ctl
        with mock.patch.object(sync_ctl, "tr", lambda s: s):
            sync_ctl.SyncControl._sync_done(c, step, None, err)

    def test_old_address_answer_after_the_own_key_change_is_ignored(self):
        from net import sync_ctl
        from net.vault import VaultError
        for err in (syncrun.VaultDeleted(1793600000), VaultError(410, "gone", {"gone": True})):
            with self.subTest(err=type(err).__name__):
                c = self.ctl()
                step, e = self.fetch_error(c, err)
                with mock.patch.object(syncrun, "available", lambda: True), \
                        mock.patch("net.rekey.change"), mock.patch("net.rekey.finish"), \
                        mock.patch("threading.Thread"):
                    c._sync_bg = mock.Mock()
                    sync_ctl.SyncControl.sync_rekey(c, "remove")   # „Remove device“ starts while the fetch runs
                self.done(c, step, e)
                c.sync_engine.deleted_elsewhere.assert_not_called()
                c.sync_engine.switch_off.assert_not_called()
                self.assertTrue(c.settings["sync_backup"])
                self.assertNotIn("removed", c.settings["relay"])
                self.assertFalse(c.sync_status["busy"])

    def test_no_sync_while_the_key_changes(self):
        from net import sync_ctl
        c = self.ctl()
        c.sync_status["rekey"] = "busy"
        c._sync_bg = mock.Mock()
        sync_ctl.SyncControl.sync_now(c)
        c._sync_bg.assert_not_called()

    def test_without_a_key_change_deleted_and_removed_still_count(self):
        from net.vault import VaultError
        c = self.ctl()
        self.done(c, *self.fetch_error(c, syncrun.VaultDeleted(1793600000)))
        c.sync_engine.deleted_elsewhere.assert_called_once()
        self.assertFalse(c.settings["sync_backup"])
        c = self.ctl()   # this device removed elsewhere: its identity changed inside the fetch – still a removal
        self.done(c, *self.fetch_error(c, VaultError(410, "gone", {"gone": True})))
        c.sync_engine.switch_off.assert_called_once()
        self.assertIn("removed", c.settings["relay"])


class FiveMonthWarning(unittest.TestCase):
    """legal/lead 07.11.: 150 days after this device's last vault access it warns (the server deletes after 183) –
    locally, without the network, also while the sync pauses outside Full Orbit."""

    VEC = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs" / "web" / "vault-expiry.json")
                     .read_text("utf-8"))

    def ctl(self, full, meta, removed=False):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings = {"relay": dict({"on": full, "seed": SEED}, **({"removed": {"by": "x"}} if removed else {}))}
        c.sync_status = {"ok": None, "text": "", "when": None, "busy": False}
        c.sync_engine = mock.Mock()
        c.sync_engine.on.return_value = True
        c.sync_engine.meta = meta
        c._sync_bg, c._sync_changed = mock.Mock(), mock.Mock()
        c._sync_t, c._sync_edit_t = mock.Mock(), mock.Mock()
        return c

    def run_setup(self, c):
        from net import sync_ctl
        with mock.patch.object(syncrun, "available", lambda: True), \
                mock.patch.object(sync_ctl.QtCore.QTimer, "singleShot"):
            sync_ctl.SyncControl.sync_setup(c)

    def test_the_shared_rule(self):
        self.assertEqual((syncrun.EXPIRY_WARN_DAYS, syncrun.VAULT_TTL_DAYS),
                         (self.VEC["warn_days"], self.VEC["ttl_days"]))

    def test_paused_five_months_warns_without_network(self):
        import time as _t
        seen = int(_t.time() * 1000) - 151 * syncrun.DAY_MS
        c = self.ctl(full=False, meta={"seeded": True, "vault_seen": seen})
        self.run_setup(c)
        self.assertEqual(c.sync_status["expiry"], {"seen": seen, "until": seen + 183 * syncrun.DAY_MS})
        c._sync_bg.assert_not_called()
        c._sync_t.start.assert_not_called()

    def test_fresh_removed_or_deleted_no_warning(self):
        import time as _t
        now = int(_t.time() * 1000)
        for meta, removed in (({"seeded": True, "vault_seen": now - 10 * syncrun.DAY_MS}, False),
                              ({"seeded": True, "vault_seen": now - 160 * syncrun.DAY_MS}, True),
                              ({"seeded": True, "vault_seen": now - 160 * syncrun.DAY_MS, "deleted_off": True}, False),
                              ({"vault_seen": now - 160 * syncrun.DAY_MS}, False)):
            c = self.ctl(full=True, meta=meta, removed=removed)
            self.run_setup(c)
            self.assertNotIn("expiry", c.sync_status, (meta, removed))

    def test_a_vault_access_clears_it(self):
        self.assertIsNone(syncrun.expiry({"seeded": True, "vault_seen": 1000 * syncrun.DAY_MS},
                                         1000 * syncrun.DAY_MS + 5))
