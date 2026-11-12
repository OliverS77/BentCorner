"""Review 08.11. T1 (mailbox): relay files only valid tickets – the game never becomes a path.

    python -m unittest tests/test_review_mailbox.py
"""
import unittest

from tests.test_review_tickets import FRIEND, ME, good


class MailboxTest(unittest.TestCase):
    def test_relay_files_only_valid_tickets(self):
        from net import relay
        f = {"pid": FRIEND}
        self.assertIsNotNone(relay._clean_ticket(good(), f, ME))
        t = good()
        t["g"] = "//attacker/share"
        self.assertIsNone(relay._clean_ticket(t, f, ME))


if __name__ == "__main__":
    unittest.main()
