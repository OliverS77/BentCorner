"""„Sign out this device“ in this device's row (PLAN-EINFACH, lead/Oliver 07.11.2026 – the sync switch is gone; the
web's wording): with other devices only THIS device leaves, after a line asking; as the only device it asks keep/delete
(with a protection code / unclear) or says so first (without a code). Nothing is ever deleted before the user's answer.
In memory, a stand-in ctrl (performance' sync_leave_plan / sync_leave).

    python -m unittest tests/test_device_switch.py
"""
import types
import unittest
from unittest import mock

from ui import qsync


class UI:
    def __getattr__(self, kind):
        return lambda *a, **k: (kind, a, k)

    def row(self, items, **k):
        return ("row", [i for i in items if i], k)

    def col(self, items, **k):
        return ("col", [i for i in items if i], k)

    def group(self, title, items, **k):
        return ("group", title, [i for i in items if i])


def flat(node):
    if isinstance(node, (list, tuple)):
        return [x for n in node for x in flat(n)]
    return [node]


def find(page, kind):
    out = []

    def walk(n):
        if isinstance(n, tuple) and n and n[0] == kind:
            out.append(n)
        if isinstance(n, (list, tuple)):
            for x in n:
                walk(x)
    walk(page)
    return out


def setup(plan):
    calls, state = [], {"on": True}
    eng = types.SimpleNamespace(on=lambda: state["on"], meta={})

    def leave(delete=None, guard=None):   # like the logic: off afterwards
        calls.append((delete, guard) if guard else (delete,))
        state["on"] = False
    ctrl = types.SimpleNamespace(sync_engine=eng, sync_status={"busy": False, "text": "", "when": None},
                                 settings={"sync_backup": True}, sync_leave_plan=lambda: plan, sync_leave=leave,
                                 sync_switch=lambda *a, **k: calls.append(("switch",) + a), pair=None,
                                 pair_left=lambda: 0, pair_show=lambda: None,
                                 sync_devices=lambda: [{"dev": "a", "name": None, "n": 1, "me": True, "os": "windows",
                                                        "ver": "0.9.7.60"}])
    b = types.SimpleNamespace(ctrl=ctrl, form=types.SimpleNamespace(refresh=lambda: None))
    return b, calls


def page(b):
    with mock.patch("net.vault.gate_needed", return_value=False):
        return qsync.page(UI(), b)


def press(p, label):
    btn = next(x for x in find(p, "button") if x[1][0] == label)
    btn[1][1]()


def sign_out(b):
    """U4 (lead 11.11.): this device's ✕ (tooltip „Sign out this device“) asks right under its row."""
    btn = next(x for x in find(page(b), "button") if x[1][0] == "✕" and x[2].get("tip") == qsync.SIGN_OUT)
    btn[1][1]()


class SignOutTest(unittest.TestCase):
    def test_no_switch_no_sync_now(self):
        p = page(setup("leave")[0])
        self.assertEqual(find(p, "check"), [])
        self.assertNotIn("Sync now", [x[1][0] for x in find(p, "button")])

    def test_other_devices_ask_a_line_then_leave(self):
        b, calls = setup("leave")
        sign_out(b)
        self.assertEqual(calls, [])                 # the line first
        p = page(b)
        self.assertIn(qsync.SIGN_OUT_ASK, [x[1][0] for x in find(p, "label")])
        press(p, qsync.SIGN_OUT)
        self.assertEqual(calls, [(None,)])          # never deletes
        b.ctrl.sync_status.update(left=True)
        self.assertIn(qsync.LEAVE, [x[1][0] for x in find(page(b), "note")])

    def test_cancel_does_nothing(self):
        b, calls = setup("leave")
        sign_out(b)
        press(page(b), "Cancel")
        self.assertEqual(calls, [])
        self.assertNotIn(qsync.SIGN_OUT_ASK, [x[1][0] for x in find(page(b), "label")])

    def test_only_device_with_code_asks_first(self):
        b, calls = setup("ask")
        sign_out(b)
        self.assertEqual(calls, [])                 # nothing happened yet
        p = page(b)
        notes = [x[1][0] for x in find(p, "note")]
        self.assertIn(qsync.ONLY_ASK, notes)
        self.assertIn(qsync.ONLY_183, notes)
        keys = [x for x in find(p, "button") if x[1][0] in (qsync.KEEP_OFF, qsync.DEL_BACKUP)]
        self.assertFalse(any(k[2].get("primary") or k[2].get("active") for k in keys))   # equal
        press(p, qsync.KEEP_OFF)
        self.assertEqual(calls, [(False,)])

    def test_only_device_without_code_says_so_and_cancel_keeps_everything(self):
        b, calls = setup("delete")
        sign_out(b)
        p = page(b)
        self.assertIn(qsync.ONLY_NOCODE, [x[1][0] for x in find(p, "note")])
        press(p, "Cancel")
        self.assertEqual(calls, [])
        sign_out(b)
        press(page(b), qsync.OFF_DELETE)
        self.assertEqual(calls, [(True,)])

    def test_no_connection_says_so(self):
        # performance' vault_delete: server first – without a connection nothing changes
        b, calls = setup("delete")
        b.ctrl.sync_leave = lambda delete=None, guard=None: calls.append((delete,))   # stays on, like the logic offline
        sign_out(b)
        press(page(b), qsync.OFF_DELETE)
        b.ctrl.sync_status.update(busy=False, deleted=False, text="Sync didn't work")
        labels = [x[1][0] for x in find(page(b), "label")]
        self.assertIn(qsync.OFF_FAILED, labels)

    def test_protection_code_asked_before_deleting(self):
        # legal A4 / performance' delete_guard: the field, not the "no connection" line; the code goes into the call
        from ui import backupui
        b, calls = setup("ask")
        b.form.forget = lambda k: None
        b.ctrl.sync_leave = lambda delete=None, guard=None: calls.append((delete, guard))
        sign_out(b)
        press(page(b), qsync.DEL_BACKUP)
        b.ctrl.sync_status.update(busy=False, delete_guard="need")
        p = page(b)
        self.assertIn(backupui.GUARD_NEED, [x[1][0] for x in find(p, "label")])
        self.assertNotIn(qsync.OFF_FAILED, [x[1][0] for x in find(p, "label")])
        find(p, "edit")[0][1][1]("TEST-CODE")
        press(page(b), qsync.DEL_BACKUP)
        self.assertEqual(calls[-1], (True, "TEST-CODE"))
        self.assertEqual(b.__dict__["devices_guard"].get("code"), "TEST-CODE")   # U2: RAM only while it is checked


class DeviceListTest(unittest.TestCase):
    def test_rows_names_and_rename(self):
        b, _ = setup("leave")
        renamed = []
        b.ctrl.device_rename = lambda name, dev=None: renamed.append((name, dev))
        b.ctrl.sync_devices = lambda: [
            {"dev": "a", "name": None, "n": 1, "me": True, "os": "windows", "ver": "0.9.7.60"},
            {"dev": "b", "name": "Handy", "n": 2, "me": False, "os": "web", "ver": "0.27", "added": 1_762_473_600_000}]
        p = page(b)
        lab = " ".join(str(x[1][0]) for x in find(p, "label"))
        from system import nicknames   # Oliver/lead 12.11.: a device without a name shows its nickname
        self.assertIn(f"<b>{nicknames.render(nicknames.fallback('a'), 'en')}</b> – this device", lab)
        self.assertIn("<b>Handy</b> – added on", lab)
        self.assertIn("Windows · 0.9.7.60", lab)
        self.assertIn("Web app · 0.27", lab)
        self.assertNotIn(qsync.NO_OTHERS, [x[1][0] for x in find(p, "note")])
        renames = [x for x in find(p, "button") if x[1][0] == qsync.RENAME]
        self.assertEqual(len(renames), 2)
        renames[1][1][1]()   # the phone
        p = page(b)
        edit = find(p, "edit")[0]
        self.assertEqual(edit[1][0], "Handy")
        edit[2]["live"]("Olivers Handy")
        press(page(b), qsync.SAVE)
        self.assertEqual(renamed, [("Olivers Handy", "b")])

    def test_alone(self):
        b, _ = setup("ask")
        self.assertIn(qsync.NO_OTHERS, [x[1][0] for x in find(page(b), "note")])

    def test_sign_out_only_in_own_row(self):
        b, _ = setup("leave")
        b.ctrl.sync_devices = lambda: [{"dev": "a", "n": 1, "me": True}, {"dev": "b", "n": 2, "me": False}]
        self.assertEqual(len([x for x in find(page(b), "button") if x[2].get("tip") == qsync.SIGN_OUT]), 1)


class JoinNameTest(unittest.TestCase):
    """Oliver 07.11.: the name is given on the new device when adding – prefilled „Device N“."""

    def test_field_after_the_code_then_once(self):
        b, _ = setup("leave")
        named = []
        b.ctrl.sync_join_name = named.append
        self.assertEqual([x for x in find(page(b), "edit") if x[2].get("key") == "devname_join"], [])
        b.ctrl.sync_my_nick = lambda: [34, 0, 0]   # Oliver/lead 12.11.: the proposal is this device's nickname
        b.ctrl.sync_status.update(join="ok", join_n=3)
        edit = [x for x in find(page(b), "edit") if x[2].get("key") == "devname_join"][0]
        self.assertEqual(edit[1][0], "Tall Brave Fox")
        edit[2]["live"]("Laptop")
        press(page(b), qsync.SAVE)
        self.assertEqual(named, ["Laptop"])
        self.assertEqual([x for x in find(page(b), "edit") if x[2].get("key") == "devname_join"], [])

    def test_number_comes_after_the_first_drawing(self):
        # performance 07.11. guide run: join busy first (no join_n), then join_n – the field follows until typed
        b, _ = setup("leave")
        b.ctrl.sync_join_name = lambda t: None
        b.ctrl.sync_status.update(join="busy")
        page(b)
        b.ctrl.sync_my_nick = lambda: [15, 2, 1]
        b.ctrl.sync_status.update(join="ok", join_n=2)
        edit = [x for x in find(page(b), "edit") if x[2].get("key") == "devname_join"][0]
        self.assertEqual(edit[1][0], "Little Clever Owl")
        edit[2]["live"]("Laptop")
        b.ctrl.sync_status.update(join_n=3)
        edit = [x for x in find(page(b), "edit") if x[2].get("key") == "devname_join"][0]
        self.assertEqual(edit[1][0], "Laptop")   # typed: it stays

    def test_number_unknown_empty_with_placeholder(self):
        b, _ = setup("leave")
        b.ctrl.sync_join_name = lambda t: None
        b.ctrl.sync_status.update(join="choice", join_n=0)
        edit = [x for x in find(page(b), "edit") if x[2].get("key") == "devname_join"][0]
        self.assertEqual(edit[1][0], "")
        self.assertEqual(edit[2]["placeholder"], "Device")


class NoCodeLeftTest(unittest.TestCase):
    """lead 08.11. (performance' step 8): after signing out or joining no code is left in any field; a second join of
    the same PC asks for the name again."""

    def setUp(self):
        from collection import syncrun
        self.p = mock.patch.object(syncrun, "available", return_value=True)   # the join field is built in
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def _enter(self, b):
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.sync_join_code = lambda code: b.ctrl.sync_status.update(join="busy")
        b.form.forget = lambda k: None
        press(page(b), qsync.ENTER_CODE)

    def codes(self, b):
        return [x[1][0] for x in find(page(b), "edit") if "XXXXX" in str(x[2].get("placeholder"))]

    def test_after_joining(self):
        b, _ = setup("leave")
        self._enter(b)
        edit = [x for x in find(page(b), "edit") if "XXXXX" in str(x[2].get("placeholder"))][0]
        edit[2]["live"]("ABCDE-12345")
        edit[1][1]("ABCDE-12345")                                     # Enter in the field
        self.assertEqual(self.codes(b), [""])                          # read once – empty at once
        b.ctrl.sync_status.update(join="ok")
        self.assertEqual(self.codes(b), [])                            # joined: the box closed

    def test_after_signing_out(self):
        b, _ = setup("leave")
        self._enter(b)
        [x for x in find(page(b), "edit") if "XXXXX" in str(x[2].get("placeholder"))][0][2]["live"]("ABCDE-12345")
        sign_out(b)
        press(page(b), qsync.SIGN_OUT)
        b.ctrl.sync_status.update(left=True)
        page(b)
        self.assertEqual(self.codes(b), [])
        from ui import joinui
        self.assertNotIn("code", joinui._ui_state(b))

    def test_second_join_asks_the_name_again(self):
        b, _ = setup("leave")
        b.ctrl.sync_join_name = lambda t: None
        b.ctrl.sync_status.update(join="ok", join_n=2)
        press(page(b), qsync.SAVE)
        b.ctrl.sync_status.update(join="")
        page(b)
        b.ctrl.sync_status.update(join="ok", join_n=2)
        self.assertTrue([x for x in find(page(b), "edit") if x[2].get("key") == "devname_join"])


class AddDeviceTest(unittest.TestCase):
    def test_one_place_show_or_enter(self):
        b, _ = setup("leave")
        b.ctrl.sync_orbit_ok = lambda: True
        p = page(b)
        groups = [g[1] for g in find(p, "group")]
        self.assertIn(qsync.ADD_TITLE, groups)
        for old in ("Couple a device", "Couple with your phone"):
            self.assertNotIn(old, groups)
        press(p, qsync.SHOW_CODE)
        self.assertIn("Show a code for a new device", [x[1][0] for x in find(page(b), "button")])

    def test_without_the_backup_only_show_waits(self):
        # ports/lead 07.11.: a fresh device joins without setting up its own backup – only „Show a code“ needs it
        b, _ = setup("leave")
        b.ctrl.sync_engine.on = lambda: False
        b.ctrl.settings["sync_backup"] = False
        b.ctrl.sync_join_code = lambda code: None
        opened = []
        b.ctrl.show_settings = opened.append
        p = page(b)
        keys = {x[1][0]: x for x in find(p, "button") if x[1][0] in (qsync.SHOW_CODE, qsync.ENTER_CODE)}
        self.assertIs(keys[qsync.SHOW_CODE][2].get("enabled"), False)
        self.assertIsNot(keys[qsync.ENTER_CODE][2].get("enabled"), False)
        press(p, qsync.TO_BACKUP)
        self.assertEqual(opened, ["backup"])


if __name__ == "__main__":
    unittest.main()
