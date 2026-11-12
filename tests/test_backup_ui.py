"""The online backup's faces (ui/backupui.py, lead/legal 06.11.2026) – behind ONE switch: with the sync not built in
(collection/syncrun.available() False) the setup has no switch and 8 steps, „What's new?“ no card, Settings → Backup no
block, and nothing calls the network. With the sync built in: the switch only in Full Orbit, the rescue code page asks
for the last 5 characters, the card only for existing users not asked yet. Only in-memory settings.

    python -m unittest tests/test_backup_ui.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from system import orbit
from ui import backupui


class UI:
    """Just enough of the form builder: every widget is a tuple (kind, …) – what a page shows can be read back."""
    def __getattr__(self, kind):
        return lambda *a, **k: (kind, a, k)

    def col(self, items, **k):
        return ("col", [i for i in items if i], k)

    def row(self, items, **k):
        return ("row", [i for i in items if i], k)

    def group(self, title, items, **k):
        return ("group", title, [i for i in items if i])


def ctrl(level="full", **s):
    st = {"orbit": "near" if level == "full" else level, "relay": {"on": level == "full"}, **s}
    c = types.SimpleNamespace(settings=st, sync_status={}, settings_changed=lambda: None,
                              guard_optional=lambda: True)   # one device (performance: the registry)
    return c


def texts(node):
    """Every string inside a built page (labels, buttons …)."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, (list, tuple)):
        return [t for n in node for t in texts(n)]
    if isinstance(node, dict):
        return [t for n in node.values() for t in texts(n)]
    return []


class SwitchOffTest(unittest.TestCase):
    """lead 06.11.: switch off = everything as before, no network call."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=False)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def test_nothing_shows(self):
        c = ctrl("full")
        self.assertFalse(backupui.built())
        self.assertIsNone(backupui.setup_sync({}, "full", lambda: None))
        self.assertEqual(backupui.news_items(UI(), c, None, lambda: None), [])
        self.assertEqual(backupui.settings_items(UI(), c, types.SimpleNamespace(), lambda: None), [])
        self.assertFalse(backupui.card_due(c))
        self.assertFalse(backupui.available(c))

    def test_setup_has_8_steps(self):
        from ui import onboarding
        ob = onboarding.Onboarding.__new__(onboarding.Onboarding)
        ob.st, ob.s = {"orbit": "full", "backup": True}, {}
        self.assertFalse(ob._with_rescue())


class SwitchOnTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()
        orbit.bind(None)

    def tearDown(self):
        self.p.stop()

    def test_switch_only_in_full_orbit(self):
        on = backupui.setup_sync({}, "full", lambda: None)
        self.assertTrue(on["on"] and on["enabled"])
        near = backupui.setup_sync({}, "near", lambda: None)
        self.assertFalse(near["on"] or near["enabled"])

    def test_new_code_only_without_a_protection_code(self):
        # performance 07.11.: with a code set a new one needs the old one (need_old) – the key waits for A4
        c = ctrl("full", sync_backup=True, sync_asked=1)
        c.guard_on = lambda: False
        page = backupui.settings_items(UI(), c, types.SimpleNamespace(), lambda: None)
        self.assertIn(backupui.NEW_CODE, texts(page))
        c.guard_on = lambda: True
        page = backupui.settings_items(UI(), c, types.SimpleNamespace(), lambda: None)
        self.assertNotIn(backupui.NEW_CODE, texts(page))

    def test_delete_asks_for_the_protection_code(self):
        # legal A4 / performance' delete_guard: the field instead of an error line, only the key sends, nothing stays
        sent = []
        c = ctrl("full", sync_backup=True, sync_asked=1)
        c.guard_on = lambda: True
        c.vault_delete = lambda guard=None: sent.append(guard)
        c.sync_rescue_confirm = lambda *a, **k: None
        c.sync_status = {"delete_guard": "need", "busy": False}
        forgot = []
        b = types.SimpleNamespace(form=types.SimpleNamespace(forget=forgot.append))
        page = backupui.settings_items(UI(), c, b, lambda: None)
        self.assertIn(backupui.GUARD_NEED, texts(page))
        self.assertNotIn(backupui.DELETE_FAILED, texts(page))
        flat = []

        def walk(n):
            if isinstance(n, tuple):
                if n:
                    flat.append(n)
                for x in n:
                    walk(x)
            elif isinstance(n, list):
                for x in n:
                    walk(x)
        walk(page)
        edit = [n for n in flat if n[0] == "edit"][0]
        self.assertTrue(edit[2].get("secret"))
        self.assertEqual(edit[1][0], "")   # never pre-filled
        edit[1][1]("TEST-CODE")            # Enter / focus loss: only kept, nothing sent
        self.assertEqual(sent, [])
        page = backupui.settings_items(UI(), c, b, lambda: None)
        flat.clear()
        walk(page)
        go = [n for n in flat if n[0] == "button" and n[1][0] == backupui.DELETE][0]
        self.assertTrue(go[2].get("enabled"))
        go[1][1]()
        self.assertEqual(sent, ["TEST-CODE"])
        # U2 (lead 11.11.): the code stays in its field (RAM only) while it is checked and after a wrong answer
        self.assertEqual(b.__dict__["backup_ui"]["guard"].get("code"), "TEST-CODE")
        self.assertEqual(forgot, [])
        c.sync_status = {"delete_guard": "wait", "guard_wait": 90, "busy": False}
        self.assertIn(backupui.GUARD_WAIT.format(n=2), texts(backupui.settings_items(UI(), c, b, lambda: None)))
        c.sync_status = {"delete_guard": "wait", "guard_wait": 4, "busy": False}   # legal: under a minute in seconds
        self.assertIn(backupui.GUARD_WAIT_SEC.format(n=4), texts(backupui.settings_items(UI(), c, b, lambda: None)))
        c.sync_status = {"delete_guard": "need", "busy": False}   # asked afresh (the last try is over): empty again
        backupui.settings_items(UI(), c, b, lambda: None)
        self.assertNotIn("code", b.__dict__["backup_ui"]["guard"])
        self.assertEqual(forgot, [backupui.GUARD_KEY])

    def test_card_only_for_existing_users_not_asked(self):
        self.assertTrue(backupui.card_due(ctrl("full")))
        self.assertFalse(backupui.card_due(ctrl("full", sync_asked=1)))
        self.assertFalse(backupui.card_due(ctrl("near")))
        self.assertFalse(backupui.card_due(ctrl("full", sync_backup=True)))

    def test_rescue_page_needs_the_last_five(self):
        sent = []
        c = ctrl("full", sync_rescue_confirm=None)
        c.sync_rescue_confirm = lambda code, l5: sent.append((code, l5))
        c.vault_delete = lambda: None
        code = backupui.new_code()   # a freshly generated one – never an example (lead 07.11.)
        st = {"mode": "gen", "code": code}
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None)
        nxt = [n for n in page if n[0] == "row" and any(b[1][0] == backupui.tr(backupui.CODE_NEXT) for b in n[1] if b[0] == "button")]
        self.assertTrue(nxt)
        self.assertEqual(len(backupui.last5(code)), 5)
        edit = [n for n in page if n[0] == "edit"][0]
        self.assertTrue(edit[2].get("nopaste"))   # typing proves it was written down

    def test_offer_three_equal_keys_generated_first(self):
        c = ctrl("full")
        c.sync_rescue_confirm = lambda code, l5: None
        c.vault_delete = lambda: None
        page = backupui.rescue_items(UI(), c, {}, lambda: None, lambda: None, lambda: None)
        keys = [b for n in page if n[0] == "row" for b in n[1] if b[0] == "button"]
        labels = [b[1][0] for b in keys]
        three = [backupui.tr(backupui.OFFER_GEN), backupui.tr(backupui.OFFER_OWN), backupui.tr(backupui.OFFER_NONE)]
        self.assertEqual(labels[:3], three)
        self.assertFalse(any(b[2].get("primary") or b[2].get("active") for b in keys[:3]))   # equal – none preselected
        texts_ = " ".join(n[1][0] for n in page if n[0] in ("note", "label") and isinstance(n[1][0], str))
        self.assertIn(backupui.tr(backupui.WITHOUT_LINE), texts_)

    def test_without_code_turns_the_backup_on(self):
        on, done = [], []
        c = ctrl("full")
        c.sync_rescue_confirm = lambda code, l5: None
        c.vault_delete = lambda: None
        c.sync_backup_set = lambda v: on.append(v)
        st = {}
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: done.append(1))
        [b for n in page if n[0] == "row" for b in n[1] if b[0] == "button" and b[1][0] == backupui.tr(backupui.OFFER_NONE)][0][1][1]()
        self.assertEqual(on, [True])
        backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: done.append(1))
        self.assertEqual(done, [1])

    def test_own_code_strength_paste_and_match(self):
        calls = []
        c = ctrl("full")
        c.sync_rescue_confirm = lambda code, l5: None
        c.vault_delete = lambda: None
        c.sync_backup_set = lambda v: calls.append(("backup", v))
        c.guard_set = lambda code, own=False, old=None: calls.append(("guard", own))
        weak = {"score": 1, "ok": False, "bits": 40}
        strong = {"score": 3, "ok": True, "bits": 90}
        c.guard_strength = lambda text: strong if text == "x" * 30 else weak   # no real code anywhere (lead)
        st = {"mode": "own", "a": "short", "b": "short"}
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None)
        edits = [n for n in page if n[0] == "edit"]
        self.assertEqual(len(edits), 2)
        self.assertFalse(any(e[2].get("nopaste") for e in edits))   # password managers may paste (lead)
        self.assertTrue(all(e[2].get("placeholder", "") == "" for e in edits))   # no example as placeholder
        nxt = [b for n in page if n[0] == "row" for b in n[1] if b[0] == "button" and b[1][0] == backupui.tr(backupui.CODE_NEXT_OWN)][0]
        self.assertFalse(nxt[2]["enabled"])   # too weak: Next off, legal's line
        self.assertTrue(any(n[0] == "label" and n[1][0] == backupui.tr(backupui.WEAK) for n in page))
        st.update(a="x" * 30, b="y" * 30)
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None)
        self.assertTrue(any(n[0] == "label" and n[1][0] == backupui.tr(backupui.OWN_DIFF) for n in page))
        st.update(b="x" * 30)
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None)
        nxt = [b for n in page if n[0] == "row" for b in n[1] if b[0] == "button" and b[1][0] == backupui.tr(backupui.CODE_NEXT_OWN)][0]
        self.assertTrue(nxt[2]["enabled"])
        nxt[1][1]()
        self.assertEqual(calls, [("backup", True), ("guard", True)])

    def test_back_on_the_offer_uploads_nothing(self):
        sent, back = [], []
        c = ctrl("full")
        c.sync_rescue_confirm = lambda code, l5: sent.append(1)
        c.vault_delete = lambda: None
        st = {}
        page = backupui.rescue_items(UI(), c, st, lambda: None, lambda: back.append(1), lambda: None)
        btn = [b for n in page if n[0] == "row" for b in n[1] if b[0] == "button" and b[1][0] == backupui.tr(backupui.CODE_BACK)][0]
        btn[1][1]()
        self.assertEqual(sent, [])
        self.assertEqual(back, [1])
        self.assertEqual(st, {})


class WaitLineTest(unittest.TestCase):
    def test_seconds_under_a_minute_then_minutes(self):   # lead 07.11.: the boundary
        self.assertEqual(backupui.wait_line(59), backupui.GUARD_WAIT_SEC.format(n=59))
        self.assertEqual(backupui.wait_line(60), backupui.GUARD_WAIT.format(n=1))
        self.assertEqual(backupui.wait_line(61), backupui.GUARD_WAIT.format(n=2))
        self.assertEqual(backupui.wait_line(0), backupui.GUARD_WAIT_SEC.format(n=1))


if __name__ == "__main__":
    unittest.main()
