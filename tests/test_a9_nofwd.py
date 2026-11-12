"""FUNDE A9 (lead/ports 08.11.): „Neuer Code“ with a seed change is gone, and a 410 {fwd} sealed with the OLD vault key is
never followed – anyone holding the old seed (a stolen backup) could send one and pull every device of a mailbox-only
ID to an address of their own. Own devices follow only via their signed per-device letter (S6).

    python -m unittest tests.test_a9_nofwd
"""
import base64
import unittest
from unittest import mock

from net import pairing, rekey, relay

OLD = base64.b64encode(b"\x11" * 32).decode()
THIEF = base64.b64encode(b"\x66" * 32).decode()


class NoFwd(unittest.TestCase):
    def test_a_sealed_fwd_is_not_followed(self):
        s = {"relay": {"on": True, "seed": OLD}}
        fwd = pairing.vault_seal(OLD, {"v": 1, "seed": THIEF, "code": pairing.code_of_seed(THIEF)})
        data = {"fwd": fwd}
        with mock.patch("net.devkeys.forget"):
            self.assertTrue(relay.moved_away(s, data))
        self.assertNotEqual(s["relay"]["seed"], THIEF, "never the thief's identity")
        self.assertTrue(s["relay"].get("identity_gone"))
        self.assertNotIn("fwd", data, "callers must not read it as „followed“")

    def test_no_new_mode(self):
        self.assertEqual(rekey.MODES, ("remove",))
        with self.assertRaises(ValueError):
            rekey.change({"relay": {"seed": OLD}}, "new")


if __name__ == "__main__":
    unittest.main()
