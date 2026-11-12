"""Review 08.11. (M8): a friend's move note that came as a parcel counts only when the server confirms the move, and a
move already waiting for the user's answer is never replaced by another note. (The forged-note case against the real
box: tools/boxchecks/rekey_check.py, „M8“.)

    python -m unittest tests.test_move_note
"""
import base64
import time
import unittest
from unittest import mock

from net import relay


def _ident(b):
    return {"relay": {"on": True, "seed": base64.b64encode(bytes([b]) * 32).decode()}}


def _pk(s):
    return relay._b64(relay._signing(s).verify_key)


class MoveNote(unittest.TestCase):
    def setUp(self):
        self.me, self.old, self.x, self.y = _ident(1), _ident(2), _ident(3), _ident(4)
        relay.state(self.me)["friends"] = {relay.my_code(self.old): {"name": "F", "status": "ok", "sign_pk": _pk(self.old)}}

    def _body(self, new):
        old, t = relay.my_code(self.old), int(time.time())
        return {"old": old, "new": relay.my_code(new), "new_sign_pk": _pk(new), "t": t,
                "sig_old": relay._signed(self.old, f"rekey_friend|{old}|{relay.my_code(new)}|{relay.my_code(self.me)}|{t}")}

    def _note(self, new, confirmed):
        with mock.patch.object(relay, "_move_confirmed", lambda s, o, n: confirmed):
            return relay._moved_note(self.me, self._body(new), relay.my_code(new), _pk(new), confirm=True)

    def test_unconfirmed_parcel_note_ignored(self):
        self.assertIsNone(self._note(self.x, False))
        self.assertIsNone(self._note(self.x, None), "no answer now: nothing either")
        self.assertNotIn("moved", relay.friends(self.me)[relay.my_code(self.old)])

    def test_confirmed_note_shown(self):
        self.assertEqual(self._note(self.x, True)["kind"], "moved")

    def test_waiting_move_not_replaced(self):
        self._note(self.x, True)
        self.assertIsNone(self._note(self.y, True))
        self.assertEqual(relay.friends(self.me)[relay.my_code(self.old)]["moved"]["new"], relay.my_code(self.x))


if __name__ == "__main__":
    unittest.main()
