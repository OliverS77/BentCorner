"""0.9.7.28 – the card back on pictures that leave the app (log image collection/share.py, deck image
collection/deckshare.py; lead 03.11.2026, the same rule as the web): only a back the user chose. Never the default back
"mtg" (a pixel copy of a game's own back – userprofile.ensure() stores it when nothing was chosen); without a chosen
one only the name, with neither nothing.

    python -m unittest tests/test_share_back.py
"""
import unittest
from unittest import mock

from PySide6 import QtGui, QtWidgets

from collection import deckshare, share
from system import userprofile

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test", "-platform", "offscreen"])
MINE = next(p[2] for p in userprofile.PRESETS if p[0] == "nacht")   # an own back, not a game's


def log():
    cards = [{"name": "Card", "price": 3.0, "rarity": "rare", "img": "", "set": "mh2"}]
    return {"id": "x", "started": 1762000000, "game": "mtg", "info": {"kind": "packs", "title": "Box"},
            "packs": [{"cards": cards, "type": "booster"}],
            "stats": {"packs": 1, "cards": 1, "total": 3.0, "avg_pack": 3.0, "paid": 0, "counts": {}}}


class SharedBack(unittest.TestCase):
    def test_only_a_chosen_back(self):
        self.assertIsNone(userprofile.shared_back(None))
        self.assertIsNone(userprofile.shared_back({"name": "Oli"}))
        self.assertIsNone(userprofile.shared_back({"back": userprofile.DEFAULT_BACK}))
        self.assertIsNone(userprofile.shared_back({"back": userprofile.normalize(userprofile.DEFAULT_BACK)}))
        self.assertIsNone(userprofile.shared_back({"back": "not a back"}))
        self.assertEqual(userprofile.shared_back({"back": MINE}), MINE)

    def test_ensure_without_a_choice_gives_no_back_on_pictures(self):
        s = {}
        userprofile.ensure(s, name="Oli")   # stores the default back
        self.assertIsNone(userprofile.shared_back(s["profile"]))


class Pictures(unittest.TestCase):
    def drawn(self, fn):
        calls = []
        orig = userprofile.back_image
        with mock.patch.object(userprofile, "back_image", lambda b, *a, **k: (calls.append(b), orig(b, *a, **k))[1]):
            fn()
        return calls

    def log_backs(self, prof):
        return self.drawn(lambda: share.render(log(), {"orbit": "near", "profile": prof}))

    def deck_backs(self, prof):
        img = QtGui.QImage(deckshare.W, deckshare.H, QtGui.QImage.Format_ARGB32_Premultiplied)
        p = QtGui.QPainter(img)
        try:
            return self.drawn(lambda: deckshare._profile(p, deckshare.W, prof))
        finally:
            p.end()

    def test_log_image(self):
        self.assertEqual(self.log_backs({"id": "a", "name": "Oli", "back": userprofile.DEFAULT_BACK}), [])
        self.assertEqual(self.log_backs({"id": "a", "name": "Oli", "back": MINE}), [MINE])
        self.assertEqual(self.log_backs({"id": "a", "name": "", "back": MINE}), [MINE])

    def test_deck_image(self):
        self.assertEqual(self.deck_backs({"id": "a", "name": "Oli", "back": userprofile.DEFAULT_BACK}), [])
        self.assertEqual(self.deck_backs({"id": "a", "name": "Oli", "back": MINE}), [MINE])
        self.assertEqual(self.deck_backs(None), [])


if __name__ == "__main__":
    unittest.main()
