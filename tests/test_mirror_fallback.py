"""Card images (Pokémon, Disney Lorcana): our mirror first; a 404 there (older servers didn't know Japanese paths "ja/SV/…") falls
back to TCGdex directly – slowly (FALLBACK_GAP), never for bulk downloads (mirror_only), never twice for an image
missing at the source too. A 429 from the mirror never falls back.

    python -m unittest tests/test_mirror_fallback.py
"""
import threading
import time
import unittest
from unittest import mock

from net import netpolite

JP = "https://assets.tcgdex.net/ja/SV/SV10/027/high.jpg"
MIRROR = netpolite.MIRROR["assets.tcgdex.net"] + "/ja/SV/SV10/027/high.jpg"
LOR = "https://api.lorcana.ravensburger.com/images/en/set1/1_ea50bda8.jpg"


def old(u):
    """The same URL under the former server name (bentcorner.oliver-schunn.tech) – the mirror's fallback."""
    return netpolite._with_host(u, next(iter(netpolite.OLD_HOSTS)))


class _R:
    def __init__(self, code):
        self.status_code = code
        self.headers = {}


class Fallback(unittest.TestCase):
    src, mir, host = JP, MIRROR, "assets.tcgdex.net"

    def setUp(self):
        netpolite._cool.clear()
        netpolite._next.clear()
        netpolite._missing_at.clear()   # the one memory for missing images (since the cleanup round)
        netpolite._lasting = {}   # ... and its lasting part (real 404s, saved): never the data folder's file
        netpolite._new_down_until[0] = 0.0   # bentcorner.app not remembered as down
        self.calls, self.waits = [], []

    def run_get(self, url, answers):
        """answers: {url: status} – what the servers reply. -> response of netpolite.get"""
        def request(method, u, **kw):
            self.calls.append(u)
            return _R(answers.get(u, 200))
        with mock.patch.object(netpolite.requests, "request", side_effect=request), \
                mock.patch.object(netpolite, "_wait", side_effect=lambda host, gap: self.waits.append((host, gap))):
            return netpolite.get(url)

    def test_mirror_hit_never_asks_tcgdex(self):
        r = self.run_get(self.src, {self.mir: 200})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.calls, [self.mir])

    def test_mirror_404_falls_back_once_and_slowly(self):
        r = self.run_get(self.src, {self.mir: 404, self.src: 200})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.calls, [self.mir, self.src])
        self.assertIn((self.host, netpolite.FALLBACK_GAP), self.waits)
        self.assertGreaterEqual(netpolite.FALLBACK_GAP, 1.0)

    def test_missing_at_the_source_too_is_never_asked_again(self):
        self.run_get(self.src, {self.mir: 404, self.src: 404})
        self.assertTrue(netpolite.is_missing(self.src))
        self.calls.clear()
        r = self.run_get(self.src, {self.mir: 404, self.src: 404})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.calls, [])   # answered from memory – neither mirror nor TCGdex asked

    def test_bulk_downloads_stay_on_the_mirror(self):
        with netpolite.mirror_only():
            r = self.run_get(self.src, {self.mir: 404, self.src: 200})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.calls, [self.mir])

    def test_bulk_downloads_never_fall_back_on_server_errors(self):
        with netpolite.mirror_only():   # 5xx from the mirror: returned as it is, TCGdex isn't asked
            r = self.run_get(self.src, {self.mir: 503, old(self.mir): 503, self.src: 200})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self.calls, [self.mir, old(self.mir)])   # same server under its old name – never TCGdex

    def test_bulk_downloads_never_fall_back_when_the_mirror_is_down(self):
        def request(method, u, **kw):
            self.calls.append(u)
            raise netpolite.requests.ConnectionError("down")
        with mock.patch.object(netpolite.requests, "request", side_effect=request), \
                mock.patch.object(netpolite, "_wait"), netpolite.mirror_only():
            with self.assertRaises(netpolite.requests.RequestException):
                netpolite.get(self.src)
        self.assertEqual(self.calls, [self.mir, old(self.mir)])

    def test_mirror_429_waits_instead_of_falling_back(self):
        r = self.run_get(self.src, {self.mir: 429, self.src: 200})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(self.calls, [self.mir])

    def test_mirror_down_goes_direct(self):
        def request(method, u, **kw):
            self.calls.append(u)
            if u in (self.mir, old(self.mir)):
                raise netpolite.requests.ConnectionError("down")
            return _R(200)
        with mock.patch.object(netpolite.requests, "request", side_effect=request), \
                mock.patch.object(netpolite, "_wait"):
            self.assertEqual(netpolite.get(self.src).status_code, 200)
        self.assertEqual(self.calls, [self.mir, old(self.mir), self.src])


class FallbackLorcana(Fallback):
    """Disney Lorcana: the same rules for Ravensburger's image host (user decision 2026-10-26)."""
    src, mir, host = LOR, netpolite.MIRROR["api.lorcana.ravensburger.com"] + "/images/en/set1/1_ea50bda8.jpg",         "api.lorcana.ravensburger.com"


if __name__ == "__main__":
    unittest.main()
