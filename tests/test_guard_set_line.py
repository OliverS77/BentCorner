"""„Ein Schutz-Code ist gesetzt.“ (lead 07.11.2026, T2/T3: after A2 nothing said that a code exists): a fixed status line
in the group Online backup above „Lost your code?“ – only with the backup on and a code set. Stand-in ctrl.

    python -m unittest tests/test_guard_set_line.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from system import orbit
from tests.test_backup_ui import UI, texts
from tests.test_guard_request_ui import ctrl
from ui import backupui


class GuardSetLineTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def page(self, c):
        b = types.SimpleNamespace(form=None, backup_ui={"folds": {"trouble": True}})   # „Probleme mit dem Code?“ open
        return texts(backupui.settings_items(UI(), c, b, lambda: None))

    def test_line_above_lost(self):
        c = ctrl()[0]
        t = self.page(c)
        self.assertIn(backupui.GUARD_SET, t)
        self.assertLess(t.index(backupui.GUARD_SET), t.index(backupui.LOST))

    def test_also_while_a_request_runs(self):
        c = ctrl(info={"until": 1, "id": "x"}, mine=True)[0]
        self.assertIn(backupui.GUARD_SET, self.page(c))

    def test_not_without_a_code(self):
        c = ctrl()[0]
        c.guard_on = lambda: False
        t = self.page(c)
        self.assertNotIn(backupui.GUARD_SET, t)
        self.assertIn(backupui.ADD_SET_UP, t)

    def test_not_while_deleting_is_asked(self):
        c = ctrl()[0]
        c.sync_status["delete_guard"] = "need"
        self.assertNotIn(backupui.GUARD_SET, self.page(c))

    def test_german(self):
        from locales import de
        self.assertEqual(de.TEXTS[backupui.GUARD_SET], "Ein Schutz-Code ist gesetzt.")


if __name__ == "__main__":
    unittest.main()


class RequestNeverFoldedTest(unittest.TestCase):
    """legal 07.11. (desk-backup2): a running request (code lost; later joining) always stands open – never folded under
    „Probleme mit dem Code?“, also while that fold is closed."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def page(self, c):
        b = types.SimpleNamespace(form=None, backup_ui={"folds": {"trouble": False}})   # the fold closed
        return backupui.settings_items(UI(), c, b, lambda: None)

    def test_mine_open(self):
        until = 1_800_000_000
        c = ctrl(info={"since": until - 600, "until": until}, mine=True)[0]
        c.settings["sync_guard_mine"] = {"until": until}
        t = texts(self.page(c))
        self.assertIn(backupui.REQ_MINE.format(date=backupui.fmt_when(until)), t)
        self.assertNotIn(backupui.CODE_TROUBLE + " ›", t)

    def test_other_device_open_in_its_frame(self):
        until = 1_800_000_000
        c = ctrl(info={"since": until - 600, "until": until})[0]
        t = texts(self.page(c))
        self.assertIn(backupui.REQ_OTHER.format(date=backupui.fmt_when(until)), t)
        self.assertNotIn(backupui.CODE_TROUBLE + " ›", t)


class ChangeCodeTest(unittest.TestCase):
    """PLAN-EINFACH D (lead 07.11.): „Change protection code“ under „Problems with the code?“ – the current code first,
    then the usual way; it goes into the call once, a wrong one brings its field back."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def test_change_with_the_current_code(self):
        from tests.test_guard_request_ui import flat
        c = ctrl()[0]
        calls = []
        c.sync_rescue_confirm = lambda code, last5, old=None: calls.append((last5, old))
        forgot = []
        b = types.SimpleNamespace(form=types.SimpleNamespace(forget=forgot.append), backup_ui={"folds": {"trouble": True}})
        page = lambda: backupui.settings_items(UI(), c, b, lambda: None)   # noqa: E731

        def press(label):
            [n for n in flat(page()) if n[0] == "button" and n[1][0] == label][0][1][1]()
        press(backupui.CHANGE_CODE)
        p = page()
        self.assertIn(backupui.CHANGE_OLD, texts(p))
        [n for n in flat(p) if n[0] == "edit"][0][2]["live"]("OLD-TEST")
        press(backupui.CODE_NEXT_OWN)
        self.assertIn("change_old", forgot)                                  # the draft dropped at once
        t = texts(page())
        self.assertNotIn(backupui.OFFER_NONE, t)                             # changing: no „without code“
        press(backupui.OFFER_GEN)
        page()                                                               # the code is made when its page shows
        code = b.backup_ui["rescue"]["code"]
        [n for n in flat(page()) if n[0] == "edit"][0][1][1](backupui.last5(code))
        press(backupui.CODE_NEXT)
        self.assertEqual(calls, [(backupui.last5(code), "OLD-TEST")])
        c.sync_status["rescue"] = "need_old"                                 # the server: not the current code
        page()
        self.assertEqual(b.backup_ui["rescue"].get("change"), "old")
        self.assertNotIn("old", b.backup_ui["rescue"])
        self.assertIn(backupui.GUARD_WRONG, texts(page()))

    def test_line_after_a_change_only(self):
        # legal 07.11.: after a change the old code is void – one line; not after a first code
        from tests.test_guard_request_ui import flat
        c = ctrl()[0]
        c.sync_rescue_confirm = lambda code, last5, old=None: c.sync_status.update(rescue="ok")
        b = types.SimpleNamespace(form=types.SimpleNamespace(forget=lambda k: None), backup_ui={"folds": {"trouble": True}})
        page = lambda: backupui.settings_items(UI(), c, b, lambda: None)   # noqa: E731

        def press(label):
            [n for n in flat(page()) if n[0] == "button" and n[1][0] == label][0][1][1]()
        press(backupui.CHANGE_CODE)
        [n for n in flat(page()) if n[0] == "edit"][0][2]["live"]("OLD-TEST")
        press(backupui.CODE_NEXT_OWN)
        press(backupui.OFFER_GEN)
        page()
        code = b.backup_ui["rescue"]["code"]
        [n for n in flat(page()) if n[0] == "edit"][0][1][1](backupui.last5(code))
        press(backupui.CODE_NEXT)
        page()                                                               # ok: the page closes
        self.assertIn(backupui.CODE_CHANGED, texts(page()))
        b.backup_ui.pop("code_changed")
        self.assertNotIn(backupui.CODE_CHANGED, texts(page()))

