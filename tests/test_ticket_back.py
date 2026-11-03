"""0.9.7.31 – the trade ticket (collection/tradelib.offer_image, "Share as ticket") never draws the default card back
(lead 03.11.2026, the rule of the shared pictures): only a back the person chose; without one the place stays empty and
name and ⇄ stay in the middle – the same whether one side, both or none has a back.

    python -m unittest tests/test_ticket_back.py
"""
import unittest
from unittest import mock

from PySide6 import QtGui, QtWidgets

from collection import tradelib
from system import userprofile

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test", "-platform", "offscreen"])
MINE = next(p[2] for p in userprofile.PRESETS if p[0] == "nacht")
ROWS = [{"name": "Lightning Bolt", "set": "M10", "number": "146", "count": 1, "price": 2.1, "lang": "en", "foil": False}]


def drawn(me_back, friend_back):
    calls, texts = [], []
    orig_pm, orig_text = userprofile.back_pixmap, QtGui.QPainter.drawText

    def spy_text(p, *a):
        texts.append((a[0], next((x for x in a if isinstance(x, str)), "")) if a else None)
        return orig_text(p, *a)
    with mock.patch.object(userprofile, "back_pixmap", lambda b, *a, **k: (calls.append(b), orig_pm(b, *a, **k))[1]), \
            mock.patch.object(QtGui.QPainter, "drawText", spy_text):
        tradelib.offer_image(("Ann", me_back), ("Ben", friend_back), ROWS, ROWS)
    head = next(r for r, t in texts if t and "⇄" in t)
    return calls, head


class TicketBack(unittest.TestCase):
    def test_default_back_never_drawn(self):
        for a, b in ((None, None), (userprofile.DEFAULT_BACK, None), (None, userprofile.DEFAULT_BACK),
                     (userprofile.DEFAULT_BACK, userprofile.DEFAULT_BACK)):
            self.assertEqual(drawn(a, b)[0], [])

    def test_own_backs_drawn(self):
        self.assertEqual(drawn(MINE, None)[0], [MINE])
        self.assertEqual(drawn(None, MINE)[0], [MINE])
        self.assertEqual(drawn(MINE, MINE)[0], [MINE, MINE])

    def test_names_stay_in_the_middle(self):
        # the "Ann ⇄ Ben" box is the same whatever backs there are – nothing shifts with one side empty
        heads = {drawn(a, b)[1].getRect() for a, b in ((MINE, MINE), (MINE, None), (None, MINE), (None, None))}
        self.assertEqual(len(heads), 1)


if __name__ == "__main__":
    unittest.main()
