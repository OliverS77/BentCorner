"""tests/optional_games.py: missing parts make their tests skip – also when only leftovers of them are there."""
import pathlib
import tempfile
import unittest

from tests import optional_games


class OptionalParts(unittest.TestCase):
    def test_server_needs_real_files_not_just_the_folder(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            self.assertFalse(optional_games.server_present(root))
            for f in optional_games.SERVER_FILES:   # leftovers after the move: folders with only __pycache__
                cache = root / "server" / pathlib.Path(f).parent / "__pycache__"
                cache.mkdir(parents=True)
                (cache / (pathlib.Path(f).stem + ".cpython-312.pyc")).write_bytes(b"")
            self.assertFalse(optional_games.server_present(root))
            for f in optional_games.SERVER_FILES:
                (root / "server" / f).write_text("", "utf-8")
            self.assertTrue(optional_games.server_present(root))

    def test_guard_counts_code_not_cache(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            self.assertEqual(optional_games.server_code(root), [])               # no server\ at all
            cache = root / "server" / "box" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "box.cpython-312.pyc").write_bytes(b"")
            (root / "server" / "stray.pyc").write_bytes(b"")
            self.assertEqual(optional_games.server_code(root), [])               # only cache remains: ok
            (root / "server" / "box" / "box.py").write_text("", "utf-8")
            self.assertEqual(optional_games.server_code(root), [str(pathlib.Path("box/box.py"))])   # code: the guard fires


if __name__ == "__main__":
    unittest.main()
