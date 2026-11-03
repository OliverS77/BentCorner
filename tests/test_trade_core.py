"""0.9.7.21 – trade in Orbit's Core (legal 03.11.2026): the ticket image shows only the cards and counts – no prices,
no TOTAL, no money, no balance; the ticket's code (what Bent°Corner reads back) stays the same."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from collection.tradelib import offer_image  # noqa: E402

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

ROWS = [{"name": "Lightning Bolt", "set": "M10", "number": "146", "count": 2, "price": 1.5, "lang": "en", "foil": False}]


class CoreTicketImage(unittest.TestCase):
    def setUp(self):
        self.drawn = []
        import collection.tradelib as tl
        self.tl = tl
        self._orig = tl.tr

        def spy(t):
            self.drawn.append(t)
            return t
        tl.tr = spy

    def tearDown(self):
        self.tl.tr = self._orig

    def test_core_leaves_out_prices_and_balance(self):
        priced = offer_image(("Ann", None), ("Ben", None), ROWS, ROWS, priced=True)
        self.assertIn("TOTAL", self.drawn)
        self.drawn.clear()
        core = offer_image(("Ann", None), ("Ben", None), ROWS, ROWS, priced=False)
        for word in ("TOTAL", "Prices: Cardmarket trend, no guarantee", "BALANCE FOR Ann"):
            self.assertNotIn(word, self.drawn)
        self.assertLess(core.height(), priced.height())


if __name__ == "__main__":
    unittest.main()
