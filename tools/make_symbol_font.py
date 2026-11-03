"""Builds fonts/BCSymbols-Regular.ttf: the symbols the app shows that Inter and Barlow lack, cut from Noto Sans
Symbols 2, Noto Sans Symbols and Noto Sans Math (all SIL OFL 1.1) and merged into one small font "BC Symbols".
Without it Linux/Mac (and Windows without Segoe UI Symbol) show empty boxes for ⇄ ✦ ⚙ ⚑ ⋯ ⟲ …

    <venv with fonttools>/python tools/make_symbol_font.py <folder with the three Noto TTFs>

The Noto files are checked against the pinned sha256 (notofonts releases: Symbols 2 v2.008, Symbols v2.003,
Math v3.000). Each character comes from the first font that has it (Symbols 2 -> Symbols -> Math).
tests/test_symbol_font.py checks that every symbol in the code is in Inter, Barlow or this font."""
import hashlib
import os
import sys

from fontTools import merge, subset
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "fonts", "BCSymbols-Regular.ttf")
FAMILY = "BC Symbols"
VERSION = "1.000"

SOURCES = [   # order = priority
    ("NotoSansSymbols2-Regular.ttf", "c4a0a80f0041ce4be81e2478faad22776d23edb98ae3f0d19bd37044820ecf9d"),
    ("NotoSansSymbols-Regular.ttf", "d0e98e9a2c046594c5021437273943be7e79e0fd980fde125279e22302212595"),
    ("NotoSansMath-Regular.ttf", "d51afd5739c7ba6c44fcab35a88160e25dfb69a2d4ad0bd99533f8d894af1f96"),
]

# Symbols the app shows that Inter or Barlow lack (tests/test_symbol_font.py, 03.11.2026); new ones: add here and rebuild.
NEED = ("↶↷⇄⇅⇆⋮⋯⌕ⓘ─▣▦▭▴▸▾◈◉☰⚑⚙⛉✎✕✦✺❄⟲⟳⤒⬡"
        "‖←↑→↓↔↕↗↺↻▲▼◆○●★☆♥⚠✓✗⬆")      # in Inter, not in Barlow (headings)
# shown symbols no Noto font has: drawn with the glyph of another character (＋ on library buttons -> Math's plus)
ALIASES = {"＋": "+"}

COPYRIGHT = ("Copyright 2022 The Noto Project Authors (https://github.com/notofonts/symbols); "
             "Copyright 2022 The Noto Project Authors (https://github.com/notofonts/math); "
             "Copyright 2022 Google LLC. Modified (subset and merged) for Bent°Corner.")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _subset(path, chars, tmp):
    opt = subset.Options()
    opt.layout_features = []
    opt.name_IDs = ["*"]
    opt.notdef_outline = True
    opt.glyph_names = False
    opt.hinting = False               # the sources differ in hinting and vertical metrics – both block the merge
    opt.drop_tables += ["MATH", "GSUB", "GPOS", "GDEF", "vhea", "vmtx", "gasp"]   # single symbols, no layout
    f = TTFont(path)
    s = subset.Subsetter(opt)
    s.populate(unicodes=chars)
    s.subset(f)
    f.save(tmp)
    return tmp


def build(src_dir, out=OUT):
    left = [ord(c) for c in NEED + "".join(ALIASES.values())]
    parts = []
    for name, sha in SOURCES:
        path = os.path.join(src_dir, name)
        if _sha(path) != sha:
            sys.exit(f"{name}: sha256 differs from the pinned file")
        have = TTFont(path).getBestCmap()
        take = [c for c in left if c in have]
        left = [c for c in left if c not in have]
        if take:
            parts.append(_subset(path, take, out + f".part{len(parts)}.ttf"))
    if left:
        sys.exit("in no Noto font: " + " ".join(f"U+{c:04X}" for c in left))
    try:
        font = merge.Merger().merge(parts)
    finally:
        for p in parts:
            os.remove(p)
    for table in font["cmap"].tables:
        for shown, glyph in ALIASES.items():
            table.cmap[ord(shown)] = table.cmap.pop(ord(glyph))
    lic = TTFont(os.path.join(src_dir, SOURCES[0][0]))["name"]
    names = font["name"]
    names.names = []
    for i, text in ((0, COPYRIGHT), (1, FAMILY), (2, "Regular"), (3, f"{VERSION};BCSymbols-Regular"),
                    (4, FAMILY), (5, f"Version {VERSION}"), (6, "BCSymbols-Regular"),
                    (13, lic.getName(13, 3, 1, 0x409).toUnicode()), (14, lic.getName(14, 3, 1, 0x409).toUnicode())):
        names.setName(text, i, 3, 1, 0x409)
    font["head"].fontRevision = float(VERSION)
    font["head"].created = font["head"].modified = 0xE4A0_0000   # fixed (2025) -> same bytes on every build
    font.recalcTimestamp = False
    # line metrics of Inter (in 1000 units) instead of the merged maximum (Math: win 3105/2550) – otherwise a line
    # with a symbol grows taller than its neighbours; all glyphs lie within 866/-177
    os2, hhea = font["OS/2"], font["hhea"]
    hhea.ascent, hhea.descent, hhea.lineGap = 969, -241, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = 969, -241, 0
    os2.usWinAscent, os2.usWinDescent = 1108, 322
    os2.fsSelection |= 1 << 7         # USE_TYPO_METRICS
    os2.fsType = 0                    # installable, like the Noto originals
    font.save(out)
    return out


if __name__ == "__main__":
    p = build(sys.argv[1])
    print(p, os.path.getsize(p), "bytes,", len(NEED) + len(ALIASES), "symbols")
