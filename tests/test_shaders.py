"""The compiled shaders (qml/shaders/*.frag.qsb) belong to their sources: every .frag has its .qsb and the
checksum noted at compile time (tools/compile_shaders.py -> *.frag.sha256) matches the .frag as it is now – otherwise
someone changed the shader without compiling it again (the app would still show the old one).

    python -m unittest tests/test_shaders.py
"""
import pathlib
import unittest

from tools import compile_shaders

SHADERS = pathlib.Path(__file__).resolve().parents[1] / "qml" / "shaders"


class Shaders(unittest.TestCase):
    def test_qsb_matches_source(self):
        frags = sorted(SHADERS.glob("*.frag"))
        self.assertTrue(frags)
        for src in frags:
            with self.subTest(shader=src.name):
                qsb, note = src.with_suffix(".frag.qsb"), src.with_suffix(".frag.sha256")
                self.assertTrue(qsb.exists() and qsb.stat().st_size > 0, "compile it: tools/compile_shaders.py")
                self.assertEqual(note.read_text("utf-8").strip(), compile_shaders.digest(src),
                                 "the .frag changed since the .qsb was made – run tools/compile_shaders.py")


if __name__ == "__main__":
    unittest.main()
