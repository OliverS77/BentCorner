"""A friend has moved (rekey, PAIRING §3 – legal's wording 07.11.2026): the friends menu shows the line with two equal
keys; the answer goes to ctrl.friend_move_answer (performance's logic), declining says where sharing stays. In memory.

    python -m unittest tests/test_friend_moved.py
"""
import types
import unittest

from system import i18n
from ui import qprofile

OLD = "0123456789ABCDEF"


def backend(old_gone=False, moved=True):
    f = {"status": "ok", "name": "Anna", "pid": "p-anna", "t": 1}
    if moved:
        f["moved"] = {"new": "FEDCBA9876543210", "t": 2, "old_gone": old_gone}
    s = {"relay": {"on": True, "friends": {OLD: f}}}
    answers = []
    ctrl = types.SimpleNamespace(settings=s, friend_move_answer=lambda code, accept: answers.append((code, accept)))
    b = qprofile.ProfileBackend(ctrl)
    return b, answers


class FriendMovedTest(unittest.TestCase):
    def setUp(self):
        self.old = i18n.LANG
        i18n.set_language("de")

    def tearDown(self):
        i18n.set_language(self.old)

    def test_line_only_when_moved(self):
        self.assertEqual(backend(moved=False)[0].moves, [])
        m = backend()[0].moves
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["code"], OLD)
        self.assertEqual(m[0]["text"], "Anna ist umgezogen (neues Gerät oder neu eingerichtet). Nimm nur an, wenn du sicher "
                                       "bist, dass es von Anna kommt – frag im Zweifel nach.")

    def test_accept_and_decline(self):
        b, answers = backend()
        b.moveAnswer(OLD, True)
        self.assertEqual(answers, [(OLD, True)])
        self.assertEqual(b.moveNote, "")
        b.moveAnswer(OLD, False)
        self.assertEqual(b.moveNote, "Abgelehnt. Teilen mit Anna bleibt bei der alten Adresse.")
        b, _ = backend(old_gone=True)
        b.moveAnswer(OLD, False)
        self.assertEqual(b.moveNote, "Abgelehnt. Mit Anna teilst du erst wieder, wenn ihr euch neu verbindet.")


if __name__ == "__main__":
    unittest.main()
