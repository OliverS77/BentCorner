"""A withdrawn game (games.WITHDRAWN – here a made-up "paused" game with its own image host and mirror): its sources
are asked by nobody, whatever the manifest says – not as the fallback when our image mirror is down or has no copy,
and not its mirror either (legal 04.11.). The image is then simply not there (imgcache.fetch False → the tile shows
NoImage); everything else on our server is asked as before.

    python -m unittest tests/test_withdrawn_block.py
"""
import pathlib
import tempfile
import unittest
from unittest import mock

import games
from cards import imgcache
from games import offswitch
from net import netpolite
from system import contacts

PAUSED = "paused"
HOST = "img.paused.example"
MIRROR = contacts.SERVER + "/dl/paused"


class WithdrawnBlocked(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.blocked, self.own = set(netpolite.BLOCKED), set(netpolite.BLOCKED_OWN)
        netpolite.BLOCKED.clear()
        netpolite.BLOCKED_OWN.clear()
        for p in (mock.patch.object(games, "GAMES", games.GAMES + ((PAUSED, "Paused Game", False),)),
                  mock.patch.object(games, "WITHDRAWN", {PAUSED}),
                  mock.patch.dict(offswitch.HOSTS, {PAUSED: (HOST,)}),
                  mock.patch.dict(netpolite.MIRROR, {HOST: MIRROR}),
                  mock.patch.object(netpolite, "_request", self.request),
                  mock.patch.object(netpolite, "_wait", lambda host, gap: None)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.restore)
        games.block_withdrawn()

    def restore(self):
        netpolite.BLOCKED.clear()
        netpolite.BLOCKED.update(self.blocked)
        netpolite.BLOCKED_OWN.clear()
        netpolite.BLOCKED_OWN.update(self.own)

    def request(self, method, url, host, **kw):   # nothing may get this far for the paused game
        self.calls.append(url)
        raise netpolite.requests.ConnectionError("mirror down")   # as if our server were unreachable

    def test_source_never_asked_even_with_the_mirror_down(self):
        with self.assertRaises(netpolite.requests.RequestException):
            netpolite.get(f"https://{HOST}/images/cardlist/AB01-001.png")
        self.assertEqual(self.calls, [])

    def test_its_mirror_not_asked_either_also_under_the_old_name(self):
        old = next(iter(netpolite.OLD_HOSTS))
        for url in (MIRROR + "/images/cardlist/AB01-001.png",
                    MIRROR.replace(netpolite.SERVER_HOST, old) + "/images/cardlist/AB01-001.png"):
            with self.assertRaises(netpolite.requests.RequestException):
                netpolite.get(url)
        self.assertEqual(self.calls, [])

    def test_the_image_is_just_missing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(imgcache, "_images_off", lambda: False):
            path = pathlib.Path(tmp) / "AB01-001.jpg"
            self.assertFalse(imgcache.fetch(path, f"https://{HOST}/images/cardlist/AB01-001.png"))
            self.assertFalse(path.exists())
        self.assertEqual(self.calls, [])

    def test_the_rest_of_our_server_still_asked(self):
        with self.assertRaises(netpolite.requests.RequestException):
            netpolite.get(contacts.SERVER + "/dl/manifest.json")
        self.assertTrue(any(u.endswith("/dl/manifest.json") for u in self.calls))

    def test_the_manifest_switch_does_not_release_it(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(offswitch, "_off", None), \
                mock.patch("system.datahome.HOME", pathlib.Path(tmp)):
            offswitch._blocked.clear()
            self.assertEqual(offswitch.apply({PAUSED: {}})[0], [PAUSED])
            offswitch.apply({})   # taken out of games_off again: still withdrawn, still blocked
        self.assertIn(HOST, netpolite.BLOCKED)


class ImportOrder(unittest.TestCase):
    def test_blocked_whichever_module_comes_first(self):
        # netpolite imports games, games blocks through netpolite: with netpolite first (e.g. a tool) the block must
        # still be complete once both are loaded – not an error, not left out
        import subprocess
        import sys
        root = pathlib.Path(__file__).resolve().parents[1]
        code = ("from net import netpolite; import games\n"
                "a = (set(netpolite.BLOCKED), set(netpolite.BLOCKED_OWN)); games.block_withdrawn()\n"
                "assert a == (set(netpolite.BLOCKED), set(netpolite.BLOCKED_OWN)), a\n")
        r = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
