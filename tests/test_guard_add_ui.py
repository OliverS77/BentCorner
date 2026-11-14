"""Adding devices WITHOUT a protection code (Oliver 13.11.2026, A2 of 08.11. taken back; legal 13.11. 1f/1g): „Show a
code“ shows the code at once; a quiet line under the list with [Set up protection code] while there are other devices
and no code; „Without protection code“ in the offer with several devices too; legal's bold line before the FIRST code
with more than one device (performance' guard_note_all); the joining device types a code only if the ID has one
(join "need_guard"), otherwise [Try again] after an error; „A protection code was set up on {device}.“ once on the
other devices (performance' guard_set_by / code_set_seen). Stand-in ctrls, no network.

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


def with_others(b, on=True):
    b.ctrl.sync_has_others = lambda: on
    b.ctrl.sync_orbit_ok = lambda: True
    return b


class AddWithoutCodeTest(unittest.TestCase):
    def test_show_code_at_once_without_a_code(self):
        b, _ = setup(guarded=False)
        shown = []
        b.ctrl.pair_show = lambda: shown.append(1)
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.pair = {}
        press(page(b), qsync.SHOW_CODE)
        self.assertEqual(shown, [1])                                        # no setup in between any more
        self.assertFalse(hasattr(backupui, "ADD_NEEDS_CODE"))

    def test_with_a_code_as_before(self):
        b, _ = setup(guarded=True)
        shown = []
        b.ctrl.pair_show = lambda: shown.append(1)
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.pair = {}
        press(page(b), qsync.SHOW_CODE)
        self.assertEqual(shown, [1])

    def test_hint_under_the_list_only_without_a_code_and_with_others(self):
        b, _ = setup(guarded=False)
        self.assertIn(backupui.NO_CODE_HINT, labels(page(with_others(b))))
        self.assertNotIn(backupui.NO_CODE_HINT, labels(page(with_others(b, False))))   # alone: nothing
        g, _ = setup(guarded=True)
        self.assertNotIn(backupui.NO_CODE_HINT, labels(page(with_others(g))))           # a code: nothing

    def test_hint_key_opens_the_offer_without_none(self):
        b, _ = setup(guarded=False)
        with_others(b)
        press(page(b), backupui.ADD_SET_UP)
        p = page(b)
        self.assertIn(backupui.OFFER_GEN, keys(p))
        self.assertIn(backupui.OFFER_OWN, keys(p))
        self.assertNotIn(backupui.OFFER_NONE, keys(p))                      # „set up“ – not „without“ here
        press(p, backupui.CODE_BACK)
        self.assertNotIn(backupui.OFFER_GEN, keys(page(b)))                 # back: the two keys again

    def test_first_alone_still_says_so(self):
        # the old box's answer stays as a fallback until Gordon's box patch (legal 1h: removed together with ports)
        c = types.SimpleNamespace(sync_status={"guard": "first_alone"}, guard_strength=lambda a: {"score": 4, "ok": True})
        st = {"second": True, "mode": "own", "sent": True}
        t = texts(backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None))
        self.assertIn(backupui.FIRST_ALONE, t)


class OfferTest(unittest.TestCase):
    def offer(self, note_all=False, **st):
        c = types.SimpleNamespace(sync_status={}, guard_note_all=lambda: note_all)
        return texts(backupui.rescue_items(UI(), c, dict(st), lambda: None, lambda: None, lambda: None))

    def test_without_with_several_devices_too(self):
        t = self.offer()
        self.assertIn(backupui.OFFER_NONE, t)
        self.assertIn(backupui.WITHOUT_LINE, t)

    def test_bold_line_before_the_first_code_with_others(self):
        self.assertIn(backupui.ALL_DEVICES, self.offer(note_all=True))
        self.assertNotIn(backupui.ALL_DEVICES, self.offer(note_all=False))

    def test_wording_legal(self):
        self.assertIn("only your backup file gets you back", backupui.NO_CODE_HINT)          # legal 1f, not „can't be opened“
        self.assertIn("from then on you need it on each of them", backupui.ALL_DEVICES)      # legal 1g


class JoinTest(unittest.TestCase):
    def test_need_guard_field_and_send(self):
        with mock.patch.object(syncrun, "available", return_value=True):
            b = joiner(sync_status={"join": "need_guard"})
            sent, dropped = [], []
            b.ctrl.sync_join_guard = sent.append
            b.ctrl.sync_join_drop = lambda: dropped.append(1)
            draw = lambda: joinui.join_items(UI(), b, lambda: None)   # noqa: E731
            t = texts(draw())
            self.assertIn(joinui.JOIN_CODE, t)
            self.assertNotIn(joinui.JOIN_HOW, t)
            find(draw(), "edit")[0][1][1]("my code")
            press(draw(), "Add device")
            self.assertEqual(sent, ["my code"])
            press(draw(), "Cancel")
            self.assertEqual(dropped, [1])

    def test_error_try_again(self):
        with mock.patch.object(syncrun, "available", return_value=True):
            b = joiner(sync_status={"join": "error", "text": "No connection"})
            tries = []
            b.ctrl._join_payload = {"seed": "x"}
            b.ctrl.sync_join_retry = lambda: tries.append(1)
            p = joinui.join_items(UI(), b, lambda: None)
            self.assertIn("No connection", texts(p))
            press(p, "Try again")
            self.assertEqual(tries, [1])
            b.ctrl._join_payload = None                                     # nothing arrived: no [Try again]
            self.assertNotIn("Try again", keys(joinui.join_items(UI(), b, lambda: None)))


class CodeSetNoticeTest(unittest.TestCase):
    """lead 13.11.: the second device sees it exactly once (also not after a restart), the setter never, no line on a
    change (performance sends nothing then), a later device nothing (likewise)."""

    def dev(self):
        b, _ = setup(guarded=True)
        seen = []

        def code_set_seen(key):   # like performance: noted, the state cleared
            seen.append(key)
            b.ctrl.sync_status.pop("guard_set_by", None)
        b.ctrl.code_set_seen = code_set_seen
        return b, seen

    def line(self, b):
        return [t for t in labels(page(b)) if "protection code was set up" in t]

    def test_once_then_gone_after_a_restart(self):
        b, seen = self.dev()
        b.ctrl.sync_status["guard_set_by"] = {"name": "Küchen-PC", "n": 2, "key": 1763030000}
        self.assertTrue(qsync.code_set_unseen(b.ctrl))                     # Settings + „Your devices“ pulse
        self.assertEqual(self.line(b), ["A protection code was set up on Küchen-PC."])
        qsync.code_set_seen(b.ctrl, b)                                     # what qsettings does after drawing
        self.assertEqual(seen, [1763030000])
        self.assertFalse(qsync.code_set_unseen(b.ctrl))                    # the pulse stops
        self.assertEqual(len(self.line(b)), 1)                             # still there on this page visit
        qsync.code_set_seen(b.ctrl, b)
        self.assertEqual(seen, [1763030000])                               # noted once only
        restarted, _ = self.dev()                                          # a restart: new memory, no state
        self.assertEqual(self.line(restarted), [])

    def test_name_missing_device_n(self):
        b, _ = self.dev()
        b.ctrl.sync_status["guard_set_by"] = {"name": "", "n": 3, "key": 1}
        self.assertEqual(self.line(b), ["A protection code was set up on Device 3."])

    def test_setter_change_and_later_device_see_nothing(self):
        b, seen = self.dev()                                               # no guard_set_by from performance
        self.assertEqual(self.line(b), [])
        self.assertFalse(qsync.code_set_unseen(b.ctrl))
        qsync.code_set_seen(b.ctrl, b)
        self.assertEqual(seen, [])


class NoCodeHintTest(unittest.TestCase):
    """Oliver 13.11. via Gordon, legal 13.11.: backup on, no code → ONCE a line under the switch, [Set up] [Later];
    „Later“ really hides it, no badge, no nagging."""

    def ctrl(self, guarded=False, **settings):
        return types.SimpleNamespace(settings=dict(settings), sync_status={}, guard_on=lambda: guarded,
                                     settings_changed=lambda: None)

    def draw(self, c, st, on=True):
        return backupui.nocode_hint_items(UI(), c, st, lambda: None, on)

    def test_shown_only_with_backup_on_and_no_code(self):
        self.assertIn(backupui.NOCODE_HINT, texts(self.draw(self.ctrl(), {})))
        self.assertEqual(self.draw(self.ctrl(), {}, on=False), [])
        self.assertEqual(self.draw(self.ctrl(guarded=True), {}), [])
        c = self.ctrl()
        c.sync_status["reached"] = False                                    # the server's answer unknown: never
        self.assertEqual(self.draw(c, {}), [])

    def test_later_hides_it_for_good(self):
        c, st = self.ctrl(), {}
        press(self.draw(c, st), "Later")
        self.assertEqual(c.settings["sync_nocode_hint"], 1)
        self.assertEqual(self.draw(c, st), [])                              # also after a restart (settings)
        self.assertNotIn("rescue", st)

    def test_set_up_opens_the_offer_without_none_and_counts(self):
        c, st = self.ctrl(), {}
        press(self.draw(c, st), backupui.ADD_SET_UP)
        self.assertEqual(st["rescue"], {"second": True})
        self.assertEqual(c.settings["sync_nocode_hint"], 1)
        self.assertNotIn(backupui.OFFER_NONE, texts(backupui.rescue_items(UI(), c, st["rescue"], lambda: None,
                                                                          lambda: None, lambda: None)))

    def test_drawing_alone_does_not_count_and_no_pulse(self):
        c = self.ctrl()
        self.draw(c, {})
        self.assertNotIn("sync_nocode_hint", c.settings)
        self.assertFalse(backupui.request_unseen(types.SimpleNamespace(sync_status={})))   # no badge from it

    def test_wording_legal(self):
        self.assertIn("up to 183 days after the last sync", backupui.NOCODE_HINT)


class GermanTest(unittest.TestCase):
    def test_german(self):
        from locales import de
        for t in (joinui.JOIN_CODE, backupui.ADD_SET_UP, backupui.WITHOUT_LINE, backupui.FIRST_ALONE,
                  backupui.NO_CODE_HINT, backupui.ALL_DEVICES, qsync.CODE_SET, backupui.NOCODE_HINT, "Later"):
            self.assertIn(t, de.TEXTS)
        self.assertTrue(de.TEXTS[backupui.NO_CODE_HINT].startswith("Ohne Schutz-Code kann jedes deiner Geräte"))
        self.assertEqual(de.TEXTS[qsync.CODE_SET], "Auf {device} wurde ein Schutz-Code eingerichtet.")

    def test_highlight_097_legal_1e(self):
        import version
        from locales import de
        src = open(version.__file__, encoding="utf-8").read()
        self.assertIn("New: the protection code. It's optional.", src)
        self.assertNotIn("From your second device on", src)
        key = next(k for k in de.TEXTS if k.startswith("New: the protection code. It's optional."))
        self.assertTrue(de.TEXTS[key].startswith("Neu: der Schutz-Code. Er ist freiwillig."))


if __name__ == "__main__":
    unittest.main()
