"""Review 08.11. (M2): log ids come from the vault (another own device) and become file names – "../x", "C:/x", a NUL
byte or a slash must never write or delete outside <game>/sessions.

    python -m unittest tests.test_log_id_paths
"""
import pathlib
import tempfile
import unittest

from collection import syncrun

BAD = ["../evil", "..\\evil", "C:/evil", "C:evil", "a/b", "evil\x00", "", "x" * 81, "..", "ä"]
GOOD = ["2026-11-08_10-00-00", "import_2026-11-08_10-00-00_d0123456789abcdef", "manual_migrated_2026-11-08"]


class Docs(syncrun.Docs):
    def __init__(self, root):
        super().__init__({})
        self.root = root

    def path(self, game, *parts):
        return self.root / "data" / game / pathlib.Path(*parts) if parts else self.root / "data" / game


def _data():
    return {"bookings": [], "items": [], "broken": [], "hidden": set()}


class LogIdPaths(unittest.TestCase):
    def test_bad_ids_never_become_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            docs = Docs(root)
            folder = (root / "data" / "mtg" / "sessions").resolve()
            logs = [{"id": i, "packs": []} for i in BAD + GOOD]
            writes, dels = docs.files_of("mtg", _data(), logs, BAD + GOOD, bookings=False, collection=False)
            self.assertEqual(sorted(p.stem for p in writes), sorted(GOOD))
            self.assertEqual(sorted(p.stem for p in dels), sorted(GOOD))
            for p in list(writes) + dels:
                self.assertEqual(p.resolve().parent, folder)

    def test_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Docs(pathlib.Path(tmp))
            for i in BAD:
                self.assertIsNone(docs.log_file("mtg", i), repr(i))
            self.assertIsNone(docs.log_file("mtg", None))
            for i in GOOD:
                self.assertEqual(docs.log_file("mtg", i).name, i + ".json")


if __name__ == "__main__":
    unittest.main()
