"""B5 – removing ONE device (Oliver 07.11.2026, legal A8 07.11.): the ✕ in its row (only visible on hover), then under
the row legal's sentence with „Removed with it: …“ when it added devices itself; without a protection code „[Yes]
[No]“, with one the A4 field – the code goes into the call only. The old box „Remove device“ (sign out all others) is
gone. Also the join request (a device from a backup file, 14 days) and the waiting device's line. Stand-in ctrl
(performance' sync_remove_plan / sync_remove / sync_join_request_*).

    python -m unittest tests/test_device_remove.py
"""
import types
import unittest

from tests.test_device_switch import find, page, press
from ui import backupui, qsync

ROWS = [{"dev": "a", "n": 1, "me": True, "os": "windows", "ver": "0.9.7.60"},
        {"dev": "b", "name": "Laptop", "n": 2, "me": False, "os": "windows", "ver": "0.9.7.60", "added": 1_762_473_600_000},
        {"dev": "c", "n": 3, "me": False, "os": "web", "ver": "0.27", "added": 1_762_500_000_000}]


def setup(guarded=False, with_=()):
    calls = []
    st = {"busy": False, "text": "", "when": None}
    eng = types.SimpleNamespace(on=lambda: True, meta={})

    def remove(dev, guard=None):   # like the logic: busy at once
        calls.append((dev, guard))
        st["remove"] = "busy"
    ctrl = types.SimpleNamespace(
        sync_engine=eng, sync_status=st, settings={"sync_backup": True}, sync_leave_plan=lambda: "leave",
        sync_leave=lambda **k: None, pair=None, pair_left=lambda: 0, pair_show=lambda: None,
        guard_on=lambda: guarded, sync_devices=lambda: ROWS, sync_remove=remove,
        sync_remove_plan=lambda dev: {"name": None, "n": 2, "with": [{"dev": "c", "name": None, "n": 3}] if with_ else [],
                                      "guard": guarded})
    b = types.SimpleNamespace(ctrl=ctrl, form=types.SimpleNamespace(refresh=lambda: None, forget=lambda k: None))
    return b, calls


def texts(p, kind):
    return [x[1][0] for x in find(p, kind)]


def xs(p):
    """The ✕ of the OTHER devices (U4, lead 11.11.: this device's own ✕ is „Sign out this device“)."""
    return [x for x in find(p, "button") if x[1][0] == "✕" and x[2].get("tip") != qsync.SIGN_OUT]


class RemoveOneTest(unittest.TestCase):
    def test_x_on_every_row_always_visible_and_no_old_box(self):
        b, _ = setup()
        p = page(b)
        self.assertEqual(len(xs(p)), 2)                                     # the other devices' ✕
        self.assertFalse(any(x[2].get("hover") for x in xs(p)))           # U4 (lead 11.11.): always visible
        own = [x for x in find(p, "button") if x[1][0] == "✕" and x[2].get("tip") == qsync.SIGN_OUT]
        self.assertEqual(len(own), 1)                                       # this device: ✕ = sign out
        self.assertNotIn(qsync.SIGN_OUT, [x[1][0] for x in find(p, "button")])   # no wide key in the row any more
        self.assertNotIn(qsync.RM_KEY, [g[1] for g in find(p, "group")])    # the box „Remove device“ is gone

    def test_without_code_yes_no(self):
        b, calls = setup()
        xs(page(b))[0][1][1]()
        self.assertEqual(calls, [])                                         # the ✕ only asks
        p = page(b)
        self.assertIn(qsync.RM_ASK1.format(name="Laptop"), texts(p, "label"))
        self.assertIn("we can't delete it", qsync.RM_ASK1)                 # legal A8
        self.assertFalse(any("Removed with it" in t for t in texts(p, "label")))
        keys = [x for x in find(p, "button") if x[1][0] in (qsync.RM_YES, qsync.RM_NO)]
        self.assertFalse(any(k[2].get("primary") or k[2].get("active") for k in keys))   # equal
        press(p, qsync.RM_NO)
        self.assertEqual(calls, [])
        xs(page(b))[0][1][1]()
        press(page(b), qsync.RM_YES)
        self.assertEqual(calls, [("b", None)])
        self.assertIn(qsync.RM_BUSY1.format(name="Laptop"), texts(page(b), "label"))
        b.ctrl.sync_status["remove"] = "ok"
        self.assertIn(qsync.RM_DONE1.format(name="Laptop"), texts(page(b), "label"))

    def test_plan_asked_again_until_the_list_is_there(self):
        # box run 12.11.: ✕ right after adding – the first answer is empty (the list is being fetched), the next one not
        b, _ = setup()
        answers = [None, {"name": None, "n": 2, "with": [], "guard": False}]
        b.ctrl.sync_remove_plan = lambda dev: answers.pop(0) if len(answers) > 1 else answers[0]
        b.ctrl.sync_remove_checking = lambda: True
        xs(page(b))[0][1][1]()
        self.assertIn(qsync.RM_YES, [x[1][0] for x in find(page(b), "button")])

    def test_removed_with_it_only_when_there_are_some(self):
        b, _ = setup(with_=True)
        xs(page(b))[0][1][1]()
        want = qsync.device_name({"dev": "c", "name": None, "n": 3})   # Oliver/lead 12.11.: its nickname (from its id)
        self.assertIn(f"<b>Removed with it: {want}</b>", texts(page(b), "label"))

    def test_with_code_the_field_and_the_code_in_the_call_only(self):
        b, calls = setup(guarded=True)
        xs(page(b))[0][1][1]()
        p = page(b)
        self.assertIn(backupui.GUARD_NEED, texts(p, "label"))
        self.assertNotIn(qsync.RM_YES, texts(p, "button"))
        find(p, "edit")[0][1][1]("TEST-CODE")
        press(page(b), qsync.RM_KEY)
        self.assertEqual(calls, [("b", "TEST-CODE")])
        self.assertEqual(b.__dict__["devices_rm_code"].get("code"), "TEST-CODE")   # U2: kept while checked (RAM)

    def test_wrong_code_and_conflict(self):
        b, _ = setup(guarded=True)
        xs(page(b))[0][1][1]()
        b.ctrl.sync_status["delete_guard"] = "wrong"
        self.assertIn(backupui.GUARD_WRONG, texts(page(b), "label"))
        b.devices_rm["sent"] = True
        b.ctrl.sync_status.update(delete_guard=None, remove="conflict")
        self.assertIn(qsync.RM_CONFLICT, texts(page(b), "label"))

    def test_picked_up_box_back_and_a_new_code(self):
        # lead 07.11.: picked up -> the box back to [Show a code] [Enter a code], no „Coupled ✓“; showing again works
        # without a restart (a new code); legal A3 under the list
        b, _ = setup(guarded=True)
        shown = []

        def pair_show():
            shown.append(1)
            b.ctrl.pair = {"code": "", "fetched": False}
        b.ctrl.pair_show = pair_show
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.sync_join_code = lambda code: None
        press(page(b), qsync.SHOW_CODE)
        b.ctrl.pair = {"fetched": True}                                      # the other device picked it up
        p = page(b)
        from system import contacts
        self.assertIn(qsync.A3.format(mail=contacts.MAIL), texts(p, "note"))
        self.assertNotIn("<b>Coupled ✓</b>", texts(p, "label"))
        self.assertNotIn("Show a code for a new device", texts(p, "button"))   # folded: only the two keys
        self.assertIn(qsync.SHOW_CODE, texts(p, "button"))
        self.assertIn(qsync.ENTER_CODE, texts(p, "button"))
        press(p, qsync.SHOW_CODE)                                            # the second time: a new code
        self.assertEqual(shown, [1, 1])                                      # the first press made one too
        self.assertEqual(b.devices_add.get("mode"), "show")


class ShowDirectTest(unittest.TestCase):
    def test_first_time_a_code_at_once(self):
        # performance' guide run 08.11.: the very first „Show a code“ shows one – no extra key in between
        b, _ = setup(guarded=True)
        shown = []
        b.ctrl.pair_show = lambda: shown.append(1)
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.pair = {}
        press(page(b), qsync.SHOW_CODE)
        self.assertEqual(shown, [1])

    def test_a_valid_code_is_kept(self):
        b, _ = setup()
        shown = []
        b.ctrl.pair_show = lambda: shown.append(1)
        b.ctrl.sync_orbit_ok = lambda: True
        b.ctrl.pair = {"code": "ABCDE12345", "shown": False, "img": "x", "turn": 0}
        b.ctrl.pair_left = lambda: 300
        b.ctrl.pair_toggle = b.ctrl.pair_copy = lambda: None
        press(page(b), qsync.SHOW_CODE)
        self.assertEqual(shown, [])


class JoinRequestTest(unittest.TestCase):
    def test_decline_or_allow_with_code(self):
        b, _ = setup(guarded=True)
        answers = []
        b.ctrl.sync_join_request_info = lambda: [{"dev": "x1", "dev_id": "x1", "since": 1, "until": 1_794_000_000}]

        def answer(dev, allow, guard=None):
            answers.append((dev, allow, guard))
            if allow and not guard:
                b.ctrl.sync_status["delete_guard"] = "need"
        b.ctrl.sync_join_request_answer = answer
        p = page(b)
        first = find(p, "group")[0]
        self.assertEqual(first[1], qsync.REQ_JOIN_TITLE)                   # its own frame, at the top
        press(p, qsync.REQ_ALLOW)
        p = page(b)
        self.assertIn(backupui.GUARD_NEED, texts(p, "label"))
        find(p, "edit")[0][1][1]("TEST-CODE")
        press(page(b), qsync.REQ_ALLOW)
        self.assertEqual(answers[-1], ("x1", True, "TEST-CODE"))
        b.ctrl.sync_status.pop("delete_guard")
        b.devices_req.clear()
        press(page(b), qsync.REQ_DECLINE)
        self.assertEqual(answers[-1], ("x1", False, None))

    def test_date_is_the_servers_until(self):
        # lead 07.11.: never computed here – the server's until (box: since + JOIN_WAIT, in seconds)
        import time
        since = int(time.time())
        until = since + 14 * 86400
        b, _ = setup()
        b.ctrl.sync_join_request_info = lambda: [{"dev": "x1", "since": since, "until": until}]
        b.ctrl.sync_join_request_answer = lambda *a, **k: None
        want = time.strftime("%d.%m.%Y", time.localtime(until))
        self.assertIn(qsync.REQ_JOIN.format(date=want), texts(page(b), "label"))

    def test_keys_aligned_while_asking(self):
        b, _ = setup()
        xs(page(b))[0][1][1]()
        self.assertEqual(len(xs(page(b))), 2)   # the ✕ keeps its place in the asked row too

    def test_unseen_until_devices_opened(self):
        b, _ = setup()
        b.ctrl.sync_join_request_info = lambda: [{"dev": "x1", "until": 5}]
        b.ctrl.settings_changed = lambda: None
        self.assertTrue(qsync.join_request_unseen(b.ctrl))
        qsync.join_request_seen(b.ctrl)
        self.assertFalse(qsync.join_request_unseen(b.ctrl))
        b.ctrl.sync_join_request_info = lambda: [{"dev": "x2", "until": 9}]
        self.assertTrue(qsync.join_request_unseen(b.ctrl))

    def test_the_waiting_device(self):
        b, _ = setup()
        b.ctrl.sync_status["join_wait"] = {"until": 1_794_000_000}
        self.assertTrue(any(t.startswith("This device wants to join") for t in texts(page(b), "label")))
        b.ctrl.sync_status["join_wait"] = {"declined": True}
        self.assertIn(qsync.JOIN_DECLINED, texts(page(b), "label"))


if __name__ == "__main__":
    unittest.main()
