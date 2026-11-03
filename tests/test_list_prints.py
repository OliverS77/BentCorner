"""Lists show exactly their prints (Oliver, review .62: "As list" from a log showed every print of each name):
entries with set and number keep language and finish, the Library filters on exactly those prints – wishes
without a print ("any version") show every own copy in "My Collection" and ONE tile in "All Cards": the cheapest
copy, with the chip "any version" (Oliver, review .90). Temp folder, no UI, no network.

    python -m unittest tests/test_list_prints.py
"""
import contextlib
import sqlite3
import unittest
from unittest import mock

from cards import carddb
from collection import trade
from tests.test_trade_binders import _Mine
from ui.librarycore import LibraryCore


class _Coll:
    """Just enough collection for clear_list: items, update, save."""

    def __init__(self, items):
        self.items = items

    def update(self, uid, **kw):
        next(it for it in self.items if it["uid"] == uid).update(kw)

    def save(self):
        pass


class Entries(_Mine):
    def test_language_and_finish_stay_apart(self):
        lid = trade.add_list("custom", "Log 28.10.")
        trade.put_entries("custom", lid, [
            {"name": "Opt", "set": "DOM", "number": "60", "count": 1, "lang": "de", "foil": True},
            {"name": "Opt", "set": "dom", "number": "60", "count": 2, "lang": "en", "foil": False},
            {"name": "Opt", "set": "dom", "number": "60", "count": 1, "lang": "de", "foil": True}], None)
        got = sorted((e["lang"] or "", e["foil"], e["count"]) for e in trade.list_entries("custom", lid, []))
        self.assertEqual(got, [("de", True, 2), ("en", False, 2)])

    def test_new_list_from_the_list_column_on_top(self):
        # the library's list column puts a new list first of its kind – above the default list too (review .101)
        a = trade.add_list("wish", "A")
        b = trade.add_list("wish", "B", top=True)
        self.assertEqual([x["id"] for x in trade.lists("wish")], [b, trade.MAIN_WISH, a])

    def test_default_wishlist_can_go_and_comes_back(self):
        # review .101: the default lists may be deleted – then there is none, until a card is starred again
        trade.add_wish("Opt")
        trade.remove_list("wish", trade.MAIN_WISH)                    # without coll: stays (old callers)
        self.assertIn(trade.MAIN_WISH, [x["id"] for x in trade.lists("wish")])
        trade.remove_list("wish", trade.MAIN_WISH, coll=_Coll([]))
        self.assertNotIn(trade.MAIN_WISH, [x["id"] for x in trade.lists("wish")])
        self.assertEqual(trade.wishes(), [])
        trade.add_list("wish", "Other")                               # writing the lists keeps it gone
        self.assertNotIn(trade.MAIN_WISH, [x["id"] for x in trade.lists("wish")])
        trade.add_wish("Shock")
        self.assertEqual([x["id"] for x in trade.lists("wish")][0], trade.MAIN_WISH)

    def test_default_trade_list_can_go(self):
        coll = _Coll([{"uid": "u1", "name": "Opt", "count": 2, "trade": 1}])
        trade.remove_list("have", trade.MAIN_HAVE, coll=coll)
        self.assertEqual(coll.items[0]["trade"], 0)                     # copies stay, just no longer for trade
        self.assertNotIn(trade.MAIN_HAVE, [x["id"] for x in trade.lists("have")])

    def test_wish_without_print_stays_plain(self):
        lid = trade.add_list("wish", "Suche")
        trade.put_entries("wish", lid, [{"name": "Opt", "count": 1, "lang": "de", "foil": True}], None)
        w = trade.wishes([lid])[0]
        self.assertNotIn("lang", w)
        self.assertNotIn("foil", w)


class PrintIds(unittest.TestCase):
    def test_language_print_or_english(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE cards (id, set_code, number, lang)")
        db.executemany("INSERT INTO cards VALUES (?, ?, ?, ?)",
                       [("en60", "dom", "60", "en"), ("de60", "dom", "60", "de"), ("en61", "dom", "61", "en")])
        with mock.patch.object(carddb, "exists", lambda: True), \
                mock.patch.object(carddb, "connection", contextlib.contextmanager(lambda game=None: (yield db))):
            self.assertEqual(carddb.ids_for_prints([("DOM", "60", "de")]), ["de60"])
            self.assertEqual(carddb.ids_for_prints([("dom", "61", "de"), ("dom", "60", None)]), ["en61", "en60"])


class CheapestPlayable(unittest.TestCase):
    """"Any version" = the cheapest PLAYABLE copy (review .90: Counterspell WC98 was "the cheapest") – gold border,
    oversized and Jumbo cards only if there is nothing else."""

    def test_gold_and_oversized_skipped_unless_alone(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE cards (id, name, set_code, set_name, border_color, layout, eur, eur_foil, released)")
        db.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?, 'normal', ?, NULL, '2000-01-01')", [
            ("wc", "Counterspell", "wc98", "World Championship Decks 1998", "gold", 0.8),
            ("big", "Counterspell", "ocmd", "Commander 2011 Oversized", "black", 0.5),
            ("ok", "Counterspell", "ema", "Eternal Masters", "black", 1.3),
            ("jumbo", "Pikachu", "j1", "Jumbo Cards", "", 0.2),
            ("pika", "Pikachu", "sv1", "Scarlet & Violet", "", 0.4),
            ("only", "Mox Diamond", "wc01", "World Championship Decks 2001", "gold", 9.0)])
        with mock.patch.object(carddb, "exists", lambda: True), \
                mock.patch.object(carddb, "_unplayable_sets", lambda: ("wc98", "ocmd", "wc01")), \
                mock.patch.object(carddb, "connection", contextlib.contextmanager(lambda game=None: (yield db))):
            got = carddb.cheapest_ids_for_names(["Counterspell", "Pikachu", "Mox Diamond"])
        self.assertEqual(got, {"counterspell": "ok", "pikachu": "pika", "mox diamond": "only"})


class Filter(unittest.TestCase):
    """LibraryCore._list_filter on a stand-in: the predicate for "My Collection" and "All Cards"."""

    WISHES = [{"name": "Opt", "set": "dom", "number": "60", "lang": "de", "foil": True, "list": "L"},
              {"name": "Shock", "set": "m19", "number": "156", "list": "L"},   # older entry: any language/finish
              {"name": "Duress", "list": "L"}]                                  # no print: every print

    def _keep(self, mode):
        me = mock.Mock(list_sel=("custom", "L"), mode=mode, list_add=False)
        with mock.patch.object(trade, "wishes", lambda ids=None, raw=False: self.WISHES), \
                mock.patch.object(carddb, "ids_for_names", lambda names: ["n-" + n for n in sorted(names)]), \
                mock.patch.object(carddb, "cheapest_ids_for_names", lambda names: {n.lower(): "c-" + n for n in names}), \
                mock.patch.object(carddb, "ids_for_prints", lambda prints: [f"p-{s}-{n}" for s, n, _ in prints]):
            keep, ids = LibraryCore._list_filter(me)
        first = "n-Duress" if mode == "mine" else "c-Duress"   # All Cards: only the cheapest copy of "any version"
        self.assertEqual(ids, [first, "p-dom-60", "p-m19-156"])
        self.assertEqual(me.list_any, set() if mode == "mine" else {"c-Duress"})
        return keep

    def test_my_collection_counts_language_and_finish(self):
        keep = self._keep("mine")
        row = lambda name, s, n, lang="en", foil=False: {"name": name, "set": s, "number": n, "lang": lang, "foil": foil}  # noqa: E731
        self.assertTrue(keep(row("Opt", "DOM", "60", "de", True)))
        self.assertFalse(keep(row("Opt", "dom", "60", "en", False)))   # the English copy is not on the list
        self.assertFalse(keep(row("Opt", "dom", "61", "de", True)))
        self.assertTrue(keep(row("Shock", "m19", "156", "fr", True)))
        self.assertFalse(keep(row("Shock", "dom", "1")))
        self.assertTrue(keep(row("Duress", "xln", "99", "ja", True)))

    def test_all_cards_only_prints(self):
        keep = self._keep("all")
        self.assertTrue(keep({"name": "Opt", "set": "dom", "number": "60", "lang": "en", "foil": False}))
        self.assertFalse(keep({"name": "Opt", "set": "m21", "number": "59", "lang": "en", "foil": False}))
        # any version: the cheapest copy only, not every print of the name
        self.assertTrue(keep({"name": "Duress", "sid": "c-Duress", "set": "xln", "number": "9"}))
        self.assertFalse(keep({"name": "Duress", "sid": "other", "set": "m21", "number": "1"}))


class TileCounts(unittest.TestCase):
    """A picked list: the tiles show how many are on the list, each entry on the row it fits best."""

    WISHES = [{"name": "Opt", "set": "dom", "number": "60", "lang": "de", "foil": True, "count": 2, "list": "L"},
              {"name": "Shock", "set": "m19", "number": "156", "count": 1, "list": "L"},
              {"name": "Duress", "count": 3, "list": "L"}]

    def _rows(self, mode):
        me = mock.Mock(list_sel=("custom", "L"), mode=mode, list_add=False)
        me.list_match = lambda w, r: LibraryCore.list_match(me, w, r)
        rows = [{"name": "Opt", "set": "dom", "number": "60", "lang": "en", "foil": False, "count": 4},
                {"name": "Opt", "set": "dom", "number": "60", "lang": "de", "foil": True, "count": 5},
                {"name": "Shock", "set": "m19", "number": "156", "lang": "fr", "foil": False, "count": 1},
                {"name": "Duress", "set": "xln", "number": "9", "lang": "en", "foil": False, "count": 7},
                {"name": "Duress", "set": "m21", "number": "1", "lang": "en", "foil": False, "count": 2}]
        with mock.patch.object(trade, "wishes", lambda ids=None, raw=False: self.WISHES):
            out = LibraryCore.list_counts(me, rows)
            keys = [LibraryCore.list_entry(me, r) for r in rows]
        return [r["count"] for r in out], keys

    def test_my_collection(self):
        counts, keys = self._rows("mine")
        self.assertEqual(counts, [0, 2, 1, 3, 0])   # your own 4 English and 7 Duress don't count – the list does
        self.assertIsNone(keys[0])
        self.assertEqual(keys[1], "Opt|dom|60|de|1")
        self.assertEqual(keys[3], "Duress||")

    def test_all_cards_prints_only(self):
        counts, _ = self._rows("all")
        self.assertEqual(counts[:2], [2, 0])   # "All Cards" knows prints, not languages: the first fitting row

    def test_adding_leaves_counts(self):
        me = mock.Mock(list_sel=("custom", "L"), list_add=True)
        self.assertEqual(LibraryCore.list_counts(me, [{"count": 4}]), [{"count": 4}])


if __name__ == "__main__":
    unittest.main()
