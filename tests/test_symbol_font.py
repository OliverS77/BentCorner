"""Every symbol the desktop app shows in its texts is in Inter and Barlow, or in BC Symbols
(fonts/BCSymbols-Regular.ttf) – otherwise Linux/Mac (and Windows without Segoe UI Symbol) show an empty box. Only string literals count, comments
may use anything. A new symbol: add it to NEED in tools/make_symbol_font.py and rebuild the font.

    python -m unittest tests/test_symbol_font.py
"""
import io
import pathlib
import re
import struct
import tokenize
import unicodedata
import unittest

import games

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONTS = ROOT / "fonts"
DIRS = ["app.py", "patchnotes.py", "cards", "collection", "games", "launcher", "locales", "net", "qml", "scanner",
        "system", "ui"]
CODE_ONLY = games.extra("CODE_ONLY_SYMBOLS", {})   # {file: symbols only in search patterns, never shown}
QML_STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"' + r"|'(?:[^'\\\n]|\\.)*'")


def cmap(path):
    """Code points a TTF maps (cmap formats 4 and 12)."""
    b = path.read_bytes()
    n = struct.unpack(">H", b[4:6])[0]
    tables = {b[12 + 16 * i:16 + 16 * i]: struct.unpack(">II", b[20 + 16 * i:28 + 16 * i]) for i in range(n)}
    off = tables[b"cmap"][0]
    pts = set()
    for i in range(struct.unpack(">H", b[off + 2:off + 4])[0]):
        t = off + struct.unpack(">I", b[off + 8 + 8 * i:off + 12 + 8 * i])[0]
        fmt = struct.unpack(">H", b[t:t + 2])[0]
        if fmt == 4:
            seg = struct.unpack(">H", b[t + 6:t + 8])[0] // 2
            ends = struct.unpack(">%dH" % seg, b[t + 14:t + 14 + 2 * seg])
            starts = struct.unpack(">%dH" % seg, b[t + 16 + 2 * seg:t + 16 + 4 * seg])
            for s, e in zip(starts, ends):
                pts.update(range(s, e + 1))
        elif fmt == 12:
            for k in range(struct.unpack(">I", b[t + 12:t + 16])[0]):
                s, e, _ = struct.unpack(">III", b[t + 16 + 12 * k:t + 28 + 12 * k])
                pts.update(range(s, e + 1))
    pts.discard(0xFFFF)
    return pts


def strings(path):
    """Text of all string literals in a .py or .qml file."""
    text = path.read_text("utf-8")
    if path.suffix == ".py":
        return [t.string for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.STRING]
    return [m.group(0) for line in text.splitlines() for m in QML_STRING.finditer(line.split("//", 1)[0]
                                                                                    if "://" not in line else line)]


def shown_symbols():
    """{code point: files} of symbols in string literals: from U+2000, no letters/marks/spaces/controls, no emoji
    (they come from the emoji font) and no private use."""
    uses = {}
    for d in DIRS:
        p = ROOT / d
        for f in ([p] if p.is_file() else sorted(list(p.rglob("*.py")) + list(p.rglob("*.qml")))):
            if f.name == "legacy_de.py":
                continue
            skip = CODE_ONLY.get(f.relative_to(ROOT).as_posix(), "")
            for s in strings(f):
                for ch in set(s) - set(skip):
                    c = ord(ch)
                    if c < 0x2000 or 0xE000 <= c <= 0xF8FF or c >= 0x1F000 or unicodedata.category(ch)[0] in "LMZC":
                        continue
                    uses.setdefault(c, set()).add(str(f.relative_to(ROOT)))
    return uses


class SymbolFont(unittest.TestCase):
    def test_font_has_its_names_and_licence(self):
        b = (FONTS / "BCSymbols-Regular.ttf").read_bytes()
        for text in ("BC Symbols", "Copyright 2022 The Noto Project Authors (https://github.com/notofonts/symbols)",
                     "Copyright 2022 Google LLC. Modified (subset and merged) for Bent°Corner.",
                     "SIL Open Font License, Version 1.1"):
            self.assertIn(text.encode("utf-16-be"), b, text)
        self.assertNotIn("Noto Sans".encode("utf-16-be") + b"\0\0", b)
        ofl = (FONTS / "OFL-Noto.txt").read_text("utf-8")
        self.assertIn("Copyright 2022 The Noto Project Authors (https://github.com/notofonts/math)", ofl)
        self.assertIn("SIL OPEN FONT LICENSE Version 1.1", ofl)

    def test_every_shown_symbol_has_a_glyph(self):
        # Inter AND Barlow: after the chosen font comes BC Symbols, not the other bundled font
        have = (cmap(FONTS / "Inter_18pt-Regular.ttf") & cmap(FONTS / "BarlowSemiCondensed-Regular.ttf")
                | cmap(FONTS / "BCSymbols-Regular.ttf"))
        missing = {f"U+{c:04X} {chr(c)} {unicodedata.name(chr(c), '?')}": sorted(f)[:3]
                   for c, f in shown_symbols().items() if c not in have}
        self.assertEqual(missing, {}, "add these to NEED in tools/make_symbol_font.py (or use another symbol)")


if __name__ == "__main__":
    unittest.main()
