"""Set completion: how much of each set do you own? Only the calculation – it is shown by
qcompletion.py / qml/components/CompletionPanel.qml.

Counted per card number (one copy is enough, language/foil don't matter). Three measures:
    booster – cards that appear in boosters (the "actual" set, without special variants); if a set has
              none marked yet (just released), all its cards count
    all     – all printings of the set (incl. showcase, borderless …)
    rare    – only rare and mythic (from boosters)
"""
from cards import carddb

MODES = [("booster", "Booster-Karten"), ("all", "Alle Drucke"), ("rare", "Nur Rare & Mythic")]
_SKIP = "('token', 'double_faced_token', 'art_series', 'emblem')"


def eur(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


SORTS = [("progress", "Fortschritt"), ("name", "Name"), ("date", "Datum"), ("missing", "Fehlt €")]
SORT_KEYS = {
    "progress": lambda s: (-s["have"] / max(1, s["total"]), -s["total"]),
    "name": lambda s: (s["name"] or "").lower(),
    "date": lambda s: tuple(-ord(ch) for ch in (s.get("released") or "")),  # newest first
    "missing": lambda s: -s["missing_value"],
}


def compute(items, mode="booster"):
    """-> [{"code", "name", "have", "total", "missing_value", "missing": [rows]}] for sets you own something
    from; sorted by progress (highest first)."""
    owned = {}
    for it in items:
        if it.get("set") and it.get("number"):
            owned.setdefault(it["set"].lower(), set()).add(str(it["number"]))
    if not owned or not carddb.exists():
        return []
    cond = "rarity IN ('rare', 'mythic')" if mode == "rare" else "1 = 1"
    codes = sorted(owned)
    with carddb.connection() as con:
        rows = con.execute(
            f"SELECT id, name, set_code, set_name, number, rarity, eur, eur_foil, released, booster FROM cards "
            f"WHERE set_code IN ({','.join('?' * len(codes))}) AND layout NOT IN {_SKIP} AND {cond}",
            codes).fetchall()
    if mode != "all":  # booster cards only – unless the set has none marked (yet) (e.g. just released)
        with_booster = {r["set_code"] for r in rows if r["booster"]}
        rows = [r for r in rows if r["booster"] or r["set_code"] not in with_booster]
    sets = {}
    for r in rows:
        s = sets.setdefault(r["set_code"], {"code": r["set_code"], "name": r["set_name"], "numbers": {},
                                            "released": r["released"] or ""})
        s["numbers"].setdefault(str(r["number"]), dict(r))  # one row per number
    out = []
    for code, s in sets.items():
        nums = s.pop("numbers")
        have = owned.get(code, set()) & set(nums)
        missing = [r for n, r in nums.items() if n not in have]
        if not have:
            continue
        s.update(have=len(have), total=len(nums), missing=sorted(missing, key=lambda r: _num_key(r["number"])),
                 missing_value=sum(r["eur"] or 0 for r in missing),
                 total_value=sum(r["eur"] or 0 for r in nums.values()))
        out.append(s)
    out.sort(key=lambda s: (-s["have"] / s["total"], -s["total"]))
    return out


def _num_key(n):
    digits = "".join(c for c in str(n) if c.isdigit())
    return (int(digits) if digits else 0, str(n))


def families(data, catalog):
    """Group sets into families (main set + Commander, tokens, promos … – via "parent" in the Scryfall set list).
    -> [{"code", "name", "have", "total", "missing_value", "missing", "sets": [sets]}] sorted by progress."""
    by_code = {c["code"]: c for c in catalog or []}

    def root(code):
        seen = set()
        while by_code.get(code, {}).get("parent") and by_code[code]["parent"] in by_code and code not in seen:
            seen.add(code)
            code = by_code[code]["parent"]
        return code
    fams = {}
    for s in data:
        r = root(s["code"])
        f = fams.setdefault(r, {"code": r, "name": by_code.get(r, {}).get("name") or s["name"], "sets": []})
        f["sets"].append(s)
    out = []
    for f in fams.values():
        f["sets"].sort(key=lambda s: (s["code"] != f["code"], -s["total"]))
        f["have"] = sum(s["have"] for s in f["sets"])
        f["total"] = sum(s["total"] for s in f["sets"])
        f["missing_value"] = sum(s["missing_value"] for s in f["sets"])
        f["total_value"] = sum(s.get("total_value", 0) for s in f["sets"])
        f["released"] = max((s.get("released") or "" for s in f["sets"]), default="")
        f["missing"] = [dict(m, _set=s["code"]) for s in f["sets"] for m in s["missing"]]
        out.append(f)
    out.sort(key=lambda f: (-f["have"] / max(1, f["total"]), -f["total"]))
    return out
