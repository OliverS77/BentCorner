"""List deltas with a PC clock that is off (ports, desk-deltatime 06.11.2026, lead): the base of a delta is the server's
time of the post (what friends get when they fetch it), not the PC's – otherwise every delta missed and the friend
fetched the old post again. If the server's time can't be worked out, the PC's time stays: then a delta only means
"fetch it anew", never something applied wrongly.

    python -m unittest tests/test_delta_time.py
"""
import time
import unittest
from unittest import mock

from net import relay
from tests.test_share_per_friend import A, Mailbox, settings

TTL = relay.BOARD_DAYS * 86400


class ServerTime(unittest.TestCase):
    def test_from_until(self):
        for skew in (1, -1, 300, -300):
            now = 1_800_000_000
            self.assertEqual(relay.server_time({"until": now + TTL}, now + skew), now)

    def test_t_wins_if_the_server_sends_it(self):
        self.assertEqual(relay.server_time({"t": 1_800_000_005, "until": 1}, 1_800_000_000), 1_800_000_005)

    def test_other_ttl_on_the_server_keeps_the_pc_time(self):
        now = 1_800_000_000
        self.assertEqual(relay.server_time({"until": now + 90 * 86400}, now + 3), now + 3)

    def test_no_answer_keeps_the_pc_time(self):
        self.assertEqual(relay.server_time({}, 42), 42)
        self.assertEqual(relay.server_time({"until": "x"}, 42), 42)


class Post(unittest.TestCase):
    def post_with_skew(self, skew, answer):
        """answer(srv) -> the server's reply to board/put; the PC's clock is skew seconds off."""
        s = settings(posted=False)
        relay.share_codes(s)
        relay.set_share(s, A, True)
        srv = int(time.time())
        with Mailbox() as mb, mock.patch.object(relay, "_post", side_effect=lambda *a, **k: answer(srv)), \
                mock.patch.object(relay.time, "time", return_value=srv + skew):
            relay.board_put(s, "mtg", "lists", {"c": [1]})
        return relay.posted(s, "mtg")["t"], srv, mb

    def test_answer_with_t(self):
        """Gordon's board-zeit (b87d434): {"ok", "t", "until"} – t is what board/get returns later."""
        for skew in (1, -1, 300, -300):
            t, srv, mb = self.post_with_skew(skew, lambda srv: {"ok": True, "t": srv - 1, "until": srv - 1 + TTL})
            self.assertEqual(t, srv - 1, skew)
            self.assertEqual([b["t"] for to, kind, b in mb.parcels if kind == "board_key"], [srv - 1])

    def test_answer_without_t(self):
        for skew in (1, -1, 300, -300):
            t, srv, _ = self.post_with_skew(skew, lambda srv: {"ok": True, "until": srv + TTL})
            self.assertEqual(t, srv, skew)

    def test_answer_without_until(self):
        """Nothing to go by: the PC's time – the friend then fetches the post anew instead of applying a delta."""
        for skew in (1, -300):
            t, srv, _ = self.post_with_skew(skew, lambda srv: {"ok": True})
            self.assertEqual(t, srv + skew)


class Receiver(unittest.TestCase):
    def friend_with_board(self, fetched):
        s = settings(posted=False, friends=(A,))
        relay.friends(s)[A].update(pid="p-anna", boards={"mtg/lists": {"key": "k", "fetched": fetched}})
        return s

    def delta(self, s, base):
        env = {"from": A, "kind": "list_delta", "game": "mtg", "body": {"base": base, "d": {"lea|1|en|0": 2}, "id": "p-anna"}}
        with mock.patch.object(relay, "apply_delta", return_value=True) as ap:
            ev = relay.apply(s, env)
        return ev, ap.called

    def test_same_post_applies(self):
        for base in (1000, 1001, 999, 1002):   # the server's stamp and "until" can be a second apart
            ev, applied = self.delta(self.friend_with_board(1000), base)
            self.assertTrue(applied, base)
            self.assertFalse(ev["refetch"])

    def test_pc_time_off_by_minutes_means_fetch_anew(self):
        """An older sender (its own clock as the base) or a server with another TTL: never applied – fetched anew."""
        for base in (1300, 700, 1005):
            ev, applied = self.delta(self.friend_with_board(1000), base)
            self.assertFalse(applied, base)
            self.assertTrue(ev["refetch"])


if __name__ == "__main__":
    unittest.main()
