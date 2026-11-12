"""Review 08.11. (S3): a document that is there but can't be read (OneDrive/virus scanner lock, half written, damaged)
is NOT „everything deleted“ – no delete ops go to the other devices, the state keeps the entries, nothing is written
over it; once it reads again, sync goes on as before.

    python -m unittest tests.test_unreadable_doc
"""
import json
import pathlib
import tempfile
import unittest

from collection import syncrun


class Docs(syncrun.Docs):
    def __init__(self, settings, root):
        super().__init__(settings)
        self.root = root

    def path(self, game, *parts):
        return self.root / "data" / game / pathlib.Path(*parts) if parts else self.root / "data" / game

    def games(self):
        return ["mtg"]

    def known_games(self):
        return ["mtg"]

    def read_logs(self, game):
        return {"logs": [], "bookings": [], "items": [], "broken": [], "hidden": set()}

    def aside(self, keys, why, other=""):
        return "aside-id"


class EmptyVault:
    def get(self, settings, since):
        return {"version": 0, "items": []}

    def server_ms(self):
        return None


class UnreadableDoc(unittest.TestCase):
    def test_damaged_file_sends_no_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            settings = {"relay": {"seed": None}}
            docs = Docs(settings, tmp)
            f = tmp / "data" / "mtg" / "decks.json"
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps({"decks": [{"id": "d1", "name": "My deck", "cards": []}]}), "utf-8")
            e = syncrun.Engine(tmp, settings, docs=docs, client=EmptyVault(), now=lambda: 1_800_000_000_000)
            e.meta.update(on=True, dev="abcd", seeded=False)
            e._save()
            e.fetch()
            e.write_back()
            e.pending = []
            e._save()
            f.write_text('{"decks": [', "utf-8")   # half written / damaged
            self.assertEqual(e.catch_up() - e._record_device(), 0)
            deletes = [o for o in e.pending if o.get("x")]
            self.assertEqual(deletes, [], "no delete ops for an unreadable file")
            self.assertIn("d1", e.state.view("mtg/decks"), "the state keeps the deck")
            f.write_text(json.dumps({"decks": [{"id": "d1", "name": "My deck", "cards": []}]}), "utf-8")
            self.assertEqual([o for o in e.pending if o.get("x")], [])

    def test_unreadable_is_not_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "x.json"
            self.assertIsNone(syncrun._read_doc(p), "missing: None")
            p.write_text("{", "utf-8")
            with self.assertRaises(syncrun.Unreadable):
                syncrun._read_doc(p)


if __name__ == "__main__":
    unittest.main()
