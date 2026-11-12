"""Writes assets/codewords.txt.gz: the word list for the strength check of a chosen protection code
(collection/codestrength.py; the web reads the same file). From the zxcvbn-ts dictionaries (MIT, legal 07.11.2026 –
licenses/THIRD_PARTY/zxcvbn-ts.md): @zxcvbn-ts/language-common 4.1.3 (passwords, diceware), language-de 4.1.1 and
language-en 4.1.1 (common words – OpenSubtitles 2024 via OPUS, ODC-BY –, first and last names).

One merged list: each word at its best rank in any of the taken lists (the first N of each, so the file stays near
150 KB packed), sorted by (rank, word), one per line – the line number is the rank both sides use.

    npm pack @zxcvbn-ts/language-common@4.1.3 @zxcvbn-ts/language-de@4.1.1 @zxcvbn-ts/language-en@4.1.1
    (unpack each into x-<name>/) then:  python tools/make_code_words.py <folder with the x-* folders>
"""
import gzip
import json
import pathlib
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "codewords.txt.gz"
TAKE = [   # (package, file, how many from the top)
    ("language-common-4.1.3", "passwords.json", 10000),
    ("language-common-4.1.3", "diceware.json", 7776),
    ("language-de-4.1.1", "commonWords.json", 10000),
    ("language-en-4.1.1", "commonWords.json", 10000),
    ("language-de-4.1.1", "firstnames.json", 1158),
    ("language-de-4.1.1", "lastnames.json", 3000),
    ("language-en-4.1.1", "firstnames.json", 4945),
    ("language-en-4.1.1", "lastnames.json", 2000),
]


def norm(w):
    return unicodedata.normalize("NFKC", str(w)).lower().strip()


def build(src):
    best = {}
    for pkg, name, n in TAKE:
        words = json.loads((src / f"x-zxcvbn-ts-{pkg}" / "package" / "src" / name).read_text("utf-8"))[:n]
        for rank, w in enumerate(words, 1):
            w = norm(w)
            if len(w) < 3 or " " in w:
                continue
            if rank < best.get(w, 1 << 30):
                best[w] = rank
    return [w for w, _r in sorted(best.items(), key=lambda kv: (kv[1], kv[0]))]


def main():
    words = build(pathlib.Path(sys.argv[1]))
    data = ("\n".join(words) + "\n").encode("utf-8")
    OUT.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    print(f"{OUT.relative_to(ROOT)}: {len(words)} words, {len(data) // 1024} KB, packed {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
