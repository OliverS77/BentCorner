"""THIRD_PARTY_NOTICES.md (lead/legal 14.11.2026, desk-notices): ONE source – tools/public/overlay/THIRD_PARTY_NOTICES.md is
what the program ships (the build comes from the public export); the root copy is the same file. Every library row
names the version that requirements.txt pins (0.9.8 still said Pillow 12.3.0 / PyNaCl 1.5.0 / setuptools 84.0.0), and
the word list of the protection-code check (zxcvbn-ts, OPUS) is named.

    python -m unittest tests.test_notices
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "tools" / "public" / "overlay" / "THIRD_PARTY_NOTICES.md"
COPY = ROOT / "THIRD_PARTY_NOTICES.md"
# rows of components INSIDE a package with their own version (not the package's): never compared with the pin
OWN_VERSION = ("OpenBLAS", "GEOS")
NOT_A_ROW = {"pyinstaller-hooks-contrib"}   # build tool, its name only looks like the PyInstaller row


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def pins():
    out = {}
    for line in (ROOT / "requirements.txt").read_text("utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;#]+)", line.strip())
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def rows(text):
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith(("| Komponente", "|---")):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3:
                yield cells


@unittest.skipUnless(OVERLAY.exists(), "the private repository (tools/public)")
class Notices(unittest.TestCase):
    def setUp(self):
        self.text = OVERLAY.read_text("utf-8")

    def test_one_source(self):
        self.assertEqual(COPY.read_bytes(), OVERLAY.read_bytes(), "root copy differs from the overlay (the shipped one)")

    def test_pillow_and_the_code_word_list(self):
        self.assertRegex(self.text, r"(?m)^\| Pillow \(")
        self.assertIn("### Wortliste der Schutz-Code-Prüfung – zxcvbn-ts (MIT)", self.text)
        self.assertIn("`assets/codewords.txt.gz`", self.text)
        self.assertIn("OpenSubtitles 2024 via OPUS (Helsinki-NLP), ODC-BY", self.text)

    def test_versions_match_requirements(self):
        checked, wrong = 0, []
        for pkg, ver in pins().items():
            if pkg in NOT_A_ROW:
                continue
            for cells in rows(self.text):
                name, version = cells[0], cells[1]
                if name.startswith(OWN_VERSION):
                    continue
                if _norm(pkg) in _norm(name) or _norm(pkg.split("-")[0]) == _norm(name.split()[0]):
                    checked += 1
                    if ver not in version:
                        wrong.append(f"{name[:40]}: notices {version!r}, requirements {pkg}=={ver}")
        self.assertEqual(wrong, [])
        self.assertGreater(checked, 20)   # the comparison really ran over the table

    def test_the_three_of_099(self):
        p = pins()
        for pkg, label in (("pillow", "| Pillow ("), ("pynacl", "| PyNaCl / libsodium"), ("setuptools", "| setuptools (")):
            line = next(l for l in self.text.splitlines() if l.startswith(label))
            self.assertIn(f"| {p[pkg]} |", line)


if __name__ == "__main__":
    unittest.main()
