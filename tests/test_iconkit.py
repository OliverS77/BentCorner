"""The Bent°Corner mark (ui/iconkit.py, logo of 30.10.2026): 16/20/24 px are the hand-made 2-bit pixel images – never
scaled –, from 32 px rendered from the SVGs; icon.ico carries the dark mark (Explorer, light by default); the window
icon follows the taskbar (light/dark) while the program runs.

    python -m unittest tests/test_iconkit.py
"""
import pathlib
import struct
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np
from PySide6 import QtWidgets

from ui import iconkit

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test", "-platform", "offscreen"])


class IconKit(unittest.TestCase):
    def test_small_sizes_are_the_pixel_images(self):
        for s in iconkit.PIXEL:
            for on, name in (("dark", "hell"), ("light", "dunkel")):
                want = cv2.imread(str(iconkit.folder() / f"mark-{name}-{s}.png"), cv2.IMREAD_UNCHANGED)
                self.assertTrue(np.array_equal(iconkit.pixel_image(s, on), want), (s, on))

    def test_larger_sizes_from_vectors(self):
        for s in (32, 40, 48, 64, 256):
            img = iconkit.pixel_image(s, "light")
            self.assertEqual(img.shape, (s, s, 4))
            ink = img[img[:, :, 3] > 200][:, :3]
            self.assertLess(int(np.median(ink)), 100)   # the dark mark on a light background
        self.assertGreater(int(np.median(iconkit.pixel_image(64, "dark")[:, :, :3][
            iconkit.pixel_image(64, "dark")[:, :, 3] > 200])), 200)

    def test_ico_has_every_size_and_the_dark_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "icon.ico"
            iconkit.write_ico(p)
            data = p.read_bytes()
        _, kind, n = struct.unpack("<HHH", data[:6])
        self.assertEqual((kind, n), (1, len(iconkit.SIZES)))
        sizes = [data[6 + 16 * i] or 256 for i in range(n)]
        self.assertEqual(sizes, list(iconkit.SIZES))
        size0, off0 = struct.unpack("<II", data[6 + 8:6 + 16])
        img = cv2.imdecode(np.frombuffer(data[off0:off0 + size0], np.uint8), cv2.IMREAD_UNCHANGED)
        want = cv2.imread(str(iconkit.folder() / "mark-dunkel-16.png"), cv2.IMREAD_UNCHANGED)
        self.assertTrue(np.array_equal(img, want))

    def test_follows_the_taskbar(self):
        seen = []
        with mock.patch.object(iconkit, "taskbar_on", return_value="light"):
            iconkit.follow_system(APP)
        iconkit.on_icon_change(seen.append)
        with mock.patch.object(iconkit, "taskbar_on", return_value="dark"):
            iconkit._follow["timer"].timeout.emit()
        self.assertEqual(len(seen), 1)
        self.assertEqual(iconkit._follow["on"], "dark")
        iconkit._follow["timer"].stop()

    def test_lockup(self):
        img, w, h = iconkit.lockup_image(24, "dark")
        self.assertGreater(w, 5 * h)   # card + BENT°CORNER side by side
        self.assertFalse(img.isNull())


if __name__ == "__main__":
    unittest.main()
