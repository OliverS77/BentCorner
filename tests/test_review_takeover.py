"""Review 08.11. T4: a trade is never taken over by a sender who isn't its partner.

    python -m unittest tests/test_review_takeover.py
"""
import unittest
from unittest import mock

from collection import offers
from tests.test_review_tickets import FRIEND, good


class TakeoverTest(unittest.TestCase):
    def test_a_trade_is_never_taken_over(self):
        if True:
            store = {}
            with mock.patch.object(offers, "load", lambda game=None: store.setdefault("i", [])), \
                    mock.patch.object(offers, "_save", lambda items, game=None: None), \
                    mock.patch("collection.collectibles.archive", lambda *a, **k: None):
                offers._put(good(), [FRIEND, "Alex"], "received")
                evil = good()
                evil.update(id="ev11", f=["9999999999999999", "Mallory"])
                o = offers._put(evil, ["9999999999999999", "Mallory"], "received")
                self.assertEqual(o["partner"], [FRIEND, "Alex"])
                self.assertEqual([v["id"] for v in o["versions"]], ["ab12cd34"])



if __name__ == "__main__":
    unittest.main()
