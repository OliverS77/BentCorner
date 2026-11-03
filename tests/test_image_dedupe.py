"""Several prints, one image address (Yu-Gi-Oh!: one image per passcode): imgcache.fetch downloads it once and
copies it for the other prints – the server and the sources see one request instead of 30.

    python -m unittest tests/test_image_dedupe.py
"""
import pathlib
import tempfile
import unittest
from unittest import mock

import games
from cards import imgcache
from games import pokemon
from net import netpolite


class FakeResponse:
    status_code = 200
    content = b"\xff\xd8 jpeg"

    def raise_for_status(self):
        pass


class Dedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        imgcache._by_url.clear()

    def tearDown(self):
        imgcache._by_url.clear()
        self.tmp.cleanup()

    def test_same_address_is_fetched_once(self):
        url = "https://example.org/img/89631139.jpg"
        calls = []
        with mock.patch.object(games, "current", lambda: pokemon.GAME), \
                mock.patch.object(netpolite, "get", lambda u, **kw: calls.append(u) or FakeResponse()), \
                mock.patch.object(netpolite, "note_missing", lambda u, r: None):
            for name in ("lob/EN001_0.jpg", "sdk/EN001_0.jpg", "ct13/EN008_0.jpg"):
                self.assertTrue(imgcache.fetch(self.dir / name, url))
                self.assertEqual((self.dir / name).read_bytes(), FakeResponse.content)
        self.assertEqual(calls, [url])

    def test_other_addresses_are_fetched(self):
        calls = []
        with mock.patch.object(games, "current", lambda: pokemon.GAME), \
                mock.patch.object(netpolite, "get", lambda u, **kw: calls.append(u) or FakeResponse()), \
                mock.patch.object(netpolite, "note_missing", lambda u, r: None):
            imgcache.fetch(self.dir / "a.jpg", "https://example.org/a.jpg")
            imgcache.fetch(self.dir / "b.jpg", "https://example.org/b.jpg")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
