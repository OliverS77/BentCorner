"""Images the source doesn't have (tester log 0.9.2: Japanese prints, new promos – hundreds of requests and warnings):
a real 404 is remembered for days, also over a restart, and the library tile shows NoImage right away instead of
asking again on every scroll. Network errors (offline) are not remembered like that.

    python -m unittest tests/test_missing_lasting.py
"""
import json
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from net import netpolite

URL = "https://assets.tcgdex.net/en/SV/SV9/117/high.jpg"


class _R:
    def __init__(self, code):
        self.status_code = code
        self.headers = {}


class Lasting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = pathlib.Path(self.tmp.name) / "missing-images.json"
        p = mock.patch.object(netpolite, "_lasting_file", lambda: self.file)
        p.start()
        self.addCleanup(p.stop)
        netpolite._missing_at.clear()
        netpolite._lasting = None
        self.addCleanup(setattr, netpolite, "_lasting", {})

    def restart(self):
        netpolite._missing_at.clear()   # the hour memory is gone with the process …
        netpolite._lasting = None       # … the lasting one is read back from the file

    def test_a_404_survives_a_restart(self):
        netpolite.note_missing(URL, _R(404))
        netpolite._save_lasting()
        self.restart()
        self.assertTrue(netpolite.is_missing(URL))

    def test_asked_again_after_days(self):
        self.file.write_text(json.dumps({URL: time.time() - netpolite.LASTING_DAYS * 86400 - 60}), "utf-8")
        self.assertFalse(netpolite.is_missing(URL))

    def test_offline_is_not_remembered_for_days(self):
        netpolite.note_missing(URL, _R(503))
        self.assertFalse(netpolite.is_missing(URL))

    def test_saved_once_a_few_seconds_later(self):
        with mock.patch.object(netpolite.threading, "Timer") as timer:
            for i in range(50):
                netpolite.mark_lasting(f"{URL}?{i}")
        timer.assert_called_once()   # 50 missing images: one write

    def test_broken_file_is_fine(self):
        self.file.write_text("{not json", "utf-8")
        self.assertFalse(netpolite.is_missing(URL))


class Tile(unittest.TestCase):
    def test_known_missing_tile_gets_no_image_source(self):
        from ui import qlibrary, quickimages
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(qlibrary, "THUMBS", pathlib.Path(d)), \
                mock.patch.object(quickimages, "ROUND_DIR", pathlib.Path(d) / "rund"), \
                mock.patch.object(qlibrary.library, "image_url", lambda *a, **k: URL), \
                mock.patch.object(quickimages, "missing_at_source", lambda url: url == URL):
            row = {"sid": "sv9-117", "set": "sv9", "number": "117", "lang": "en"}
            self.assertEqual(qlibrary.card_source(row, False, width=300), "")


if __name__ == "__main__":
    unittest.main()
