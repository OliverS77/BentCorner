"""Sharing per friend (lead/legal 06.11.2026, ports' review): only the friends switched on get the keys of what I share
and the list deltas. New friends get nothing but name and card back; no audience = nobody (a new device); a friend
switched off gets no new key, their app is asked to delete my content, and the old key opens nothing new.

    python -m unittest tests/test_share_per_friend.py
"""
import base64
import json
import types
import unittest
import zlib
from unittest import mock

from net import relay, relay_ctl

A, B, C = "A" * 16, "B" * 16, "C" * 16


def friend(name):
    return {"name": name, "status": "ok", "sign_pk": "PK"}


def settings(posted=True, audience=None, friends=(A, B)):
    st = {"on": True, "friends": {c: friend(c[0]) for c in friends}}
    if posted:
        st["posted"] = {"mtg/lists": {"t": 1, "until": 2, "to": list(friends)}}
    if audience is not None:
        st["audience"] = audience
    return {"relay": st, "profile": {"id": "p-me", "name": "Ich", "back": None}}


class Mailbox:
    """board_put / send without a network: what was posted and which parcels went where."""

    def __init__(self):
        self.posts, self.parcels = [], []

    def __enter__(self):
        self.ps = [mock.patch.object(relay, "register"), mock.patch.object(relay, "my_code", return_value="M" * 16),
                   mock.patch.object(relay, "_signed", return_value="sig"),
                   mock.patch.object(relay, "_post", side_effect=self.post),
                   mock.patch.object(relay, "send", side_effect=self.send)]
        for p in self.ps:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self.ps:
            p.stop()

    def post(self, settings, path, body):
        self.posts.append(body)
        return {"until": 999}

    def send(self, settings, to, kind, body, **kw):
        self.parcels.append((to, kind, body))

    def keys_to(self, code):
        return [b["key"] for to, kind, b in self.parcels if to == code and kind == "board_key"]


class Audience(unittest.TestCase):
    def test_update_keeps_todays_friends_where_this_device_shared(self):
        s = settings(posted=True)
        self.assertEqual(sorted(relay.share_codes(s)), [A, B])

    def test_no_audience_means_nobody(self):
        """A new device (nothing posted from here) – even with friends: nobody, never everybody."""
        s = settings(posted=False)
        self.assertEqual(relay.share_codes(s), [])
        self.assertEqual(relay.state(s)["audience"], {"mode": "only", "codes": []})

    def test_a_new_friend_starts_off(self):
        s = settings(posted=True)
        relay.share_codes(s)                                   # the update ran
        relay.friends(s)[C] = friend("C")                      # paired afterwards
        self.assertNotIn(C, relay.share_codes(s))
        relay.set_share(s, C, True)
        self.assertIn(C, relay.share_codes(s))

    def test_removed_or_blocked_friend_starts_off_when_back(self):
        s = settings(posted=True)
        relay.share_codes(s)
        relay.remove_friend(s, B)
        relay.block(s, A)
        self.assertNotIn(A, relay.state(s)["audience"]["codes"])
        relay.friends(s)[B] = friend("B")                      # accepted again later
        self.assertNotIn(B, relay.share_codes(s))


class NewFriendGetsNothing(unittest.TestCase):
    """lead 06.11.: a newly paired friend gets NOTHING but name and card back after a full share."""

    def test_full_share(self):
        s = settings(posted=True)
        relay.share_codes(s)
        relay.friends(s)[C] = friend("C")
        with Mailbox() as mb:
            relay.send_lists(s, {"c": [["lea", "1", "en", 0, 1]], "w": [], "lib": [["lea", "1", "en", 0, 1]]}, game="mtg")
            relay.board_put(s, "mtg", "binder-x", {"cards": []})           # a binder (audience None: the default)
            relay.send_delta(s, "mtg", 1, {"lea|1|en|0": 2}, "p-me")
        self.assertEqual(mb.keys_to(C), [])
        self.assertFalse([p for p in mb.parcels if p[0] == C])
        self.assertEqual(len(mb.keys_to(A)), 2)
        self.assertEqual(relay._me(s), {"name": "Ich", "back": relay._me(s)["back"], "pid": "p-me"})   # the request

    def test_controller_paths_use_the_audience(self):
        """relay_send_lists, relay_send_delta and qbinder.share_put all ask relay.share_codes."""
        s = settings(posted=True)
        relay.share_codes(s)
        relay.friends(s)[C] = friend("C")
        got = []
        ctrl = types.SimpleNamespace(settings=s, _relay_bg=lambda what, fn: got.append(what))
        with mock.patch.object(relay, "send_lists", side_effect=lambda st, d, game=None, audience=None: got.append(audience)), \
                mock.patch("games.current", return_value=types.SimpleNamespace(key="mtg")):
            relay_ctl.RelayControl.relay_send_lists(types.SimpleNamespace(
                settings=s, relay_export=lambda: {"c": [1], "w": []}, _relay_bg=lambda what, fn: fn()), quiet=True)
        self.assertEqual([a for a in got if isinstance(a, list)], [[A, B]])
        del ctrl


class SwitchedOff(unittest.TestCase):
    def test_no_new_key_and_the_old_one_opens_nothing(self):
        from nacl.secret import SecretBox
        from nacl.exceptions import CryptoError
        s = settings(posted=True)
        relay.share_codes(s)
        with Mailbox() as mb:
            relay.board_put(s, "mtg", "lists", {"c": [1], "lib": [2]})
            old_b = mb.keys_to(B)[-1]
            relay.set_share(s, B, False)                         # first the audience …
            relay.revoke(s, B, relay.revoke_plan(s, B))          # … their app is asked to delete …
            relay.board_put(s, "mtg", "lists", {"c": [1]})       # … then the new key
        self.assertEqual(len(mb.keys_to(B)), 1)                  # no second key for B
        self.assertEqual(len(mb.keys_to(A)), 2)
        self.assertNotEqual(mb.keys_to(A)[-1], old_b)
        new = mb.posts[-1]["data"]
        with self.assertRaises(CryptoError):
            SecretBox(base64.b64decode(old_b)).decrypt(base64.b64decode(new))
        raw = SecretBox(base64.b64decode(mb.keys_to(A)[-1])).decrypt(base64.b64decode(new))
        self.assertEqual(json.loads(zlib.decompress(raw)), {"c": [1]})
        self.assertIn((B, "board_gone", {"game": "mtg", "slot": "lists"}), mb.parcels)
        self.assertNotIn(B, relay.posted(s, "mtg")["to"])

    def test_no_delta_after_switching_off(self):
        """ports 06.11.: the audience is saved before anything else – the regular delta does not reach them."""
        s = settings(posted=True)
        relay.share_codes(s)
        relay.set_share(s, B, False)
        with Mailbox() as mb:
            relay.send_delta(s, "mtg", 1, {"lea|1|en|0": 2}, "p-me")
        self.assertEqual({p[0] for p in mb.parcels}, {A})

    def test_controller_order(self):
        """relay_share_friend: audience saved, revoke decided, then relay_rekey."""
        s = settings(posted=True)
        relay.share_codes(s)
        calls = []
        fake = types.SimpleNamespace(settings=s, settings_changed=lambda: calls.append("saved"),
                                     _relay_bg=lambda what, fn: calls.append(what),
                                     relay_rekey=lambda: calls.append("rekey" if B not in relay.share_codes(s) else "rekey-too-early"))
        relay_ctl.RelayControl.relay_share_friend(fake, B, False)
        self.assertEqual(calls, ["saved", "revoke", "rekey"])


class Slots(unittest.TestCase):
    def test_twenty_at_most(self):
        s = settings(posted=True)
        relay.state(s)["posted"] = {f"mtg/binder-{i}": {"to": []} for i in range(relay.MAX_SLOTS)}
        with Mailbox():
            with self.assertRaises(relay.RelayError):
                relay.board_put(s, "pokemon", "lists", {"c": []})
            relay.board_put(s, "mtg", "binder-3", {"cards": []})   # replacing one of them is fine


class Page(unittest.TestCase):
    """The page is built from the same source as the parcel: chips = relay_share_contents × share_codes."""

    def ctrl(self, s, contents):
        return types.SimpleNamespace(settings=s, relay_share_contents=lambda: contents)

    def view(self, s, contents):
        from ui import qshared
        with mock.patch("collection.trade.lists", return_value=[]), mock.patch("ui.qbinder.all_binders", return_value=[]):
            return qshared.overview(self.ctrl(s, contents))

    def test_chips_follow_the_parcel(self):
        s = settings(posted=True, friends=(A, B, C))
        relay.share_codes(s)                                   # A, B, C from before …
        relay.set_share(s, C, False)                           # … C switched off
        c = {"library": True, "lists": [("wish", {"id": "w1", "name": "Wünsche"})],
             "binders": [("mtg", {"id": "b1", "name": "Staples"})]}
        v = self.view(s, c)
        rows = {f["code"]: f for f in v["friends"]}
        self.assertEqual([x["text"] for x in rows[A]["chips"]][1:], ["Library", "Wünsche", "Binder „Staples“"])
        self.assertTrue(all(x["on"] for x in rows[A]["chips"]))
        self.assertEqual([x["on"] for x in rows[C]["chips"]], [True, False, False, False])   # name + back only
        self.assertIn("2 friends", v["card"]["text"])          # exactly those who get it
        self.assertIn("1 list and 1 binder with these 2 friends", v["also"])

    def test_no_card_after_the_answer_or_without_library(self):
        s = settings(posted=True)
        c = {"library": False, "lists": [], "binders": []}
        self.assertEqual(self.view(s, c)["card"], {})
        s["share_library_confirmed"] = True
        self.assertEqual(self.view(s, dict(c, library=True))["card"], {})

    def test_menu_line_counts_friends(self):
        from ui import qprofile
        s = settings(posted=True)
        relay.share_codes(s)
        relay.set_share(s, B, False)
        c = {"library": True, "lists": [], "binders": []}
        b = qprofile.ProfileBackend(types.SimpleNamespace(settings=s, relay_share_contents=lambda: c))
        self.assertIn("with 1 friend (", b.libShare["text"])

    def test_german_counts(self):
        """Singular, plural, no zero – and the dative "Freunden" after "mit" (de)."""
        from system import i18n
        from ui import qshared
        old = i18n.LANG
        try:
            i18n.set_language("de")
            self.assertEqual(qshared.things(1, 0), "1 Liste")
            self.assertEqual(qshared.things(2, 1), "2 Listen und 1 Binder")
            self.assertEqual(qshared.library_line(1), "Du teilst deine ganze Bibliothek mit 1 Freund (alle Karten und Anzahlen).")
            self.assertEqual(qshared.library_line(3), "Du teilst deine ganze Bibliothek mit 3 Freunden (alle Karten und Anzahlen).")
            w = qshared.things(1, 2)
            self.assertEqual(i18n.tr(f"In addition you share {w} with these 4 friends – change them one by one below."),
                             "Außerdem teilst du 1 Liste und 2 Binder mit diesen 4 Freunden – unten einzeln änderbar.")
        finally:
            i18n.set_language(old)


if __name__ == "__main__":
    unittest.main()
