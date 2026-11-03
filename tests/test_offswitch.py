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


if __name__ == "__main__":
    unittest.main()
