"""0.9.7.24 – trade logs (03.11.2026, like the web): "I give this" in every trade log, however it was made (New
log → Scan a trade, or the tile's kind Singles with What = Trade); before ending one with cards given away the sentence
what leaves the collection – it can't be undone."""
import unittest

from scanner import core
from system import i18n


class TradeAnyWay(unittest.TestCase):
    def test_every_trade_log(self):
        self.assertTrue(core.is_trade({"trade_scan": True, "kind": "singles", "pack_type": "trade"}))
        self.assertTrue(core.is_trade({"kind": "singles", "pack_type": "trade"}))   # the tile's kind + What = Trade
        self.assertFalse(core.is_trade({"kind": "singles", "pack_type": "purchase"}))
        self.assertFalse(core.is_trade({"kind": "packs", "pack_type": "booster"}))

    def test_end_sentence(self):
        lang = i18n.LANG
        self.addCleanup(i18n.set_language, lang)
        i18n.set_language("en")
        packs = [{"cards": [{"out": True}, {"name": "x"}]}]
        info = {"kind": "singles", "pack_type": "trade", "title": "Anna"}
        self.assertEqual(core.trade_end_text(info, packs),
                         "1 card goes to Anna and leaves your collection – this can't be undone.")
        self.assertEqual(core.trade_end_text({"kind": "singles", "pack_type": "purchase"}, packs), "")
        self.assertEqual(core.trade_end_text(info, [{"cards": [{"name": "x"}]}]), "")
        i18n.set_language("de")
        self.assertEqual(core.trade_end_text({"kind": "singles", "pack_type": "trade"}, [{"cards": [{"out": True}] * 3}]),
                         "3 Karten gehen an deinen Tauschpartner und werden aus deiner Sammlung genommen – das lässt "
                         "sich nicht rückgängig machen.")


if __name__ == "__main__":
    unittest.main()
