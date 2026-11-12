"""Trade display (ports, desk-anzeige 06.11.2026, lead): card names for tickets read from the pixel code, the ticket's
own date on the image, the same card twice as one line "2×"."""
import os
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from collection import ticket  # noqa: E402
from collection import tradelib  # noqa: E402
from collection.tradelib import same_cards, same_rows  # noqa: E402
from ui import qtrade  # noqa: E402
from tests.test_trade_core_money import ANNA, ME, FakeUi  # noqa: E402

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def row(name, n=1, foil=False):
    return {"name": name, "set": "M10", "number": "146", "count": n, "price": None, "lang": "en", "foil": foil}


class SameCards(unittest.TestCase):
    def test_rows_summed_in_first_place(self):
        out = same_rows([row("Bolt"), row("Shock"), row("Bolt", 2)])
        self.assertEqual([(r["name"], r["count"]) for r in out], [("Bolt", 3), ("Shock", 1)])

    def test_foil_stays_apart(self):
        self.assertEqual(len(same_rows([row("Bolt"), row("Bolt", foil=True)])), 2)

    def test_ticket_cards_as_in_the_booking_dialog(self):
        cards = [["m10", "146", "en", 0, 1, "Bolt"], ["M10", "146", "", 0, 1, "Bolt"], ["m10", "146", "de", 0, 1, "Bolt"]]
        out = same_cards(cards, lambda c: (str(c[0]).lower(), str(c[1]), c[2] or "en", bool(c[3])),
                         lambda c: int(c[4] or 1), lambda c, n: c[:4] + [n] + c[5:])
        self.assertEqual([(c[2], c[4]) for c in out], [("en", 2), ("de", 1)])
        self.assertEqual(cards[0][4], 1)   # the ticket's own cards stay untouched


class TicketDate(unittest.TestCase):
    def test_the_ticket_date_not_now(self):
        t = ticket.new(ME, ANNA, [["m10", "146", "en", 0, 1, "Bolt"]], [])
        t["t"] = int(time.mktime((2026, 11, 5, 18, 30, 0, 0, 0, -1)))
        seen = []
        real = time.strftime
        with mock.patch.object(tradelib.time, "strftime", side_effect=lambda f, *a: seen.append(a) or real(f, *a)):
            tradelib.offer_image(("Me", None), ("Anna", None), [row("Bolt")], [], t, priced=False)
        self.assertEqual(real("%d.%m.%Y %H:%M", seen[0][0]), "05.11.2026 18:30")


class CounterNames(unittest.TestCase):
    def test_names_from_the_card_database(self):
        """A ticket read from its pixel code has five fields per card – the dialog showed " · M10 #146"."""
        t = ticket.new(ANNA, ME, [["m10", "146", "en", 0, 1]], [["mh2", "50", "en", 1, 1]])
        o = {"id": t["x"], "partner": list(ANNA), "status": "received", "versions": [t]}
        ui = FakeUi()
        page = types.SimpleNamespace(priced=lambda: False, show_ticket=lambda nt: None,
                                     counter_offer=lambda *a: None)
        backend = types.SimpleNamespace(page=page, ctrl=types.SimpleNamespace(settings={}), offers_refresh=lambda: None)
        dlg = types.SimpleNamespace(close=lambda r: None, form=types.SimpleNamespace(soon=lambda: None))
        db = {("m10", "146"): {"name": "Lightning Bolt"}, ("mh2", "50"): {"name": "Counterspell"}}

        def show(title, build, **kw):
            build(ui, dlg)
            return None
        with mock.patch("collection.offers.get", return_value=o), \
                mock.patch("collection.offers.latest", return_value=t), \
                mock.patch("system.userprofile.ensure", return_value={"id": ME[0]}), \
                mock.patch("cards.carddb.by_prints", side_effect=lambda keys, game=None: {
                    (str(s).lower(), str(n)): db[(str(s).lower(), str(n))] for s, n in keys}), \
                mock.patch("ui.qdialogs.show", side_effect=show):
            qtrade.TradeBackend._counter_dialog(backend, o["id"])
        self.assertIn("Lightning Bolt · M10 #146", ui.texts)
        self.assertIn("Counterspell · MH2 #50 · Foil", ui.texts)

    def test_same_card_twice_one_row(self):
        bolt = ["m10", "146", "en", 0, 1, "Lightning Bolt"]
        t = ticket.new(ANNA, ME, [], [list(bolt), list(bolt)])
        o = {"id": t["x"], "partner": list(ANNA), "status": "received", "versions": [t]}
        ui, seen = FakeUi(), {}
        page = types.SimpleNamespace(priced=lambda: False, show_ticket=lambda nt: None,
                                     counter_offer=lambda oid, g, r, m: seen.update(give=g))
        backend = types.SimpleNamespace(page=page, ctrl=types.SimpleNamespace(settings={}), offers_refresh=lambda: None)
        dlg = types.SimpleNamespace(close=lambda r: None, form=types.SimpleNamespace(soon=lambda: None))

        def show(title, build, **kw):
            build(ui, dlg)
            return "share"
        with mock.patch("collection.offers.get", return_value=o), \
                mock.patch("collection.offers.latest", return_value=t), \
                mock.patch("system.userprofile.ensure", return_value={"id": ME[0]}), \
                mock.patch("ui.qdialogs.show", side_effect=show):
            qtrade.TradeBackend._counter_dialog(backend, o["id"])
        self.assertEqual(ui.texts.count("Lightning Bolt · M10 #146"), 1)
        self.assertEqual([c[4] for c in seen["give"]], [2])


if __name__ == "__main__":
    unittest.main()
