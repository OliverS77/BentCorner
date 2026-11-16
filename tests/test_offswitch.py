"""Emergency switch per game (games/offswitch.py): "games_off" in the signed manifest switches a game off for
everyone – gone from the game picker, no requests to its sources, the open game falls back to Magic, user data stays;
taken out of the list, the game is simply back.

    python -m unittest tests/test_offswitch.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import games
from games import offswitch
from net import netpolite
from system import datahome


class OffSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.patch = mock.patch.object(datahome, "HOME", self.home)
        self.patch.start()
        self.blocked = set(netpolite.BLOCKED)
        offswitch._off = None
        offswitch._blocked.clear()

    def tearDown(self):
        offswitch.apply({})   # back to "nothing off" for the other tests
        offswitch._off = None
        self.patch.stop()
        netpolite.BLOCKED.clear()
        netpolite.BLOCKED.update(self.blocked)
        self.tmp.cleanup()

    def ready(self, key):
        return next(c for c in games.choices() if c["key"] == key)

    def test_switched_off_game_leaves_the_picker_and_comes_back(self):
        self.assertTrue(self.ready("lorcana")["ready"])
        went, back = offswitch.apply({"lorcana": {"de": "weg", "en": "gone"}})
        self.assertEqual((went, back), (["lorcana"], []))
        self.assertFalse(self.ready("lorcana")["ready"])
        self.assertTrue(self.ready("lorcana")["off"])
        went, back = offswitch.apply({})
        self.assertEqual((went, back), ([], ["lorcana"]))
        self.assertTrue(self.ready("lorcana")["ready"])

    def test_notice_only_once(self):
        self.assertEqual(offswitch.apply({"riftbound": {}})[0], ["riftbound"])
        self.assertEqual(offswitch.apply({"riftbound": {}}), ([], []))   # next update check: nothing new

    def test_state_survives_a_restart_offline(self):
        offswitch.apply({"riftbound": {"de": "x", "en": "y"}})
        self.assertTrue((self.home / offswitch.FILE_NAME).exists())
        offswitch._off = None   # "restart": read from the file, no manifest
        self.assertTrue(offswitch.is_off("riftbound"))
        offswitch.apply({})
        self.assertFalse((self.home / offswitch.FILE_NAME).exists())

    def test_sources_are_blocked_and_released(self):
        offswitch.apply({"lorcana": {}})
        for h in offswitch.HOSTS["lorcana"]:
            self.assertIn(h, netpolite.BLOCKED)
        with self.assertRaises(netpolite.requests.RequestException):
            netpolite.get("https://api.lorcana.ravensburger.com/images/en/set1/1_x.jpg")
        offswitch.apply({})
        for h in offswitch.HOSTS["lorcana"]:
            self.assertNotIn(h, netpolite.BLOCKED)

    def test_switch_on_keeps_blocks_it_did_not_make(self):
        netpolite.block_hosts(["images.example.test"])   # e.g. a game unlocked only locally (images_off)
        offswitch.apply({"riftbound": {}})
        offswitch.apply({})
        self.assertIn("images.example.test", netpolite.BLOCKED)

    def test_magic_and_unknown_games_cannot_be_switched_off(self):
        went, _ = offswitch.apply({"mtg": {}, "nonsense": {}, "pokemon": "plain text"})
        self.assertEqual(went, ["pokemon"])
        self.assertTrue(self.ready("mtg")["ready"])
        self.assertEqual(offswitch.reason("pokemon", "en"), "plain text")

    def test_default_reason_names_the_game(self):
        offswitch.apply({"riftbound": {"de": "", "en": ""}})
        self.assertIn("Riftbound ist vorübergehend nicht verfügbar", offswitch.reason("riftbound", "de"))
        self.assertIn("Your collection is kept", offswitch.reason("riftbound", "en"))

    def test_open_game_falls_back_to_magic_at_start(self):
        s = self.home / "settings.json"
        s.write_text(json.dumps({"game": "lorcana"}), "utf-8")
        self.assertEqual(games.active_key(s), "lorcana")
        offswitch.apply({"lorcana": {}})
        self.assertEqual(games.active_key(s), games.DEFAULT)
        self.assertEqual(json.loads(s.read_text("utf-8"))["game"], "lorcana")   # settings untouched



class KillSwitchReally(unittest.TestCase):
    """Oliver/legal 16.11.2026 – an emergency switch really switches off: a game off (games_off) or only its images off
    (images_off, Magic too) = no request to its foreign hosts nor to its paths on our server, not even the fallback
    when the mirror has a fault; a 410 from the mirror counts as "off" (remembered, no fallback); the image cache on
    disk is locked (renamed), not deleted. Network never real: every request is caught and counted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.patch = mock.patch.object(datahome, "HOME", self.home)
        self.patch.start()
        self.blocked, self.blocked_own = set(netpolite.BLOCKED), set(netpolite.BLOCKED_OWN)
        offswitch._off = offswitch._img_off = None
        offswitch._blocked.clear()
        offswitch._blocked_own.clear()
        self.sent = []
        self.answer = 200

        def request(method, url, host, **kw):
            self.sent.append(url)
            r = mock.Mock(status_code=self.answer, headers={}, content=b"img")
            r.raise_for_status = mock.Mock(side_effect=None if self.answer < 400 else
                                           netpolite.requests.HTTPError(str(self.answer)))
            return r
        self.p2 = mock.patch.object(netpolite, "_request", request)
        self.p2.start()
        self.p3 = mock.patch.object(netpolite, "_wait", lambda host, gap: None)
        self.p3.start()

    def tearDown(self):
        offswitch.apply_images({})
        offswitch.apply({})
        offswitch._off = offswitch._img_off = None
        for q in (self.p3, self.p2, self.patch):
            q.stop()
        netpolite.BLOCKED.clear()
        netpolite.BLOCKED.update(self.blocked)
        netpolite.BLOCKED_OWN.clear()
        netpolite.BLOCKED_OWN.update(self.blocked_own)
        self.tmp.cleanup()

    def fetch(self, url, name="a.jpg"):
        from cards import imgcache
        with mock.patch.object(imgcache, "offline", lambda: False), \
                mock.patch.object(imgcache, "_images_off", lambda: False):   # the open game: tested apart
            return imgcache.fetch(self.home / "img" / name, url)

    def test_images_off_blocks_image_hosts_and_the_mirror_path_only(self):
        offswitch.apply_images({"pokemon": {}})
        self.assertIn("assets.tcgdex.net", netpolite.BLOCKED)
        self.assertIn("images.pokemontcg.io", netpolite.BLOCKED)
        self.assertNotIn("api.tcgdex.net", netpolite.BLOCKED)                 # card data keeps working
        self.assertIn("/dl/tcgdex/", netpolite.BLOCKED_OWN)
        self.assertNotIn("/dl/packs/pokemon/", netpolite.BLOCKED_OWN)
        self.answer = 503   # even a mirror with a fault: no fallback, the request never leaves
        self.assertFalse(self.fetch("https://assets.tcgdex.net/en/sv/sv01/1/high.png"))
        self.assertEqual(self.sent, [])
        offswitch.apply_images({})
        self.assertNotIn("assets.tcgdex.net", netpolite.BLOCKED)
        self.assertNotIn("/dl/tcgdex/", netpolite.BLOCKED_OWN)

    def test_game_off_blocks_everything_of_it_for_every_game(self):
        for key in ("pokemon", "yugioh", "lorcana", "riftbound"):
            offswitch.apply({key: {}})
            for h in offswitch.HOSTS[key] + offswitch.IMAGE_HOSTS[key]:
                self.assertIn(h.lower(), netpolite.BLOCKED, key)
            for path in offswitch.own_paths(key):
                self.assertIn(path, netpolite.BLOCKED_OWN, key)
            offswitch.apply({})
        offswitch.apply({"yugioh": {}})
        from system import contacts
        self.assertFalse(self.fetch(contacts.SERVER + "/dl/packs/yugioh/img/80181649.jpg"))
        with self.assertRaises(netpolite.requests.RequestException):
            netpolite.get(contacts.SERVER + "/dl/prices/yugioh.json.gz")
        self.assertEqual(self.sent, [])

    def test_mirror_answers_410_no_fallback_and_remembered(self):
        self.answer = 410
        url = "https://assets.tcgdex.net/en/sv/sv01/7/high.png"
        self.assertFalse(self.fetch(url))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("/dl/tcgdex/", self.sent[0])                             # the mirror, never the source
        self.assertFalse(self.fetch(url))                                      # shown again: not asked again
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(netpolite.is_missing(url))

    def test_mirror_fault_still_falls_back_when_nothing_is_off(self):   # the privacy text's "fault" case
        self.answer = 503
        self.fetch("https://assets.tcgdex.net/en/sv/sv01/8/high.png")
        self.assertTrue(any("assets.tcgdex.net" in u for u in self.sent))

    def test_magic_images_may_go_off_magic_itself_not(self):
        self.assertEqual(offswitch.apply_images({"mtg": {}})[0], ["mtg"])
        self.assertIn("cards.scryfall.io", netpolite.BLOCKED)
        self.assertEqual(offswitch.apply({"mtg": {}})[0], [])

    def test_state_survives_a_restart(self):
        offswitch.apply_images({"lorcana": {"de": "x", "en": "y"}})
        self.assertTrue((self.home / offswitch.IMAGES_FILE).exists())
        offswitch._img_off = None
        self.assertTrue(offswitch.images_locked("lorcana"))
        self.assertEqual(offswitch.image_reason("lorcana", "en"), "y")

    def test_default_note_claims_no_reason(self):
        offswitch.apply_images({"pokemon": {}})
        self.assertEqual(offswitch.image_reason("pokemon", "de"),
                         "Bilder von Pokémon sind vorübergehend abgeschaltet. Deine Sammlung und alle Daten bleiben.")
        self.assertNotIn("rights holder", offswitch.image_reason("pokemon", "en"))

    def test_cache_locked_not_deleted_and_back(self):
        imgs = self.home / "data" / "games" / "pokemon" / "card-images" / "sv01"
        thumbs = self.home / "data" / "games" / "pokemon" / "card-data" / "thumbs"
        for d in (imgs, thumbs):
            d.mkdir(parents=True)
            (d / "1.jpg").write_bytes(b"x")
        mtg = self.home / "data" / "card-images" / "lea"
        mtg.mkdir(parents=True)
        (mtg / "1.jpg").write_bytes(b"m")
        offswitch.apply_images({"pokemon": {}})
        self.assertFalse((imgs / "1.jpg").exists())
        self.assertFalse((thumbs / "1.jpg").exists())
        self.assertTrue((imgs.parent.with_name("card-images.off") / "sv01" / "1.jpg").exists())
        self.assertTrue((mtg / "1.jpg").exists())                              # another game untouched
        imgs.mkdir(parents=True)                                               # a file appeared meanwhile
        (imgs / "2.jpg").write_bytes(b"y")
        offswitch.apply_images({})
        self.assertTrue((imgs / "1.jpg").exists())                             # back without a new download
        self.assertTrue((imgs / "2.jpg").exists())
        self.assertTrue((thumbs / "1.jpg").exists())
        self.assertFalse(imgs.parent.with_name("card-images.off").exists())

    def test_whole_game_off_locks_its_cache_too_and_start_follows_the_file(self):
        d = self.home / "data" / "games" / "lorcana" / "card-images"
        d.mkdir(parents=True)
        (d / "x.jpg").write_bytes(b"x")
        (self.home / offswitch.FILE_NAME).write_text(json.dumps({"lorcana": {"de": "", "en": ""}}), "utf-8")
        offswitch._off = None
        offswitch.startup()                                                    # e.g. the switch came while closed
        self.assertFalse(d.exists())
        self.assertTrue(d.with_name("card-images.off").exists())

    def test_open_game_shows_no_image_not_even_its_local_copy(self):
        from cards import imgcache
        from ui import quickimages
        offswitch.apply_images({"pokemon": {}})
        g = games.load("pokemon")
        with mock.patch.object(games, "current", lambda: g):
            self.assertTrue(imgcache._images_off())
            quickimages.register("t1", local="C:/x.jpg", url="https://assets.tcgdex.net/x.png", cache="C:/c.jpg")
            self.assertEqual(quickimages._sources["t1"], (None, None, None, None))
        m = games.load("mtg")
        with mock.patch.object(games, "current", lambda: m):
            self.assertFalse(imgcache._images_off())


if __name__ == "__main__":
    unittest.main()
