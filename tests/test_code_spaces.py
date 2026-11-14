"""The generated protection code with spaces instead of dashes (Oliver 12.11., after the 0.9.7 ship): the same 25
characters and strength; codes made earlier with dashes stay valid everywhere (keys, last 5, strength).

    python -m unittest tests/test_code_spaces.py
"""
import unittest

from collection import codestrength, syncrescue
from net import pairing
from ui import backupui


class CodeSpaces(unittest.TestCase):
    def test_new_code_has_spaces(self):
        for _ in range(20):
            c = pairing.new_rescue_code()
            self.assertEqual(len(c), 29)
            self.assertNotIn("-", c)
            self.assertEqual([len(b) for b in c.split(" ")], [5] * 5)
            self.assertEqual(len(pairing.norm_rescue(c)), 25)

    def test_old_dashes_same_key_text(self):
        c = pairing.new_rescue_code()
        dashed = c.replace(" ", "-")
        self.assertEqual(pairing.norm_rescue(c), pairing.norm_rescue(dashed))
        self.assertEqual(pairing.norm_rescue(c), pairing.norm_rescue(dashed.lower()))
        self.assertEqual(pairing.norm_rescue(c), pairing.norm_rescue(c.replace(" ", "")))

    def test_same_strength(self):
        c = pairing.new_rescue_code()
        self.assertEqual(codestrength.strength(c), codestrength.strength(c.replace(" ", "-")))
        self.assertTrue(codestrength.strength(c)["ok"])

    def test_last5_both_ways(self):
        c = pairing.new_rescue_code()
        dashed = c.replace(" ", "-")
        self.assertEqual(backupui.last5(c), backupui.last5(dashed))
        self.assertTrue(syncrescue.last5_ok(c, c[-5:]))
        self.assertTrue(syncrescue.last5_ok(dashed, c[-5:]))

    def test_pairing_code_too(self):
        """lead 13.11.: the pairing code „XXXXX XXXXX“ as well – the seal opens with either spelling (display only)."""
        import base64
        import os
        code = pairing.new_code()
        self.assertRegex(code, r"^[A-Z0-9]{5} [A-Z0-9]{5}$")
        seed = base64.b64encode(os.urandom(32)).decode()
        data = pairing.seal(code, pairing.payload_of(seed))
        self.assertEqual(pairing.open_sealed(code.replace(" ", "-"), data)["seed"], seed)
        self.assertEqual(pairing.open_sealed(code.replace(" ", ""), data)["seed"], seed)
        self.assertEqual(pairing.code_of_picture(pairing.picture_bytes(code)), code)

    def test_shown_the_same_way(self):
        c = pairing.new_rescue_code()
        self.assertEqual(backupui.blocks(c), backupui.blocks(c.replace(" ", "-")))
        self.assertNotIn("-", backupui.blocks(c))


if __name__ == "__main__":
    unittest.main()
