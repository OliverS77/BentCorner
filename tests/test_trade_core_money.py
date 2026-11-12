"""Money in Orbit's Core (lead + legal 06.11.2026): no card values, sums or balance – but an amount a partner entered is
part of the deal and shows as their proposal ("Anna adds 3,00 €" / "Anna wants 3,00 € from you"). Nothing new can be
entered in Core; a counter-offer keeps the amount (money=None) or takes it out ("Remove amount" -> 0)."""
import types
import unittest
from unittest import mock

from collection import ticket
from collection.tradelib import eur, money_text
from ui import qtrade

ME, ANNA = ("m" * 32, "Me"), ("a" * 32, "Anna")
CARD = ["mh2", "50", "en", 0, 1, "Counterspell"]


def anna_offer(money):
    """Anna's offer to me; money: € from Anna to me (negative = Anna wants money from me)."""
    return ticket.new(ANNA, ME, [list(CARD)], [list(CARD)], money=money)


class MoneyText(unittest.TestCase):
    def test_friend_adds(self):
        self.assertEqual(money_text(anna_offer(3.0), ME[0]), f"Anna adds {eur(3.0)}")

    def test_friend_wants(self):
        self.assertEqual(money_text(anna_offer(-3.0), ME[0]), f"Anna wants {eur(3.0)} from you")

    def test_own_offer_both_ways(self):
        mine = ticket.new(ME, ANNA, [list(CARD)], [], money=2.5)    # I pay Anna
        self.assertEqual(money_text(mine, ME[0]), f"You add {eur(2.5)}")
        mine = ticket.new(ME, ANNA, [list(CARD)], [], money=-2.5)   # Anna pays me
        self.assertEqual(money_text(mine, ME[0]), f"You want {eur(2.5)} from Anna")

    def test_no_money_no_text(self):
        self.assertEqual(money_text(anna_offer(0), ME[0]), "")


class ClosingTicket(unittest.TestCase):
    """Accepting (lead 06.11.): the closing ticket is mine, but nobody "wants" anything any more – who pays whom."""

    def setUp(self):
        from system import i18n
        self.i18n, self._lang = i18n, i18n.LANG

    def tearDown(self):
        self.i18n.set_language(self._lang)

    def closing(self, offer_money, friend=ANNA):
        offer = ticket.new(friend, ME, [list(CARD)], [list(CARD)], money=offer_money)
        return ticket.new(ME, friend, [list(CARD)], [list(CARD)], kind="f", money=ticket.money_from_me(offer, ME[0]))

    def test_friend_pays_me(self):
        self.assertEqual(money_text(self.closing(3.0), ME[0]), f"Anna pays you {eur(3.0)}")
        self.i18n.set_language("de")
        self.assertEqual(money_text(self.closing(3.0), ME[0]), f"Anna zahlt dir {eur(3.0)}")

    def test_i_pay_the_friend(self):
        self.assertEqual(money_text(self.closing(-3.0), ME[0]), f"You pay {eur(3.0)} to Anna")
        self.i18n.set_language("de")
        self.assertEqual(money_text(self.closing(-3.0), ME[0]), f"Du zahlst Anna {eur(3.0)}")

    def test_friend_without_a_name(self):
        nobody = ("b" * 32, "")
        self.i18n.set_language("de")
        self.assertEqual(money_text(self.closing(3.0, nobody), ME[0]), f"Dein Freund zahlt dir {eur(3.0)}")
        self.assertEqual(money_text(self.closing(-3.0, nobody), ME[0]), f"Du zahlst deinem Freund {eur(3.0)}")

    def test_offers_keep_their_wording(self):
        self.i18n.set_language("de")
        self.assertEqual(money_text(anna_offer(3.0), ME[0]), f"Anna legt {eur(3.0)} dazu")


class FakeUi:
    """Records which texts the dialog would show and which buttons it has."""
    def __init__(self):
        self.texts, self.buttons = [], {}

    def button(self, text, fn, **kw):
        self.buttons[text] = fn
        self.texts.append(text)
        return "button"

    def __getattr__(self, name):
        def node(*a, **k):
            self.texts += [x for x in a if isinstance(x, str)]
            for x in a:
                if isinstance(x, list):
                    for row in x:
                        if isinstance(row, tuple) and isinstance(row[0], str):
                            self.texts.append(row[0])
            return name
        return node


class CoreCounterOffer(unittest.TestCase):
    def run_dialog(self, priced, money=3.0, press=None):
        t = anna_offer(money)
        o = {"id": t["x"], "partner": list(ANNA), "status": "received", "versions": [t]}
        seen, ui = {}, FakeUi()
        page = types.SimpleNamespace(priced=lambda: priced, show_ticket=lambda nt: None,
                                     counter_offer=lambda oid, g, r, m: seen.update(money=m))
        backend = types.SimpleNamespace(page=page, ctrl=types.SimpleNamespace(settings={}), offers_refresh=lambda: None)
        dlg = types.SimpleNamespace(close=lambda r: None, form=types.SimpleNamespace(soon=lambda: None))

        def show(title, build, **kw):
            build(ui, dlg)
            if press:   # a button in the dialog, then the dialog is built again (form.soon)
                ui.buttons[press]()
                build(ui, dlg)
            return "share"
        with mock.patch("collection.offers.get", return_value=o), \
                mock.patch("collection.offers.latest", return_value=t), \
                mock.patch("system.userprofile.ensure", return_value={"id": ME[0]}), \
                mock.patch("ui.qdialogs.show", side_effect=show):
            qtrade.TradeBackend._counter_dialog(backend, o["id"])
        return seen.get("money", "not called"), ui

    def test_core_shows_the_proposal_and_keeps_it(self):
        money, ui = self.run_dialog(priced=False)
        self.assertIsNone(money)   # None = counter_offer keeps the offer's amount
        self.assertIn(f"Anna adds {eur(3.0)}", ui.texts)
        self.assertIn("Remove amount", ui.buttons)
        self.assertNotIn("Money in the trade", ui.texts)   # no field to enter money

    def test_core_counter_without_money(self):
        money, ui = self.run_dialog(priced=False, money=-3.0, press="Remove amount")
        self.assertEqual(money, 0.0)
        self.assertIn(f"Anna wants {eur(3.0)} from you", ui.texts)
        self.assertIn("Without money", ui.texts)

    def test_core_without_money_no_amount_row(self):
        _, ui = self.run_dialog(priced=False, money=0)
        self.assertNotIn("Remove amount", ui.buttons)
        self.assertFalse([x for x in ui.texts if "€" in x])

    def test_prices_on_show_the_money_field(self):
        money, ui = self.run_dialog(priced=True)
        self.assertEqual(money, -3.0)
        self.assertIn("Money in the trade", ui.texts)


if __name__ == "__main__":
    unittest.main()
