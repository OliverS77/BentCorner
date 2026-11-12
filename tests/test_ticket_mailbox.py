"""Trade tickets through the mailbox (lead/legal 06.11.2026, Oliver: in 0.9.7): a one-off parcel to exactly one friend,
slot "tk-<trade ID>" (a newer version / the withdrawal replaces one not fetched yet), accepted only from a friend whose
profile ID issued the ticket and only if it is issued to me; filed under Trade offers without a dialog, in the ticket's
game; a closing ticket waits to be booked; a withdrawal marks the open offer."""
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import offers, ticket
from net import relay

ME, ANNA, BEN = ("m" * 32, "Me"), ("a" * 32, "Anna"), ("b" * 32, "Ben")
CARD = ["mh2", "50", "en", 0, 1, "Counterspell"]
ANNA_CODE = "A" * 16


def settings(pid=ANNA[0], status="ok"):
    return {"profile": {"id": ME[0], "name": "Me"},
            "relay": {"friends": {ANNA_CODE: {"status": status, "name": "Anna", "pid": pid, "sign_pk": "x"}}}}


def env(kind, body):
    return {"kind": kind, "from": ANNA_CODE, "body": body, "_sign_pk": "x"}


class Apply(unittest.TestCase):
    def offer(self, frm=ANNA, to=ME):
        return ticket.new(frm, to, [list(CARD)], [list(CARD)])

    def test_an_offer_from_the_friend_to_me(self):
        t = self.offer()
        ev = relay.apply(settings(), env("ticket", {"tk": t}))
        self.assertEqual(ev["kind"], "ticket")
        self.assertEqual(ev["ticket"]["id"], t["id"])

    def test_not_issued_by_that_friend_or_not_to_me_is_dropped(self):
        self.assertIsNone(relay.apply(settings(), env("ticket", {"tk": self.offer(frm=BEN)})))   # Anna sends Ben's
        self.assertIsNone(relay.apply(settings(), env("ticket", {"tk": self.offer(to=BEN)})))    # not to me
        self.assertIsNone(relay.apply(settings(pid=""), env("ticket", {"tk": self.offer()})))   # profile ID unknown
        self.assertIsNone(relay.apply(settings(status="in"), env("ticket", {"tk": self.offer()})))   # no friend yet
        self.assertIsNone(relay.apply(settings(), env("ticket", {"tk": "nonsense"})))

    def test_withdrawn(self):
        ev = relay.apply(settings(), env("ticket_gone", {"x": "c0ffee01", "n": 2}))
        self.assertEqual((ev["kind"], ev["x"], ev["n"], ev["pid"]), ("ticket_gone", "c0ffee01", 2, ANNA[0]))
        self.assertIsNone(relay.apply(settings(), env("ticket_gone", {"x": "../evil"})))


class Send(unittest.TestCase):
    def test_slot_per_trade_and_the_withdrawal_replaces_it(self):
        t = ticket.new(ME, ANNA, [list(CARD)], [], trade_id="c0ffee01")
        with mock.patch.object(relay, "send") as send:
            relay.send_ticket(settings(), ANNA_CODE, t)
            relay.send_ticket_gone(settings(), ANNA_CODE, "c0ffee01", 1)
        (a, kw), (b, kw2) = [(c.args, c.kwargs) for c in send.call_args_list]
        self.assertEqual((a[2], kw["slot"]), ("ticket", "tk-c0ffee01"))
        self.assertEqual((b[2], kw2["slot"], b[3]), ("ticket_gone", "tk-c0ffee01", {"x": "c0ffee01", "n": 1, "why": "withdrawn"}))
        with mock.patch.object(relay, "send") as send:
            relay.send_ticket_gone(settings(), ANNA_CODE, "c0ffee01", 2, "declined")   # lead 06.11.: declining tells them
        self.assertEqual(send.call_args.args[3], {"x": "c0ffee01", "n": 2, "why": "declined"})
        self.assertEqual(relay.friend_of_profile(settings(), ANNA[0]), ANNA_CODE)
        self.assertIsNone(relay.friend_of_profile(settings(status="out"), ANNA[0]))

    def test_errors_carry_the_status(self):
        r = mock.Mock(status_code=507, json=lambda: {"error": "Fach voll"})
        with mock.patch("net.netpolite.post", return_value=r):
            with self.assertRaises(relay.RelayError) as e:
                relay._post({}, "/v1/send", {})
        self.assertEqual(e.exception.status, 507)


class Intake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.mine = root / "mine"
        self.patches = [mock.patch.object(offers, "FILE", self.mine / "offers.json"),
                        mock.patch("scanner.common.DATA", root / "data")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_offer_then_closing_then_nothing_twice(self):
        t = ticket.new(ANNA, ME, [list(CARD)], [list(CARD)], trade_id="t1")
        self.assertEqual(offers.from_mailbox(t, ME[0]), "received")
        self.assertIsNone(offers.from_mailbox(t, ME[0]))   # the same ticket again (or once as an image)
        self.assertEqual(offers.get("t1")["status"], "received")
        closing = ticket.new(ANNA, ME, [list(CARD)], [list(CARD)], trade_id="t1", kind="f")
        self.assertEqual(offers.from_mailbox(closing, ME[0]), "closing")
        self.assertEqual(offers.get("t1")["status"], "closing")
        self.assertIn("closing", offers.OPEN)

    def test_another_games_ticket_goes_into_that_games_file(self):
        import games
        c = ["sv1", "1", "en", 0, 1, "Pikachu", "pokemon"]
        t = ticket.new(ANNA, ME, [c], [], trade_id="p1")
        self.assertEqual(ticket.game_of(t), "pokemon")
        with mock.patch.object(games, "current", return_value=mock.Mock(key="mtg")):
            self.assertEqual(offers.from_mailbox(t, ME[0]), "received")
            self.assertIsNone(offers.get("p1"))   # not in the open game's file
            self.assertEqual(offers.get("p1", "pokemon")["status"], "received")

    def test_withdrawn_marks_only_the_friends_open_offer(self):
        import games
        t = ticket.new(ANNA, ME, [list(CARD)], [], trade_id="t2")
        offers.from_mailbox(t, ME[0])
        with mock.patch.object(games, "GAMES", [("mtg", "Magic", True)]), \
                mock.patch.object(games, "mine", side_effect=lambda k, *p: self.mine.joinpath(*p)):
            self.assertFalse(offers.gone_from_mailbox("t2", BEN[0]))   # someone else can't withdraw it
            self.assertTrue(offers.gone_from_mailbox("t2", ANNA[0]))
            self.assertEqual(offers.get("t2")["status"], "withdrawn")
            t3 = ticket.new(ME, ANNA, [list(CARD)], [], trade_id="t3")
            offers.record_sent(t3)
            self.assertTrue(offers.gone_from_mailbox("t3", ANNA[0], "declined"))   # Anna declined my offer
            self.assertEqual(offers.get("t3")["status"], "declined")
        ev = relay.apply(settings(), env("ticket_gone", {"x": "t3", "n": 1, "why": "declined"}))
        self.assertEqual(ev["why"], "declined")



class Undelivered(unittest.TestCase):
    """lead 07.11.: an offer the mailbox couldn't deliver says "Not delivered", not "waiting for an answer"."""

    def test_the_state_follows_the_delivery(self):
        o = {"id": "x", "status": "sent"}
        self.assertEqual(offers.status_text(o), offers.STATUS_TEXT["sent"])            # only shared as an image
        for status in (507, 403):
            o["mail"] = {"ok": False, "status": status, "t": 1}
            self.assertTrue(offers.undelivered(o))
            self.assertEqual(offers.status_text(o), "Not delivered")
        o["mail"] = {"ok": True, "status": 200, "t": 2}                                  # delivered (again)
        self.assertFalse(offers.undelivered(o))
        self.assertEqual(offers.status_text(o), offers.STATUS_TEXT["sent"])
        done = {"id": "y", "status": "accepted", "mail": {"ok": False, "status": 507}}
        self.assertFalse(offers.undelivered(done))                                       # closed: no line any more
        self.assertEqual(offers.status_text(done), offers.STATUS_TEXT["accepted"])

    def test_german(self):
        from locales import de
        self.assertEqual(de.TEXTS["Not delivered"], "Nicht zugestellt")


if __name__ == "__main__":
    unittest.main()
