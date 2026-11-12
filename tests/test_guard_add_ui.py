"""The protection code from the second device on (Oliver 08.11.2026, legal's „Neufassung 08.11.“): „Show a code“ without
a code → legal's A2 with [Set up protection code] [Cancel] → the setup (never „without code“) → the code at once; the
joining device types the code of the others (performance: join "need_guard" → sync_join_guard); „Without protection
code“ only while guard_optional (one device). Stand-in ctrls, no network.

    python -m unittest tests/test_guard_add_ui.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from tests.test_device_remove import setup
from tests.test_device_switch import find, page, press
from tests.test_join_ui import UI, joiner, texts
from ui import backupui, joinui, qsync


def labels(p):
    return [x[1][0] for x in find(p, "label")] + [x[1][0] for x in find(p, "note")]


def keys(p):
    return [x[1][0] for x in find(p, "button")]


class AddWithoutCodeTest(unittest.TestCase):
    def test_setup_first_then_the_code(self):
        b, _ = setup(guarded=False)
        shown = []
        b.ctrl.pair_show = lambda: shown.append(1)
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.pair = {}
        press(page(b), qsync.SHOW_CODE)
        self.assertEqual(shown, [])                                         # no code without a protection code
        p = page(b)
        self.assertIn(backupui.ADD_NEEDS_CODE, labels(p))
        self.assertIn("Cancel", keys(p))
        press(p, backupui.ADD_SET_UP)
        p = page(b)
        self.assertIn(backupui.OFFER_GEN, keys(p))
        self.assertIn(backupui.OFFER_OWN, keys(p))
        self.assertNotIn(backupui.OFFER_NONE, keys(p))                      # never „without code“ here
        self.assertNotIn(backupui.WITHOUT_LINE, labels(p))
        self.assertNotIn(backupui.CODE_BACK_NOTE, labels(p))                # the backup stays on
        mem = b.__dict__
        st = next(v["rescue"] for v in mem.values() if isinstance(v, dict) and "rescue" in v)
        st.update(mode="own", sent=True)                                    # own code typed and sent ...
        b.ctrl.sync_status["guard"] = "ok"
        page(b)                                                            # ... set: the code shows at once
        self.assertEqual(shown, [1])

    def test_cancel_back_to_the_keys(self):
        b, _ = setup(guarded=False)
        b.ctrl.sync_orbit_ok = lambda: True
        press(page(b), qsync.SHOW_CODE)
        press(page(b), "Cancel")
        p = page(b)
        self.assertNotIn(backupui.ADD_NEEDS_CODE, labels(p))
        self.assertIn(qsync.SHOW_CODE, keys(p))

    def test_with_a_code_as_before(self):
        b, _ = setup(guarded=True)
        shown = []
        b.ctrl.pair_show = lambda: shown.append(1)
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.pair = {}
        press(page(b), qsync.SHOW_CODE)
        self.assertEqual(shown, [1])

    def test_first_alone_says_so(self):
        c = types.SimpleNamespace(sync_status={"guard": "first_alone"}, guard_strength=lambda a: {"score": 4, "ok": True})
        st = {"second": True, "mode": "own", "sent": True}
        t = texts(backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None))
        self.assertIn(backupui.FIRST_ALONE, t)
        c.sync_status = {"rescue": "first_alone"}                          # the generated code (rescue_put)
        st = {"second": True, "mode": "gen", "code": "ABCDE-FGHIJ", "sent": True}
        t = texts(backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None))
        self.assertIn(backupui.FIRST_ALONE, t)
        self.assertNotIn(backupui.CODE_BUSY, t)


class EnterAfterSignOutTest(unittest.TestCase):
    def test_field_opens_after_signing_out(self):
        # performance' guide run 09.11. (step 8): signed out, then „Enter a code“ – the field must open, not close again
        with mock.patch.object(syncrun, "available", return_value=True):
            b, _ = setup(guarded=True)
            codes = []
            b.ctrl.sync_join_code = codes.append
            b.ctrl.sync_status["left"] = True
            press(page(b), qsync.ENTER_CODE)
            p = page(b)
            self.assertNotIn("left", b.ctrl.sync_status)
            self.assertIn(joinui.JOIN_HOW_CODE, labels(p))                  # the join part is open ...
            self.assertIn(joinui.JOIN_HOW_CODE, labels(page(b)))            # ... and stays open on the next redraw
            find(page(b), "edit")[0][1][1]("7f3a2-1c90b")
            self.assertEqual(codes, ["7F3A21C90B"])                         # the join goes out
            b.ctrl.sync_status["join"] = "ok"                               # joined: closed as before
            self.assertNotIn(joinui.JOIN_HOW, labels(page(b)))
            self.assertEqual(b.__dict__["devices_add"].get("mode"), None)


class WithoutOnlyAloneTest(unittest.TestCase):
    def offer(self, optional):
        c = types.SimpleNamespace(sync_status={}, guard_optional=lambda: optional)
        return texts(backupui.rescue_items(UI(), c, {}, lambda: None, lambda: None, lambda: None))

    def test_one_device(self):
        t = self.offer(True)
        self.assertIn(backupui.OFFER_NONE, t)
        self.assertIn(backupui.WITHOUT_LINE, t)
        self.assertIn("backup file", backupui.WITHOUT_LINE)                 # legal 08.11.

    def test_more_devices(self):
        t = self.offer(False)
        self.assertNotIn(backupui.OFFER_NONE, t)
        self.assertNotIn(backupui.WITHOUT_LINE, t)


class JoinCodeTest(unittest.TestCase):
    def test_need_guard_field_and_send(self):
        with mock.patch.object(syncrun, "available", return_value=True):
            b = joiner(sync_status={"join": "need_guard"})
            sent, dropped = [], []
            b.ctrl.sync_join_guard = sent.append
            b.ctrl.sync_join_drop = lambda: dropped.append(1)
            draw = lambda: joinui.join_items(UI(), b, lambda: None)   # noqa: E731
            t = texts(draw())
            self.assertIn(joinui.JOIN_CODE, t)
            self.assertIn(joinui.JOIN_CODE_CANCEL, t)
            self.assertNotIn(joinui.JOIN_CODE_REQ, t)                     # only while a request runs
            self.assertNotIn(joinui.JOIN_HOW, t)                          # the pairing code part is done
            edit = find(draw(), "edit")[0]
            edit[1][1]("my code")
            press(draw(), "Add device")
            self.assertEqual(sent, ["my code"])
            self.assertEqual(b.join_guard_code.get("code"), "my code")    # U2: stays in the field (RAM) while checked
            b.ctrl.sync_status["guard"] = "wrong"
            self.assertIn(backupui.GUARD_WRONG, texts(draw()))
            self.assertEqual(find(draw(), "edit")[0][1][0], "my code")    # after a wrong code: still there to fix
            b.ctrl.sync_status["join_request"] = True
            self.assertIn(joinui.JOIN_CODE_REQ, texts(draw()))
            press(draw(), "Cancel")
            self.assertEqual(dropped, [1])
            self.assertNotIn("code", getattr(b, "join_guard_code", {}))  # Cancel: gone

    def test_german(self):
        from locales import de
        for t in (joinui.JOIN_CODE, joinui.JOIN_CODE_REQ, joinui.JOIN_CODE_CANCEL, backupui.ADD_NEEDS_CODE,
                  backupui.ADD_SET_UP, backupui.WITHOUT_LINE, backupui.FIRST_ALONE):
            self.assertIn(t, de.TEXTS)
        self.assertTrue(de.TEXTS[backupui.ADD_NEEDS_CODE].startswith("Für ein weiteres Gerät"))


if __name__ == "__main__":
    unittest.main()
