"""legal 02.11.2026: under the prices exactly one small sentence on where the shop links come from – Scryfall's
(purchase_uris) or our own, without a partner code – and none when no shop link is shown there.

    python -m unittest tests/test_shop_note.py
"""
import unittest

from ui.qdetail import DIRECT_NOTE, SCRYFALL_NOTE, shop_note

LINKED = '<table><tr><td><a href="https://www.cardmarket.com/x">Cardmarket Trend ↗</a></td><td>8,70 €</td></tr></table>'
PLAIN = "<table><tr><td>Cardmarket Trend</td><td>–</td></tr></table>"


class ShopNote(unittest.TestCase):
    def test_scryfall_links(self):
        self.assertEqual(shop_note(LINKED, True), SCRYFALL_NOTE)

    def test_own_links(self):
        self.assertEqual(shop_note(LINKED, False), DIRECT_NOTE)

    def test_no_link_no_sentence(self):
        self.assertEqual(shop_note(PLAIN, True), "")
        self.assertEqual(shop_note(PLAIN, False), "")
        self.assertEqual(shop_note("", True), "")
        self.assertEqual(shop_note(None, False), "")


if __name__ == "__main__":
    unittest.main()
