"""Sharing the library with friends (legal 06.11.2026): off until you turn it on yourself – no question pops up any
more – and turning it off takes it away again: the next parcel has no "lib" and replaces the friend's copy.

    python -m unittest tests/test_share_library.py
"""
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from collection import trade
from net import relay_ctl

ITEMS = [{"id": "a_0", "sid": "a", "set": "LEA", "number": "161", "lang": "en", "foil": False, "count": 2,
          "name": "Lightning Bolt", "eur": 400.0, "note": "Ordner 3", "location": "Kiste"}]


def contents(self):
    """relay_share_contents of the controller – binders of all games left out (no game folders in the tests)."""
    with mock.patch("ui.qbinder.shared_binders", return_value=[]):
        return relay_ctl.RelayControl.relay_share_contents(self)


def export(share):
    """relay_export of the controller with these settings – no shared lists, the collection = ITEMS."""
    settings = {"profile": {"id": "p-me", "name": "Ich"}}
    if share is not None:
        settings["share_library"] = share
    fake = types.SimpleNamespace(settings=settings, collection=types.SimpleNamespace(items=ITEMS))
    fake.relay_share_contents = lambda: contents(fake)
    with mock.patch.object(trade, "lists", return_value=[]):
        return relay_ctl.RelayControl.relay_export(fake)


class ShareLibrary(unittest.TestCase):
    def test_off_by_default_and_when_turned_off(self):
        self.assertNotIn("lib", export(None))
        self.assertNotIn("lib", export(False))

    def test_on_sends_only_cards_and_counts(self):
        lib = export(True)["lib"]
        self.assertEqual(lib, [["lea", "161", "en", 0, 2, "Lightning Bolt"]])   # no price, note or location

    def test_no_question_any_more(self):
        self.assertFalse(hasattr(relay_ctl.RelayControl, "share_library_ask"))
        root = pathlib.Path(__file__).resolve().parent.parent
        self.assertNotIn("share_library_ask", (root / "app.py").read_text("utf-8"))

    def test_turning_off_replaces_the_friends_copy(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(trade, "FRIENDS", pathlib.Path(tmp)):
            on = export(True)
            trade.friend_from_import({"kind": "bentcorner", "data": on})
            self.assertTrue(trade.friend("p-me").get("library"))
            trade.friend_from_import({"kind": "bentcorner", "data": export(False)})
            self.assertNotIn("library", trade.friend("p-me"))


class Ctrl:
    """Just enough of the main window for the page: relay_send_lists records the parcel it would send."""

    def __init__(self, settings):
        self.settings = settings
        self.sent, self.pages, self.bg = [], [], []
        self.collection = types.SimpleNamespace(items=ITEMS)
        self.stream = types.SimpleNamespace(show_page=lambda page, back=False: self.pages.append(page))

    def settings_changed(self):
        pass

    def relay_share_contents(self):
        with mock.patch.object(trade, "lists", return_value=[]):
            return contents(self)

    def relay_send_lists(self, quiet=False):
        with mock.patch.object(trade, "lists", return_value=[]):
            self.sent.append(relay_ctl.RelayControl.relay_export(self))

    relay_share_library_off = relay_ctl.RelayControl.relay_share_library_off

    def _relay_bg(self, what, fn):   # the network part right away, recorded
        self.bg.append((what, fn()))


def backend(settings):
    """The page's part (ui/qshared.py) on a small host."""
    from PySide6 import QtCore
    from ui import qshared

    class Host(QtCore.QObject):
        listsChanged = QtCore.Signal()
    c = Ctrl(settings)
    h = Host()
    h.ctrl = c
    return c, qshared.SharedBackend(h), h


def card(c):
    from ui import qshared
    with mock.patch.object(trade, "lists", return_value=[]), mock.patch("ui.qbinder.all_binders", return_value=[]):
        return qshared.overview(c)["card"]


FRIEND = {"F" * 16: {"name": "Mia", "status": "ok"}}


def sharing(**kw):
    """Shares the library from before (the old question): posted from this device, Mia among the friends."""
    return dict({"share_library": True, "relay": {"on": True, "friends": dict(FRIEND), "posted": {"mtg/lists": {"lib": True}}}}, **kw)


class Card(unittest.TestCase):
    """Who shares from before is asked once on "Shared with friends" (legal 06.11.): a card, two equal answers;
    afterwards no card again – no reminders."""

    def test_card_only_for_who_shares(self):
        self.assertTrue(card(Ctrl(sharing())))
        self.assertEqual(card(Ctrl(sharing(share_library=False))), {})
        self.assertEqual(card(Ctrl({"share_library": True, "relay": {"on": True}})), {})   # no friends: nothing goes out

    def test_keep_sharing(self):
        c, b, _h = backend(sharing())
        b.answer(True)
        self.assertIs(c.settings["share_library"], True)
        self.assertEqual(c.sent, [])                                  # nothing changes for the friends
        self.assertEqual(card(c), {})                                  # never the card again

    def test_stop_sharing_reaches_every_game(self):
        """Two games shared their library: the open one gets a parcel without it, the other is withdrawn at once
        (rebuilt without the library the next time it is open). A post known to be without it stays."""
        s = sharing()
        s["relay"]["posted"] = {"mtg/lists": {"lib": True}, "pokemon/lists": {"lib": True},
                                "lorcana/lists": {"lib": False}, "yugioh/lists": {}, "pokemon/binder-x": {}}   # yugioh: older
        c, b, _h = backend(s)
        gone = []
        with mock.patch("games.current", return_value=types.SimpleNamespace(key="mtg")),                 mock.patch("net.relay.withdraw", side_effect=lambda st, g, slot="lists": gone.append((g, slot)) or 1):
            b.answer(False)
        self.assertIs(c.settings["share_library"], False)
        self.assertEqual(len(c.sent), 1)
        self.assertNotIn("lib", c.sent[0])                             # the open game: a new parcel without it
        self.assertEqual(sorted(gone), [("pokemon", "lists"), ("yugioh", "lists")])   # the others: withdrawn now
        self.assertEqual([w for w, _ in c.bg], ["withdraw_lib"])
        self.assertEqual(card(c), {})

    def test_a_withdrawn_game_shares_again_when_open(self):
        """relay_auto_lists: no post for the open game → share (without the library, the switch is off)."""
        c = Ctrl({"share_library": False, "relay": {"on": True, "friends": dict(FRIEND), "posted": {}}})
        c.relay_changes = lambda: 0
        sent = []
        c.relay_send_lists = lambda quiet=False: sent.append(quiet)
        from ui import qbinder  # noqa: F401  (imported with the real game; patched below)
        with mock.patch("games.current", return_value=types.SimpleNamespace(key="pokemon")),                 mock.patch("ui.qbinder.auto_share"):
            relay_ctl.RelayControl.relay_auto_lists(c)
        self.assertEqual(sent, [True])

    def test_the_switch_counts_as_an_answer(self):
        src = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "qsetpages.py").read_text("utf-8")
        self.assertIn("s.update(share_library=bool(v), share_library_confirmed=True)", src)
        self.assertIn("ctrl.relay_send_lists(quiet=True) if v else ctrl.relay_share_library_off()", src)   # off: every game
        page = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "qshared.py").read_text("utf-8")
        self.assertIn('s["share_library_confirmed"] = True   # a choice under the new rules', page)


if __name__ == "__main__":
    unittest.main()
