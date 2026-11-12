"""„Another device with your ID“ on Your devices (legal 08.11. via performance, lead go): its own frame at the top;
without a protection code only [Create new ID] (asked once more as a line); with one [Take over with protection code]
runs the B5 removal (A8 question, A4 field) and „Or create a new ID“. Stand-in ctrl (performance' sync_status
["foreign_device"], identity_new, sync_remove_plan / sync_remove).

    python -m unittest tests/test_foreign_device_ui.py
"""
import unittest

from tests.test_device_remove import setup, texts
from tests.test_device_switch import find, page, press
from ui import backupui, qsync


def foreign(guarded=False):
    b, calls = setup(guarded=guarded)
    b.ctrl.sync_status["foreign_device"] = {"dev": None, "since": 1}
    news, takes = [], []

    def identity_new():   # local, at once (performance)
        news.append(1)
        b.ctrl.sync_status.pop("foreign_device", None)
        b.ctrl.sync_status["identity_new"] = "ok"
    b.ctrl.identity_new = identity_new
    b.ctrl.sync_add_with_code = lambda code: (takes.append(code), b.ctrl.sync_status.update(add_code="busy"))
    return b, takes, news


class ForeignTest(unittest.TestCase):
    def test_nothing_without_the_flag(self):
        b, _ = setup()
        self.assertNotIn(qsync.FOREIGN_HEAD, texts(page(b), "label"))

    def test_only_the_frame_while_it_applies(self):
        # lead 08.11.: not signed in yet – no device list, no „Add a device“, no sign-out; back after a new ID
        b, takes, news = foreign()
        p = page(b)
        self.assertEqual([g[1] for g in find(p, "group")], ["Your ID"])
        self.assertNotIn(qsync.SIGN_OUT, texts(p, "button"))
        self.assertNotIn(qsync.SHOW_CODE, texts(p, "button"))
        press(p, qsync.NEW_ID)
        press(page(b), "Yes")
        groups = [g[1] for g in find(page(b), "group")]
        self.assertIn(qsync.LIST_TITLE, groups)
        self.assertIn(qsync.ADD_TITLE, groups)

    def test_without_code_new_id_asked_once_more(self):
        b, takes, news = foreign()
        p = page(b)
        self.assertEqual(find(p, "group")[0][1], "Your ID")                    # its own frame, at the top
        self.assertIn(qsync.FOREIGN_NOCODE, texts(p, "note"))
        self.assertNotIn(qsync.TAKE_OVER, texts(p, "button"))
        press(p, qsync.NEW_ID)
        self.assertEqual(news, [])                                             # the line first
        p = page(b)
        self.assertIn(qsync.NEW_ID_ASK, texts(p, "label"))
        press(p, "Back")
        self.assertEqual(news, [])
        press(page(b), qsync.NEW_ID)
        press(page(b), "Yes")
        self.assertEqual(news, [1])
        self.assertNotIn(qsync.FOREIGN_HEAD, texts(page(b), "label"))         # gone at once

    def test_with_code_add(self):
        # lead 09.11.: the code only adds this device – no removal promised; the head line without „allow it there“
        b, takes, news = foreign(guarded=True)
        p = page(b)
        self.assertIn(qsync.FOREIGN_HEAD_CODE, texts(p, "label"))
        self.assertNotIn(qsync.FOREIGN_HEAD, texts(p, "label"))
        self.assertIn(qsync.FOREIGN_CODE, texts(p, "note"))
        self.assertNotIn("removed", qsync.FOREIGN_CODE + qsync.TAKE_DONE)
        self.assertIn(qsync.FOREIGN_OR_NEW, texts(p, "label"))
        press(p, qsync.TAKE_OVER)
        p = page(b)
        self.assertIn(backupui.GUARD_NEED, texts(p, "label"))                  # the A4 field
        find(p, "edit")[0][1][1]("TEST-CODE")
        press(page(b), qsync.TAKE_OVER)
        self.assertEqual(takes, ["TEST-CODE"])
        self.assertEqual(b.__dict__["devices_take_code"].get("code"), "TEST-CODE")   # U2: in RAM while checked
        self.assertIn(qsync.TAKE_BUSY, texts(page(b), "label"))
        b.ctrl.sync_status["add_code"] = "wrong"
        self.assertIn(backupui.GUARD_WRONG, texts(page(b), "label"))
        b.ctrl.sync_status.update(add_code="wait", guard_wait=30)              # the pause: its line, field still usable
        p = page(b)
        self.assertIn(backupui.wait_line(30), texts(p, "label"))
        find(p, "edit")[0][1][1]("RIGHT-CODE")
        press(page(b), qsync.TAKE_OVER)
        self.assertEqual(takes, ["TEST-CODE", "RIGHT-CODE"])                    # the right code goes through
        b.ctrl.sync_status.update(add_code="ok")
        b.ctrl.sync_status.pop("foreign_device")
        self.assertIn(qsync.TAKE_DONE, texts(page(b), "label"))
        self.assertEqual(news, [])


if __name__ == "__main__":
    unittest.main()
