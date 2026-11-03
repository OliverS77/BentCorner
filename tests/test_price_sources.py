"""Pokémon TCGplayer prices via our own price server: server builder (TCGCSV JSON -> pokemon-tcgplayer.json.gz) and
the app reader (download once a day, cache, fallback). No network – small fixtures and fake requests.

    .venv\\Scripts\\python -m unittest tests.test_price_sources
"""
import gzip
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock
from tests.optional_games import needs_server  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# TCGCSV /tcgplayer/3/<group>/prices – shape as delivered (shortened)
GROUP_PRICES = {
    604: [
        {"productId": 42444, "lowPrice": 1.0, "midPrice": 2.0, "highPrice": 9.0, "marketPrice": 1.234,
         "directLowPrice": None, "subTypeName": "Holofoil"},
        {"productId": 42444, "lowPrice": 0.5, "midPrice": 1.0, "highPrice": 3.0, "marketPrice": None,
         "directLowPrice": None, "subTypeName": "1st Edition Holofoil"},
        {"productId": 42551, "lowPrice": 0.1, "midPrice": 0.2, "highPrice": 0.5, "marketPrice": 0.15,
         "directLowPrice": None, "subTypeName": "Normal"},
        {"productId": 42551, "marketPrice": 0.9, "subTypeName": "Reverse Holofoil"},
        {"marketPrice": 3.0, "subTypeName": "Normal"},   # broken row without product
    ],
    605: [],
}


def _load_server():
    spec = importlib.util.spec_from_file_location("bc_server_prices", ROOT / "server" / "prices" / "prices.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@needs_server
class ServerBuilder(unittest.TestCase):
    def setUp(self):
        self.srv = _load_server()
        self.tmp = tempfile.TemporaryDirectory()
        self.srv.OUT = self.tmp.name
        sleep = mock.patch.object(self.srv.time, "sleep", lambda s: None)   # the server module waits between calls
        sleep.start()
        self.addCleanup(sleep.stop)
        self.calls = []
        self.last_updated = b"2026-10-24T20:05:00+0000"
        self.fail = set()

        def get_raw(url, timeout=120, accept="application/json"):
            self.calls.append(url)
            if url.endswith("last-updated.txt"):
                return self.last_updated
            if url.endswith("/groups"):
                return json.dumps({"results": [{"groupId": g} for g in GROUP_PRICES]}).encode()
            gid = int(url.rsplit("/", 2)[-2])
            if gid in self.fail:
                raise OSError("boom")
            return json.dumps({"success": True, "results": GROUP_PRICES[gid]}).encode()
        self.srv.get_raw = get_raw

    def tearDown(self):
        self.tmp.cleanup()

    def out(self):
        with gzip.open(os.path.join(self.tmp.name, self.srv.POKEMON), "rt", encoding="utf-8") as f:
            return json.load(f)

    def test_table(self):
        t = self.srv.pokemon_table(GROUP_PRICES)
        self.assertEqual(t, {"604": {"42444": {"Holofoil": 1.23, "1st Edition Holofoil": None},
                                     "42551": {"Normal": 0.15, "Reverse Holofoil": 0.9}}})

    def test_build_and_skip_unchanged(self):
        self.srv.build_pokemon()
        d = self.out()
        self.assertEqual(d["v"], 1)
        self.assertEqual(d["src"], self.last_updated.decode())
        self.assertEqual(d["g"]["604"]["42551"], {"Normal": 0.15, "Reverse Holofoil": 0.9})
        self.assertEqual(sum("/prices" in u for u in self.calls), len(GROUP_PRICES))   # each group once
        self.calls.clear()
        self.srv.build_pokemon()   # TCGCSV unchanged: only last-updated.txt
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0].endswith("last-updated.txt"))

    def test_failed_group_keeps_yesterday(self):
        self.srv.build_pokemon()
        self.last_updated = b"2026-10-25T20:05:00+0000"
        self.fail = {604}
        self.srv.build_pokemon()
        d = self.out()
        self.assertIn("42444", d["g"]["604"])
        self.assertEqual(d["src"], "")   # incomplete: rebuild next time even if TCGCSV hasn't changed

    def test_new_games_own_category_and_file(self):
        cats = {c: n for c, n, _ in self.srv.TCGCSV_GAMES}
        self.assertEqual(set(cats), {68, 71, 89})   # three newer games (TCGplayer categories)
        self.srv.build_tcgcsv(71, cats[71], "Lorcana")
        self.assertTrue(any(u.endswith("/71/groups") for u in self.calls))
        self.assertFalse(any("/3/" in u for u in self.calls))
        with gzip.open(os.path.join(self.tmp.name, cats[71]), "rt", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["g"]["604"]["42551"], {"Normal": 0.15, "Reverse Holofoil": 0.9})
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, self.srv.POKEMON)))


class _Resp:
    def __init__(self, content, status=200, headers=None):
        self.content, self.status_code, self.headers = content, status, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(self.status_code)


class _Net:
    def __init__(self, resp):
        self.resp, self.urls, self.sent = resp, [], []

    def get(self, url, **kw):
        self.urls.append(url)
        self.sent.append(kw.get("headers") or {})
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


class AppReader(unittest.TestCase):
    def setUp(self):
        from games import pokemon
        self.pk = pokemon
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = pathlib.Path(self.tmp.name) / "ref" / "tcgplayer-prices.json.gz"
        self.table = {"604": {"42444": {"Holofoil": 1.23}}}
        self.body = gzip.compress(json.dumps({"v": 1, "day": "2026-10-25", "g": self.table}).encode())

    def tearDown(self):
        self.tmp.cleanup()

    def tcg(self, net):   # Pokémon's file from our price server (games.base.tcgplayer_table)
        from games.base import tcgplayer_table
        return tcgplayer_table(net, self.cache, self.pk.TCG_PRICES)

    def test_download_then_cache(self):
        net = _Net(_Resp(self.body))
        self.assertEqual(self.tcg(net), (self.table, False))
        self.assertEqual(len(net.urls), 1)
        self.assertTrue(net.urls[0].endswith("/dl/prices/pokemon-tcgplayer.json.gz"))
        self.assertNotIn("tcgcsv.com", net.urls[0])
        self.assertTrue(self.cache.exists())
        self.assertEqual(self.tcg(net), (self.table, False))   # same day: from cache
        self.assertEqual(len(net.urls), 1)

    def test_unchanged_file_not_downloaded_again(self):
        self.tcg(_Net(_Resp(self.body, headers={"ETag": '"v1"'})))
        old = time.time() - 2 * 24 * 3600
        os.utime(self.cache, (old, old))
        net = _Net(_Resp(b"", 304))
        self.assertEqual(self.tcg(net), (self.table, False))
        self.assertEqual(net.sent[0].get("If-None-Match"), '"v1"')
        self.assertGreater(self.cache.stat().st_mtime, old + 3600)   # checked again only tomorrow

    def test_server_down_keeps_last_file(self):
        self.tcg(_Net(_Resp(self.body)))
        old = time.time() - 2 * 24 * 3600
        os.utime(self.cache, (old, old))
        net = _Net(_Resp(b"", 404))
        self.assertEqual(self.tcg(net), (self.table, True))
        self.assertEqual(len(net.urls), 1)   # tried our server once, never TCGCSV

    def test_nothing_cached_offline(self):
        net = _Net(OSError("offline"))
        self.assertEqual(self.tcg(net), ({}, True))
        self.assertFalse(self.cache.exists())


if __name__ == "__main__":
    unittest.main()
