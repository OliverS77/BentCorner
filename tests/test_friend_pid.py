"""Review 08.11. (H2-1, live in 0.9.6): a friend's profile ID is fixed once known. Lists, binders and tickets are filed
by it – a friend who later sends another ID (or the ID of another friend) must not take over that friend's files or
tickets on this PC.

    python -m unittest tests.test_friend_pid
"""
import unittest
from unittest import mock

from net import relay

A, B, C = "AAAAAAAAAAAAAAAA", "BBBBBBBBBBBBBBBB", "CCCCCCCCCCCCCCCC"


def settings():
    return {"relay": {"friends": {
        A: {"name": "Anna", "pid": "pidAnna", "status": "ok", "sign_pk": "ka"},
        B: {"name": "Ben", "pid": "pidBen", "status": "ok", "sign_pk": "kb"}}}}


def owners(s, pid):
    """Which friends carry this profile ID (what lists, binders and tickets are filed by)."""
    return [c for c, f in s["relay"]["friends"].items() if f.get("pid") == pid]


def parcel(frm, kind, pid, name="X"):
    return {"from": frm, "kind": kind, "body": {"name": name, "pid": pid}, "_sign_pk": "k"}


class FriendPid(unittest.TestCase):
    def apply(self, s, env):
        with mock.patch.object(relay, "_clean_person", lambda body: {"name": body["name"], "back": None,
                                                                    "pid": body["pid"]}):
            return relay.apply(s, env)

    def test_friend_ok_cannot_change_the_id(self):
        s = settings()
        self.apply(s, parcel(B, "friend_ok", "pidAnna", "Ben neu"))
        f = s["relay"]["friends"][B]
        self.assertEqual(f["pid"], "pidBen", "the ID stays")
        self.assertEqual(f["name"], "Ben neu", "name and back may change")
        self.assertEqual(owners(s, "pidAnna"), [A])

    def test_friend_request_cannot_change_the_id(self):
        s = settings()
        self.apply(s, parcel(B, "friend", "pidOther"))
        self.assertEqual(s["relay"]["friends"][B]["pid"], "pidBen")

    def test_a_new_contact_cannot_take_a_friends_id(self):
        s = settings()
        self.apply(s, parcel(C, "friend", "pidAnna"))
        self.assertEqual(s["relay"]["friends"][C]["pid"], "", "an ID another friend has is not taken")
        self.assertEqual(owners(s, "pidAnna"), [A])

    def test_first_id_is_taken(self):
        s = settings()
        s["relay"]["friends"][C] = {"name": "", "pid": "", "status": "out", "sign_pk": "kc"}
        self.apply(s, parcel(C, "friend_ok", "pidCarl", "Carl"))
        self.assertEqual(s["relay"]["friends"][C]["pid"], "pidCarl")


if __name__ == "__main__":
    unittest.main()
