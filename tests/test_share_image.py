"""The log recap as an image (collection/share.py), legal 03.11.2026: with a drawn card image the rights holders'
notice sits under the big card (per game, English); without one (only placeholders) it goes; in Orbit's Core no amount
at all is on the picture (key figures, biggest hit, small cards).

    python -m unittest tests/test_share_image.py
"""
import pathlib
import tempfile
import unittest
from unittest import mock

from PySide6 import QtGui, QtWidgets

from collection import share

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test", "-platform", "offscreen"])
CREDIT = (72, share.H - 50, 600, 30)   # where the notice goes


def log(img="", game="mtg"):
    cards = [{"name": f"Card {i}", "price": 10.0 - i, "foil": i == 1, "rarity": "rare", "img": img, "set": "mh2"}
             for i in range(5)]
    return {"id": "x", "started": 1762000000, "game": game,
            "info": {"kind": "packs", "title": "Box", "paid": 12.0},
            "packs": [{"cards": cards, "type": "booster"}],
            "stats": {"packs": 1, "cards": 5, "total": 40.0, "avg_pack": 40.0, "paid": 12.0, "counts": {}}}


def ink(img, rect):
    """How many pixels in rect differ clearly from the background."""
    bg = img.pixelColor(5, share.H - 5)
    x, y, w, h = rect
    n = 0
    for i in range(x, x + w, 2):
        for j in range(y, y + h, 2):
            c = img.pixelColor(i, j)
            if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) + abs(c.blue() - bg.blue()) > 60:
                n += 1
    return n


class ShareImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.png = str(pathlib.Path(self.tmp.name) / "card.png")
        im = QtGui.QImage(488, 680, QtGui.QImage.Format_RGB32)
        im.fill(QtGui.QColor("#777777"))
        im.save(self.png)

    def render(self, d, orbit="near"):
        texts = []
        orig = QtGui.QPainter.drawText

        def spy(p, *a):
            texts.append(next((x for x in a if isinstance(x, str)), ""))
            return orig(p, *a)
        with mock.patch.object(QtGui.QPainter, "drawText", spy):
            img = share.render(d, {"orbit": orbit})
        return img, texts

    def test_notice_only_with_a_card_image(self):
        img, texts = self.render(log(self.png))
        self.assertIn(share.CREDITS["mtg"], texts)
        self.assertGreater(ink(img, CREDIT), 20)
        img, texts = self.render(log(""))
        self.assertNotIn(share.CREDITS["mtg"], texts)

    def test_notice_per_game(self):
        for g in ("pokemon", "yugioh", "lorcana"):
            _, texts = self.render(log(self.png, g))
            self.assertIn(share.CREDITS[g], texts, g)

    def test_game_without_images_has_no_notice(self):
        with mock.patch.object(share, "NO_IMAGES", {"mtg"}):
            img, texts = self.render(log(self.png))
        self.assertFalse([t for t in texts if t.startswith("Card images")])
        self.assertEqual(ink(img, CREDIT), 0)

    def test_core_shows_no_amount(self):
        _, near = self.render(log(""), "near")
        _, core = self.render(log(""), "core")
        self.assertTrue(any("€" in t for t in near))
        self.assertFalse([t for t in core if "€" in t], core)


if __name__ == "__main__":
    unittest.main()


class CopiesTogether(unittest.TestCase):
    """Copies of the same card show once with their count (4× Lightning Bolt, 03.11.2026) – the same print, finish
    and language; a foil or another language is its own entry."""

    def test_hits_group_copies(self):
        bolt = {"id": "b_0", "name": "Lightning Bolt", "price": 1.43}
        d = {"packs": [{"cards": [dict(bolt), dict(bolt), {"id": "c_0", "name": "Counterspell", "price": 2.0}, dict(bolt),
                                  dict(bolt, foil=True, price=2.2), dict(bolt, lang="de")]}]}
        got = [(c["name"], c.get("foil", False), c.get("lang", "en"), c["n"]) for c in share.hits(d, 5)]
        self.assertEqual(got, [("Lightning Bolt", True, "en", 1), ("Counterspell", False, "en", 1),
                               ("Lightning Bolt", False, "en", 3), ("Lightning Bolt", False, "de", 1)])
