"""A friend's library stays up to date (ports, desk-libdelta 06.11.2026, lead's item 11): the fingerprint counts the shared
library (keys "printing|language|foil|l" – five parts, older apps skip them), list deltas carry its changes and the
receiver writes them into "library". Deltas go to exactly the friends of share_codes, like every full post; a library
switched on or off since the full post is posted anew, never as a delta.

    python -m unittest tests/test_library_delta.py
"""
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from net import relay, relay_ctl
from collection import trade
from tests.test_share_per_friend import A, B, Mailbox, settings

LISTS = [["mh2", "50", "en", 0, 1]]
LIB = [["mh2", "50", "en", 0, 1], ["m10", "146", "en", 0, 4]]
LIB2 = [["mh2", "50", "en", 0, 1], ["m10", "146", "en", 0, 1], ["neo", "1", "en", 1, 2]]


class Sender(unittest.TestCase):
    def test_a_library_change_is_a_change(self):
        old = relay.fingerprint({"c": LISTS, "w": [], "lib": LIB})
        new = relay.fingerprint({"c": LISTS, "w": [], "lib": LIB2})
        self.assertEqual(relay.delta(old, new), {"m10|146|en|0|l": 1, "neo|1|en|1|l": 2})

    def test_without_library_as_before(self):
        fp = relay.fingerprint({"c": LISTS, "w": [["Bolt", 2]]})
        self.assertEqual(fp, {"mh2|50|en|0": 1, "w:Bolt": 2})
        self.assertFalse(relay.has_lib(fp))

    def test_older_apps_skip_library_keys(self):
        """apply_delta of older versions kept only keys with exactly four parts – a library key never lands in the list."""
        fp = relay.fingerprint({"c": [], "lib": LIB})
        self.assertTrue(all(len(k.split("|")) == 5 for k in fp))


class Receiver(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.ps = [mock.patch.object(trade, "friends_folder", return_value=self.tmp),
                   mock.patch.object(relay, "fill_names", lambda d: d),
                   mock.patch.object(trade, "FRIENDS", self.tmp)]
        for p in self.ps:
            p.start()
        self.pid = "p" * 32

    def tearDown(self):
        for p in self.ps:
            p.stop()

    def store(self, **d):
        f = trade.friend_path(self.tmp, self.pid)
        f.write_text(json.dumps(dict({"id": self.pid, "name": "Anna", "cards": LISTS, "wants": []}, **d)), "utf-8")
        return f

    def test_library_follows_the_delta(self):
        f = self.store(library=LIB)
        ok = relay.apply_delta("mtg", self.pid, {"m10|146|en|0|l": 1, "neo|1|en|1|l": 2, "mh2|50|en|0": 0})
        d = json.loads(f.read_text("utf-8"))
        self.assertTrue(ok)
        self.assertEqual(d["cards"], [])
        self.assertEqual(sorted(map(tuple, d["library"])), sorted(map(tuple, LIB2)))

    def test_library_change_without_a_library_fetches_everything(self):
        f = self.store()
        before = f.read_text("utf-8")
        self.assertFalse(relay.apply_delta("mtg", self.pid, {"neo|1|en|1|l": 2}))   # -> refetch the full post
        self.assertEqual(f.read_text("utf-8"), before)


class Controller(unittest.TestCase):
    """relay_send_delta: library deltas only where the full post carries the library; recipients = share_codes."""

    def run_tick(self, s, old, export):
        fp = pathlib.Path(tempfile.mkdtemp()) / "posted-lists.json"
        fp.write_text(json.dumps(relay.fingerprint(old)), "utf-8")
        calls = []
        fake = types.SimpleNamespace(settings=s, relay_fp_file=lambda: fp, relay_export=lambda: export,
                                     relay_send_lists=lambda quiet=False: calls.append("full"),
                                     _relay_bg=lambda what, fn: (calls.append(what), fn()))
        with Mailbox() as mb, mock.patch("games.current", return_value=types.SimpleNamespace(key="mtg")):
            relay_ctl.RelayControl.relay_send_delta(fake)
        return calls, mb

    def test_two_friends_only_the_switched_on_one_gets_the_library(self):
        """lead 06.11.: after a library change only the friend who gets my shared things receives library keys –
        the other one nothing at all."""
        s = settings(posted=True)
        s["relay"]["posted"]["mtg/lists"]["lib"] = True
        relay.share_codes(s)
        relay.set_share(s, B, False)
        calls, mb = self.run_tick(s, {"c": LISTS, "lib": LIB}, {"c": LISTS, "lib": LIB2})
        self.assertEqual(calls, ["delta"])
        self.assertEqual({p[0] for p in mb.parcels}, {A})
        self.assertTrue(all(k.endswith("|l") for k in mb.parcels[0][2]["d"]))
        self.assertFalse([p for p in mb.parcels if p[0] == B])

    def test_library_not_shared_no_library_keys(self):
        s = settings(posted=True)
        s["relay"]["posted"]["mtg/lists"]["lib"] = False
        relay.share_codes(s)
        calls, mb = self.run_tick(s, {"c": LISTS}, {"c": LISTS + [["neo", "1", "en", 0, 1]]})
        self.assertEqual(calls, ["delta"])
        self.assertEqual({p[0] for p in mb.parcels}, {A, B})
        self.assertFalse([k for p in mb.parcels for k in p[2]["d"] if k.endswith("|l")])

    def test_library_switched_on_posts_everything(self):
        s = settings(posted=True)
        s["relay"]["posted"]["mtg/lists"]["lib"] = False
        relay.share_codes(s)
        calls, mb = self.run_tick(s, {"c": LISTS}, {"c": LISTS, "lib": LIB})
        self.assertEqual(calls, ["full"])
        self.assertEqual(mb.parcels, [])

    def test_post_from_before_library_deltas_posts_everything_once(self):
        """The fingerprint file of an older version has no library keys although the post carries the library."""
        s = settings(posted=True)
        s["relay"]["posted"]["mtg/lists"]["lib"] = True
        relay.share_codes(s)
        calls, mb = self.run_tick(s, {"c": LISTS}, {"c": LISTS, "lib": LIB})
        self.assertEqual(calls, ["full"])
        self.assertEqual(mb.parcels, [])


if __name__ == "__main__":
    unittest.main()
