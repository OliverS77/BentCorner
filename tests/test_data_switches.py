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
            from net import relay

            def full(**kw):   # /v1 only in Full Orbit (lead/legal 14.11.) – the exchange on
                s = dict(kw)
                relay.state(s)["on"] = True
                return s
            self.assertFalse(anonstats.due(full(stats_share=False)))
            self.assertFalse(anonstats.due(full()))                      # not asked yet = no
            self.assertTrue(anonstats.due(full(stats_share=True)))
            self.assertFalse(anonstats.due(full(stats_share=True, stats_sent=time.time())))   # once a week
            self.assertFalse(anonstats.due({"stats_share": True}))   # Core/Near Orbit: never

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
        with mock.patch.object(deckimport.netpolite, "get", side_effect=AssertionError("asked the site")):
            for url in ("https://moxfield.com/decks/abc123", "https://archidekt.com/decks/12345"):
                with self.assertRaises(RuntimeError):
                    deckimport.fetch(url)

    def test_edhrec_stays_off(self):
        from cards import edhrec
        self.assertFalse(edhrec.ALLOWED)



class SpellbookGate(unittest.TestCase):
    """Commander Spellbook and EDHTop16 only from Near Orbit on and with their switch (Oliver/legal 16.11.2026): in Core
    or with the switch off nothing goes to either – no combo search, no bracket, no cEDH numbers, no deck import by
    link, no cached combos shown. Network mocked, never real."""

    def setUp(self):
        from system import orbit
        self.orbit = orbit
        self.addCleanup(orbit.bind, None)

    def bind(self, level, switch=None):
        s = {"orbit": "near" if level == "full" else level, "relay": {"on": level == "full"}}
        if switch is not None:
            s["spellbook"] = switch
        self.orbit.bind(s)
        return s

    def calls(self):
        from cards import combos
        from collection import deckimport
        sent = []

        def post(url, **kw):
            sent.append(url)
            r = mock.Mock(ok=True, status_code=200)
            r.json.return_value = {"results": {}, "data": {"commander": None}, "bracketTag": ""}
            return r

        def get(url, **kw):
            sent.append(url)
            r = mock.Mock(ok=True, status_code=200)
            r.json.return_value = {"cards": [], "deck": {}}
            return r
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(combos.netpolite, "post", post), mock.patch.object(deckimport.netpolite, "get", get), \
                mock.patch.object(combos, "CACHE", pathlib.Path(tmp.name)):
            for fn in (lambda: combos.find(["Atraxa"], {"Sol Ring": 1}), lambda: combos.cedh(["Atraxa"]),
                       lambda: deckimport.fetch("https://example.org/deck/1")):
                try:
                    fn()
                except Exception:  # noqa: BLE001 – refused (off) or the mocked answer's shape
                    pass
        return sent

    def test_core_sends_nothing(self):
        self.bind("core")
        self.assertEqual(self.calls(), [])
        self.bind("core", True)   # the switch alone does not open Core
        self.assertEqual(self.calls(), [])

    def test_switch_off_sends_nothing(self):
        self.bind("near", False)
        self.assertEqual(self.calls(), [])
        self.bind("full", False)
        self.assertEqual(self.calls(), [])

    def test_near_and_full_as_before(self):
        for lv in ("near", "full"):
            self.bind(lv)   # default: on
            sent = self.calls()
            self.assertTrue(any("commanderspellbook.com/find-my-combos" in u for u in sent), lv)
            self.assertTrue(any("edhtop16.com" in u for u in sent), lv)
            self.assertTrue(any("card-list-from-url" in u for u in sent), lv)

    def test_level_change_at_runtime_and_unbound(self):
        s = self.bind("near")
        self.assertTrue(self.orbit.spellbook_ok())
        s["orbit"] = "core"
        self.assertFalse(self.orbit.spellbook_ok())
        self.orbit.bind(None)
        self.assertFalse(self.orbit.spellbook_ok())   # fails closed

    def test_link_import_says_why(self):
        from collection import deckimport
        self.bind("core")
        with self.assertRaises(RuntimeError) as e:
            deckimport.fetch("https://example.org/deck/1")
        self.assertEqual(str(e.exception), deckimport.LINK_OFF)
        from locales import de
        self.assertIn(deckimport.LINK_OFF, de.TEXTS)

    def test_deck_editor_no_lookup_no_cache_in_core(self):
        from collection import deckcore
        fake = types.SimpleNamespace(deck={"format": "commander"}, rows={}, online={"csb": {"included": [1]}},
                                     page=types.SimpleNamespace(ctrl=types.SimpleNamespace(
                                         settings={"orbit": "core", "relay": {"on": False}})))
        with mock.patch.object(deckcore.combos, "cached_find", side_effect=AssertionError("cache read")):
            deckcore.DeckEditor.online_lookup(fake)
        self.assertEqual(fake.online, {})
        fake.page.ctrl.settings = {"orbit": "near", "spellbook": False}
        fake.online = {"csb": {}}
        with mock.patch.object(deckcore.combos, "cached_find", side_effect=AssertionError("cache read")):
            deckcore.DeckEditor.online_lookup(fake)
        self.assertEqual(fake.online, {})

    def test_wait_on_429(self):
        self.assertGreaterEqual(netpolite.COOL_429["backend.commanderspellbook.com"], 60)
        self.assertGreaterEqual(netpolite.COOL_429["edhtop16.com"], 60)
        self.assertIn("BentCorner/", netpolite.UA)
        import version
        self.assertIn(version.VERSION, netpolite.UA)



class ScryfallOnlyForMagic(unittest.TestCase):
    """The detail view asked Scryfall for a Pokémon ID (api.scryfall.com/cards/xy7-98, lead 16.11.2026): Scryfall's
    card record and extra info only for a game whose details are online (Magic). Network mocked."""

    def ask(self, key):
        import games
        from cards import library
        sent = []

        def get(url, **kw):
            sent.append(url)
            r = mock.Mock(status_code=200)
            r.json.return_value = {"name": "x", "prints_search_uri": "https://api.scryfall.com/x?q=1",
                                   "rulings_uri": "https://api.scryfall.com/r", "data": []}
            return r
        g = games.load(key)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = pathlib.Path(tmp.name)
        with mock.patch.object(games, "current", lambda: g), mock.patch.object(library.netpolite, "get", get), \
                mock.patch.object(library, "DETAILS", d), mock.patch.object(library, "FULL", d / "full"):
            full = library.card_full("xy7-98")
            info = library.card_details({"id": "xy7-98_0"})
        return sent, full, info

    def test_other_games_never_ask_scryfall(self):
        for key in ("pokemon", "yugioh", "lorcana"):
            sent, full, info = self.ask(key)
            self.assertEqual(sent, [], key)
            self.assertIsNone(full, key)
            self.assertEqual(info, {}, key)

    def test_magic_as_before(self):
        sent, full, info = self.ask("mtg")
        self.assertTrue(any("api.scryfall.com/cards/xy7-98" in u for u in sent))
        self.assertIsNotNone(full)


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
