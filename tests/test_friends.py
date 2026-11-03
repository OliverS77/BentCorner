"""Friends (test plan 1.8, what test_relay_block and server/box/test_box don't cover yet): send a request, accept,
decline, both at the same time, incoming parcels from blocked or unknown people are ignored, lists and keys only from
friends. Nothing goes on the network (relay.send / lookup replaced), no data folder is touched.

    python -m unittest tests/test_friends.py
"""
import unittest
from unittest import mock

from net import relay

ME = relay.norm("AAAA-BBBB-CCCC-DDDD")   # IDs are kept normalized (no dashes, capitals)
BEN = relay.norm("7F3A-21C9-0B44-E1D2")


class Friends(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.p = [mock.patch.object(relay, "my_code", lambda s: ME),
                  mock.patch.object(relay, "lookup", lambda s, code: "PK-" + code),
                  mock.patch.object(relay, "send", lambda s, code, kind, body, sign_pk=None:
                                    self.sent.append((code, kind))),
                  mock.patch.object(relay, "server_block", lambda s, code, on: self.sent.append((code, "block", on))),
                  mock.patch.object(relay, "_me", lambda s: {"name": "Me", "back": None, "pid": "p-me"}),
                  mock.patch.object(relay, "_drop_friend_files", lambda pid: None),
                  mock.patch.object(relay, "_patch_friend_files", lambda pid, back: None)]
        for p in self.p:
            p.start()
        self.s = {}

    def tearDown(self):
        for p in self.p:
            p.stop()

    def parcel(self, kind, body=None, frm=BEN):
        return relay.apply(self.s, {"from": frm, "kind": kind, "body": body or {"name": "Bene", "pid": "p-ben"},
                                    "_sign_pk": "PK-" + frm})

    def test_request_validation(self):
        with self.assertRaises(relay.RelayError):
            relay.request_friend(self.s, "not an id")
        with self.assertRaises(relay.RelayError):
            relay.request_friend(self.s, ME)                     # own ID
        self.assertEqual(self.sent, [])

    def test_request_then_accepted(self):
        f = relay.request_friend(self.s, "7f3a 21c9-0b44 e1d2")   # typed sloppily
        self.assertEqual(f["status"], "out")
        self.assertEqual(self.sent, [(BEN, "friend")])
        ev = self.parcel("friend_ok")
        self.assertEqual((ev["kind"], relay.friends(self.s)[BEN]["status"]), ("friend_ok", "ok"))

    def test_incoming_accept_and_decline(self):
        self.assertEqual(self.parcel("friend")["kind"], "friend")
        self.assertEqual(relay.friends(self.s)[BEN]["status"], "in")
        relay.answer_friend(self.s, BEN, True)
        self.assertEqual((relay.friends(self.s)[BEN]["status"], self.sent[-1]), ("ok", (BEN, "friend_ok")))
        other = relay.norm("1111-2222-3333-4444")
        self.parcel("friend", frm=other)
        relay.answer_friend(self.s, other, False)
        self.assertEqual(relay.friends(self.s)[other]["status"], "no")   # declined, not blocked
        self.assertNotIn((other, "block", True), self.sent)

    def test_both_at_once_become_friends(self):
        relay.request_friend(self.s, BEN)
        self.assertEqual(self.parcel("friend")["kind"], "friend_ok")
        self.assertEqual(relay.friends(self.s)[BEN]["status"], "ok")

    def test_decline_reply_only_for_open_request(self):
        relay.request_friend(self.s, BEN)
        self.parcel("friend_no")
        self.assertEqual(relay.friends(self.s)[BEN]["status"], "no")
        relay.friends(self.s)[BEN]["status"] = "ok"
        self.assertIsNone(self.parcel("friend_no"))                      # already friends: ignored
        self.assertEqual(relay.friends(self.s)[BEN]["status"], "ok")

    def test_blocked_sends_nothing_through(self):
        self.parcel("friend")
        relay.answer_friend(self.s, BEN, None)                           # "decline and block"
        self.assertIn((BEN, "block", True), self.sent)
        for kind in ("friend", "friend_ok", "board_key", "list_delta", "board_gone"):
            self.assertIsNone(self.parcel(kind, {"name": "Bene", "game": "mtg", "slot": "lists", "key": "k"}), kind)
        f = relay.friends(self.s)[BEN]
        self.assertEqual((f["status"], f.get("boards")), ("blocked", None))   # no new request, no key stored
        self.assertIsNone(relay.shown_back(dict(f, back="x")))

    def test_strangers_cannot_send_lists_or_keys(self):
        for kind in ("board_key", "list_delta", "friend_ok", "friend_no"):
            self.assertIsNone(self.parcel(kind, {"game": "mtg", "slot": "lists", "key": "k"}, frm=relay.norm("9999-8888-7777-6666")), kind)
        self.assertNotIn(relay.norm("9999-8888-7777-6666"), relay.friends(self.s))

    def test_pending_request_gets_no_keys(self):
        self.parcel("friend")                                             # only "in", not accepted yet
        self.assertIsNone(self.parcel("board_key", {"game": "mtg", "slot": "lists", "key": "k"}))
        self.assertNotIn("boards", relay.friends(self.s)[BEN])

    def test_unblock_allows_a_new_start(self):
        relay.block(self.s, BEN)
        relay.unblock(self.s, BEN)
        self.assertEqual(self.parcel("friend")["kind"], "friend")


if __name__ == "__main__":
    unittest.main()
