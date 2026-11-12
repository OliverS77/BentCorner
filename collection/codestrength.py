"""How hard a protection code the user chose is to guess (Oliver 07.11.2026: own codes allowed, minimum strength; lead:
ONE rule for desktop and web – docs/web/codestrength-vectors.json, the web's guard.js strength() gives the same).
Runs only on the device; the code never leaves it.

    strength(text) -> {"bits", "mbits", "score" 0..3, "ok"}       ok: at least MIN_BITS (60)

The rule (port it exactly – integer millibits, so both sides decide alike):
  * the text as pairing.norm_rescue gives it; in the format of a generated code -> 119 bits (random by construction)
  * characters are Unicode code points (JS: Array.from), "low" = the text lower-cased (Python str.lower, JS
    toLowerCase); mb(x) = floor(log2(x) · 1000 + 0.5)
  * candidate pieces s = low[i:j] (3 to 24 code points), each with millibits:
      word      s in the word list (assets/codewords.txt.gz, line number = rank r): mb(r) + case(i, j)
      leet      s with LEET replaced is in the list (and differs from s): mb(r) + case + 1000
      reversed  s reversed is in the list: mb(r) + case + 1000
      repeat    one code point repeated: mb(pool(c)) + mb(len)
      sequence  every next code point +1 (or -1) and all in one ASCII class (digits, a–z): mb(pool) + mb(len)
                (+1000 when falling)
      keyboard  s or s reversed lies in one of ROWS: mb(44) + mb(len)
      year      4 digits 1900–2039: mb(140)
      date      6 or 8 digits that are a real day (DDMMYY, DDMMYYYY, YYYYMMDD; years 1900–2039): mb(36500)
    plus one code point alone: mb(pool(c))
  * case(i, j) over the original text's letters in the piece: none upper -> 0; all upper or only the first upper ->
    1000; otherwise 1000 · min(upper, lower)
  * pool(c): space - _ . 4 (separators), a–z 26, A–Z 26, 0–9 10, other ASCII 33, anything else 100
  * total = the cheapest way to cover the text with pieces (dynamic programming over code points, left to right)
  * bits = total // 1000; score: < 40 -> 0, < 60 -> 1, < 80 -> 2, else 3; ok = bits >= 60
"""
import gzip
import math
import pathlib
import sys

MIN_BITS = 60
MAX_LEN = 256
PIECE = 24
LEET = {"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t", "+": "t", "8": "b",
        "9": "g", "2": "z"}
ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "qwertzuiop", "yxcvbnm", "1234567890")
_WORDS = [None]


def _words_file():
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
    return base / "assets" / "codewords.txt.gz"


def words():
    if _WORDS[0] is None:
        lines = gzip.decompress(_words_file().read_bytes()).decode("utf-8").split("\n")
        _WORDS[0] = {w: i for i, w in enumerate(lines, 1) if w}
    return _WORDS[0]


def mb(x):
    return int(math.floor(math.log2(x) * 1000 + 0.5))


SEPARATORS = " -_."   # between words: an attacker tries only a few


def pool(c):
    if c in SEPARATORS:
        return 4
    if "a" <= c <= "z" or "A" <= c <= "Z":
        return 26
    if "0" <= c <= "9":
        return 10
    if ord(c) < 128:
        return 33
    return 100


def _case(orig):
    letters = [c for c in orig if c.isalpha()]
    up = sum(1 for c in letters if c.isupper())
    if up == 0:
        return 0
    if up == len(letters) or (up == 1 and letters[0].isupper()):
        return 1000
    return 1000 * min(up, len(letters) - up)


def _is_date(d):
    def ok(day, month, year):
        import calendar
        return 1900 <= year <= 2039 and 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]
    if len(d) == 6:
        y = int(d[4:])
        return ok(int(d[:2]), int(d[2:4]), 2000 + y if y < 40 else 1900 + y)
    return len(d) == 8 and (ok(int(d[:2]), int(d[2:4]), int(d[4:])) or ok(int(d[6:]), int(d[4:6]), int(d[:4])))


def _piece(orig, low, wl):
    """-> the cheapest millibits of one part, or None."""
    n = len(low)
    best = []
    case = _case(orig)
    r = wl.get(low)
    if r:
        best.append(mb(r) + case)
    un = "".join(LEET.get(c, c) for c in low)
    if un != low and wl.get(un):
        best.append(mb(wl[un]) + case + 1000)
    rv = low[::-1]
    if rv != low and wl.get(rv):
        best.append(mb(wl[rv]) + case + 1000)
    if len(set(low)) == 1:
        best.append(mb(pool(low[0])) + mb(n))
    steps = {ord(b) - ord(a) for a, b in zip(low, low[1:])}
    if len(steps) == 1 and steps <= {1, -1} and (low.isdigit() or all("a" <= c <= "z" for c in low)):
        best.append(mb(pool(low[0])) + mb(n) + (1000 if -1 in steps else 0))
    if any(low in row or rv in row for row in ROWS):
        best.append(mb(44) + mb(n))
    if low.isdigit() and low.isascii():
        if n == 4 and 1900 <= int(low) <= 2039:
            best.append(mb(140))
        if n in (6, 8) and _is_date(low):
            best.append(mb(36500))
    return min(best) if best else None


def strength(text):
    from net import pairing
    try:
        code = pairing.norm_rescue(text)
    except pairing.PairError:
        return {"bits": 0, "mbits": 0, "score": 0, "ok": False}
    raw = "".join(str(text or "").upper().split()).replace("-", "")
    if code == raw and len(code) == pairing.RESCUE_LEN + 1:   # the generated format: random by construction
        total = 119000
    else:
        cps = list(code)[:MAX_LEN]
        low = [c.lower() for c in cps]
        wl = words()
        n = len(cps)
        cost = [0] + [None] * n
        for j in range(1, n + 1):
            options = [cost[j - 1] + mb(pool(cps[j - 1]))]
            for i in range(max(0, j - PIECE), j - 2):
                p = _piece("".join(cps[i:j]), "".join(low[i:j]), wl)
                if p is not None:
                    options.append(cost[i] + p)
            cost[j] = min(options)
        total = cost[n]
    bits = total // 1000
    score = 0 if bits < 40 else 1 if bits < MIN_BITS else 2 if bits < 80 else 3
    return {"bits": bits, "mbits": total, "score": score, "ok": bits >= MIN_BITS}
