"""PLAN-EINFACH D (lead/Oliver 07.11.2026): another device's protection-code request – Settings at the top and „Backup“
pulse orange until its frame was seen (remembered per request); choice rows carry the dot like the top bar. Stand-in ctrl.

    python -m unittest tests/test_einfach_pulse.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from tests.test_backup_ui import UI
from ui import backupui


def ctrl(until=1_800_000_000, mine=False):
    badges = []
    c = types.SimpleNamespace(settings={}, sync_status={})
    c.guard_request_info = lambda: {"since": until - 600, "until": until}
    if mine:
        c.settings["sync_guard_mine"] = {"until": until}
    c.settings_changed = lambda: None
    c.autobackup_badge = lambda: badges.append(backupui.request_unseen(c))
    return c, badges


class PulseTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_pulses_until_answered_not_until_seen(self):
        # lead 11.11. (Oliver's test round): opening the page no longer stops it – only the answer does
        c, badges = ctrl()
        self.assertTrue(backupui.request_unseen(c))
        backupui.request_seen(c)
        self.assertTrue(backupui.request_unseen(c))
        c.guard_request_info = lambda: None   # declined or in effect: quiet
        self.assertFalse(backupui.request_unseen(c))

    def test_own_request_never_pulses(self):
        c, _ = ctrl(mine=True)
        self.assertFalse(backupui.request_unseen(c))

    def test_no_request_no_pulse(self):
        c, _ = ctrl()
        c.guard_request_info = lambda: None
        self.assertFalse(backupui.request_unseen(c))


class ChoiceDotTest(unittest.TestCase):
    def test_seg_buttons_carry_the_dot(self):
        from ui import qform
        ui = qform.UI(types.SimpleNamespace(_cb={}, _keys={}))
        node = ui.seg([("a", "A"), ("b", "B")], "a", lambda v: None)
        buttons = [n for n in node["items"] if n.get("t") == "button"]
        self.assertTrue(all(b.get("led") for b in buttons))
        self.assertEqual([b["active"] for b in buttons], [True, False])
