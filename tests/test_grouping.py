"""Group by (ui/grouping.py): every card in exactly one branch, numbers that add up, only the bright path fans out,
jumping across keeps deeper levels where they exist, "+ n more" after 9 branches. No UI, no database.

    python -m unittest tests/test_grouping.py
"""
import unittest
from types import SimpleNamespace
from unittest import mock

from ui import grouping

GAME = SimpleNamespace(key="mtg", rarities=(("common", "Common"), ("uncommon", "Uncommon"), ("rare", "Rare"),
                                            ("mythic", "Mythic")),
                       type_order=(("Creature", "Creatures"), ("Instant", "Instants"), ("Land", "Lands")),
                       palette="WUBRG", color_names={"W": "White", "U": "Blue"}, foil_word="Foil",
                       card_type=lambda db: db.get("type") or "Other")


def row(name, set_code, rarity, colors="", count=1, price=1.0, foil=False, released="2020-01-01", typ="Creature"):
    return {"name": name, "set": set_code, "rarity": rarity, "count": count, "price": price, "foil": foil,
            "lang": "en", "db": {"colors": colors, "set_name": set_code + " Set", "released": released, "cmc": 2,
                                 "type": typ}}


ROWS = [row("A", "NEW", "rare", "W", 2, 5.0, released="2026-01-01"), row("B", "NEW", "common", "U"),
        row("C", "OLD", "rare", "WU", 3, 2.0, released="2001-01-01"), row("D", "OLD", "mythic", ""),
        row("E", "MID", "common", "U", released="2015-01-01")]


class Grouping(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(grouping.games, "current", lambda: GAME)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_every_card_in_one_branch_and_numbers_add_up(self):
        kids = grouping.children(ROWS, "color")
        self.assertEqual({b["v"] for b in kids}, {"W", "U", "M", "C"})   # multicoloured is a branch of its own
        self.assertEqual(sum(b["cards"] for b in kids), grouping.cards(ROWS))

    def test_natural_order(self):
        self.assertEqual([b["v"] for b in grouping.children(ROWS, "set")], ["NEW", "MID", "OLD"])   # new → old
        self.assertEqual([b["v"] for b in grouping.children(ROWS, "rarity")], ["common", "rare", "mythic"])
        self.assertEqual([b["v"] for b in grouping.children(ROWS, "color")], ["W", "U", "M", "C"])
        self.assertEqual([b["v"] for b in grouping.children(ROWS, "set", by="count")][0], "OLD")   # biggest first

    def test_only_the_bright_path_fans_out(self):
        t = grouping.tree(ROWS, ["set", "rarity"], [])
        self.assertEqual(len(t["cols"]), 1)                               # nothing picked: only level 1
        t = grouping.tree(ROWS, ["set", "rarity"], ["OLD"])
        self.assertEqual([n["v"] for n in t["cols"][1]["nodes"]], ["rare", "mythic"])
        self.assertTrue(t["cols"][0]["nodes"][2]["on"])
        self.assertEqual(t["here"]["cards"], 4)

    def test_grid_filter(self):
        keep = grouping.keep(["set", "rarity"], ["NEW", "rare"])
        self.assertEqual([r["name"] for r in ROWS if keep(r)], ["A"])
        self.assertIsNone(grouping.keep([], []))

    def test_jump_across_keeps_deeper_level_only_where_it_exists(self):
        t = grouping.tree(ROWS, ["set", "rarity"], ["MID", "rare"])       # MID has no rare
        self.assertEqual(t["path"], ["MID"])
        t = grouping.tree(ROWS, ["set", "rarity"], ["OLD", "rare"])
        self.assertEqual(t["path"], ["OLD", "rare"])

    def test_suggestions_at_the_end_of_the_path(self):
        t = grouping.tree(ROWS, ["set"], ["OLD"])
        nxt = {n["key"]: n["branches"] for n in t["next"]}
        self.assertEqual(nxt["rarity"], 2)
        self.assertNotIn("set", nxt)
        self.assertNotIn("lang", nxt)                                    # one branch only: no point

    def test_many_branches_show_nine_plus_more(self):
        rows = [row(f"N{i}", f"S{i:02d}", "common", count=i + 1) for i in range(14)]
        t = grouping.tree(rows, ["set"], ["S00"])                         # the picked one stays though it's tiny
        col = t["cols"][0]
        self.assertEqual(col["hidden"], 4)
        self.assertIn("S00", [n["v"] for n in col["nodes"]])
        self.assertEqual(len(grouping.tree(rows, ["set"], [], more={0})["cols"][0]["nodes"]), 14)


def _mtg_type(db):   # like games/mtg.py: the type in the front face
    front = (db.get("type_line") or "").split("//")[0]
    return next((k for k, _ in GAME.type_order if k in front), "Other")


SQL_GAME = SimpleNamespace(**{**vars(GAME), "card_type": _mtg_type})
# (set, rarity, colors, cmc, type line, eur, eur_foil, lang, released)
DB = [("neo", "rare", "W", 2.0, "Creature — Human", 5.0, None, "en", "2022-02-18"),
      ("neo", "common", "U,R", 3.0, "Instant", 0.1, None, "en", "2022-02-18"),
      ("neo", "mythic", "", 9.0, "Land // Creature", None, 30.0, "en", "2022-02-18"),
      ("lea", "rare", "", None, "Artifact", 150.0, None, "en", "1993-08-05"),
      ("lea", "", "G", 1.0, "Creature — Elf", 0.5, None, "de", "1993-08-05")]


class AllCardsInSql(unittest.TestCase):
    """"All cards": the branches in SQL are the same as value() gives for the rows from the database, and tree_sql
    builds the same tree as tree() over those rows (the numbers are prints)."""

    def setUp(self):
        import sqlite3
        self.p = mock.patch.object(grouping.games, "current", lambda: SQL_GAME)
        self.p.start()
        self.con = sqlite3.connect(":memory:")
        self.con.execute("CREATE TABLE cards (set_code, set_name, rarity, colors, cmc, type_line, eur, eur_foil, lang, "
                         "released)")
        self.con.executemany("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?)",
                             [(s, s.upper() + " Set", r, c, m, t, e, ef, lg, rel) for s, r, c, m, t, e, ef, lg, rel in DB])
        self.rows = [{"set": s.upper(), "rarity": r, "lang": lg, "count": 1, "price": e if e is not None else ef,
                      "foil": False, "db": {"colors": c, "cmc": m, "type_line": t, "set_name": s.upper() + " Set",
                                            "released": rel}}
                     for s, r, c, m, t, e, ef, lg, rel in DB]

    def tearDown(self):
        self.p.stop()
        self.con.close()

    def _query(self, expr, args, where):
        sql = (f"SELECT {expr} AS v, COUNT(*), SUM(COALESCE(c.eur, c.eur_foil, 0)), MAX(c.set_name), MAX(c.released) "
               "FROM cards c" + (" WHERE " + " AND ".join(w for w, _ in where) if where else "") + " GROUP BY v")
        return self.con.execute(sql, list(args) + [a for _, xs in where for a in xs]).fetchall()

    def _distinct(self, exprs, where):
        cols = ", ".join(f"COUNT(DISTINCT {e})" for e, _ in exprs)
        sql = f"SELECT {cols} FROM cards c" + (" WHERE " + " AND ".join(w for w, _ in where) if where else "")
        return list(self.con.execute(sql, [a for _, xs in exprs for a in xs] + [a for _, xs in where for a in xs])
                    .fetchone())

    def test_same_branch_as_value(self):
        for key in ("set", "rarity", "type", "color", "mv", "lang", "price"):
            e, a = grouping.sql_expr(key)
            got = [r[0] for r in self.con.execute(f"SELECT {e} FROM cards c ORDER BY rowid", a)]
            self.assertEqual(got, [grouping.value(r, key) for r in self.rows], key)
        self.assertIsNone(grouping.sql_expr("foil"))                     # no finish in the card database
        self.assertNotIn("foil", dict(grouping.keys(all_cards=True)))

    def test_tree_sql_like_tree(self):
        for chain, path in ((["set", "rarity"], []), (["set", "rarity"], ["NEO"]), (["color", "type"], ["C", "Land"])):
            a = grouping.tree(self.rows, chain, path)
            b = grouping.tree_sql(self._query, self._distinct, chain, path)
            strip = lambda t: [[(n["v"], n["cards"], n["on"]) for n in c["nodes"]] for c in t["cols"]]  # noqa: E731
            self.assertEqual(strip(a), strip(b), (chain, path))
            self.assertEqual(a["path"], b["path"])
            self.assertEqual(a["here"]["cards"], b["here"]["cards"])
            self.assertEqual({(x["key"], x["branches"]) for x in a["next"] if x["key"] != "foil"},
                             {(x["key"], x["branches"]) for x in b["next"]})

    def test_grid_condition(self):
        where = grouping.sql_where(["set", "foil", "rarity"], ["NEO", "foil", "rare"])
        self.assertEqual(len(where), 1)                                  # a finish level ends the chain in SQL
        n = self.con.execute("SELECT COUNT(*) FROM cards c WHERE " + where[0][0], where[0][1]).fetchone()[0]
        self.assertEqual(n, 3)


if __name__ == "__main__":
    unittest.main()
