"""Remembered results that must never go stale (performance round 0.9.2.60): the backup mark only refreshes the pages
when something changed, the price alert rows are rebuilt as soon as an alert, the game or the language changes, the
pack and friend file checks forget themselves on install / new files.

    python -m unittest discover -t . -s tests -p test_perf_caches.py
"""
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from cards import packs
from system import autobackup, upkeep_ctl
from net import teamnews


class Signal:
    def __init__(self):
        self.n = 0

    def emit(self):
        self.n += 1


class BadgeOnlyOnChange(unittest.TestCase):
    def setUp(self):
        self.refreshed = 0
        profile = types.SimpleNamespace(refresh=self._refresh)
        backends = {"profile": profile, "import": types.SimpleNamespace(changed=Signal()),
                    "settings": types.SimpleNamespace(changed=Signal())}
        self.badges = []
        self.ctrl = types.SimpleNamespace(settings={}, updater=None, shell=types.SimpleNamespace(backends=backends),
                                          stream=types.SimpleNamespace(set_badge=lambda k, on: self.badges.append((k, on))))
        self.attention = ""
        self.p = [mock.patch.object(teamnews, "unread", lambda s: 0),
                  mock.patch.object(autobackup, "attention", lambda s: self.attention)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def _refresh(self):
        self.refreshed += 1

    def badge(self, **kw):
        upkeep_ctl.UpkeepControl.autobackup_badge(self.ctrl, **kw)

    def test_unchanged_state_triggers_nothing(self):
        self.badge(only_changed=True)
        self.assertEqual(self.refreshed, 1)   # the first time: there was no state yet
        self.badge(only_changed=True)
        self.badge(only_changed=True)
        self.assertEqual(self.refreshed, 1)
        self.assertEqual(self.ctrl.shell.backends["settings"].changed.n, 1)

    def test_a_changed_notice_refreshes(self):
        self.badge(only_changed=True)
        self.attention = "No backup yet"
        self.badge(only_changed=True)
        self.assertEqual(self.refreshed, 2)
        self.assertIn(("settings", True), self.badges)

    def test_other_callers_still_refresh_always(self):
        self.badge()
        self.badge()
        self.assertEqual(self.refreshed, 2)


class AlarmRows(unittest.TestCase):
    """qtrade_alarms._alarm_rows on a stand-in host: rebuilt only when its inputs change."""

    def setUp(self):
        from ui import qtrade_alarms
        self.A = qtrade_alarms.AlarmsBackend
        self.built = 0
        settings = {"price_alarms": [{"name": "Oko", "kind": "wish", "game": "mtg", "below": 5}]}
        host = types.SimpleNamespace(_alarm_rev=0, _open_alarms=set())
        self.b = types.SimpleNamespace(ctrl=types.SimpleNamespace(settings=settings,
                                                                  collection=types.SimpleNamespace(rev=0)),
                                       host=host)
        self.b._alarm_key = lambda: self.A._alarm_key(self.b)
        self.b._alarm_rows_here = self._rows_here
        self.b._alarm_rows_other = lambda cur: []

    def _rows_here(self):
        self.built += 1
        return [{"key": a["name"], "name": a["name"]} for a in self.b.ctrl.settings["price_alarms"]]

    def rows(self):
        return self.A._alarm_rows(self.b)

    def test_remembered_while_nothing_changes(self):
        self.rows()
        self.rows()
        self.assertEqual(self.built, 1)

    def test_changed_alert_shows_at_once(self):
        self.rows()
        self.b.ctrl.settings["price_alarms"].append({"name": "Sol Ring", "kind": "wish", "game": "mtg"})
        self.assertEqual([r["name"] for r in self.rows()], ["Oko", "Sol Ring"])
        self.b.ctrl.settings["price_alarms"][0]["below"] = 3   # edited
        self.rows()
        self.assertEqual(self.built, 3)

    def test_language_collection_and_touch_rebuild(self):
        from system import i18n
        self.rows()
        with mock.patch.object(i18n, "LANG", "de" if i18n.LANG != "de" else "en"):
            self.rows()
        self.b.ctrl.collection.rev += 1
        self.rows()
        self.b.host._alarm_rev += 1   # _alarms_touched (add/edit/delete in the page)
        self.rows()
        self.assertEqual(self.built, 4)

    def test_rows_handed_out_are_copies(self):
        self.rows()[0]["chip"] = "MTG"
        self.assertNotIn("chip", self.rows()[0])


class Installed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.p = [mock.patch.object(packs, "folder", lambda key: self.dir),
                  mock.patch.dict(packs.PACKS, {"tst": {"files": ["a.bin"], "name": "Test"}})]
        for p in self.p:
            p.start()
        packs.forget_installed()

    def tearDown(self):
        for p in self.p:
            p.stop()
        packs.forget_installed()
        self.tmp.cleanup()

    def test_remembered_and_forgotten_on_install(self):
        self.assertFalse(packs.installed("tst"))
        (self.dir / "a.bin").write_bytes(b"x")
        self.assertFalse(packs.installed("tst"))   # still remembered (≤ INSTALLED_TTL)
        packs.forget_installed("tst")              # = download() at its end
        self.assertTrue(packs.installed("tst"))

    def test_ttl_at_most_five_seconds(self):
        self.assertLessEqual(packs.INSTALLED_TTL, 5.0)


class FriendFiles(unittest.TestCase):
    def setUp(self):
        from ui import qprofile
        self.q = qprofile
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.p = mock.patch.object(qprofile.trade, "friends_folder", lambda key: self.dir)
        self.p.start()
        qprofile.forget_friend_files()

    def tearDown(self):
        self.p.stop()
        self.q.forget_friend_files()
        self.tmp.cleanup()

    def test_a_new_friend_file_shows_at_once(self):
        (self.dir / "a.json").write_text('{"id": "a"}', "utf-8")
        self.assertEqual([d["id"] for d in self.q.friend_files("mtg")], ["a"])
        import os
        (self.dir / "b.json").write_text('{"id": "b"}', "utf-8")
        st = self.dir.stat()   # coarse file systems: make sure the folder's mtime moved
        os.utime(self.dir, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
        self.assertEqual(sorted(d["id"] for d in self.q.friend_files("mtg")), ["a", "b"])
        self.assertLessEqual(self.q.FRIEND_FILES_TTL, 5.0)

    def test_handed_out_dicts_are_copies(self):
        (self.dir / "a.json").write_text('{"id": "a"}', "utf-8")
        self.q.friend_files("mtg")[0]["id"] = "changed"
        self.assertEqual(self.q.friend_files("mtg")[0]["id"], "a")


if __name__ == "__main__":
    unittest.main()
