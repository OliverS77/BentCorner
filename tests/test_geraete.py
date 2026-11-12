"""Oliver's device test round 11.11.2026 (lead): F1/U2 code fields, F5 own request, U3/U4 ✕ in every row, F4 binder slots
from the sync, U5 cancel at the comparison table (ports' T3/T5), U6 equal counts, the sphere off. Stand-ins and temp
folders only – no network, no real data.

    python -m unittest tests/test_geraete.py
"""
import json
import os
import pathlib
import tempfile
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore  # noqa: E402

from collection import binders, syncrun  # noqa: E402
from ui import backupui, qform  # noqa: E402

_app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


def form_of(build):
    f = qform.Form(lambda ui: ui.col(build(ui)))
    return f


def wid(f, key):
    f.refresh()
    for v in f._vals.values():
        if v.get("t") == "edit" and f._keys.get(v.get("id")) == key:
            return v["id"]
    return None


def typed(f, key, text):
    """Key by key like a person; -> after which keys the structure changed (= QML rebuilt the field, focus gone)."""
    lost = []
    for i in range(1, len(text) + 1):
        before = f._skey
        f.act(wid(f, key), ["live", text[:i]])
        f.refresh()
        if f._skey != before:
            lost.append(i)
    return lost


class OwnCodeFocusTest(unittest.TestCase):
    """F1: the own code's page never changes its structure while typing (strength, „too weak“, „don't match“)."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_typing_keeps_the_fields(self):
        sent = []
        c = types.SimpleNamespace(settings={}, sync_status={}, guard_strength=lambda t: {"score": 3 if len(t) > 20 else 0,
                                                                                    "ok": len(t) > 20},
                                  sync_rescue_confirm=lambda *a, **k: None, vault_delete=lambda *a: None,
                                  sync_backup_set=lambda v: None, guard_set=lambda code, own=False, old=None: sent.append(code))
        st = {"mode": "own"}
        holder = {}
        f = form_of(lambda ui: backupui.rescue_items(ui, c, st, lambda: holder["f"].refresh(), lambda: None, lambda: None,
                                                     form=holder.get("f")))
        holder["f"] = f
        f.refresh()
        code = "Wolke7 trinkt Kakao am Nordbahnhof"
        self.assertEqual(typed(f, "own_a", code), [])   # before the fix: [1, 21]
        self.assertEqual(typed(f, "own_b", code), [])   # before the fix: [1, 34]
        f.act(wid(f, "own_b"), ["enter", code])         # Enter in the second field: Next
        self.assertEqual(sent, [code])
        self.assertEqual((st.get("a"), st.get("b")), (code, code))   # U2: stays while it is checked


class GuardFieldTest(unittest.TestCase):
    """U2: Enter sends, the code stays in the field while checked and after a wrong one, the line never rebuilds it."""

    def test_enter_sends_and_wrong_keeps(self):
        sent, mem, state = [], {}, {"s": "need"}
        holder = {}
        f = form_of(lambda ui: backupui.guard_items(ui, state["s"], None, mem, "Add device", sent.append, lambda: None,
                                                    holder.get("f")))
        holder["f"] = f
        f.refresh()
        self.assertEqual(typed(f, backupui.GUARD_KEY, "my own code"), [])
        f.act(wid(f, backupui.GUARD_KEY), ["enter", "my own code"])
        self.assertEqual(sent, ["my own code"])
        state["s"] = "wrong"
        f.refresh()
        node = [v for v in f._vals.values() if v.get("t") == "edit"][0]
        self.assertEqual(node["text"], "my own code")   # still there to fix one character
        self.assertTrue(node.get("reveal"))             # Show / Hide
        state["s"] = "need"                             # asked afresh (went through): empty again
        f.refresh()
        self.assertNotIn("code", mem)

    def test_kept_two_minutes_at_most(self):
        mem = {"code": "x"}
        drop = backupui.keep_for(mem, ("code",), secs=3600)
        drop()
        self.assertEqual(mem, {})


class OwnRequestTest(unittest.TestCase):
    """F5: this device's own request stays its own until the server reported it (then its end ends the mark)."""

    def ctrl(self, info=None):
        from net import sync_ctl
        e = types.SimpleNamespace(meta={"seeded": True, "guard_request": info})
        c = types.SimpleNamespace(sync_engine=e, settings={"sync_guard_mine": {"until": time.time() + 600}},
                                  settings_changed=lambda: None)
        c.guard_request_info = types.MethodType(sync_ctl.SyncCtl.guard_request_info, c) \
            if hasattr(sync_ctl, "SyncCtl") else None
        return c, e

    def test_mark_survives_until_reported(self):
        from net import sync_ctl
        cls = next(v for v in vars(sync_ctl).values() if isinstance(v, type) and hasattr(v, "guard_request_info"))
        c, e = self.ctrl()
        info = lambda: cls.guard_request_info(c)   # noqa: E731
        self.assertIsNone(info())                       # right after sending: the server's request not here yet
        self.assertIn("sync_guard_mine", c.settings)    # before: popped here -> „one of your devices …“ about itself
        e.meta["guard_request"] = {"since": 1, "until": 2}
        info()
        self.assertFalse(backupui.foreign_request(types.SimpleNamespace(settings=c.settings,
                                                                        guard_request_info=info)))
        e.meta["guard_request"] = None                  # declined / in effect
        info()
        self.assertNotIn("sync_guard_mine", c.settings)


class BinderSlotsTest(unittest.TestCase):
    """F4 (Oliver's log): slots from the sync carry sid/lang/foil only – set/number/name are filled before writing."""

    def test_complete_and_tolerant_key(self):
        doc = {"binders": [{"id": "b", "slots": [{"sid": "s1", "lang": "en", "foil": False}, None,
                                                 {"sid": "unknown", "lang": "en", "foil": True}]}]}
        rows = {"s1": {"id": "s1", "set_code": "MH2", "number": "50", "name": "Counterspell"}}
        with mock.patch("cards.carddb.cards_by_ids", return_value=rows):
            binders.complete(doc, "mtg")
        s1, _none, unk = doc["binders"][0]["slots"]
        self.assertEqual((s1["set"], s1["number"], s1["name"]), ("mh2", "50", "Counterspell"))
        self.assertEqual((unk["set"], unk["number"]), ("", ""))   # unknown card: empty, never a KeyError
        self.assertEqual(binders.value({"slots": [{"sid": "x"}]}, {}, {"x": 1.0}), (1.0, 0.0))   # the crash in F4


class EqualCountsTest(unittest.TestCase):
    """U6: the same numbers on both sides – no question, merged."""

    def test_equal_counts_no_question(self):
        e = syncrun.Engine.__new__(syncrun.Engine)
        e.meta = {}
        e._fresh_here = lambda: False   # this device has data of its own (the fresh case: FreshDeviceTest)
        same = {"decks": 1, "lists": 3, "binders": 0, "friends": 0, "cards": 5}
        e._counts_there = lambda: dict(same)
        e._counts_here = lambda: dict(same)
        self.assertIsNone(e._join_question())
        e._counts_here = lambda: dict(same, decks=2)
        self.assertIsNotNone(e._join_question())


class CancelAtTableTest(unittest.TestCase):
    """U5 (ports' T3/T5): [Cancel] at the table – this device as before, out of the joined ID; offline: a mark, again at
    the next start; 200 or 403/404/410 -> the mark goes."""

    def setUp(self):
        from net import sync_ctl
        self.cls = next(v for v in vars(sync_ctl).values() if isinstance(v, type) and hasattr(v, "_join_cancel"))
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def ctrl(self):
        import threading
        c = self.cls.__new__(self.cls)
        old = {"relay": {"seed": "OLD", "url": "http://127.0.0.1:1", "friends": {"F": {"status": "ok"}}},
               "sync_backup": False, "profile": {"name": "Me"}}
        c.settings = json.loads(json.dumps(old))
        c.sync_status = {}
        e = types.SimpleNamespace(meta={"on": False, "dev": "d1"}, lock=threading.Lock(), _save=lambda: None,
                                  _suffix=lambda: None, join_answer=lambda kind: None, switch_on=lambda: None)
        c.sync_engine = e
        c.settings_changed = lambda: None
        c.sync_setup = lambda: None
        c._sync_changed = lambda: None
        c.sync_now = lambda manual=False: None
        c.bg = []
        c._sync_bg = lambda step, fn: c.bg.append((step, fn))
        return c, old

    def test_cancel_puts_everything_back_and_leaves(self):
        c, old = self.ctrl()
        c._join_dk = "OLDCODE"
        c._join_apply({"seed": "NEW", "extra": {"friends": {"G": {"status": "ok"}}, "next_n": 2}})
        self.assertEqual(c.settings["relay"]["seed"], "NEW")
        self.assertTrue(c.settings["sync_backup"])
        updates = []
        with mock.patch("net.devkeys._update", side_effect=lambda **kw: updates.append(kw)):
            c.sync_join_answer("")
        self.assertEqual(c.settings["relay"], old["relay"])            # the old ID, its friends only
        self.assertEqual(c.settings["sync_backup"], False)
        self.assertNotIn("sync_paired", c.settings)
        self.assertEqual(c.sync_engine.meta, {"on": False, "dev": "d1"})
        self.assertEqual(updates, [{"code": "OLDCODE"}])               # the device key points back
        self.assertEqual(c.settings["sync_leave_pending"]["seed"], "NEW")
        self.assertEqual([s for s, _ in c.bg], ["join_leave"])

    def test_leave_answers(self):
        from net.vault import VaultError
        for err, kept in ((None, False), (VaultError(404, "gone", {}), False), (VaultError(403, "no", {}), False),
                          (OSError("offline"), True), (VaultError(500, "?", {}), True)):
            c, _ = self.ctrl()
            c.settings["sync_leave_pending"] = {"seed": "NEW", "at": 1}
            c._join_leave_done(True if err is None else None, err)
            self.assertEqual("sync_leave_pending" in c.settings, kept, err)

    def test_retry_at_start(self):
        c, _ = self.ctrl()
        c.leave_pending_check()
        self.assertEqual(c.bg, [])                                     # no mark: nothing
        c.settings["sync_leave_pending"] = {"seed": "NEW", "at": 1}
        c.leave_pending_check()
        self.assertEqual([s for s, _ in c.bg], ["join_leave"])
        with mock.patch("net.devkeys._post") as post, mock.patch("net.devkeys._load",
                                                                  return_value={"dev_id": "d1", "sign_sk": "A" * 44}), \
                mock.patch("net.devkeys.sign", return_value="sig"), mock.patch("net.relay._signed", return_value="s"), \
                mock.patch("net.vault._me", return_value=("CODE", 5)):
            c.bg[0][1]()
        self.assertEqual(post.call_args[0][1], "/v1/dev/leave")
        self.assertEqual(post.call_args[0][0]["relay"]["seed"], "NEW")   # signed as the joined ID


class SphereOffTest(unittest.TestCase):
    def test_off_by_default(self):
        from net import sync_ctl
        self.assertFalse(sync_ctl.SPHERE)
        self.assertFalse(sync_ctl.sphere_on({"sync_sphere": True}))   # no setting turns it on

    def test_german(self):
        from locales import de
        from ui import joinui, qsync
        for t in (qsync.TYPE_THERE, joinui.JOIN_HOW_CODE):
            self.assertIn(t, de.TEXTS)


if __name__ == "__main__":
    unittest.main()


class FollowUpTest(unittest.TestCase):
    """lead 11.11. (pictures 1a/2c): fewer lines while joining, „don't match“ not while still typing."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_mismatch_only_when_as_long_or_enter(self):
        from tests.test_backup_ui import UI
        c = types.SimpleNamespace(settings={}, sync_status={}, guard_strength=lambda t: {"score": 3, "ok": True},
                                  sync_rescue_confirm=lambda *a, **k: None, vault_delete=lambda *a: None,
                                  sync_backup_set=lambda v: None, guard_set=lambda *a, **k: None)

        def texts(st):
            out = []

            def walk(n):
                if isinstance(n, tuple):
                    out.extend(x for x in n if isinstance(x, str))
                    for x in n:
                        walk(x)
                elif isinstance(n, list):
                    for x in n:
                        walk(x)
            walk(backupui.rescue_items(UI(), c, st, lambda: None, lambda: None, lambda: None))
            return " ".join(out)
        diff = backupui.tr(backupui.OWN_DIFF)
        self.assertNotIn(diff, texts({"mode": "own", "a": "x" * 30, "b": "x" * 12}))    # still typing
        self.assertIn(diff, texts({"mode": "own", "a": "x" * 30, "b": "y" * 30}))       # as long, differs
        self.assertIn(diff, texts({"mode": "own", "a": "x" * 30, "b": "x" * 12, "tried": True}))   # Enter pressed

    def test_joining_without_backup_only_the_join(self):
        from tests.test_device_switch import find, page, setup
        from ui import qsync
        b, _ = setup("leave")
        b.ctrl.settings["sync_backup"] = False
        b.ctrl.sync_engine.on = lambda: False
        b.ctrl.sync_join_code = lambda code: None
        b.__dict__["devices_add"] = {"mode": "enter"}
        p = page(b)
        labels = [x[1][0] for x in find(p, "button")]
        self.assertNotIn(qsync.SHOW_CODE, labels)
        self.assertNotIn(qsync.TO_BACKUP, labels)
        self.assertNotIn(qsync.NEED_BACKUP, [x[1][0] for x in find(p, "note")])
        self.assertIn(qsync.ENTER_CODE, labels)


class FreshDeviceTest(unittest.TestCase):
    """Oliver 11.11. (decision 4 extended): a new device without stored data merges without asking."""

    def engine(self, docs, logs=(), friends=None):
        e = syncrun.Engine.__new__(syncrun.Engine)
        e.meta = {}
        e.settings = {"relay": {"friends": friends or {}}}
        e.docs = types.SimpleNamespace(games=lambda: ["mtg"], read=lambda g, f: docs.get(f),
                                       read_logs=lambda g: {"items": list(logs)})
        e._counts_there = lambda: {"decks": 2, "lists": 3, "binders": 0, "friends": 0, "cards": 9}
        e._counts_here = lambda: {"decks": 0, "lists": 2, "binders": 0, "friends": 0, "cards": 0}
        return e

    def test_only_default_lists_no_question(self):
        fresh = {"lists.json": {"wish": [{"id": "main", "name": "Wunschliste"}],
                                "have": [{"id": "trade", "name": "Tauschkarten"}], "custom": []}}
        self.assertIsNone(self.engine(fresh)._join_question())

    def test_anything_own_asks(self):
        base = {"lists.json": {"wish": [{"id": "main"}], "have": [{"id": "trade"}], "custom": []}}
        cases = [dict(base, **{"decks.json": {"decks": [{"id": "d"}]}}),
                 dict(base, **{"lists.json": {"custom": [{"id": "x1", "name": "Mine"}]}}),
                 dict(base, **{"lists.json": {"have": [{"id": "trade", "items": {"u": 1}}]}}),
                 dict(base, **{"wishlist.json": {"items": [{"name": "Sol Ring"}]}}),
                 dict(base, **{"binders.json": {"binders": [{"id": "b"}]}})]
        for docs in cases:
            self.assertIsNotNone(self.engine(docs)._join_question(), docs)
        self.assertIsNotNone(self.engine(base, logs=[{"count": 1}])._join_question())
        self.assertIsNotNone(self.engine(base, friends={"F": {"status": "ok"}})._join_question())
