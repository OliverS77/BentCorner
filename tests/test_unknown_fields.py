"""An extra field in a card entry ("from_print", collection/printmove – and whatever comes later) must never get in the
way: kept where whole entries are stored (collection, sessions, trash), ignored where rows leave the PC (exports,
Bent°Corner file for friends, friend changes over the relay). Lead's condition for from_print, 30.10.2026.

    python -m unittest tests/test_unknown_fields.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import collection as collmod
from collection import trade
from net import relay
from system import datastore


def entry(**kw):
    return dict({"id": "dabl-en001_0", "name": "Ash Blossom & Joyous Spring", "set": "DABL", "number": "EN001",
                 "rarity": "common", "finishes": ["nonfoil"], "booster": True, "eur": 0.5, "eur_foil": None,
                 "img": "", "url": "", "lang": "ja", "foil": False, "count": 2, "uid": "u1", "added": 1.0,
                 "from_print": "dabl-jp001", "some_future_field": {"x": 1}}, **kw)


class UnknownFields(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        for p in (mock.patch.object(collmod, "FILE", self.root / "collection.json"),
                  mock.patch.object(collmod, "MINE", self.root),
                  mock.patch("system.undo.before_write", lambda *a, **k: None),
                  mock.patch.object(datastore, "TRASH", self.root / "trash")):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_kept_in_collection_and_trash(self):
        c = collmod.Collection()
        c.items = [entry()]
        c.save()
        self.assertEqual(collmod.Collection().items[0]["from_print"], "dabl-jp001")
        name = datastore.trash_put("cards", "x", {"items": [entry()]})
        back = datastore.trash_take(name)
        c2 = collmod.Collection()
        c2.items = []
        c2.restore_items(back["data"]["items"])
        self.assertEqual((c2.items[0]["from_print"], c2.items[0]["some_future_field"]), ("dabl-jp001", {"x": 1}))

    def test_session_sync_carries_it(self):
        c = collmod.Collection()
        sess = {"id": "s1", "info": {"kind": "cards"}, "packs": [{"cards": [entry(added=5.0)]}]}
        self.assertTrue(c.sync_session(sess))
        self.assertEqual(c.items[0]["from_print"], "dabl-jp001")
        sess["packs"][0]["cards"][0]["from_print"] = "dabl-sp001"
        c.sync_session(sess)
        self.assertEqual(c.items[0]["from_print"], "dabl-sp001")

    def test_ignored_in_exports_and_friend_file(self):
        groups = collmod.groups_of([entry()])
        for fmt in ("manabox", "moxfield", "excel"):
            collmod.export_csv(groups, self.root / f"out-{fmt}.csv", fmt)
            self.assertNotIn("dabl-jp001", (self.root / f"out-{fmt}.csv").read_text("utf-8-sig"))
        data = trade.build_export({"id": "me"}, [entry()])
        self.assertNotIn("from_print", json.dumps(data))
        trade.write_bentcorner(self.root / "me.bentcorner", dict(data, extra_top_level={"y": 2}))
        parsed = trade.read_file(self.root / "me.bentcorner")
        with mock.patch.object(trade, "FRIENDS", self.root / "friends"):
            out = trade.friend_from_import(parsed)
        self.assertEqual(out["cards"][0][:2], ["dabl", "EN001"])
        self.assertNotIn("extra_top_level", out)

    def test_friend_delta_applies(self):
        """relay.apply_delta: a friend's changes onto their stored list (it used to fail with a NameError)."""
        friends = self.root / "friends"
        friends.mkdir()
        (friends / "f1.json").write_text(json.dumps({"id": "f1", "name": "A", "cards": [["dabl", "EN001", "ja", 0, 1]],
                                                      "wants": [], "extra": True}), "utf-8")
        with mock.patch.object(trade, "friends_folder", lambda game: friends), \
                mock.patch.object(trade, "FRIENDS", friends), mock.patch.object(relay, "fill_names", lambda d: None):
            self.assertTrue(relay.apply_delta("yugioh", "f1", {"dabl|EN001|ja|0": 3, "lob|EN001|en|0": 1}))
        d = json.loads((friends / "f1.json").read_text("utf-8"))
        self.assertEqual(sorted(c[:5] for c in d["cards"]), [["dabl", "EN001", "ja", 0, 3], ["lob", "EN001", "en", 0, 1]])


if __name__ == "__main__":
    unittest.main()
