"""Coupling with data on both devices + the state set aside (ui/joinui.py, lead 07.11.2026, legal's wording in
docs/KOPPEL-TEXTE.md) – behind the sync switch: off = nothing shows. On: three equal keys (none primary – nothing on
Enter), a Cancel of its own, each key calls sync_join_answer with its kind; „Set aside“ asks once before bringing
back or deleting. In memory only, against a stand-in ctrl (performance's names).

    python -m unittest tests/test_join_ui.py
"""
import types
import unittest
from unittest import mock

from collection import syncrun
from ui import joinui


class UI:
    """Every widget is a tuple (kind, args, kwargs) – what the page shows can be read back; buttons keep their fn."""
    def __getattr__(self, kind):
        return lambda *a, **k: (kind, a, k)

    def row(self, items, **k):
        return ("row", [i for i in items if i], k)


def texts(node):
    if isinstance(node, str):
        return [node]
    if isinstance(node, (list, tuple)):
        return [t for n in node for t in texts(n)]
    if isinstance(node, dict):
        return [t for n in node.values() for t in texts(n)]
    return []


def buttons(items):
    out = []
    for it in items:
        if it[0] == "button":
            out.append(it)
        elif it[0] == "row":
            out += buttons(it[1])
    return out


def press(items, text):
    b = next(b for b in buttons(items) if b[1][0] == text)
    b[1][1]()


def ctrl(**kw):
    c = types.SimpleNamespace(sync_status={}, answers=[], done=[])
    c.sync_join_choice = {"other": "phone", "here": {"decks": 2, "cards": 120}, "there": {"lists": 1}}
    c.sync_join_answer = lambda k: c.answers.append(k)
    c.aside_list = lambda: [{"id": "2026-11-07", "when": 1794000000, "what": {"decks": 1}, "why": "theirs"}]
    c.aside_restore = lambda i: c.done.append(("back", i))
    c.aside_delete = lambda i: c.done.append(("drop", i))
    c.aside_open = lambda i: c.done.append(("open", i))
    c.aside_seen = lambda i: c.done.append(("seen", i))
    c.__dict__.update(kw)
    return c


class SwitchOffTest(unittest.TestCase):
    def test_nothing_shows(self):
        with mock.patch.object(syncrun, "available", return_value=False):
            c = ctrl()
            b = types.SimpleNamespace(ctrl=c)
            c.sync_status["aside"] = "2026-11-07"
            self.assertEqual(joinui.choice_items(UI(), c, lambda: None), [])
            self.assertEqual(joinui.aside_items(UI(), b, lambda: None), [])
            self.assertEqual(joinui.notice_items(UI(), b, lambda: None), [])


class SwitchOnTest(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_no_choice_no_rows(self):
        self.assertEqual(joinui.choice_items(UI(), ctrl(sync_join_choice=None), lambda: None), [])

    def test_three_equal_keys_and_cancel(self):
        c = ctrl()
        items = joinui.choice_items(UI(), c, lambda: None)
        keys = buttons(items)
        self.assertEqual([k[1][0] for k in keys],
                         ["Merge", "Keep the other device's state", "Keep this device's state", "Cancel"])
        self.assertFalse(any(k[2].get("primary") or k[2].get("active") for k in keys))   # none chosen, none on Enter
        for text in ("Merge", "Keep the other device's state", "Keep this device's state", "Cancel"):
            press(items, text)
        self.assertEqual(c.answers, ["merge", "theirs", "mine", ""])
        t = " ".join(texts(items))
        self.assertIn("<b>This device</b>", texts(items))              # the table: names as heads, one row per kind
        for cell in ("<b>Other device</b>", "Cards", "120", "Decks", "2", "Lists", "1", "–"):
            self.assertIn(cell, texts(items))
        self.assertIn("Anything set aside stays on that device only", t)

    def test_second_step_as_a_line(self):
        # PLAN-EINFACH B: side by side, four keys in one row, then „Do it this way? [Yes] [Back]“ – nothing before Yes
        c, mem = ctrl(), {}
        items = joinui.choice_items(UI(), c, lambda: None, mem)
        self.assertEqual([k[1][0] for k in buttons(items)],
                         ["Merge", "Keep the other device's state", "Keep this device's state", "Cancel"])
        press(items, "Keep the other device's state")
        self.assertEqual(c.answers, [])
        items = joinui.choice_items(UI(), c, lambda: None, mem)
        self.assertIn(joinui.CONFIRM, texts(items))
        press(items, "Back")
        self.assertEqual(c.answers, [])
        press(joinui.choice_items(UI(), c, lambda: None, mem), "Merge")
        press(joinui.choice_items(UI(), c, lambda: None, mem), "Yes")
        self.assertEqual(c.answers, ["merge"])
        press(joinui.choice_items(UI(), c, lambda: None, mem), "Cancel")   # Cancel never asks
        self.assertEqual(c.answers, ["merge", ""])

    def test_joining_device_by_its_number(self):
        # performance 07.11. guide run: the joining device isn't in the list yet – „Device 2 (this one)“ from join_n,
        # never „Device 1“ twice; without a number „This device“
        c = ctrl(sync_join_choice={"other": "pc", "other_n": 1, "here": {"cards": 3}, "there": {"cards": 5}},
                 sync_devices=lambda: [], settings={})
        c.sync_status["join_n"] = 2
        t = texts(joinui.choice_items(UI(), c, lambda: None))
        self.assertIn("<b>PC 2 (this one)</b>", t)                 # B (lead 12.11.): „<type> <n>“, never „Device n“
        self.assertIn("Keep the state of PC 2", t)
        self.assertIn("Keep the state of PC 1", t)
        c.sync_status["join_n"] = 0
        t = texts(joinui.choice_items(UI(), c, lambda: None))
        self.assertIn("<b>This device</b>", t)
        self.assertIn("Keep this device's state", t)

    def test_busy_and_again(self):
        c = ctrl(sync_status={"join": "busy"})
        items = joinui.choice_items(UI(), c, lambda: None)
        self.assertTrue(all(k[2]["enabled"] is False for k in buttons(items)))
        c.sync_status["join"] = "again"
        self.assertIn("Another device chose first – please choose again.", texts(joinui.choice_items(UI(), c, lambda: None)))

    def test_names_not_kinds(self):
        # Gordon/lead 07.11.: always the device's name (two PCs are possible); the tip „only part of it?“ is gone
        c = ctrl(sync_join_choice={"other": "pc", "other_n": 2, "here": {}, "there": {}})
        items = joinui.choice_items(UI(), c, lambda: None)
        self.assertIn("<b>PC 2</b>", texts(items))                  # B (lead 12.11.)
        self.assertIn("Keep the state of PC 2", texts(items))
        self.assertNotIn("Keep the PC's state", texts(items))
        self.assertFalse(any("only part of it" in t for t in texts(items) if isinstance(t, str)))
        c.sync_join_choice["other_name"] = "Laptop"
        self.assertIn("Keep the state of Laptop", texts(joinui.choice_items(UI(), c, lambda: None)))

    def test_aside_asks_once(self):
        c = ctrl()
        b = types.SimpleNamespace(ctrl=c)
        draw = lambda: joinui.aside_items(UI(), b, lambda: None)   # noqa: E731
        press(draw(), "Bring back")
        self.assertEqual(c.done, [])                       # first click only asks
        asked = texts(draw())
        self.assertIn(joinui.BACK_ASK, asked)
        self.assertNotIn("friends and profile go back", " ".join(asked))   # friends never come back (legal/lead)
        press(draw(), "Bring back")
        self.assertEqual(c.done, [("back", "2026-11-07")])
        press(draw(), "Delete")
        press(draw(), "Cancel")
        self.assertEqual(c.done, [("back", "2026-11-07")])  # Cancel: nothing deleted
        press(draw(), "Delete")
        press(draw(), "Delete")
        self.assertEqual(c.done[-1], ("drop", "2026-11-07"))

    def test_aside_tickets_view_and_delete_only(self):
        # legal 07.11.: open trades of a state set aside – legal's line, one row each, only View and Delete (two clicks)
        dropped = []
        tk = {"id": "t1", "partner": "Ben", "give": [["MH3", "1", "en", False, 2, "Card"]], "get": [], "money": 250,
              "t": 1794000000}
        c = ctrl(aside_tickets=lambda sid: {"mtg": [tk]},
                 aside_ticket_delete=lambda sid, g, i: dropped.append((sid, g, i)) or True)
        b = types.SimpleNamespace(ctrl=c)
        draw = lambda: joinui.aside_items(UI(), b, lambda: None)   # noqa: E731
        self.assertNotIn(joinui.TICKETS_LINE, texts(draw()))          # only once the state is viewed
        press(draw(), "View")
        items = draw()
        self.assertIn(joinui.TICKETS_LINE, texts(items))
        line = joinui.ticket_line(tk)
        self.assertIn(line, texts(items))
        self.assertIn("Ben", line)
        self.assertIn("2 cards", line)
        self.assertIn("you pay", line)
        self.assertNotIn("you get", line)                            # nothing coming: left out (lead)
        clara = joinui.ticket_line({"partner": "Clara", "t": 1794000000, "give": [], "money": -400,
                                    "get": [["WOE", "9", "en", False, 3, "Card"]]})
        self.assertNotIn("you give", clara)
        self.assertIn("you get 3 cards · Clara pays", clara)          # „bekommst“ never twice
        press(items, "Delete")                                       # the trade's key comes first
        self.assertEqual(dropped, [])                                # first click only asks
        self.assertIn(joinui.TICKET_ASK, texts(draw()))
        press(draw(), "Delete")
        self.assertEqual(dropped, [("2026-11-07", "mtg", "t1")])
        self.assertEqual(c.done, [("open", "2026-11-07")])            # the state itself untouched

    def test_notice_offline(self):
        c = ctrl()
        c.aside_list = lambda: [{"id": "x", "when": 1, "what": {}, "why": "offline"}]
        c.sync_status["aside"] = "x"
        b = types.SimpleNamespace(ctrl=c)
        items = joinui.notice_items(UI(), b, lambda: None)
        self.assertIn(joinui.OFFLINE, texts(items))
        press(items, "View")
        self.assertIn(("open", "x"), c.done)
        self.assertIn(("seen", "x"), c.done)


class StatusTest(unittest.TestCase):
    """Signed out / backup of a removed identity: lines at the top of „Your devices“ (legal 07.11.)."""

    def test_signed_out_and_gone(self):
        with mock.patch.object(syncrun, "available", return_value=True):
            seen, cam = [], []
            c = types.SimpleNamespace(sync_status={"removed": {"by": "Handy"}}, settings={"relay": {"identity_gone": 5}},
                                      identity_gone_seen=lambda: seen.append(1),
                                      sync_join_camera=lambda on, device=None: cam.append(on))
            b = types.SimpleNamespace(ctrl=c)
            items = joinui.status_items(UI(), b, lambda: None)
            self.assertIn(joinui.REMOVED.format(device="Handy"), texts(items))
            self.assertNotIn(joinui.GONE, texts(items))           # signed out: only that line (lead 07.11.)
            self.assertNotIn("Add again", [k[1][0] for k in buttons(items)])   # D (lead 12.11.): removed = emptied, no „Add again“
            self.assertEqual(cam, [])
            c.sync_status = {}                                    # after a restart: the kept mark still says it
            c.settings["relay"]["removed"] = {"by": "PC 1", "at": 1}
            items = joinui.status_items(UI(), b, lambda: None)
            self.assertIn(joinui.REMOVED.format(device="PC 1"), texts(items))
            self.assertNotIn(joinui.GONE, texts(items))
            del c.settings["relay"]["removed"]                   # a backup of a removed identity, not signed out
            items = joinui.status_items(UI(), b, lambda: None)
            self.assertIn(joinui.GONE, texts(items))
            press(items, "OK")
            self.assertEqual(seen, [1])
            seen.clear()
            c.settings["relay"]["removed"] = {"by": "", "at": 1}         # D: [OK] reads the line away
            press(joinui.status_items(UI(), b, lambda: None), "OK")
            self.assertEqual(seen, [1])
        with mock.patch.object(syncrun, "available", return_value=False):
            self.assertEqual(joinui.status_items(UI(), b, lambda: None), [])


class CoupledTest(unittest.TestCase):
    """„Coupled ✓“ only while this device is really paired and syncing (lead 07.11., performance' Part A run)."""

    def ctrl(self, on=True, removed=None, kept=None, deleted_off=False):
        eng = types.SimpleNamespace(on=lambda: on, meta={"deleted_off": True} if deleted_off else {})
        relay = {"removed": kept} if kept else {}
        return types.SimpleNamespace(sync_engine=eng, sync_status={"removed": removed} if removed else {},
                                     settings={"relay": relay})

    def test_rule(self):
        self.assertTrue(joinui.really_coupled(self.ctrl()))
        self.assertFalse(joinui.really_coupled(self.ctrl(on=False)))
        self.assertFalse(joinui.really_coupled(self.ctrl(removed={"by": "PC 1"})))   # signed out
        self.assertFalse(joinui.really_coupled(self.ctrl(kept={"by": "PC 1", "at": 1})))   # … after a restart
        self.assertFalse(joinui.really_coupled(self.ctrl(deleted_off=True)))   # deleted on another device

    def test_join_group_shows_it_only_then(self):
        with mock.patch.object(syncrun, "available", return_value=True):
            b = joiner()
            c = b.ctrl
            c.sync_status["join"] = "ok"
            self.assertIn("Coupled ✓", " ".join(texts(joinui.join_items(UI(), b, lambda: None))))
            c.sync_status["removed"] = {"by": "PC 1"}
            items = joinui.join_items(UI(), b, lambda: None)
            self.assertNotIn("Coupled ✓", " ".join(texts(items)))   # back to „type the code“ (SPHERE off, 11.11.)
            self.assertIn(joinui.JOIN_HOW_CODE, texts(items))


class StatusLineOffTest(unittest.TestCase):
    """The sync row's text only while the switch is on (lead 07.11.): off / signed out / deleted elsewhere – none."""

    def test_no_status_line_when_off(self):
        from tests.test_device_switch import find, page, setup
        for removed, deleted in ((False, False), (True, False), (False, True)):
            b, _ = setup("leave")
            eng = b.ctrl.sync_engine
            eng.on = lambda: False
            if deleted:
                eng.meta["deleted_off"] = True
            if removed:
                b.ctrl.sync_status["removed"] = {"by": "PC 1"}
            b.ctrl.sync_status["text"] = "Sync didn't work – try again later"
            labels = [x[1][0] for x in find(page(b), "label")]
            self.assertNotIn("Sync didn't work – try again later", labels, (removed, deleted))
        b, _ = setup("leave")                                   # on: the row shows it
        b.ctrl.sync_status["text"] = "Sync didn't work – try again later"
        labels = [x[1][0] for x in find(page(b), "label")]
        self.assertIn("Sync didn't work – try again later", labels)


def joiner(**kw):
    c = types.SimpleNamespace(sync_status={}, codes=[], cam=[], settings_listeners=[], settings={},
                              sync_engine=types.SimpleNamespace(on=lambda: True, meta={}))   # paired and syncing
    c.sync_join_code = lambda code: c.codes.append(code)
    c.sync_join_camera = lambda on, device=None: c.cam.append((on, device))
    c.sync_join_cameras = lambda: [(0, "Webcam"), (1, "Capture")]
    c.__dict__.update(kw)
    return types.SimpleNamespace(ctrl=c)


class JoinTest(unittest.TestCase):
    """This PC joins the phone (Paket 2c): read the sphere or type the code – legal's lines, the camera never left on."""

    def test_off_without_sync(self):
        with mock.patch.object(syncrun, "available", return_value=False):
            self.assertEqual(joinui.join_items(UI(), joiner(), lambda: None), [])

    def test_code_and_camera(self):
        from net import sync_ctl   # the sphere behind its switch (11.11.): this test is about the switch on
        with mock.patch.object(syncrun, "available", return_value=True), mock.patch.object(sync_ctl, "SPHERE", True):
            b = joiner()
            draw = lambda: joinui.join_items(UI(), b, lambda: None)   # noqa: E731
            t = " ".join(texts(draw()))
            self.assertIn(joinui.JOIN_HOW, t)
            self.assertIn(joinui.JOIN_SAFE, t)
            self.assertNotIn(joinui.CAM_LOCAL, t)                 # only while reading
            edit = next(i for i in draw() if i[0] == "form")[1][0][0][1]
            edit[1][1]("abc")                                     # too short: a line, nothing sent
            self.assertEqual(b.ctrl.codes, [])
            self.assertIn("The code has 10 letters and digits.", texts(draw()))
            edit[1][1]("7f3a2-1c90b")
            self.assertEqual(b.ctrl.codes, ["7F3A21C90B"])
            press(draw(), "Read the sphere")
            self.assertEqual(b.ctrl.cam[-1][0], True)
            self.assertIn(joinui.CAM_LOCAL, texts(draw()))
            for fn in b.ctrl.settings_listeners:                  # another settings page: the camera goes off
                fn("backup")
            self.assertEqual(b.ctrl.cam[-1][0], False)

    def test_states(self):
        with mock.patch.object(syncrun, "available", return_value=True):
            b = joiner(sync_status={"join": "wrong"})
            self.assertIn("The code doesn't fit or has expired – show a new one on your phone.",
                          texts(joinui.join_items(UI(), b, lambda: None)))
            b.__dict__.setdefault("join_ui", {})["cam"] = True   # reading the sphere again: the old answer goes
            b.ctrl.sync_status = {"join": "wrong", "join_cam": "looking"}
            self.assertNotIn("The code doesn't fit or has expired – show a new one on your phone.",
                             texts(joinui.join_items(UI(), b, lambda: None)))
            b.__dict__["join_ui"]["cam"] = False
            b.ctrl.sync_status = {"join": "busy"}
            self.assertTrue(all(k[2].get("enabled") is False for k in buttons(joinui.join_items(UI(), b, lambda: None))))
            b.ctrl.sync_status = {"join": "ok"}
            self.assertTrue(any("Coupled" in s for s in texts(joinui.join_items(UI(), b, lambda: None))))


if __name__ == "__main__":
    unittest.main()
