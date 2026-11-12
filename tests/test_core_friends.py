"""Friends and trade tickets only in Full Orbit, no friends by file (Oliver 06.11., B; legal's conditions): the gate per
level, the flag that keeps the file path switched off, the Import/Export tiles per level, and legal's (2): whoever
turns on Full Orbit sends friends imported by file NOTHING – only friends switched on by hand get what is shared.
Only in-memory settings, never the real ones.

    python -m unittest tests/test_core_friends.py
"""
import types
import unittest

from net import relay
from system import orbit

A, B = "A" * 16, "B" * 16


def settings(level, friends=()):
    st = {"on": level == "full", "friends": {c: {"name": c[0], "status": "ok", "sign_pk": "PK", "pid": "p-" + c[0]}
                                             for c in friends}}
    return {"orbit": "near" if level == "full" else level, "relay": st,
            "profile": {"id": "p-me", "name": "Ich", "back": None}}


class GateTest(unittest.TestCase):
    def tearDown(self):
        orbit.bind(None)

    def test_only_full_orbit(self):
        for lv, shown in (("core", False), ("near", False), ("full", True)):
            orbit.bind(settings(lv))
            self.assertEqual(orbit.friends_shown(), shown, lv)

    def test_unbound_shows(self):
        orbit.bind(None)
        self.assertTrue(orbit.friends_shown())

    def test_file_friends_off(self):
        """Switched off, not removed – it can come back (Oliver 06.11.)."""
        self.assertFalse(orbit.FILE_FRIENDS)


class TilesTest(unittest.TestCase):
    def tearDown(self):
        orbit.bind(None)

    def keys(self, level):
        from ui import importview
        orbit.bind(settings(level))
        return {t[0]: t for _, tabs in importview.groups() for t in tabs}

    def test_core_and_near_no_id_no_ticket_image(self):
        for lv in ("core", "near"):
            k = self.keys(lv)
            self.assertNotIn("friend_code", k, lv)
            self.assertNotIn("offer", k, lv)
            self.assertNotIn("friend", k, lv)
            self.assertEqual(k["friend_export"][2], "Exportieren", lv)   # CSV/text export stays

    def test_full_id_and_ticket_image_but_no_file_friend(self):
        k = self.keys("full")
        self.assertIn("friend_code", k)
        self.assertIn("offer", k)
        self.assertNotIn("friend", k)
        self.assertEqual(k["friend_export"][2], "Exportieren")


class DefaultOffTest(unittest.TestCase):
    """legal (2): turning on Full Orbit shares with nobody by itself – friends from files have no mailbox address at
    all, and mailbox friends only get what is shared once switched on one by one."""

    def test_file_friends_only_nobody_gets_anything(self):
        s = settings("full")   # Full Orbit, but the only friends came by file (they live in trade.friends(), not here)
        self.assertEqual(relay.share_codes(s), [])

    def test_new_mailbox_friend_starts_off(self):
        s = settings("full", friends=(A, B))
        self.assertEqual(relay.share_codes(s), [])
        relay.set_share(s, A, True)
        self.assertEqual(relay.share_codes(s), [A])


class AskFirstTest(unittest.TestCase):
    """legal (to „Was ist neu?“ 0.9.7): whoever is in Core or Near Orbit at the update and turns on Full Orbit later is
    asked FIRST – until then nothing goes out, and the old "Yes" to "Share library?" doesn't count."""

    def before(self, level):
        s = settings(level, friends=(A, B))
        s["relay"]["posted"] = {"mtg/lists": {"t": 1, "until": 2, "to": [A, B]}}   # had shared before
        s["share_library"] = True   # the old question's "Yes"
        return s

    def contents(self, s):
        from unittest import mock
        from collection import trade
        from net import relay_ctl
        fake = types.SimpleNamespace(settings=s)
        with mock.patch.object(trade, "lists", return_value=[]), mock.patch("ui.qbinder.shared_binders", return_value=[]):
            return relay_ctl.RelayControl.relay_share_contents(fake)

    def test_core_at_update_nothing_goes_out_in_full_until_answered(self):
        for lv in ("core", "near"):
            s = self.before(lv)
            self.assertTrue(orbit.hold_sharing(s), lv)
            s["relay"]["on"] = True   # later: Full Orbit
            self.assertEqual(relay.share_codes(s), [], lv)            # no friend switched on
            self.assertFalse(self.contents(s)["library"], lv)         # the old "Yes" rests
            self.assertTrue(s.get("shared_ask_on_full"), lv)          # "Shared with friends" opens first
            self.assertFalse(orbit.hold_sharing(s), lv)               # only once

    def test_full_at_update_keeps_todays_friends(self):
        s = self.before("full")
        self.assertFalse(orbit.hold_sharing(s))
        self.assertEqual(sorted(relay.share_codes(s)), [A, B])   # relay's own migration: nothing changes for them
        self.assertTrue(self.contents(s)["library"])

    def test_answer_share_again_or_not(self):
        from ui import qshared
        for keep in (True, False):
            s = self.before("core")
            orbit.hold_sharing(s)
            s["relay"]["on"] = True
            sent = []
            ctrl = types.SimpleNamespace(settings=s, settings_changed=lambda: None,
                                         relay_send_lists=lambda quiet=False: sent.append(1),
                                         relay_share_library_off=lambda: sent.append(0))
            host = types.SimpleNamespace(ctrl=ctrl)
            b = qshared.SharedBackend.__new__(qshared.SharedBackend)
            b.host, b.ctrl = host, ctrl
            b.changed = types.SimpleNamespace(emit=lambda: None)
            qshared.SharedBackend.answer(b, keep)
            self.assertEqual(sent, [1] if keep else [0])   # shared again (to friends switched on) – or withdrawn
            self.assertNotIn("share_library_paused", s)
            self.assertEqual(s["share_library"], keep)
            self.assertEqual(self.contents(s)["library"], keep)


if __name__ == "__main__":
    unittest.main()
