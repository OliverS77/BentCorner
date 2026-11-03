"""Polite networking by the sources' own rules (2026-10-26): EDHREC off, longer block after 429 per service,
conditional requests (ETag), "changed?" before big downloads (Scryfall bulk, MTGJSON Meta.json, YGOPRODeck
checkDBVer), RiftHunt API host.

    python -m unittest tests/test_net_rules.py
"""
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from cards import carddb, edhrec, pricehist
from net import netpolite
from tests.optional_games import needs_server  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _R:
    def __init__(self, code=200, headers=None, body=None):
        self.status_code, self.headers, self._body = code, headers or {}, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(self.status_code)


class Cooling(unittest.TestCase):
    def setUp(self):
        netpolite._cool.clear()
        netpolite._next.clear()

    def hit(self, url, resp):
        with mock.patch.object(netpolite.requests, "request", return_value=resp), \
                mock.patch.object(netpolite.time, "sleep"):
            netpolite.get(url)

    def test_tcgcsv_and_ygoprodeck_block_longer(self):
        self.hit("https://tcgcsv.com/tcgplayer/3/groups", _R(429))
        self.assertGreater(netpolite.cooling("https://tcgcsv.com/x"), 590)
        self.hit("https://db.ygoprodeck.com/api/v7/cardinfo.php", _R(429))
        self.assertGreater(netpolite.cooling("https://db.ygoprodeck.com/x"), 3590)

    def test_retry_after_takes_precedence(self):
        self.hit("https://tcgcsv.com/x", _R(429, {"Retry-After": "120"}))
        self.assertLess(netpolite.cooling("https://tcgcsv.com/x"), 121)

    def test_others_one_minute(self):
        self.hit("https://api.scryfall.com/cards/named", _R(429))
        self.assertTrue(55 < netpolite.cooling("https://api.scryfall.com/") <= 60)

    def test_rifthunt_api_host(self):
        self.assertIn("api.rifthunt.com", netpolite.POLICY)


class Conditional(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "f.json"
            self.assertEqual(netpolite.cond_headers(path), {})   # no copy yet: normal download
            path.write_text("{}")
            netpolite.remember(path, _R(200, {"ETag": '"abc"', "Last-Modified": "Sun, 25 Oct 2026 06:00:00 GMT"}))
            self.assertEqual(netpolite.cond_headers(path), {"If-None-Match": '"abc"',
                                                            "If-Modified-Since": "Sun, 25 Oct 2026 06:00:00 GMT"})
            path.unlink()
            self.assertEqual(netpolite.cond_headers(path), {})   # copy gone: never send a condition

    def test_remember_never_breaks(self):
        with tempfile.TemporaryDirectory() as d:
            netpolite.remember(pathlib.Path(d) / "f", object())   # response without headers: just nothing


class Edhrec(unittest.TestCase):
    def test_off_never_fetches(self):
        self.assertFalse(edhrec.ALLOWED)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(edhrec, "CACHE", pathlib.Path(d)), \
                mock.patch.object(edhrec.netpolite, "get", side_effect=AssertionError("EDHREC called")):
            edhrec._mem.clear()
            self.assertIsNone(edhrec.commander("Atraxa, Praetors' Voice"))
            (pathlib.Path(d) / "atraxa-praetors-voice.json").write_text(json.dumps({"creature": 30}), "utf-8")
            self.assertEqual(edhrec.commander("Atraxa, Praetors' Voice")["types"], {"creature": 30})   # cache ok


class ScryfallBulk(unittest.TestCase):
    def test_unchanged_bulk_skips_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            ref = pathlib.Path(d)
            con = sqlite3.connect(ref / "cards.sqlite")
            con.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
            con.executemany("INSERT INTO meta VALUES (?, ?)", [("bulk", "2026-10-25T09:00"), ("cards", "90000"),
                                                               ("langs", "400000")])
            con.commit()
            con.close()
            bulk = {"default_cards": {"updated_at": "2026-10-25T09:00", "jsonl_download_uri": "x"}}
            with mock.patch.object(carddb, "REF", ref), mock.patch.object(carddb, "_bulk_info", return_value=bulk), \
                    mock.patch.object(carddb, "_download", side_effect=AssertionError("downloaded")):
                self.assertEqual(carddb.download(game=None), (90000, 400000))
            bulk["default_cards"]["updated_at"] = "2026-10-26T09:00"   # new file at Scryfall: download
            with mock.patch.object(carddb, "REF", ref), mock.patch.object(carddb, "_bulk_info", return_value=bulk), \
                    mock.patch.object(carddb, "_download", side_effect=RuntimeError("download")), \
                    self.assertRaises(RuntimeError):
                carddb.download(game=None)

    def test_old_database_without_marker_rebuilds(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(carddb._built_from(pathlib.Path(d) / "none.sqlite"), {})


class Mtgjson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(pricehist, "DB", pathlib.Path(self.tmp.name) / "hist.sqlite"),
                  mock.patch.object(pricehist, "_build_date", return_value="2026-10-25"),
                  mock.patch.object(pricehist, "status", return_value={"updated": pricehist.today()})]
        for p in self.p:
            p.start()
        con = pricehist._connect()
        con.execute("INSERT INTO meta VALUES ('ids', ?)", (str(time.time()),))
        con.execute("INSERT INTO ids VALUES ('u1', 's1')")
        con.commit()
        con.close()
        self.downloads = 0

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def fake_download(self, name, progress, label):
        self.downloads += 1
        import io
        return io.BytesIO()

    def test_same_build_downloaded_once(self):
        with mock.patch.object(pricehist, "_download", self.fake_download), \
                mock.patch.object(pricehist, "_stream_entries", lambda *a: iter(())):
            pricehist.today_prices(lambda *a: None)
            self.assertEqual(self.downloads, 1)
            self.assertEqual(pricehist.today_prices(lambda *a: None), {})   # same MTGJSON build: nothing
            self.assertEqual(self.downloads, 1)
            pricehist.daily_update(lambda *a: None)   # the history has its own marker: still loads once
            self.assertEqual(self.downloads, 2)
            self.assertEqual(pricehist.daily_update(lambda *a: None), (0, "heute"))
            self.assertEqual(self.downloads, 2)


@needs_server
class YgoprodeckServer(unittest.TestCase):
    def test_check_db_version_first(self):
        spec = importlib.util.spec_from_file_location("bc_prices_rules", ROOT / "server" / "prices" / "prices.py")
        srv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(srv)
        calls = []

        def get_json(url, timeout=120):
            calls.append(url.rsplit("/", 1)[-1])
            if "checkDBVer" in url:
                return [{"database_version": "130.5", "last_update": "2026-10-25"}]
            return {"data": [{"name": "Dark Magician", "card_prices": [{"cardmarket_price": "0.20",
                                                                         "tcgplayer_price": "0.25"}]}]}
        with mock.patch.object(srv, "get_json", get_json), mock.patch.object(srv.time, "sleep"):
            self.assertEqual(srv.ygoprodeck_prices(), ({"Dark Magician": 0.2}, {"Dark Magician": 0.25}))
            self.assertEqual(srv.ygoprodeck_prices()[0], {"Dark Magician": 0.2})
        self.assertEqual(calls, ["checkDBVer.php", "cardinfo.php", "checkDBVer.php"])   # second day: no cardinfo


if __name__ == "__main__":
    unittest.main()
