"""Review 08.11. (S4, M1): taking the vault 1:1 (offline longer than tombstones live) or healing (checksum differs)
never replaces this device's data with an emptied, expired or deleted vault – it asks instead (VaultEmptied: „back it
up again from this device?“) or stops (VaultDeleted), as the normal fetch already does.

    python -m unittest tests.test_take_all_guard
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


class Guard(unittest.TestCase):
    def engine(self, tmp):
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
        return e, f

    def test_long_offline_and_expired_vault_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            e, f = self.engine(pathlib.Path(tmp))
            e.meta["fetched_at"] = 1_800_000_000_000 - 200 * 86400 * 1000   # > TOMB_DAYS away, vault expired
            with self.assertRaises(syncrun.VaultEmptied):
                e.fetch()
            self.assertNotIn("aside_next", e.meta)
            self.assertIn("My deck", f.read_text("utf-8"), "the local data stays")

    def test_heal_into_a_deleted_vault_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            e, f = self.engine(pathlib.Path(tmp))
            e._pull = lambda since: (0, True)   # a checksum differs …
            e.client.get = lambda s, since: {"deleted": 123}   # … and the vault was deleted in between
            with self.assertRaises(syncrun.VaultDeleted):
                e.fetch()
            self.assertIn("d1", e.state.view("mtg/decks"))
            self.assertIn("My deck", f.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
