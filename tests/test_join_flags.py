"""Review 08.11. (S2): the answer to one join („merge“ / „keep the other device's“ / „keep mine“) belongs to that join.
A stale join_theirs made a later switch-on skip the question and the seeding – the vault's state overwrote this device's
data without asking or setting it aside, and every later local edit was turned back.

    python -m unittest tests.test_join_flags
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


class StaleJoinAnswer(unittest.TestCase):
    def test_switching_on_again_never_reuses_an_old_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            settings = {"relay": {"seed": None}}
            docs = Docs(settings, tmp)
            (tmp / "data" / "mtg").mkdir(parents=True)
            deck = {"decks": [{"id": "d1", "name": "My deck", "cards": []}]}
            (tmp / "data" / "mtg" / "decks.json").write_text(json.dumps(deck), "utf-8")
            e = syncrun.Engine(tmp, settings, docs=docs, client=EmptyVault(), now=lambda: 1_800_000_000_000)
            e.meta.update(on=True, dev="abcd", seeded=True, join_theirs=True, join_merge=True)
            e._save()
            e.switch_off()
            e.switch_on()
            for k in syncrun.JOIN_FLAGS:
                self.assertNotIn(k, e.meta, k)
            e.fetch()
            e.write_back()
            got = json.loads((tmp / "data" / "mtg" / "decks.json").read_text("utf-8"))
            self.assertEqual([d["name"] for d in got["decks"]], ["My deck"], "the local deck survives")
            self.assertTrue(e.meta.get("seeded"))
            self.assertGreater(len(e.pending), 0, "its data goes up (seeded) instead of being overwritten")


if __name__ == "__main__":
    unittest.main()
