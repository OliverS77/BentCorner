"""Cleanup round, network (CLEANUP lines 39, 126–131): tools go through netpolite, one memory for missing images,
Retry-After as an HTTP date, exchange rates not retried on every price job after a failure.

    python -m unittest tests/test_net_cleanup.py
"""
import email.utils
import pathlib
import re
import time
import unittest
from unittest import mock

import requests

from net import netpolite
from tests.optional_games import needs_private_tools  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _R:
    def __init__(self, code=200, headers=None):
        self.status_code, self.headers, self.content = code, headers or {}, b""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return {"rates": {"USD": 1.1}}


class Tools(unittest.TestCase):
    @needs_private_tools
    def test_tools_use_netpolite(self):
        for name in ("build_mtg_langs", "fix_pokemon_market", "fill_pokemon_images", "build_fingerprints"):
            src = (ROOT / "tools" / f"{name}.py").read_text("utf-8")
            self.assertIn("netpolite", src, name)
            self.assertIsNone(re.search(r"requests\.(get|head|post|Session)\(", src), name)
            self.assertNotIn("User-Agent\": \"BentCorner-build", src, name)   # one honest UA: netpolite.UA

    def test_head_never_through_the_mirror(self):
        netpolite._next.clear()
        seen = []
        with mock.patch.object(netpolite.requests, "request", lambda m, u, **kw: seen.append((m, u)) or _R(200)):
            netpolite.head("https://assets.tcgdex.net/en/sv/sv03/1/high.jpg")
        self.assertEqual(seen, [("HEAD", "https://assets.tcgdex.net/en/sv/sv03/1/high.jpg")])


class OneMissingMemory(unittest.TestCase):
    def setUp(self):
        netpolite._missing_at.clear()
        netpolite._lasting = {}
        netpolite._next.clear()
        netpolite._cool.clear()

    def test_no_private_memories_left(self):
        for path, word in (("scanner/aiscan.py", "_lang_missing"), ("app.py", "img_missing"),
                           ("net/netpolite.py", "_gone")):
            self.assertNotIn(word, (ROOT / path).read_text("utf-8"), path)

    def test_imgcache_and_netpolite_share_it(self):
        from cards import imgcache
        imgcache.mark_missing("data/card-images/x.jpg")
        self.assertTrue(netpolite.is_missing("data/card-images/x.jpg"))
        netpolite._missing_at["data/card-images/x.jpg"] -= netpolite.MISSING_TTL + 1
        self.assertFalse(imgcache.is_missing("data/card-images/x.jpg"))   # an hour later: asked again

    def test_mirror_404_then_source_404_not_asked_again(self):
        url = "https://assets.tcgdex.net/ja/SV/SV10/27/high.webp"
        calls = []
        with mock.patch.object(netpolite.requests, "request", lambda m, u, **kw: calls.append(u) or _R(404)), \
                mock.patch.object(netpolite.time, "sleep"):
            for _ in range(3):
                self.assertEqual(netpolite.get(url).status_code, 404)
        self.assertEqual(len(calls), 2)   # mirror + source once, then from the memory


class RetryAfter(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(netpolite.retry_after("120"), 120.0)
        self.assertAlmostEqual(netpolite.retry_after(email.utils.formatdate(time.time() + 300, usegmt=True)), 300, delta=3)
        self.assertEqual(netpolite.retry_after(email.utils.formatdate(time.time() - 300, usegmt=True)), 0.0)
        for bad in (None, "", "soon"):
            self.assertEqual(netpolite.retry_after(bad), 0.0)

    def test_429_with_http_date(self):
        netpolite._cool.clear()
        netpolite._next.clear()
        when = email.utils.formatdate(time.time() + 900, usegmt=True)
        with mock.patch.object(netpolite.requests, "request", lambda m, u, **kw: _R(429, {"Retry-After": when})):
            netpolite.get("https://api.scryfall.com/sets")
        self.assertGreater(netpolite.cooling("https://api.scryfall.com/x"), 880)   # the date counts, not 60 s


class ExchangeRates(unittest.TestCase):
    def test_failure_not_retried_on_every_job(self):
        from cards import currency
        calls = []
        with mock.patch.object(currency, "_stamp", 0.0), mock.patch.object(currency, "_failed", 0.0), \
                mock.patch.object(currency, "_rates", {"EUR": 1.0}), \
                mock.patch.object(currency.netpolite, "get", lambda u, **kw: calls.append(u) or _R(503)):
            for _ in range(3):   # three price jobs while offline
                self.assertFalse(currency.refresh())
        self.assertEqual(len(calls), 2)   # both addresses once, then a pause of an hour


if __name__ == "__main__":
    unittest.main()
