"""„Code verloren?“ on the PC (legal A4/A5 07.11.2026, lead T3; performance' guard_request_prepare / _confirm): the new
code shown once, the last 5 typed, only then sent; the date only from the server, with the time; the code only in the
page's memory – gone when the request is sent, on Back and on leaving the section/page. The others see legal's big line
with [Decline (with protection code)]. In memory, stand-in ctrl.

    python -m unittest tests/test_guard_request_ui.py
"""
import time
import types
import unittest
from unittest import mock

from collection import syncrun
from system import i18n, orbit
from tests.test_backup_ui import UI, texts
from ui import backupui


def flat(node, out=None):
    out = [] if out is None else out
    if isinstance(node, tuple):
        if node:
            out.append(node)
        for x in node:
            flat(x, out)
    elif isinstance(node, list):
        for x in node:
            flat(x, out)
    return out


def press(page, label):
    btn = [n for n in flat(page) if n[0] == "button" and n[1][0] == label][0]
    btn[1][1]()


def ctrl(info=None, mine=None):
    sent, declined, listeners = [], [], []
    code = backupui.new_code()   # freshly made – never an example (lead)
    c = types.SimpleNamespace(settings={"orbit": "near", "relay": {"on": True}, "sync_backup": True, "sync_asked": 1},
                              sync_status={}, settings_changed=lambda: None, guard_on=lambda: True,
                              settings_listeners=listeners)
    if mine:
        c.settings["sync_guard_mine"] = mine
    c.guard_request_prepare = lambda: code
    c.guard_request_info = lambda: info
    c.show_settings = lambda key: [fn(key) for fn in list(listeners)]

    def confirm(cd, l5):
        if l5 != backupui.last5(cd):
            return False
        sent.append(cd)
        c.sync_status["guard"] = "busy"
        return True
    c.guard_request_confirm = confirm
    c.guard_decline = lambda cd: (declined.append(cd), c.sync_status.update(guard="busy"))
    c.sync_rescue_confirm = lambda *a, **k: None
    c.vault_delete = lambda guard=None: None
    return c, code, sent, declined


class RequestPageTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def page(self, c, b, trouble=True):
        # „Code verloren?“ sits folded under „Probleme mit dem Code?“ (PLAN-EINFACH D) – opened here
        b.__dict__.setdefault("backup_ui", {}).setdefault("folds", {})["trouble"] = trouble
        return backupui.settings_items(UI(), c, b, lambda: None)

    def test_lost_folded_until_opened(self):
        c = ctrl()[0]
        b = types.SimpleNamespace(form=None)
        t = texts(self.page(c, b, trouble=False))
        self.assertIn(backupui.GUARD_SET, t)
        self.assertNotIn(backupui.LOST, t)
        self.assertIn(backupui.CODE_TROUBLE + " ›", t)
        press(self.page(c, b, trouble=False), backupui.CODE_TROUBLE + " ›")
        self.assertIn(backupui.LOST, texts(backupui.settings_items(UI(), c, b, lambda: None)))

    def test_lost_line_then_the_request_in_two_steps(self):
        c, code, sent, _ = ctrl()
        b = types.SimpleNamespace(form=types.SimpleNamespace(forget=lambda k: None))
        p = self.page(c, b)
        self.assertIn(backupui.LOST, texts(p))
        press(p, backupui.LOST_KEY)
        p = self.page(c, b)
        self.assertIn(backupui.REQ_WHY, texts(p))
        self.assertIn(backupui.blocks(code), " ".join(t for t in texts(p) if isinstance(t, str)))
        edit = [n for n in flat(p) if n[0] == "edit"][0]
        self.assertTrue(edit[2].get("nopaste"))                       # typed proves it was written down
        go = [n for n in flat(p) if n[0] == "button" and n[1][0] == backupui.REQ_SEND][0]
        self.assertFalse(go[2]["enabled"])
        edit[1][1](backupui.last5(code))
        self.assertEqual(sent, [])                                    # typing sends nothing
        press(self.page(c, b), backupui.REQ_SEND)
        self.assertEqual(sent, [code])
        self.assertIn(backupui.REQ_BUSY, texts(self.page(c, b)))
        # the server's answer: the page closes, the code is gone; the own line with the server's date
        until = int(time.mktime((2026, 11, 8, 14, 5, 0, 0, 0, -1)))
        c.sync_status.update(guard="ok", request_until=until)
        c.settings["sync_guard_mine"] = {"until": until}
        c.guard_request_info = lambda: {"since": until - 600, "until": until}
        p = self.page(c, b)
        self.assertNotIn("req", b.backup_ui)
        self.assertNotIn(backupui.blocks(code), " ".join(t for t in texts(p) if isinstance(t, str)))
        with mock.patch.object(i18n, "LANG", "de"):
            self.assertEqual(backupui.fmt_when(until), "8.11., 14:05")
        self.assertIn(backupui.REQ_MINE.format(date=backupui.fmt_when(until)), texts(p))

    def test_back_and_leaving_drop_the_code(self):
        c, code, sent, _ = ctrl()
        b = types.SimpleNamespace(form=types.SimpleNamespace(forget=lambda k: None))
        press(self.page(c, b), backupui.LOST_KEY)
        self.page(c, b)
        self.assertEqual(b.backup_ui["req"]["code"], code)
        c.show_settings("devices")                                    # another section: gone
        self.assertNotIn("req", b.backup_ui)
        press(self.page(c, b), backupui.LOST_KEY)
        self.page(c, b)
        press(self.page(c, b), backupui.CODE_BACK)                    # Back: gone, nothing sent
        self.assertNotIn("req", b.backup_ui)
        self.assertEqual(sent, [])

    def test_lost_under_the_a4_field(self):
        c, _, _, _ = ctrl()
        c.sync_status = {"delete_guard": "need", "busy": False}
        b = types.SimpleNamespace(form=types.SimpleNamespace(forget=lambda k: None))
        p = self.page(c, b)
        self.assertIn(backupui.GUARD_NEED, texts(p))
        press(p, backupui.LOST_KEY)
        self.assertNotIn("delete_guard", c.sync_status)
        self.assertIn(backupui.REQ_WHY, texts(self.page(c, b)))

    def test_others_see_the_big_line_and_decline_with_the_code(self):
        until = int(time.time()) + 600
        c, _, _, declined = ctrl(info={"since": until - 600, "until": until})
        b = types.SimpleNamespace(form=types.SimpleNamespace(forget=lambda k: None))
        p = self.page(c, b)
        self.assertIn(backupui.REQ_OTHER.format(date=backupui.fmt_when(until)), texts(p))
        self.assertIn("remove the unknown device with ✕", backupui.REQ_OTHER)   # legal: decline AND remove (B5: the ✕)
        self.assertNotIn(backupui.LOST, texts(p))
        press(p, backupui.REQ_DECLINE)
        p = self.page(c, b)
        edit = [n for n in flat(p) if n[0] == "edit"][0]
        self.assertTrue(edit[2].get("secret"))
        edit[1][1]("TEST-CODE")
        self.assertEqual(declined, [])
        press(self.page(c, b), backupui.REQ_DECLINE)
        self.assertEqual(declined, ["TEST-CODE"])
        c.sync_status.update(guard="wrong")
        self.assertIn(backupui.GUARD_WRONG, texts(self.page(c, b)))
        c.sync_status.update(guard="ok")
        self.assertNotIn(backupui.REQ_OTHER.format(date=backupui.fmt_when(until)), texts(self.page(c, b)))

    def test_own_request_no_decline(self):
        until = int(time.time()) + 600
        c, _, _, _ = ctrl(info={"since": until - 600, "until": until}, mine={"until": until})
        p = self.page(c, types.SimpleNamespace(form=types.SimpleNamespace(forget=lambda k: None)))
        self.assertIn(backupui.REQ_MINE.format(date=backupui.fmt_when(until)), texts(p))
        self.assertNotIn(backupui.REQ_DECLINE, texts(p))

    def test_no_14_days_reckoned(self):
        import inspect
        src = inspect.getsource(backupui)
        self.assertNotRegex(src, r"14\s*\*\s*(24|86400)|1209600")


class FrameDotRestoreTest(unittest.TestCase):
    """lead 07.11.: the other devices' notice in its own frame, a dot on „Your devices“, restoring only when not syncing."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def test_notice_in_its_own_frame_and_the_dot(self):
        until = int(time.time()) + 600
        c, _, _, _ = ctrl(info={"since": until - 600, "until": until})
        self.assertTrue(backupui.foreign_request(c))
        p = backupui.settings_items(UI(), c, types.SimpleNamespace(form=None), lambda: None)
        groups = [n for n in p if n[0] == "group"]
        self.assertEqual(groups[0][1], backupui.NOTICE_TITLE)          # first, its own frame
        self.assertIn(backupui.REQ_OTHER.format(date=backupui.fmt_when(until)), texts(groups[0]))
        self.assertNotIn(backupui.REQ_OTHER.format(date=backupui.fmt_when(until)), texts(groups[1]))
        c.settings["sync_guard_mine"] = {"until": until}                # my own: no dot, no frame
        self.assertFalse(backupui.foreign_request(c))
        c.guard_request_info = lambda: None
        self.assertFalse(backupui.foreign_request(c))

    def test_restore_only_when_not_syncing(self):
        c, _, _, _ = ctrl()
        c.sync_engine = types.SimpleNamespace(on=lambda: True)
        b = types.SimpleNamespace(form=None)
        self.assertNotIn(backupui.RESTORE, texts(backupui.settings_items(UI(), c, b, lambda: None)))
        c.sync_engine = types.SimpleNamespace(on=lambda: False)
        b.backup_ui = {"folds": {"restore": True}}   # set up already: folded (lead 07.11.) – opened here
        self.assertIn(backupui.RESTORE, texts(backupui.settings_items(UI(), c, b, lambda: None)))


if __name__ == "__main__":
    unittest.main()
