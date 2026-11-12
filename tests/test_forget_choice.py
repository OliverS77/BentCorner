"""Settings → "Delete Bent°Corner" in 0.9.7 (lead/legal 07.11., A7 – behind the sync switch): two equal keys instead of the
checkboxes, nothing preselected; legal's sentences under the chosen one (the last-device line always with "only this
device"); with a protection code the A4 field (performance' need_code); offline with a code: nothing deleted, "needs a
connection"; offline without: here now, legal's line about the kept key. net.forget / wipe faked, nothing real.

    python -m unittest tests/test_forget_choice.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from net import forget
from system import wipe
from ui import backupui, qforget
from tests.test_device_switch import UI, find
from tests.test_forget_ui import sync


def texts(p, kind):
    kinds = ("label", "note") if kind == "label" else (kind,)   # notes are labels too (gray)
    return [x[1][0] for k in kinds for x in find(p, k)]


def press(p, label):
    next(x for x in find(p, "button") if x[1][0] == label)[1][1]()


class ChoiceTest(unittest.TestCase):
    def setUp(self):
        self.plan = wipe.Plan(folder="C:/Test/BentCorner", delete=["C:/Test/BentCorner/data"])
        self.results = []
        self.sent = []

        def delete_server(settings, full=None, guard_code=None):
            self.sent.append(guard_code)
            return self.results.pop(0)
        for x in (mock.patch.object(syncrun, "available", return_value=True),
                  mock.patch.object(forget, "has_id", lambda s: True),
                  mock.patch.object(forget, "available", lambda s: True),
                  mock.patch.object(forget, "pending", lambda: None),
                  mock.patch.object(forget, "remember_pending", lambda s: True),
                  mock.patch.object(forget, "delete_server", delete_server),
                  mock.patch.object(wipe, "plan", lambda s: self.plan)):
            x.start()
            self.addCleanup(x.stop)
        self.guarded = False
        ctrl = types.SimpleNamespace(settings={}, import_page=types.SimpleNamespace(bk_msg="", make_backup=lambda: None),
                                     show_import=lambda k: None, guard_on=lambda: self.guarded)
        ctrl._forget = qforget.Forget({}, run=sync, changed=lambda: None, quit_after=lambda p: None)
        self.b = types.SimpleNamespace(ctrl=ctrl, form=types.SimpleNamespace(soon=lambda: None, forget=lambda k: None))
        self.st = ctrl._forget

    def page(self):
        return qforget.page(UI(), self.b)

    def test_two_equal_keys_nothing_preselected(self):
        p = self.page()
        keys = [x for x in find(p, "button") if x[1][0] in (qforget.ONLY_HERE, qforget.ALL_ONLINE)]
        self.assertEqual(len(keys), 2)
        self.assertFalse(any(k[2].get("active") or k[2].get("primary") for k in keys))
        go = next(x for x in find(p, "button") if x[1][0] == qforget.BUTTON)
        self.assertFalse(go[2]["enabled"])                               # nothing chosen: nothing to delete
        self.assertIn(qforget.LOST_DEVICE, texts(p, "label"))
        self.assertEqual(find(p, "check"), [])                           # the 03.11. checkboxes are gone

    def test_only_here_says_the_last_device_line_and_sends_nothing(self):
        press(self.page(), qforget.ONLY_HERE)
        p = self.page()
        self.assertIn(qforget.ONLY_HERE_WHY, texts(p, "label"))
        dims = {x[1][0]: x[2].get("dim") for x in find(p, "button") if x[1][0] in (qforget.ONLY_HERE, qforget.ALL_ONLINE)}
        self.assertEqual(dims, {qforget.ONLY_HERE: False, qforget.ALL_ONLINE: True})   # selection = brightness
        self.assertIn(qforget.LAST_DEVICE, texts(p, "label"))             # legal: always
        press(p, qforget.BUTTON)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.st.state, "local_done")

    def test_everything_with_a_code_asks_for_it(self):
        self.results = [forget.Result(forget.MAIN_REQUIRED, ""), forget.Result(forget.DELETED)]
        press(self.page(), qforget.ALL_ONLINE)
        p = self.page()
        self.assertIn(qforget.ALL_ONLINE_WHY, texts(p, "label"))
        press(p, qforget.BUTTON)
        p = self.page()
        self.assertIn(backupui.GUARD_NEED, texts(p, "label"))
        self.assertIn(backupui.LOST, texts(p, "label"))                  # „lost?“ under the field
        find(p, "edit")[0][1][1]("TEST-CODE")
        press(self.page(), qforget.BUTTON)
        self.assertEqual(self.sent, [None, "TEST-CODE"])
        self.assertEqual(self.st.state, "local_done")
        self.assertIsNone(self.st.guard_code)                            # never kept

    def test_wrong_code_and_wait(self):
        self.results = [forget.Result(forget.MAIN_REQUIRED, ""), forget.Result(forget.MAIN_REQUIRED, "4")]
        press(self.page(), qforget.ALL_ONLINE)
        press(self.page(), qforget.BUTTON)
        find(self.page(), "edit")[0][1][1]("TEST-CODE")
        press(self.page(), qforget.BUTTON)
        self.assertIn(backupui.GUARD_WAIT_SEC.format(n=4), texts(self.page(), "label"))
        self.st.result = forget.Result(forget.MAIN_REQUIRED, "")
        self.assertIn(backupui.GUARD_WRONG, texts(self.page(), "label"))

    def test_offline_with_a_code_deletes_nothing(self):
        self.guarded = True
        r = forget.Result(forget.FAILED, "offline")
        r.offline = True
        self.results = [r]
        press(self.page(), qforget.ALL_ONLINE)
        press(self.page(), qforget.BUTTON)
        self.assertEqual(self.st.state, "needs_net")
        p = self.page()
        self.assertIn(qforget.NEEDS_NET, texts(p, "label"))
        self.assertIsNone(self.st.plan)                                   # nothing planned for deleting here
        press(p, qforget.ONLY_HERE)                                       # the other choice is still open
        self.assertEqual(self.st.choice, "here")

    def test_offline_without_a_code_says_the_key_stays(self):
        r = forget.Result(forget.FAILED, "offline")
        r.offline = True
        self.results = [r]
        press(self.page(), qforget.ALL_ONLINE)
        press(self.page(), qforget.BUTTON)
        self.assertEqual(self.st.state, "local_done")
        self.assertIn(qforget.OFFLINE, texts(self.page(), "label"))
        self.assertIn("only keeps the key", qforget.OFFLINE)


if __name__ == "__main__":
    unittest.main()
