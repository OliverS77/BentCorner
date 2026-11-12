"""Code fields keep nothing (ports' T3 check, lead 07.11.2026): „Restore with protection code“ and the own code –
password echo, never pre-filled, emptied when sent (success or failure): page memory and form drafts gone, the code
only in the one call. In memory, stand-in ctrl.

    python -m unittest tests/test_codefields.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from system import orbit
from tests.test_backup_ui import UI, ctrl, texts
from tests.test_guard_request_ui import flat, press
from ui import backupui


class CodeFieldsTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)
        self.forgot = []
        self.form = types.SimpleNamespace(forget=self.forgot.append)

    def tearDown(self):
        self.p.stop()

    def test_restore_field_secret_and_emptied(self):
        sent = []
        c = ctrl("full")
        c.sync_rescue_restore = sent.append
        c.sync_rescue_confirm = lambda *a, **k: None
        c.vault_delete = lambda guard=None: None
        b = types.SimpleNamespace(form=self.form)
        page = backupui.settings_items(UI(), c, b, lambda: None)
        edit = [n for n in flat(page) if n[0] == "edit" and n[2].get("key") == "restore_code"][0]
        self.assertTrue(edit[2].get("secret"))
        self.assertEqual(edit[1][0], "")
        edit[2]["live"]("TEST-CODE")
        press(backupui.settings_items(UI(), c, b, lambda: None), backupui.RESTORE)
        self.assertEqual(sent, ["TEST-CODE"])
        self.assertNotIn("restore_code", b.backup_ui)                    # not in the page memory
        self.assertIn("restore_code", self.forgot)                       # nor in the form's draft
        c.sync_status = {"rescue": "wrong"}                              # failed: the field is empty again
        page = backupui.settings_items(UI(), c, b, lambda: None)
        edit = [n for n in flat(page) if n[0] == "edit" and n[2].get("key") == "restore_code"][0]
        self.assertEqual(edit[1][0], "")
        self.assertIn(backupui.WRONG, texts(page))

    def test_own_code_emptied_when_sent_and_on_failure(self):
        calls = []
        c = ctrl("full")
        c.sync_rescue_confirm = lambda *a, **k: None
        c.vault_delete = lambda guard=None: None
        c.sync_backup_set = lambda v: None
        c.guard_set = lambda code, own=False, old=None: calls.append(code)
        c.guard_strength = lambda t: {"score": 3, "ok": True}
        st = {"mode": "own", "a": "x" * 30, "b": "x" * 30}
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None, form=self.form)
        self.assertTrue(all(e[2].get("secret") for e in flat(page) if e[0] == "edit"))
        press(page, backupui.tr(backupui.CODE_NEXT_OWN))
        self.assertEqual(calls, ["x" * 30])
        # U2 (lead 11.11.): both fields stay filled while the code is checked – RAM only, never a draft
        self.assertEqual((st.get("a"), st.get("b")), ("x" * 30, "x" * 30))
        self.assertEqual(self.forgot, [])
        c.sync_status = {"guard": "error"}
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None, form=self.form)
        self.assertTrue(all(e[1][0] == "x" * 30 for e in flat(page) if e[0] == "edit"))   # still there: try again
        self.assertNotIn(backupui.AGAIN, texts(page))
        press(page, backupui.tr(backupui.CODE_NEXT_OWN))   # Next works again after an answer
        self.assertEqual(calls, ["x" * 30] * 2)
        c.sync_status = {"guard": "ok"}                     # set: the fields and drafts go
        backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None, form=self.form)
        self.assertNotIn("a", st)
        self.assertEqual(sorted(self.forgot), ["own_a", "own_b"])


if __name__ == "__main__":
    unittest.main()
