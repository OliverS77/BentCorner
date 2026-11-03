"""Group by ("Gruppieren", Oliver 29.10.): the Library as a tree – a chain of properties (e.g. Set › Rarity), each
level splits the cards of the chosen node further. Only a view: it changes nothing in the collection, lists or export.

Pure logic without Qt (tested in tests/test_grouping.py): which properties exist in a game, the value of a row for a
property (every card sits in exactly one branch – multicoloured is a branch of its own, so the numbers add up), the
children of a node with count and value, and the filter for the grid.

Rows are the library's rows ("My Collection": row_from_group) – count = copies, price = euros per copy, db = card row.
"""
import games
from system.i18n import tr

MORE_AT = 9   # a level shows its 9 biggest branches, the rest as "+ n more" (Oliver's draft)

# (key, English name) – the name is the button "Group by …"; per game some of them don't exist (see keys())
KEYS = (("set", "Set"), ("rarity", "Rarity"), ("type", "Card type"), ("color", "Color"), ("mv", "Mana value"),
        ("lang", "Language"), ("foil", "Finish"), ("price", "Price"))
COLOR_WORD = {"pokemon": "Energy type", "yugioh": "Attribute", "lorcana": "Ink"}
PRICE_BANDS = ((1, "under 1 €"), (5, "1–5 €"), (20, "5–20 €"), (100, "20–100 €"), (None, "100 € and more"))


def keys(all_cards=False):
    """[(key, label)] of the open game – mana value only where cards have one (Magic). all_cards: "All cards" (no
    finish – the card database has one row per print, not foil and normal copies)."""
    g = games.current()
    out = []
    for k, name in KEYS:
        if k == "mv" and g.key != "mtg":
            continue
        if all_cards and sql_expr(k) is None:
            continue
        if k == "color":
            name = COLOR_WORD.get(g.key, name)
        out.append((k, tr(name)))
    return out


def label_of_key(key):
    return dict(keys()).get(key, key)


def _db(r):
    return r.get("db") or {}


def value(r, key):
    """The branch of a row for a property – always exactly one (never None: "–" collects the unknown)."""
    if key == "set":
        return str(r.get("set") or "").upper() or "–"
    if key == "rarity":
        return str(r.get("rarity") or _db(r).get("rarity") or "").lower() or "–"
    if key == "type":
        db = _db(r)
        return games.current().card_type(db) if db else "–"
    if key == "color":
        cs = [c for c in str(_db(r).get("colors") or "") if c.isalpha()]
        return "M" if len(set(cs)) > 1 else (cs[0] if cs else "C")
    if key == "mv":
        mv = _db(r).get("cmc")
        return "–" if mv is None else str(min(7, int(mv)))
    if key == "lang":
        return str(r.get("lang") or "en").lower()
    if key == "foil":
        return "foil" if r.get("foil") else "nonfoil"
    if key == "price":
        p = float(r.get("price") or 0)
        for i, (top, _name) in enumerate(PRICE_BANDS):
            if top is None or p < top:
                return str(i)
    return "–"


def _natural(key, vals, rows_of):
    """Natural order of the branches (draft): sets new → old, rarities as the game lists them, colours in the
    palette's order + multi + colourless, mana value 0 → 7+, price bands low → high."""
    g = games.current()
    if key == "rarity":
        order = [k for k, _ in g.rarities]
        return sorted(vals, key=lambda v: (order.index(v) if v in order else len(order), v))
    if key == "type":
        order = [k for k, _ in g.type_order]
        return sorted(vals, key=lambda v: (order.index(v) if v in order else len(order), v))
    if key == "color":
        order = list(g.palette) + ["M", "C"]
        return sorted(vals, key=lambda v: (order.index(v) if v in order else len(order), v))
    if key in ("mv", "price"):
        return sorted(vals, key=lambda v: (v == "–", int(v) if v.isdigit() else 0))
    if key == "set":
        def released(v):
            db = next((_db(r) for r in rows_of[v] if _db(r)), {})
            return str(db.get("released") or "")
        return sorted(vals, key=lambda v: (v == "–", "".join(chr(0x10FFFF - ord(c)) for c in released(v)), v))
    if key == "foil":
        return sorted(vals, key=lambda v: v != "nonfoil")
    return sorted(vals)


def branch_label(key, v, rows=()):
    """Human name of a branch."""
    g = games.current()
    if v == "–":
        return tr("unknown")
    if key == "set":
        db = next((_db(r) for r in rows if _db(r).get("set_name")), {})
        return db.get("set_name") or v
    if key == "rarity":
        return tr(dict(g.rarities).get(v, v.title()))
    if key == "type":
        return tr(dict(g.type_order).get(v, v))
    if key == "color":
        if v == "M":
            return tr("Multicolored")
        if v == "C":
            return tr("Colorless")
        return tr((g.color_names or {}).get(v, v))
    if key == "mv":
        return "7+" if v == "7" else v
    if key == "lang":
        return v.upper()
    if key == "foil":
        return g.foil_word if v == "foil" else tr("Normal")
    if key == "price":
        return tr(PRICE_BANDS[int(v)][1])
    return v


def cards(rows):
    return sum(int(r.get("count") or 0) for r in rows)


def worth(rows):
    return sum(float(r.get("price") or 0) * int(r.get("count") or 0) for r in rows)


def children(rows, key, by="natural"):
    """Branches of the cards `rows` by `key`: [{"v", "label", "cards", "value", "rows"}] – natural order, or the
    biggest first (by="count" | "value", when the library is sorted that way)."""
    rows_of = {}
    for r in rows:
        rows_of.setdefault(value(r, key), []).append(r)
    out = [{"v": v, "label": branch_label(key, v, rows_of[v]), "cards": cards(rows_of[v]), "value": worth(rows_of[v]),
            "rows": rows_of[v]} for v in _natural(key, list(rows_of), rows_of)]
    if by == "count":
        out.sort(key=lambda b: -b["cards"])
    elif by == "value":
        out.sort(key=lambda b: -b["value"])
    return out


def keep(chain, path):
    """Filter for the grid: a row stays if it lies on the chosen path (path = branch values, as long as or shorter
    than the chain). Empty path = everything."""
    steps = list(zip(chain, path))
    if not steps:
        return None
    return lambda r: all(value(r, k) == v for k, v in steps)


def tree(rows, chain, path, more=(), by="natural"):
    """The tree for the view: one column per level of the chain. Only the bright path fans out (otherwise three
    levels would be unreadable – 7 colours × 8 types × 5 rarities = 280 leaves): column d holds the branches of the
    node path[:d]; the one on the path is lit, the others dimmed – every one with its number.
    more: levels that show all their branches (otherwise the 9 biggest + "+ n more").
    -> {"root": {cards, value}, "cols": [{"key", "label", "nodes": [{v, label, cards, value, on, share}], "hidden"}],
        "next": [{"key", "label", "branches"}] (suggestions "branch on by …" at the end of the path), "path": [...]}"""
    out = {"root": {"cards": cards(rows), "value": worth(rows)}, "cols": [], "next": [], "path": []}
    here = rows
    for d, key in enumerate(chain):
        kids = children(here, key, by)
        if not kids:
            break
        pick = path[d] if d < len(path) else None
        if pick is not None and not any(b["v"] == pick for b in kids):
            pick = None   # (the path doesn't exist here any more – e.g. a filter emptied it)
        out["cols"].append(_column(key, kids, pick, d in more))
        if pick is None:
            break
        out["path"].append(pick)
        here = next(b["rows"] for b in kids if b["v"] == pick)
    # suggestions at the end of the bright path: the properties not yet in the chain, with their number of branches
    if len(out["path"]) == len(chain):
        used = set(chain)
        for k, name in keys():
            if k in used:
                continue
            n = len({value(r, k) for r in here})
            if n > 1:
                out["next"].append({"key": k, "label": name, "branches": n})
    out["here"] = {"cards": cards(here), "value": worth(here)}
    return out


# ---------- "All cards" (Oliver, after 0.9.2): the same tree from the card database ----------
# Not every print is loaded: each level is one GROUP BY in SQL (in the background, ui/qgroup.py), the grid stays
# page by page and gets the chosen branch as an SQL condition (sql_where). The expressions give the same branch as
# value() does for a row from the database (row_from_db).
_FRONT_TYPE = "(CASE WHEN instr(COALESCE(c.type_line, ''), '//') > 0 " \
              "THEN substr(c.type_line, 1, instr(c.type_line, '//') - 1) ELSE COALESCE(c.type_line, '') END)"
_LETTERS = "replace(replace(replace(COALESCE(c.colors, ''), ',', ''), ' ', ''), '/', '')"


def _type_sql():
    """card_type() of the open game in SQL: Magic looks for the type in the front face, the others at the start."""
    g = games.current()
    if not g.type_order:
        return "'Other'", []
    if g.key == "mtg":
        parts = " ".join("WHEN instr(" + _FRONT_TYPE + ", ?) > 0 THEN ?" for _ in g.type_order)
    else:
        parts = " ".join("WHEN substr(COALESCE(c.type_line, ''), 1, length(?)) = ? THEN ?" for _ in g.type_order)
    args = []
    for k, _ in g.type_order:
        args += [k, k] if g.key == "mtg" else [k, k, k]
    return f"(CASE {parts} ELSE 'Other' END)", args


def sql_expr(key):
    """(SQL expression on c, its parameters) for a property – None where "All cards" has none (finish)."""
    if key == "set":
        return "COALESCE(NULLIF(upper(c.set_code), ''), '–')", []
    if key == "rarity":
        return "COALESCE(NULLIF(lower(c.rarity), ''), '–')", []
    if key == "type":
        return _type_sql()
    if key == "color":
        return (f"(CASE WHEN length({_LETTERS}) > 1 THEN 'M' WHEN length({_LETTERS}) = 1 THEN {_LETTERS} "
                f"ELSE 'C' END)"), []
    if key == "mv":
        return "(CASE WHEN c.cmc IS NULL THEN '–' ELSE CAST(MIN(7, CAST(c.cmc AS INTEGER)) AS TEXT) END)", []
    if key == "lang":
        return "COALESCE(NULLIF(lower(c.lang), ''), 'en')", []
    if key == "price":
        p = "COALESCE(c.eur, c.eur_foil, 0)"
        whens = " ".join(f"WHEN {p} < {top} THEN '{i}'" for i, (top, _n) in enumerate(PRICE_BANDS) if top is not None)
        return f"(CASE {whens} ELSE '{len(PRICE_BANDS) - 1}' END)", []
    return None


def _sql_chain(chain):
    """The chain as far as "All cards" can follow it (a finish level from My Collection ends it)."""
    out = []
    for k in chain:
        if sql_expr(k) is None:
            break
        out.append(k)
    return out


def sql_where(chain, path):
    """Conditions for the grid: the cards of the chosen branch -> [(sql, args)] for carddb (filter "where_sql")."""
    out = []
    for k, v in zip(_sql_chain(chain), path):
        e, a = sql_expr(k)
        out.append((f"{e} = ?", a + [v]))
    return out


def tree_sql(count, distinct, chain, path, more=(), by="natural"):
    """tree() for "All cards": count(expr, args, where) -> [(v, prints, value, set name, released)] and
    distinct(exprs, where) -> [n, …] ask the card database (carddb.group_counts / distinct_counts with the library's
    search and filters). Same result as tree() – the numbers are prints, not copies."""
    chain = _sql_chain(chain)
    total = count("'all'", [], [])
    root = {"cards": sum(r[1] for r in total), "value": sum(r[2] or 0 for r in total)}
    out = {"root": root, "cols": [], "next": [], "path": [], "here": dict(root)}
    where = []
    for d, key in enumerate(chain):
        e, a = sql_expr(key)
        res = count(e, a, where)
        if not res:
            break
        rows_of = {str(v): [{"db": {"set_name": sn, "released": rel}}] for v, _n, _w, sn, rel in res}
        nums = {str(v): (n, w or 0) for v, n, w, _sn, _rel in res}
        kids = [{"v": v, "label": branch_label(key, v, rows_of[v]), "cards": nums[v][0], "value": nums[v][1]}
                for v in _natural(key, list(rows_of), rows_of)]
        if by == "count":
            kids.sort(key=lambda b: -b["cards"])
        elif by == "value":
            kids.sort(key=lambda b: -b["value"])
        pick = path[d] if d < len(path) else None
        if pick is not None and not any(b["v"] == pick for b in kids):
            pick = None
        out["cols"].append(_column(key, kids, pick, d in more))
        if pick is None:
            break
        out["path"].append(pick)
        out["here"] = {"cards": nums[pick][0], "value": nums[pick][1]}
        where = where + [(f"{e} = ?", a + [pick])]
    if len(out["path"]) == len(chain):
        used = set(chain)
        rest = [(k, name) for k, name in keys(all_cards=True) if k not in used]
        ns = distinct([sql_expr(k) for k, _ in rest], where)
        out["next"] = [{"key": k, "label": name, "branches": n} for (k, name), n in zip(rest, ns) if n > 1]
    return out


def _column(key, kids, pick, show_all):
    """One column of the tree: the 9 biggest branches (+ the one on the path) unless all are shown."""
    total = max(1, sum(b["cards"] for b in kids))
    shown, hidden = kids, 0
    if not show_all and len(kids) > MORE_AT:
        top = sorted(kids, key=lambda b: -b["cards"])[:MORE_AT]
        keepv = {b["v"] for b in top} | ({pick} if pick else set())
        shown = [b for b in kids if b["v"] in keepv]
        hidden = len(kids) - len(shown)
    return {"key": key, "label": label_of_key(key), "hidden": hidden, "all": len(kids),
            "nodes": [{"v": b["v"], "label": b["label"], "cards": b["cards"], "value": b["value"],
                       "on": b["v"] == pick, "share": b["cards"] / total} for b in shown]}
