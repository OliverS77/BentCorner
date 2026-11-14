"""Review 0.9.7 H2-6 and H2-8 on the PC – exactly as the web (ports 10.11., relaybounds/closingmirror tests):
H2-6: at most MAX_IN open requests (the oldest go), a "no" holds NO_WAIT, a friend's boards at most MAX_SLOTS (an
existing one may still change, game/slot/key checked); H2-8: a closing ticket is „Accepted – book it“ only if it
mirrors the trade's latest version – from the mailbox and as an image; otherwise an offer to answer. Temp files only.

    python -m unittest tests/test_h2pc.py
"""
import os
import pathlib
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collection import offers, ticket  # noqa: E402
from net import relay  # noqa: E402

ME, ANNA = ("m" * 32, "Me"), ("a" * 32, "Anna")
CARD = ["mh2", "50", "en", 0, 1, "Counterspell"]


def code(i):
    return ("A" + str(i).zfill(15))[:16]


def env(kind, body, frm="AAAAAAAAAAAAAAAA"):
    return {"kind": kind, "from": frm, "body": body, "game": "mtg", "_sign_pk": "x"}


class Bounds(unittest.TestCase):
    def test_more_than_max_in_strangers_the_oldest_go(self):
        s = {"profile": {"id": ME[0], "name": "Me"}, "relay": {"friends": {}}}
        for i in range(relay.MAX_IN + 5):
            self.assertEqual(relay.apply(s, env("friend", {"name": f"P{i}"}, code(i)))["kind"], "friend")
            s["relay"]["friends"][code(i)]["t"] = 1000 + i
        open_ = [c for c, f in s["relay"]["friends"].items() if f["status"] == "in"]
        self.assertEqual(len(open_), relay.MAX_IN)
        self.assertNotIn(code(0), open_)
        self.assertIn(code(relay.MAX_IN + 4), open_)

    def test_a_no_holds_for_no_wait(self):
        f = {"status": "no", "name": "Max", "t": time.time() - 3600}
        s = {"profile": {"id": ME[0]}, "relay": {"friends": {"AAAAAAAAAAAAAAAA": f}}}
        self.assertIsNone(relay.apply(s, env("friend", {"name": "Max"})))
        self.assertEqual(f["status"], "no")
        f["t"] = time.time() - relay.NO_WAIT - 60
        self.assertEqual(relay.apply(s, env("friend", {"name": "Max"}))["kind"], "friend")
        self.assertEqual(s["relay"]["friends"]["AAAAAAAAAAAAAAAA"]["status"], "in")

    def test_a_friends_boards_at_most_max_slots(self):
        s = {"profile": {"id": ME[0]},
             "relay": {"friends": {"AAAAAAAAAAAAAAAA": {"status": "ok", "name": "Anna", "pid": "a" * 32, "sign_pk": "x"}}}}
        for i in range(relay.MAX_SLOTS):
            self.assertEqual(relay.apply(s, env("board_key", {"game": "mtg", "slot": f"s{i}", "key": "k"}))["kind"],
                             "board_key")
        self.assertIsNone(relay.apply(s, env("board_key", {"game": "mtg", "slot": "one-more", "key": "k"})))
        self.assertEqual(relay.apply(s, env("board_key", {"game": "mtg", "slot": "s3", "key": "k2"}))["kind"], "board_key")
        b = s["relay"]["friends"]["AAAAAAAAAAAAAAAA"]["boards"]
        self.assertEqual(len(b), relay.MAX_SLOTS)
        self.assertEqual(b["mtg/s3"]["key"], "k2")

    def test_board_names_and_keys_checked(self):
        s = {"profile": {"id": ME[0]},
             "relay": {"friends": {"AAAAAAAAAAAAAAAA": {"status": "ok", "name": "Anna", "pid": "a" * 32, "sign_pk": "x"}}}}
        for body in ({"game": "x" * 1000, "slot": "lists", "key": "k"}, {"game": "mtg", "slot": "../x", "key": "k"},
                     {"game": "mtg", "slot": "lists", "key": "k" * 101}, {"game": "mtg", "slot": "lists", "key": 5}):
            self.assertIsNone(relay.apply(s, env("board_key", body)), body)
        self.assertNotIn("boards", s["relay"]["friends"]["AAAAAAAAAAAAAAAA"])


class Closing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.patches = [mock.patch.object(offers, "FILE", root / "mine" / "offers.json"),
                        mock.patch("scanner.common.DATA", root / "data")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def offer(self, tid, give=None, get=None, money=0.0):
        """My offer to Anna (sent) – the version on the table."""
        t = ticket.new(ME, ANNA, give or [list(CARD)], get or [list(CARD)], trade_id=tid, money=money)
        offers.record_sent(t)
        return t

    def closing(self, tid, give=None, get=None, money=0.0):
        """Anna's closing ticket: her give is my get."""
        return ticket.new(ANNA, ME, give or [list(CARD)], get or [list(CARD)], trade_id=tid, kind="f", money=money)

    def test_mirror_is_closing(self):
        self.offer("t1", money=2.5)
        self.assertEqual(offers.from_mailbox(self.closing("t1", money=-2.5), ME[0]), "closing")

    def test_no_offer_here_is_an_offer(self):
        self.assertEqual(offers.from_mailbox(self.closing("t2"), ME[0]), "received")
        self.assertEqual(offers.get("t2")["status"], "received")

    def test_other_cards_counts_or_money_are_an_offer(self):
        two = CARD[:4] + [2, CARD[5]]   # the same card, another count
        for tid, kw in (("c", {"give": [two]}), ("m", {"money": -5.0}),
                        ("x", {"give": [["mh2", "51", "en", 0, 1, "Other"]]})):
            self.offer(tid)
            self.assertEqual(offers.from_mailbox(self.closing(tid, **kw), ME[0]), "received", tid)

    def test_ports_cases(self):
        """ports' cases 10.11.: Bolt against 2× Counterspell, I pay 1.50 – mirrored: closing; 4× Bolt, 9 € or without
        Bolt: received; foil true and 1 count the same."""
        bolt, cs2 = ["2xm", "117", "en", 0, 1, "Lightning Bolt"], ["mh2", "50", "en", 0, 2, "Counterspell"]
        cases = {"p1": ([bolt], [cs2], 1.5, [cs2], [bolt], -1.5, "closing"),
                 "p2": ([bolt], [cs2], 1.5, [cs2], [bolt[:4] + [4, bolt[5]]], -1.5, "received"),
                 "p3": ([bolt], [cs2], 1.5, [cs2], [bolt], -9.0, "received"),
                 "p4": ([bolt], [cs2], 1.5, [cs2], [], -1.5, "received")}
        for tid, (give, get, m, her_give, her_get, her_m, want) in cases.items():
            self.offer(tid, give=[list(c) for c in give], get=[list(c) for c in get], money=m)
            t = self.closing(tid, give=[list(c) for c in her_give], get=[list(c) for c in her_get], money=her_m)
            self.assertEqual(offers.from_mailbox(t, ME[0]), want, tid)
            self.assertEqual(offers.get(tid)["status"], want, tid)
        foil1, foil_true = ["mh2", "9", "en", 1, 1, "X"], ["mh2", "9", "en", True, 1, "X"]
        self.assertTrue(offers.same_deal(ticket.new(ME, ANNA, [foil1], [], trade_id="f"),
                                         ticket.new(ANNA, ME, [], [foil_true], trade_id="f", kind="f"), ME[0]))

    def test_same_deal_any_order(self):
        a, b = ["mh2", "1", "en", 0, 1, "A"], ["mh2", "2", "en", 1, 3, "B"]
        x = ticket.new(ME, ANNA, [a, b], [], trade_id="o")
        y = ticket.new(ANNA, ME, [], [b, a], trade_id="o", kind="f")
        self.assertTrue(offers.same_deal(x, y, ME[0]))

    def test_image_of_a_mismatching_closing_ticket_is_filed_not_booked(self):
        from ui import tradeview
        import games
        self.offer("t9")
        bad = self.closing("t9", money=-9.0)
        import types
        page = types.SimpleNamespace(ctrl=mock.Mock(settings={"profile": {"id": ME[0], "name": "Me"}}), toast=mock.Mock(),
                                     book_ticket=mock.Mock(side_effect=AssertionError("booked")))
        receive = lambda t: tradeview.TradePage.receive_ticket(page, t)   # noqa: E731 – the page's logic, no window
        with mock.patch.object(games, "current", return_value=mock.Mock(key="mtg")), \
                mock.patch.object(games, "choices", return_value=[{"key": "mtg", "ready": True}]):
            receive(bad)
            self.assertEqual(offers.get("t9")["status"], "received")
            page.toast.assert_called_once_with(tradeview.tr(tradeview.CLOSING_DIFFERS))
            self.offer("t10")   # another trade: its closing ticket mirrors my offer
            good = self.closing("t10")
            page.book_ticket = mock.Mock(return_value="booked")
            self.assertEqual(receive(good), "booked")   # the mirror: booking as before

    def test_german(self):
        from locales import de
        from ui import tradeview
        self.assertIn(tradeview.CLOSING_DIFFERS, de.TEXTS)


if __name__ == "__main__":
    unittest.main()
