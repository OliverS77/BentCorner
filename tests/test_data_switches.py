"""Test phase, rows "45" (2026-10-26): request log, one image at a time at the publishers, a missing image is not
asked for again, the Cardmarket file at most once a day in every price mode, data switches off = no request to our
mailbox, link imports (Moxfield/Archidekt) and EDHREC stay off.

    python -m unittest tests/test_data_switches.py
"""
import os
import pathlib
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

import requests

from net import netpolite


class _R:
    def __init__(self, code=200, content=b"x"):
        self.status_code, self.content, self.headers = code, content, {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def slow(code=200, delay=0.05):
    def request(method, url, **kw):
        time.sleep(delay)
        return _R(code)
    return request


class Log(unittest.TestCase):
    def setUp(self):
        netpolite._next.clear()
        netpolite._cool.clear()
        netpolite._missing_at.clear()

    def test_log_records_and_stops(self):
        with mock.patch.object(netpolite.requests, "request", slow(delay=0)):
            netpolite.log_start()
            netpolite.get("https://api.scryfall.com/cards/named?exact=Opt")
            log = netpolite.log_stop()
            netpolite.get("https://api.scryfall.com/cards/named?exact=Opt")
        self.assertEqual([(e["host"], e["path"], e["status"]) for e in log],
                         [("api.scryfall.com", "/cards/named", 200)])
        self.assertEqual(netpolite.log_stop(), [])   # off: nothing more noted

    def test_publisher_images_one_at_a_time(self):
        """Six image threads against Ravensburger: never two requests at once, gap counted from the end. (Normally
        the images come via our mirror – this is the rule for the publisher's host itself, used when it can't.)"""
        with mock.patch.object(netpolite.requests, "request", slow(delay=0.05)),                 mock.patch.dict(netpolite.MIRROR, clear=True):
            netpolite.log_start()
            ts = [threading.Thread(target=netpolite.get,
                                   args=(f"https://api.lorcana.ravensburger.com/images/en/set1/{i}.jpg",))
                  for i in range(6)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            log = sorted(netpolite.log_stop(), key=lambda e: e["start"])
        self.assertEqual(len(log), 6)
        gap = netpolite.POLICY["api.lorcana.ravensburger.com"]
        for a, b in zip(log, log[1:]):
            self.assertGreaterEqual(b["start"], a["end"] + gap * 0.9)   # strictly one after the other

    def test_serial_hosts(self):
        for host in ("api.lorcana.ravensburger.com", "cmsassets.rgpub.io", "images.ygoprodeck.com",
                     "assets.tcgdex.net"):
            self.assertIn(host, netpolite.SERIAL)
        self.assertNotIn("cards.scryfall.io", netpolite.SERIAL)   # Scryfall: images explicitly unlimited


class MissingImage(unittest.TestCase):
    def setUp(self):
        netpolite._missing_at.clear()
        netpolite._lasting = {}   # never the data folder's file
        netpolite._next.clear()

    def test_404_not_asked_again_within_an_hour(self):
        from cards import library
        calls = []
        with mock.patch.object(netpolite, "get", lambda url, **kw: calls.append(url) or _R(404)):
            for _ in range(5):   # every repaint of the tile asks
                with self.assertRaises(requests.HTTPError):
                    library.fetch_bytes("https://cards.scryfall.io/normal/front/x.jpg")
        self.assertEqual(len(calls), 1)
        url = "https://cards.scryfall.io/normal/front/x.jpg"
        netpolite._missing_at[url] -= netpolite.MISSING_TTL + 1
        self.assertTrue(netpolite.is_missing(url))    # a real 404: not even an hour later (tester log 0.9.2) …
        netpolite._lasting[url] -= netpolite.LASTING_DAYS * 86400 + 1
        self.assertFalse(netpolite.is_missing(url))   # … only after days

    def test_imgcache_same(self):
        from cards import imgcache
        calls = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(netpolite, "get", lambda url, **kw: calls.append(url) or _R(404)):
            for _ in range(3):
                self.assertFalse(imgcache.fetch(pathlib.Path(d) / "a.jpg", "https://cards.scryfall.io/a.jpg"))
        self.assertEqual(len(calls), 1)


class CardmarketOncePerDay(unittest.TestCase):
    """daily_file: every start, every close, every game switch on the same day reads the local copy."""

    def test_once_a_day(self):
        from games.base import daily_file
        net = types.SimpleNamespace(n=0)

        def get_large(url, **kw):
            net.n += 1
            return b'{"priceGuides": []}'
        net.get_large = get_large
        with tempfile.TemporaryDirectory() as d:
            cache = pathlib.Path(d) / "card-data" / "cardmarket-guide.json"
            for _ in range(3):   # start, close, game switch
                self.assertEqual(daily_file(net, "https://downloads.s3.cardmarket.com/x.json", cache), b'{"priceGuides": []}')
            self.assertEqual(net.n, 1)
            yesterday = time.time() - 86400
            os.utime(cache, (yesterday, yesterday))
            daily_file(net, "https://downloads.s3.cardmarket.com/x.json", cache)
            self.assertEqual(net.n, 2)   # a new day: the new file

    def test_games_use_it(self):
        for name in ("pokemon", "lorcana"):
            path = pathlib.Path(__file__).resolve().parents[1] / "games" / f"{name}.py"
            src = path.read_text("utf-8")
            self.assertTrue(any(f in src for f in ("cardmarket_guide(CM_GUIDE", "daily_prices(ext, CM_GUIDE", "daily_file(net, CM_GUIDE")), name)
            self.assertNotIn("get_large(CM_GUIDE", src, name)

    def test_game_jobs_once_per_day_and_mode(self):
        """Start/daily: enqueued once a day per game – a second program start the same day doesn't; manual: never."""
        import app
        for mode, want in (("start", 1), ("daily", 1), ("manual", 0), ("close", 0)):
            settings = {"price_update": mode}
            jobs = []
            game = types.SimpleNamespace(key="pokemon", price_source="daily", update_prices=lambda *a, **k: None)
            for _start in range(2):   # two program starts on the same day
                win = types.SimpleNamespace(settings=settings, enqueue=lambda *a, **k: jobs.append(a),
                                            settings_changed=lambda: None)
                with mock.patch.object(app.games, "current", lambda: game), \
                        mock.patch.object(app.carddb, "exists", return_value=True):
                    app.MainWindow.game_jobs(win)
            self.assertEqual(len(jobs), want, mode)

    def test_no_prices_without_card_database(self):
        """Lorcana before its first build: no price job (it opened the missing database = left an empty file, and
        the next game switch to Lorcana crashed – 0.9.2.54)."""
        import app
        jobs = []
        game = types.SimpleNamespace(key="lorcana", price_source="daily", update_prices=lambda *a, **k: None)
        win = types.SimpleNamespace(settings={"price_update": "start"}, enqueue=lambda *a, **k: jobs.append(a),
                                    settings_changed=lambda: None)
        with mock.patch.object(app.games, "current", lambda: game), \
                mock.patch.object(app.carddb, "exists", return_value=False):
            app.MainWindow.game_jobs(win)
        self.assertEqual(jobs, [])


class SwitchesOff(unittest.TestCase):
    def test_usage_numbers_only_with_consent(self):
        from net import anonstats
        from system import datahome
        import version
        with mock.patch.object(datahome, "FROZEN", True), mock.patch.object(datahome, "TEST", False), \
                mock.patch.object(version, "is_release", lambda v=None: True):
            self.assertFalse(anonstats.due({"stats_share": False}))
            self.assertFalse(anonstats.due({}))                      # not asked yet = no
            self.assertTrue(anonstats.due({"stats_share": True}))
            self.assertFalse(anonstats.due({"stats_share": True, "stats_sent": time.time()}))   # once a week

    def test_team_news_not_fetched_when_off(self):
        from net import teamnews, updater
        calls = []
        man = {"latest": "0.0.1", "platforms": {}}
        with mock.patch.object(updater, "fetch_manifest", lambda base: dict(man)), \
                mock.patch.object(teamnews, "fetch_news", lambda base: calls.append(base) or []):
            for on in (False, True):
                u = updater.Updater(news=lambda on=on: on)
                u.check(auto_download=False)
                for _ in range(100):
                    if u.state not in ("idle", "checking"):
                        break
                    time.sleep(0.01)
        self.assertEqual(len(calls), 1)   # only with "Messages from the team" on

    def test_friends_off_by_default(self):
        from net import relay
        self.assertFalse(relay.enabled({}))

    def test_studio_upload_needs_consent(self):
        from ui import qstudio
        fake = types.SimpleNamespace(_box_ids=lambda: ["c1"], ctrl=types.SimpleNamespace(settings={}))
        with mock.patch.object(qstudio.shutil, "copy2", side_effect=AssertionError("uploaded without consent")):
            self.assertIsNone(qstudio.StudioBackend.uploadBox(fake))

    def test_link_imports_stay_off(self):
        from collection import deckimport
        self.assertEqual(deckimport.ALLOWED, {"moxfield": False, "archidekt": False})
        with mock.patch.object(deckimport.netpolite, "get", side_effect=AssertionError("asked the site")):
            for url in ("https://moxfield.com/decks/abc123", "https://archidekt.com/decks/12345"):
                with self.assertRaises(RuntimeError):
                    deckimport.fetch(url)

    def test_edhrec_stays_off(self):
        from cards import edhrec
        self.assertFalse(edhrec.ALLOWED)


if __name__ == "__main__":
    unittest.main()


class NetpoliteHardening(unittest.TestCase):
    """Review 2026-10-26: reachable contact in the User-Agent, bulk loading never past the mirror, timeout."""

    def setUp(self):
        netpolite._next.clear()
        netpolite._cool.clear()
        netpolite._missing_at.clear()
        netpolite._new_down_until[0] = 0.0

    def test_user_agent_reachable_contact(self):
        from system import contacts
        self.assertIn(contacts.MAIL, netpolite.UA)
        self.assertIn(contacts.SITE, netpolite.UA)
        self.assertNotIn("github.com", netpolite.UA)   # the repo is private: a 404 for the services
        seen = []
        with mock.patch.object(netpolite.requests, "request",
                               lambda m, u, headers=None, **kw: seen.append(headers) or _R(200)):
            netpolite.get("https://api.scryfall.com/sets", headers={"User-Agent": "something else"})
        self.assertEqual(seen[0]["User-Agent"], netpolite.UA)   # always ours, whatever the caller passes

    def calls_with(self, mirror_answer):
        hosts = []

        def request(method, url, **kw):
            hosts.append(url.split("/")[2])
            if url.split("/")[2] in netpolite.OWN:   # our mirror – under the new and the old name
                if isinstance(mirror_answer, Exception):
                    raise mirror_answer
                return _R(mirror_answer)
            return _R(200)
        return hosts, request

    def test_bulk_never_past_the_mirror(self):
        url = "https://assets.tcgdex.net/en/sv/sv03/1/high.webp"
        for answer in (503, 404, requests.ConnectionError("down")):
            hosts, request = self.calls_with(answer)
            with mock.patch.object(netpolite.requests, "request", request), mock.patch.object(netpolite.time, "sleep"):
                with netpolite.mirror_only():
                    try:
                        netpolite.get(url)
                    except requests.RequestException:
                        pass   # mirror down: the bulk loader stops
            self.assertNotIn("assets.tcgdex.net", hosts, f"mirror answered {answer!r}")
            netpolite._cool.clear()

    def test_single_image_may_go_direct(self):
        hosts, request = self.calls_with(503)
        with mock.patch.object(netpolite.requests, "request", request), mock.patch.object(netpolite.time, "sleep"):
            self.assertEqual(netpolite.get("https://assets.tcgdex.net/en/sv/sv03/2/high.webp").status_code, 200)
        self.assertEqual(hosts[-1], "assets.tcgdex.net")

    def test_default_timeout(self):
        seen = []
        with mock.patch.object(netpolite.requests, "request", lambda m, u, **kw: seen.append(kw.get("timeout")) or _R(200)):
            netpolite.get("https://api.scryfall.com/sets")
            netpolite.get("https://api.scryfall.com/sets", timeout=5)
        self.assertEqual(seen, [30, 5])
