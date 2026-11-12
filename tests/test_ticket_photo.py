"""0.9.7.38 – a trade ticket from a camera picture (collection/ticket.decode_photo) also when the phone is held at an
angle (lead 03.11.2026): one side nearer makes the code block a trapezoid; a rotated rectangle cut it askew – 8 px were
enough to fail. Now the block's four edges are fitted (one line each) and the corners straightened. The code is drawn
here straight from ticket.bits (no Qt) and laid into a 1280×720 frame: tilted left/right and top/bottom by several
amounts – each must give the same ticket, an empty frame none. The broader comparison on spoiled "photos" (blur,
glare, JPEG …) runs in labs/ticket-synth (eval_desk.py).

    python -m unittest tests/test_ticket_photo.py
"""
import unittest
from unittest import mock

import cv2
import numpy as np

from collection import ticket

CARDS = [{"set": "m10", "number": "146", "lang": "en", "foil": False, "count": 2, "name": "Lightning Bolt"},
         {"set": "c21", "number": "263", "lang": "de", "foil": True, "count": 1, "name": "Sol Ring"}]


def code_image(t, s=2, lay=ticket.RECEIPT):
    """The ticket's pixel code as the app draws it (dark ticket, light blocks, row 0 at the bottom), s px per pixel."""
    rows, bits = ticket.bits(t, lay)
    h = ticket.band_height(rows, lay) + 60
    img = np.full((h * s, lay.W * s), 18, np.uint8)
    for i, b in enumerate(bits):
        if b:
            x, y, m = ticket.module_rect(i, h, lay)
            img[(y + 1) * s:(y + m - 1) * s, (x + 1) * s:(x + m - 1) * s] = 225
    return img


def frame(src, axis="", pct=0, deg=0.0, size=(1280, 720)):
    """src laid into a camera frame at ~70 % of its width, turned by deg, one side farther away by pct %."""
    fw, fh = size
    h, w = src.shape
    sc = 0.7 * fw / w
    cw, ch = w * sc, h * sc
    a = np.radians(deg)
    rot = np.float32([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    dst = np.float32([[-cw / 2, -ch / 2], [cw / 2, -ch / 2], [cw / 2, ch / 2], [-cw / 2, ch / 2]])
    f = pct / 100
    if axis == "x":     # the right edge farther away: shorter
        dst[1] += [-f * cw * 0.3, f * ch / 2]
        dst[2] += [-f * cw * 0.3, -f * ch / 2]
    elif axis == "y":   # the bottom edge farther away: shorter
        dst[2] += [-f * cw / 2, -f * ch * 0.3]
        dst[3] += [f * cw / 2, -f * ch * 0.3]
    dst = dst @ rot.T + [fw / 2, fh / 2]
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), dst.astype(np.float32))
    out = cv2.warpPerspective(src, m, (fw, fh), flags=cv2.INTER_AREA, borderValue=45)
    return cv2.GaussianBlur(out, (0, 0), 0.6)


class TicketPhoto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # a fixed ticket (ID and time), so the picture is the same each run
        with mock.patch.object(ticket, "_game", lambda: "mtg"), \
                mock.patch.object(ticket.uuid, "uuid4", lambda: mock.Mock(hex="5eed0cde" * 4)), \
                mock.patch.object(ticket.time, "time", lambda: 1793750400):
            cls.t = ticket.new(("a1b2c3d4e5f6a7b8", "Ann"), ("f0e1d2c3b4a59687", "Ben"), CARDS[:1], CARDS[1:])
        cls.src = code_image(cls.t)

    def read(self, img):
        t = ticket.decode_photo(img)
        return t and t["id"]

    def test_straight_and_turned(self):
        for deg in (0, 6, 180):
            with self.subTest(deg=deg):
                self.assertEqual(self.read(frame(self.src, deg=deg)), self.t["id"])

    def test_held_at_an_angle(self):
        for axis in "xy":
            for pct in (6, 10, 15):
                for deg in (0, -4):
                    with self.subTest(axis=axis, pct=pct, deg=deg):
                        self.assertEqual(self.read(frame(self.src, axis, pct, deg)), self.t["id"])

    def test_empty_frame_gives_none(self):
        self.assertIsNone(ticket.decode_photo(np.full((720, 1280), 50, np.uint8)))
        noise = cv2.GaussianBlur(np.random.default_rng(1).integers(0, 255, (720, 1280), dtype=np.uint8), (0, 0), 3)
        self.assertIsNone(ticket.decode_photo(noise))


if __name__ == "__main__":
    unittest.main()
