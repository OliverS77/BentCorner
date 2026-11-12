"""Texts in trade (ports, desk-texte 06.11.2026, lead): what the desktop showed in the wrong language or twice."""
import types
import unittest
from unittest import mock

from system import i18n


class Lang(unittest.TestCase):
    def setUp(self):
        self._lang = i18n.LANG

    def tearDown(self):
        i18n.set_language(self._lang)


class ImportToast(Lang):
    def test_first_import_in_german(self):
        """The rule needed text after "loaded" – a first import stayed English."""
        i18n.set_language("de")
        self.assertEqual(i18n.tr("Anna: 6 cards, 2 wishes loaded"), "Anna: 6 Karten, 2 Wünsche geladen")
        diff = i18n.tr(" · before 3 different, now 6")   # as in tradeview.import_file: the tail first
        self.assertEqual(i18n.tr(f"Anna: 6 cards, 2 wishes loaded{diff}"),
                         "Anna: 6 Karten, 2 Wünsche geladen · vorher 3 verschiedene, jetzt 6")


class CsvWithoutName(Lang):
    def test_error_follows_the_language(self):
        from collection import trade
        for lang, word in (("en", "No “Name” column found"), ("de", "Keine Spalte „Name“ gefunden")):
            i18n.set_language(lang)
            with self.assertRaises(ValueError) as cm:
                trade.parse_csv("Count;Thing;Set\n1;Bolt;m10\n")
            self.assertEqual(str(cm.exception), word)


class CsvErrorAsALine(Lang):
    def test_no_box_a_line_under_the_button(self):
        """lead 06.11.: no box with OK – the reason stays as a line under "Import friend" until the next import."""
        import pathlib
        import tempfile
        from ui import qtrade_friends, tradeview
        p = pathlib.Path(tempfile.mkdtemp()) / "x.csv"
        p.write_text("Count;Thing;Set\n1;Bolt;m10\n", "utf-8")
        page = types.SimpleNamespace()
        i18n.set_language("de")
        with mock.patch("ui.qdialogs.warn") as warn, mock.patch("ui.qdialogs.info") as info:
            self.assertIsNone(tradeview.TradePage.import_file(page, str(p)))
        warn.assert_not_called()
        info.assert_not_called()
        self.assertEqual(page.import_error, "Konnte die Datei nicht lesen: Keine Spalte „Name“ gefunden")
        tf = types.SimpleNamespace(page=page)
        self.assertEqual(qtrade_friends.FriendsBackend.importError.fget(tf), page.import_error)


class ImportMessagesAsALine(Lang):
    """lead 06.11. ("alle"): messages, not serious questions – a line under the button, never a box."""

    def run_import(self, parsed=None, ticket_file=False, friends=None):
        from ui import tradeview
        page = types.SimpleNamespace(ctrl=types.SimpleNamespace(settings={"profile": {"id": "me" * 16, "name": "Ich"}}))
        i18n.set_language("de")
        with mock.patch("ui.qdialogs.warn") as warn, mock.patch("ui.qdialogs.info") as info, \
                mock.patch("collection.ticket.is_ticket_file", return_value=ticket_file), \
                mock.patch("collection.ticket.read_image", return_value=None), \
                mock.patch("collection.trade.read_file", return_value=parsed), \
                mock.patch("net.relay.friends", return_value=friends or {}):
            self.assertIsNone(tradeview.TradePage.import_file(page, "x"))
        warn.assert_not_called()
        info.assert_not_called()
        return page.import_error

    def test_no_ticket_in_the_image(self):
        self.assertEqual(self.run_import(ticket_file=True), "In diesem Bild steckt kein Bent°Corner-Tauschticket – oder es "
                                                            "wurde zugeschnitten. Am besten das Bild unverändert schicken.")

    def test_own_collection(self):
        own = {"kind": "bentcorner", "data": {"id": "me" * 16, "name": "Ich", "c": [], "w": []}}
        self.assertEqual(self.run_import(own), "Das ist deine eigene Sammlung 🙂")

    def test_blocked_person(self):
        blk = {"kind": "bentcorner", "data": {"id": "b" * 32, "name": "Bo", "c": [], "w": []}}
        err = self.run_import(blk, friends={"X" * 16: {"pid": "b" * 32, "status": "blocked"}})
        self.assertEqual(err, "Du hast diese Person blockiert – ihre Dateien lassen sich nicht importieren. Aufheben geht im Profil.")


class FriendWithoutName(Lang):
    def test_fallback_name_follows_the_language(self):
        from collection import trade
        parsed = {"kind": "bentcorner", "data": {"id": "b" * 32, "name": "", "c": [], "w": []}}
        for lang, word in (("en", "Friend"), ("de", "Freund")):
            i18n.set_language(lang)
            with mock.patch.object(trade, "friend", return_value=None), mock.patch.object(trade, "save_friend"):
                self.assertEqual(trade.friend_from_import(parsed)["name"], word)


class AddFriendOnce(unittest.TestCase):
    def test_no_toast_before_the_result(self):
        from ui import qprofile
        toasts = []
        ctrl = types.SimpleNamespace(settings={"relay": {"on": True}}, relay_add=lambda code: None,
                                     stream_toast=toasts.append, relay_ask=lambda: None)
        backend = types.SimpleNamespace(ctrl=ctrl, refresh=lambda: None)
        with mock.patch("PySide6.QtCore.QTimer.singleShot"):
            err = qprofile.ProfileBackend.addFriend(backend, "7F3A-21C9-0B44-E1D2")
        self.assertEqual(err, "")
        self.assertEqual(toasts, [])   # relay_ctl says "sent" or "not sent: …" when the server answered


class ExportWithoutName(unittest.TestCase):
    def test_goes_to_the_profile_name(self):
        from ui import importview
        shown, toasts = [], []
        stream = types.SimpleNamespace(ensure_page=lambda k: None, show_page=lambda k, **kw: shown.append(k))
        ctrl = types.SimpleNamespace(settings={}, stream=stream, stream_toast=toasts.append,
                                     trade_page=types.SimpleNamespace(), collection=types.SimpleNamespace(items=[]))
        page = types.SimpleNamespace(ctrl=ctrl, fexp={"fmt": "bentcorner", "send_lists": True, "have": {"main"},
                                                       "all_cards": False, "wish": set(), "decks": False, "cols": set()})
        with mock.patch("system.userprofile.ensure", return_value={"id": "x", "name": ""}), \
                mock.patch("ui.qdialogs.save_file") as save:
            importview.ImportPage.friend_export(page)
        save.assert_not_called()
        self.assertEqual(shown, ["profile"])
        self.assertTrue(ctrl.focus_profile_name)
        self.assertEqual(len(toasts), 1)


if __name__ == "__main__":
    unittest.main()
