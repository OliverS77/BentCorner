"""tools/check_binaries.py: binaries in the exe only from the venv, Python or Windows – a DLL picked up from the PATH
(0.9.7.4: miniconda's ucrtbase.dll and friends) stops the build.

    python -m unittest tests/test_build_checks.py
"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import check_binaries  # noqa: E402


class Binaries(unittest.TestCase):
    def _toc(self, entries):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = pathlib.Path(d.name) / "COLLECT-00.toc"
        p.write_text(repr((entries,)), "utf-8")
        return p

    def test_venv_python_and_windows_are_fine(self):
        roots = [r"c:\proj\.venv", r"c:\python312", r"c:\windows"]
        toc = self._toc([("a.dll", r"C:\proj\.venv\Lib\site-packages\x\a.dll", "BINARY"),
                         ("_ssl.pyd", r"C:\Python312\DLLs\_ssl.pyd", "EXTENSION"),
                         ("d3dcompiler_47.dll", r"C:\Windows\System32\d3dcompiler_47.dll", "BINARY"),
                         ("notes.txt", r"D:\anywhere\notes.txt", "DATA")])
        self.assertEqual(check_binaries.foreign(toc, roots), [])

    def test_dll_from_the_path_is_found(self):
        roots = [r"c:\proj\.venv", r"c:\python312", r"c:\windows"]
        toc = self._toc([("ucrtbase.dll", r"C:\Users\x\miniconda3\ucrtbase.dll", "BINARY"),
                         ("libcrypto-3-x64.dll", r"C:\msys64\mingw64\bin\libcrypto-3-x64.dll", "BINARY"),
                         ("ok.dll", r"C:\proj\.venv\ok.dll", "BINARY")])
        self.assertEqual([n for n, _ in check_binaries.foreign(toc, roots)], ["ucrtbase.dll", "libcrypto-3-x64.dll"])

    def test_a_similar_prefix_is_not_inside(self):
        toc = self._toc([("x.dll", r"C:\Windows2\x.dll", "BINARY")])
        self.assertEqual(len(check_binaries.foreign(toc, [r"c:\windows"])), 1)


if __name__ == "__main__":
    unittest.main()
