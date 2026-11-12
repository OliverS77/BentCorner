"""Profile → „Blocked“ (lead 08.11.): the block question and the file import promise „you can undo this in your profile“
– the box shows only while someone is blocked, one row per ID with [Unblock], the second click as a line, then
ctrl.relay_unblock (performance' logic: entry gone, server unblock). Stand-in ctrl, no network.

    python -m unittest tests/test_unblock_ui.py
"""
import types
import unittest

from tests.test_backup_ui import UI, texts
from tests.test_guard_request_ui import flat
from ui import qprofile

CODE = "a1b2c3d4e5f6a7b8"


def ctrl(blocked=True):
    done = []
    friends = {CODE: {"status": "blocked" if blocked else "ok", "name": "Max<b>"}, "ffffeeeeddddcccc": {"status": "ok"}}
    c = types.SimpleNamespace(settings={"relay": {"friends": friends}}, relay_unblock=done.append)
    return c, done


def press(items, label):
    [n for n in flat(items) if n[0] == "button" and n[1][0] == label][0][1][1]()


class UnblockTest(unittest.TestCase):
    def test_nothing_without_a_block(self):
        c, _ = ctrl(blocked=False)
        self.assertEqual(qprofile.blocked_items(UI(), c, {}, lambda: None), [])

    def test_row_asked_once_more_then_unblocked(self):
        c, done = ctrl()
        mem = {}
        items = qprofile.blocked_items(UI(), c, mem, lambda: None)
        t = " ".join(str(x) for x in texts(items))
        self.assertIn("Max&lt;b&gt;", t)                                   # the name as known, escaped
        press(items, "Unblock")
        self.assertEqual(done, [])                                         # the line first
        items = qprofile.blocked_items(UI(), c, mem, lambda: None)
        self.assertIn(qprofile.UNBLOCK_ASK, texts(items))
        press(items, "Back")
        self.assertEqual(done, [])
        press(qprofile.blocked_items(UI(), c, mem, lambda: None), "Unblock")
        press(qprofile.blocked_items(UI(), c, mem, lambda: None), "Yes")
        self.assertEqual(done, [CODE])

    def test_server_first_busy_and_failed(self):
        # lead 08.11.: the server first – busy while it runs, a failure changes nothing and says so
        c, done = ctrl()
        c.relay_unblock_state = {CODE: "busy"}
        t = texts(qprofile.blocked_items(UI(), c, {}, lambda: None))
        self.assertIn(qprofile.UNBLOCK_BUSY, t)
        self.assertNotIn("Unblock", t)
        c.relay_unblock_state = {CODE: "offline"}
        items = qprofile.blocked_items(UI(), c, {}, lambda: None)
        self.assertIn(qprofile.UNBLOCK_OFFLINE, texts(items))               # only a real connection error says so
        self.assertIn("Unblock", texts(items))                             # try again
        c.relay_unblock_state = {CODE: "failed"}
        t = texts(qprofile.blocked_items(UI(), c, {}, lambda: None))
        self.assertIn(qprofile.UNBLOCK_FAILED, t)
        self.assertNotIn(qprofile.UNBLOCK_OFFLINE, t)

    def test_mailbox_off_points_to_the_orbit(self):
        c, done = ctrl()
        opened = []
        c.stream = types.SimpleNamespace(show_page=lambda *a, **k: opened.append("settings"))
        c.show_settings = opened.append
        c.relay_unblock_state = {CODE: "mailbox_off"}
        items = qprofile.blocked_items(UI(), c, {}, lambda: None)
        self.assertIn(qprofile.UNBLOCK_ORBIT, texts(items))
        press(items, "Change Orbit settings")
        self.assertEqual(opened, ["settings", "privacy"])

    def test_german(self):
        from locales import de
        self.assertIn(qprofile.UNBLOCK_ASK, de.TEXTS)
        self.assertEqual(de.TEXTS["Blocked"], "Blockiert")


if __name__ == "__main__":
    unittest.main()
