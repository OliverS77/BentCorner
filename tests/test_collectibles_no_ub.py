"""0.9.7.29+ – the collectibles samples (assets/collectibles/versions/*/sample.png + about.json, drawn by
tools/ticket_snapshot.py) never show Universes Beyond: UB is not covered by the Fan Content Policy (legal's review of
the public repo, P1, 03.11.2026). And never the default card back (the rule of 0.9.7.29). A data folder that still has
an older sample gets the new one; your own tickets (tickets/) stay.

    python -m unittest tests/test_collectibles_no_ub.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import collectibles

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "assets" / "collectibles" / "versions"
# Universes Beyond sets (Magic) known by 11/2026 – crossovers with other brands: Lord of the Rings, Doctor Who,
# Fallout, Warhammer 40,000, Assassin's Creed, Final Fantasy, Spider-Man, Avatar, Jurassic World, Transformers, TMNT …
UB = {"ltr", "ltc", "who", "pip", "40k", "acr", "fin", "fic", "fca", "spm", "spe", "tla", "tle", "rex", "bot", "tmt",
      "tmc", "pltr", "pwho", "ppip", "pfin", "pspm", "ptla"}
UB_NAMES = ("Cloud, Midgar Mercenary", "The One Ring")   # the cards of the old samples


def sample_rows():
    for d in sorted(VERSIONS.iterdir()):
        about = json.loads((d / "about.json").read_text("utf-8"))
        s = about.get("sample") or {}
        for side in ("a", "b"):
            for c in s.get(side) or []:
                yield d.name, c


class NoUniversesBeyond(unittest.TestCase):
    def test_samples_show_no_ub_set(self):
        rows = list(sample_rows())
        self.assertTrue(rows)
        for ver, c in rows:
            self.assertNotIn(str(c.get("set")).lower(), UB, ver)
            self.assertNotIn(c.get("name"), UB_NAMES, ver)

    def test_raw_ticket_in_about_has_no_ub_either(self):
        for d in VERSIONS.iterdir():
            text = (d / "about.json").read_text("utf-8")
            for name in UB_NAMES:
                self.assertNotIn(name, text, d.name)

    def test_the_tool_draws_no_ub_and_no_default_back(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ticket_snapshot", ROOT / "tools" / "ticket_snapshot.py")
        ts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ts)
        for c in ts.GIVE + ts.GET:
            self.assertNotIn(c["set"].lower(), UB)
        from system import userprofile
        default_key = userprofile.PRESETS[0][0]
        self.assertNotIn(default_key, ts.BACKS)
        keys = {p[0] for p in userprofile.PRESETS}
        self.assertTrue(set(ts.BACKS) <= keys)


class NewSamplesReachTheDataFolder(unittest.TestCase):
    def test_an_older_sample_is_replaced_own_tickets_stay(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = pathlib.Path(tmp) / "src", pathlib.Path(tmp) / "data"
            (src / "versions" / "0.8.2").mkdir(parents=True)
            (src / "versions" / "0.8.2" / "about.json").write_text('{"new": 1}', "utf-8")
            (src / "versions" / "0.8.2" / "sample.png").write_bytes(b"new")
            (dst / "versions" / "0.8.2").mkdir(parents=True)
            (dst / "versions" / "0.8.2" / "about.json").write_text('{"old": 1}', "utf-8")
            (dst / "versions" / "0.8.2" / "sample.png").write_bytes(b"old")
            (dst / "tickets").mkdir(parents=True)
            (dst / "tickets" / "mine.json").write_text("{}", "utf-8")
            with mock.patch.object(collectibles, "_bundled", lambda: src), mock.patch.object(collectibles, "DIR", dst):
                collectibles.sync_bundled()
                self.assertEqual((dst / "versions" / "0.8.2" / "sample.png").read_bytes(), b"new")
                self.assertTrue((dst / "tickets" / "mine.json").exists())
                (dst / "versions" / "0.8.2" / "sample.png").write_bytes(b"same about, kept")
                collectibles.sync_bundled()   # the same about.json: nothing copied again
                self.assertEqual((dst / "versions" / "0.8.2" / "sample.png").read_bytes(), b"same about, kept")


if __name__ == "__main__":
    unittest.main()
