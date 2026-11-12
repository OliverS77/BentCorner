"""The shared list docs/web/aside-kinds.json (lead 07.11., ports and performance): what goes aside and comes back,
what is only looked at, what never – the desktop's syncaside/syncrun must say exactly the same (the web tests the
same file).

    python -m unittest tests/test_aside_kinds.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import syncaside, syncrun

VEC = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs" / "web" / "aside-kinds.json").read_text("utf-8"))
# the shared names -> where the desktop keeps them
FILES = {"decks": "decks.json", "lists": "lists.json", "wishlist": "wishlist.json", "binders": "binders.json",
         "collection": "collection.json", "bookings": "bookings.json", "offers": "offers.json"}
DIRS = {"logs": "sessions"}
SETTINGS = {"profile": "profile", "price_alarms": "price_alarms", "list_alarms": "list_alarms"}


class Kinds(unittest.TestCase):
    def test_restore_is_exactly_the_desktops_own_data(self):
        names = set(VEC["restore"])
        self.assertEqual(names, set(FILES) | set(DIRS) | set(SETTINGS), "a name without a desktop place")
        self.assertEqual(set(syncaside.OWN_FILES), set(FILES.values()))
        self.assertEqual(set(syncaside.OWN_DIRS), set(DIRS.values()))
        self.assertEqual(set(syncaside.OWN_SETTINGS), set(SETTINGS.values()))

    def test_view_only_and_compare(self):
        self.assertEqual(VEC["view_only"], ["pending"])
        self.assertEqual(syncaside.VIEW_ONLY, "pending-trades.json")
        self.assertEqual(set(VEC["compare_not"]), set(syncrun.NOT_ASIDE))

    def test_never_is_never_in_a_set_aside_state(self):
        for n in VEC["never"]:
            self.assertNotIn(n, VEC["restore"])
        self.assertTrue(set(VEC["never"]).isdisjoint(syncaside.OWN_SETTINGS))
        self.assertNotIn("friends", " ".join(syncaside.OWN_FILES + syncaside.OWN_DIRS))

    def test_ticket_keeps_only_these_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "pending-trades.json"
            p.write_text(json.dumps({"pending": [{"ticket": {"id": "T", "f": ["a", "A"], "m": 1, "x": "secret"},
                                                  "partner": ["b", "B"], "give": [], "get": [], "foreign": [],
                                                  "t": 1}]}), "utf-8")
            row = syncaside._tickets_of(p)[0]
        self.assertEqual(set(row), set(VEC["ticket_keep"]))

    def test_after_restore_sync_is_off_and_the_identity_stays(self):
        from net import sync_ctl
        self.assertEqual(VEC["sync_after_restore"], {"sync_on": False, "keeps_identity": True})
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.settings, c.sync_status = {"relay": {"seed": "S"}, "sync_backup": True}, {}
        c.sync_engine = mock.Mock()
        for n in ("_sync_changed", "settings_changed", "sync_setup", "aside_seen", "reload_all"):
            setattr(c, n, mock.Mock())
        with mock.patch.object(syncrun, "available", lambda: True), \
                mock.patch.object(syncaside, "restore", lambda sid, mine, s, now=None: "cur"):
            try:
                sync_ctl.SyncControl.aside_restore(c, "x")
            except Exception:  # noqa: BLE001 – only the order of things matters here
                pass
        c.sync_engine.switch_off.assert_called()
        self.assertEqual(c.settings["relay"]["seed"], "S", "the identity stays")
