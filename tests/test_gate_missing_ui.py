"""The test server's access code missing (T2 07.11.2026: Test-PC 2 after a restart never reached the server, yet said
„Coupled ✓“ and offered „Create a new protection code“; performance' sync_status["gate"] / ["reached"]): the line with a
password field right on the page (no dialog), the code kept nowhere; no „Coupled ✓“, no „just synced“, no new-code key
while it is unknown whether a code exists. „Coupled ✓“ also needs another device in the list. Stand-in ctrl.

    python -m unittest tests/test_gate_missing_ui.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from system import orbit
from tests.test_backup_ui import UI, texts
from tests.test_guard_request_ui import ctrl, flat
from ui import backupui, joinui, qsync

GATE = "The test server needs its access code."


class Eng:
    def __init__(self, others=1):
        self.meta = {}
        self._devs = [{"dev": "a", "me": True}] + [{"dev": f"o{i}", "me": False} for i in range(others)]

    def on(self):
        return True

    def devices(self):
        return list(self._devs)


def gate_ctrl(**status):
    sent = []
    c = types.SimpleNamespace(sync_status={"gate": "missing", **status}, settings={}, sync_engine=Eng())
    c.sync_gate = lambda code: sent.append(code)
    return c, sent


class GateItemsTest(unittest.TestCase):
    def test_nothing_without_the_flag(self):
        c, _ = gate_ctrl()
        c.sync_status.pop("gate")
        self.assertEqual(qsync.gate_items(UI(), c, {}, lambda: None), [])

    def test_field_secret_empty_read_once(self):
        c, sent = gate_ctrl()
        forgot, mem = [], {}
        form = types.SimpleNamespace(forget=forgot.append)
        items = qsync.gate_items(UI(), c, mem, lambda: None, form)
        self.assertIn(GATE, texts(items))
        edit = [n for n in flat(items) if n[0] == "edit"][0]
        self.assertEqual(edit[1][0], "")
        self.assertTrue(edit[2]["secret"])
        edit[2]["live"]("abc123")
        [n for n in flat(items) if n[0] == "button"][0][1][1]()
        self.assertEqual(sent, ["abc123"])
        self.assertNotIn("code", mem)
        self.assertEqual(forgot, ["gate_code"])

    def test_empty_field_sends_nothing(self):
        c, sent = gate_ctrl()
        items = qsync.gate_items(UI(), c, {}, lambda: None)
        [n for n in flat(items) if n[0] == "button"][0][1][1]()
        self.assertEqual(sent, [])

    def test_wrong_code_line_after_sending(self):
        c, _ = gate_ctrl(text="Access code wrong.")
        self.assertNotIn("Access code wrong.", texts(qsync.gate_items(UI(), c, {}, lambda: None)))
        self.assertIn("Access code wrong.", texts(qsync.gate_items(UI(), c, {"sent": True}, lambda: None)))


class CoupledTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(joinui, "_removed", return_value=False)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_coupled_needs_server_and_another_device(self):
        c, _ = gate_ctrl()
        self.assertFalse(joinui.really_coupled(c))
        c.sync_status.pop("gate")
        self.assertTrue(joinui.really_coupled(c))
        c.sync_engine = Eng(others=0)
        self.assertFalse(joinui.really_coupled(c))


class BackupPageTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def page(self, c):
        c.sync_gate = lambda code: None
        return texts(backupui.settings_items(UI(), c, types.SimpleNamespace(form=None), lambda: None))

    def test_gate_line_and_no_new_code_key(self):
        c = ctrl()[0]
        c.guard_on = lambda: False
        c.sync_status.update(gate="missing")
        t = self.page(c)
        self.assertIn(GATE, t)
        self.assertNotIn(backupui.ADD_SET_UP, t)

    def test_never_reached_no_new_code_key(self):
        c = ctrl()[0]
        c.guard_on = lambda: False
        c.sync_status.update(reached=False)
        self.assertNotIn(backupui.ADD_SET_UP, self.page(c))
        c.sync_status.update(reached=True)
        t = self.page(c)
        self.assertIn(backupui.ADD_SET_UP, t)
        self.assertNotIn(GATE, t)


if __name__ == "__main__":
    unittest.main()


class RunsOnTest(unittest.TestCase):
    """lead 07.11.: a missing access code never takes a coupled device out – after typing the code it simply runs on
    (PLAN-EINFACH: no switch any more, no „Sync now“)."""

    def test_line_then_runs_on(self):
        from tests import test_device_switch as ds
        b, calls = ds.setup("leave")
        sent = []
        b.ctrl.sync_gate = sent.append
        b.ctrl.sync_status["gate"] = "missing"
        p = ds.page(b)
        self.assertIn(GATE, texts(p))
        edit = [n for n in ds.find(p, "edit") if n[2].get("key") == "gate_code"][0]
        edit[2]["live"]("abc123")
        ds.press(p, "Enter access code")
        self.assertEqual(sent, ["abc123"])
        b.ctrl.sync_status.pop("gate")   # the code accepted (performance' _gate_state)
        self.assertNotIn(GATE, texts(ds.page(b)))
        self.assertEqual(calls, [])   # nothing was signed out
