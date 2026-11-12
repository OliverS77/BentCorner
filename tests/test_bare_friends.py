"""Friends on the mailbox who share nothing yet show in the friends menu and the rail too (lead 07.11., like the web):
„No friends yet“ only when there really are none. Pending / blocked / already listed friends are not added. In memory.

    python -m unittest tests/test_bare_friends.py
"""
import unittest

from ui import qtrade_friends


def settings(**friends):
    return {"relay": {"on": True, "friends": friends}}


class BareFriendsTest(unittest.TestCase):
    def test_only_accepted_without_a_file(self):
        s = settings(A1={"status": "ok", "name": "Anna", "pid": "p-anna"},
                     B2={"status": "ok", "name": "Ben", "pid": "p-ben"},
                     C3={"status": "in", "name": "Cleo", "pid": "p-cleo"},
                     D4={"status": "blocked", "name": "Dan", "pid": "p-dan"})
        out = qtrade_friends.bare_friends(s, {"p-ben"})   # Ben already has a list file
        self.assertEqual([(f["name"], f["fid"], f["bare"]) for f in out], [("Anna", "p-anna", True)])
        self.assertEqual(out[0]["folder"], "")
        self.assertEqual(out[0]["n"], 0)

    def test_none(self):
        self.assertEqual(qtrade_friends.bare_friends(settings(), set()), [])


if __name__ == "__main__":
    unittest.main()
