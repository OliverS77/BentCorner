"""Import: does the file belong to the open game? Card names repeat across games (Magic ↔ Yu-Gi-Oh!: 86, e.g.
"Forest" and "Mountain" – both are also YGO field spells; Magic ↔ Lorcana 40, Magic ↔ Pokémon 18 …), so a Magic export
imported while Yu-Gi-Oh! was open used to land on the YGO cards of the same name (Oliver, 30.10.2026).

  rate(items, key)   how many lines of the file this game confirms – by its own ID, set + number, or name within
                     a set it knows; lines without a set count by name alone
  guess(items)       the same for every game that is set up here (read only, local databases) -> best first
  name_only_ok(…)    may a line whose set this game doesn't know be matched by name alone? Only if the file as a
                     whole fits the open game (a brand-new Magic set the database doesn't know yet) – never across

items: [(name, set code, number, own ID)] – empty strings where the file has nothing.
"""
import sqlite3

import games
from cards import carddb

FITS = 0.8   # share of lines a game confirms: from here the file is that game's
FEW = 0.5    # below: don't import silently – show what was found and what wasn't ("Import anyway (12 of 40)")

_index = {}   # game -> ((path, mtime), {"sets": {…}, "names": {…}})


def _db(key):
    p = carddb.path_of(key)
    return p if p is not None and p.exists() else None


def _load(key):
    """Set codes and names (lowercase, every face of a double-faced card) of a game's local database – cached."""
    p = _db(key)
    if p is None:
        return None
    stamp = (str(p), p.stat().st_mtime)
    hit = _index.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        sets = {r[0] for r in con.execute("SELECT DISTINCT set_code FROM cards") if r[0]}
        names = set()
        for (n,) in con.execute("SELECT DISTINCT lower(name) FROM cards WHERE name IS NOT NULL"):
            names.add(n)
            names.update(x.strip() for x in n.split(" // "))
    finally:
        con.close()
    idx = {"sets": sets, "names": names}
    _index[key] = (stamp, idx)
    return idx


def known_sets(key=None):
    idx = _load(key or games.current().key)
    return idx["sets"] if idx else set()


def foreign_set(code, key=None):
    """A set code from the file this game doesn't have -> True."""
    code = (code or "").strip().lower()
    sets = known_sets(key)
    return bool(code) and bool(sets) and code not in sets


def rate(items, key):
    """-> (lines this game confirms, lines) – see the module text."""
    idx = _load(key)
    if idx is None or not items:
        return 0, len(items or ())
    p = _db(key)
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    ok = 0
    try:
        for name, set_code, number, sid in items:
            name, set_code = (name or "").strip().lower(), (set_code or "").strip().lower()
            if sid:   # its own ID: only that counts (a Scryfall ID in Yu-Gi-Oh! is no Yu-Gi-Oh! card)
                ok += con.execute("SELECT 1 FROM cards WHERE id = ?", (sid,)).fetchone() is not None
            elif set_code:
                if set_code not in idx["sets"]:
                    continue
                r = con.execute("SELECT lower(name) FROM cards WHERE set_code = ? AND number = ?",
                                (set_code, str(number or ""))).fetchone() if number else None
                if r is not None and (not name or name in (r[0], *(x.strip() for x in r[0].split(" // ")))):
                    ok += 1
                elif name and con.execute("SELECT 1 FROM cards WHERE set_code = ? AND lower(name) = ? LIMIT 1",
                                          (set_code, name)).fetchone():
                    ok += 1
            elif name in idx["names"]:
                ok += 1
    finally:
        con.close()
    return ok, len(items)


def guess(items):
    """[(game, confirmed, lines)] of every game set up here (its database exists), best first; the open game wins
    a tie."""
    cur = games.current().key
    keys = [c["key"] for c in games.choices() if c.get("ready")]
    if cur not in keys:
        keys.append(cur)
    out = []
    for k in keys:
        if _db(k) is None:
            continue
        ok, n = rate(items, k)
        out.append((k, ok, n))
    return sorted(out, key=lambda t: (-t[1], t[0] != cur))


def verdict(items):
    """For the import form: {"game": open game, "ok": confirmed here, "n": lines, "other": better game or None,
    "other_ok": its count, "few": below FEW here, "fits": the file is the open game's (name_only_ok)}."""
    cur = games.current().key
    res = guess(items)
    mine = next(((ok, n) for k, ok, n in res if k == cur), (0, len(items)))
    best = res[0] if res else (cur, *mine)
    n = mine[1] or 1
    other = best[0] if best[0] != cur and best[1] >= FITS * best[2] and best[1] > mine[0] else None
    return {"game": cur, "ok": mine[0], "n": mine[1], "other": other, "other_ok": best[1] if other else 0,
            "few": mine[1] > 0 and mine[0] < FEW * n, "fits": other is None and mine[0] >= FEW * n}


def name_only_ok(set_code, fits, key=None, sid=""):
    """May a line be matched by its name alone? Lines without a set: yes. With a set this game knows: yes (another
    print of the same card). With a set it doesn't know – or an ID it doesn't have: only if the file as a whole is
    this game's (fits)."""
    return bool(fits) or not (sid or foreign_set(set_code, key))
