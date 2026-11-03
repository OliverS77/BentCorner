"""Scan page tiles (ui/scantiles.py): the stored layout is completed and kept inside the grid, a tile only lands
where it fits (no overlap, not off the grid), a tile that came with an update finds a free place, money typed into
the tiles, one card row for QML, the session fields edited in place, the filtered scan's whole sets (switched in the
menu with several at once, taken out with ✕), "End scan" with its "Undo", the list per pack and editing a card of
any pack.

    python -m unittest tests/test_scan_tiles.py
"""
import time
import types
import unittest
from unittest import mock

from ui import scantiles as st


class Layout(unittest.TestCase):
    def test_default_and_completion(self):
        lay = st.layout_of({})
        self.assertEqual(set(lay), set(st.KEYS))
        self.assertEqual(lay["top"], st.DEFAULT["top"])
        part = st.layout_of({"scan_tiles": {"hit": {"c": 2, "stream": False}, "junk": 1}})
        self.assertEqual(part["hit"]["c"], 2)
        self.assertNotIn("stream", part["hit"])   # no stream view any more (review .101 c3)
        self.assertEqual(part["hit"]["h"], st.DEFAULT["hit"]["h"])

    def test_clamped_to_the_grid(self):
        lay = st.layout_of({"scan_tiles": {"top": {"c": 30, "r": -4, "w": 99, "h": 0}}})
        t = lay["top"]
        self.assertEqual((t["w"], t["h"]), (st.COLS, st.MIN["top"][1]))
        self.assertEqual((t["c"], t["r"]), (0, 0))
        broken = st.layout_of({"scan_tiles": "nonsense"})
        self.assertEqual(broken, st.layout_of({}))

    def test_defaults_do_not_overlap(self):
        lay = st.layout_of({})
        keys = list(lay)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                self.assertFalse(st._overlaps(lay[a], lay[b]), (a, b))

    def test_a_new_tile_finds_a_free_place(self):
        """An older layout (log, cards, hit, status – before .102): the biggest hit goes where it fits, else it waits
        hidden in the drawer; the old cards tile is gone (it is part of the scan tile now)."""
        old = {"status": {"c": 6, "r": 0, "w": 4, "h": 1}, "session": {"c": 0, "r": 0, "w": 4, "h": 4},
               "cards": {"c": 12, "r": 0, "w": 4, "h": 7}, "hit": {"c": 0, "r": 11, "w": 4, "h": 2}}
        lay = st.layout_of({"scan_tiles": old})
        self.assertNotIn("cards", lay)
        self.assertTrue(lay["top"]["shown"])
        self.assertFalse(any(st._overlaps(lay["top"], o) for k, o in lay.items() if k != "top" and o["shown"]))
        full = {"session": {"c": 0, "r": 0, "w": st.COLS, "h": st.ROWS}}
        self.assertFalse(st.layout_of({"scan_tiles": full})["top"]["shown"])


class Place(unittest.TestCase):
    def setUp(self):
        self.lay = st.layout_of({})

    def test_moves_where_free(self):
        new = st.place(self.lay, "hit", 5, 9, 4, 2)
        self.assertEqual((new["hit"]["c"], new["hit"]["r"]), (5, 9))
        self.assertEqual(self.lay["hit"]["c"], st.DEFAULT["hit"]["c"])   # the old layout stays as it was

    def test_refuses_overlap_and_outside(self):
        s = self.lay["session"]
        self.assertIsNone(st.place(self.lay, "hit", s["c"], s["r"], 4, 2))            # onto the session tile
        self.assertIsNone(st.place(self.lay, "hit", st.COLS - 2, 0, 4, 2))            # sticks out on the right
        self.assertIsNone(st.place(self.lay, "hit", 0, st.ROWS - 1, 4, 2))            # sticks out at the bottom
        self.assertIsNone(st.place(self.lay, "session", 0, 0, 2, 4))                  # narrower than the minimum

    def test_resize_in_place(self):
        c = self.lay["session"]
        new = st.place(self.lay, "session", c["c"], c["r"], c["w"] + 1, c["h"])
        self.assertEqual(new["session"]["w"], c["w"] + 1)


class MinimumAndDrawer(unittest.TestCase):
    """Oliver's review on .86/.90: a stored size below the content's minimum grows; the tile drawer hides/shows."""
    def setUp(self):
        self.lay = st.layout_of({})

    def test_too_small_grows_in_place_or_moves(self):
        lay = st.place(self.lay, "session", 0, 1, 3, 3)   # a scan tile below what its purpose needs
        new = st.fit(lay, "session", 4, 6)
        self.assertEqual((new["session"]["c"], new["session"]["r"], new["session"]["w"], new["session"]["h"]), (0, 1, 4, 6))
        self.assertIsNone(st.fit(new, "session", 4, 6))   # big enough: nothing changes
        # no room where it is (the hit tile beside it): the nearest free place
        crowd = st.place(st.place(self.lay, "session", 0, 4, 3, 3), "hit", 3, 4, 4, 2)
        moved = st.fit(crowd, "session", 4, 6)
        t = moved["session"]
        self.assertEqual((t["w"], t["h"]), (4, 6))
        self.assertFalse(any(st._overlaps(t, o) for k, o in moved.items() if k != "session" and o["shown"]))

    def test_hidden_tiles_take_no_room(self):
        self.assertFalse(self.lay["stats"]["shown"])   # the stats only when picked
        s = self.lay["session"]
        hidden = st.shown_at(self.lay, "session", False, 4, 6)
        self.assertFalse(hidden["session"]["shown"])
        self.assertIsNotNone(st.place(hidden, "hit", s["c"], s["r"], 4, 2))   # its place is free now

    def test_shown_again_where_free(self):
        new = st.shown_at(self.lay, "stats", True, 6, 5)
        t = new["stats"]
        self.assertTrue(t["shown"])
        self.assertFalse(any(st._overlaps(t, o) for k, o in new.items() if k != "stats" and o["shown"]))
        # its stored place taken: it goes to the nearest free one
        lay = st.place(new, "stats", 5, 3, 6, 7)
        lay = st.shown_at(lay, "stats", False, 6, 5)
        lay = st.place(lay, "hit", 5, 3, 4, 2)
        again = st.shown_at(lay, "stats", True, 6, 5)["stats"]
        self.assertFalse(st._overlaps(again, lay["hit"]))

    def test_no_room_stays_hidden(self):
        lay = dict(self.lay)
        for k in ("session", "top", "hit", "status"):
            lay = st.shown_at(lay, k, False, 2, 1)
        lay = st.place(st.shown_at(lay, "top", True, 2, 1), "top", 0, 0, st.COLS, st.ROWS)   # one tile everywhere
        self.assertIsNone(st.shown_at(lay, "stats", True, 6, 5))

    def test_saved_shown_flag(self):
        lay = st.layout_of({"scan_tiles": {"hit": {"shown": False}}})
        self.assertFalse(lay["hit"]["shown"])
        self.assertTrue(lay["top"]["shown"])


class Money(unittest.TestCase):
    def test_inputs(self):
        self.assertEqual(st.money("32,50 €"), 32.5)
        self.assertEqual(st.money("32.5"), 32.5)
        self.assertEqual(st.money("1.234,56"), 1234.56)
        self.assertEqual(st.money(""), 0.0)
        self.assertIsNone(st.money("viel"))
        self.assertIsNone(st.money("-3"))


class CardRow(unittest.TestCase):
    def test_row(self):
        e = {"name": "Sol Ring", "set": "c21", "number": "263", "lang": "de", "foil": True, "price": 1.5,
             "pack": 2, "idx": 3, "cond": ""}
        r = st.card_row(e)
        self.assertEqual(r["name"], "Sol Ring")
        self.assertIn("C21", r["sub"])
        self.assertIn("DE", r["sub"])
        self.assertEqual((r["pack"], r["idx"]), (2, 3))
        self.assertEqual(r["priceShort"], "1,50")
        self.assertEqual(r["img"], "")   # no file -> NoImage in QML
        self.assertEqual(st.card_row(dict(e, price=None))["price"], "–")


class Fields(unittest.TestCase):
    """setSessionField without Qt widgets: a fake controller and session."""

    def setUp(self):
        self.info = {}
        sess = types.SimpleNamespace(set_info=lambda **kw: self.info.update(kw), active=True, cards_view=lambda: [],
                                     lock=mock.MagicMock())
        ctrl = types.SimpleNamespace(session=sess, settings={}, snap={}, settings_changed=lambda: None)
        with mock.patch.object(st.TilesBackend, "_poll", lambda self: None):
            self.b = st.TilesBackend(ctrl)
        self.b._poll = lambda: None

    def test_title_paid_tags(self):
        self.assertTrue(self.b.setSessionField("title", "  Duskmourn Display "))
        self.assertEqual(self.info["title"], "Duskmourn Display")
        self.assertTrue(self.b.setSessionField("paid", "32,00 €"))
        self.assertEqual(self.info["paid"], 32.0)
        self.assertFalse(self.b.setSessionField("paid", "viel"))
        self.assertTrue(self.b.setSessionField("tags", "stream, duskmourn ·  "))
        self.assertEqual(self.info["tags"], ["stream", "duskmourn"])
        self.assertFalse(self.b.setSessionField("nonsense", "x"))


class PreferredSets(unittest.TestCase):
    CATALOG = [{"code": "otj", "name": "Outlaws of Thunder Junction"}, {"code": "mh3", "name": "Modern Horizons 3"}]
    # a whole set (review .101 c6): Final Fantasy with its Commander decks, tokens and the promos of its Commander
    FIN = [{"code": "fin", "name": "Final Fantasy", "released": "2025-06-13"},
           {"code": "fic", "name": "Final Fantasy Commander", "parent": "fin"},
           {"code": "tfin", "name": "Final Fantasy Tokens", "parent": "fin"},
           {"code": "pfic", "name": "Final Fantasy Commander Promos", "parent": "fic"},
           {"code": "dsk", "name": "Duskmourn", "released": "2024-09-27"}]

    def test_whole_sets(self):
        self.assertEqual([s["code"] for s in st.set_family("fic", self.FIN)], ["fin", "fic", "tfin", "pfic"])
        sets = st.sets_flipped([], {"code": "fin", "name": "Final Fantasy"}, self.FIN)
        self.assertEqual(len(sets), 4)
        sets = st.sets_flipped(sets, {"code": "dsk", "name": "Duskmourn"}, self.FIN)
        sets = st.sets_toggled(sets, {"code": "", "name": "Foundations"})
        groups = st.set_groups(sets, self.FIN)
        self.assertEqual([(g["key"], g["label"], g["n"]) for g in groups],
                         [("fin", "FIN", 4), ("dsk", "DSK", 1), ("Foundations", "Foundations", 1)])
        self.assertEqual([s["code"] for s in st.sets_without(sets, "fin", self.FIN)], ["dsk", ""])
        self.assertEqual(st.sets_flipped(sets, {"code": "fin", "name": "Final Fantasy"}, self.FIN),
                         st.sets_without(sets, "fin", self.FIN))   # the menu's click again: the whole set out

    def test_menu_lists_whole_sets(self):
        info = {"sets": [{"code": "fic", "name": "Final Fantasy Commander"}]}   # an older choice: one part only
        sess = types.SimpleNamespace(info=info, set_info=lambda **kw: info.update(kw))
        ctrl = types.SimpleNamespace(session=sess, catalog_sets=self.FIN)
        seen = {}
        with mock.patch("ui.qdialogs.menu", lambda title, items, pick, **kw: seen.update(items=items, pick=pick, **kw)):
            st.pick_sets(ctrl)
        self.assertEqual([(i["text"], i["on"]) for i in seen["items"]],
                         [("FIN  Final Fantasy", True), ("DSK  Duskmourn", False)])   # no parts in the list
        seen["pick"](0)
        self.assertEqual(info["sets"], [])
        seen["pick"](0)
        self.assertEqual([s["code"] for s in info["sets"]], ["fin", "fic", "tfin", "pfic"])

    def test_toggle_and_summary(self):
        sets = st.sets_toggled([], {"code": "otj", "name": "Outlaws of Thunder Junction"})
        self.assertEqual(st.sets_summary(sets), "Outlaws of Thunder Junction")
        sets = st.sets_toggled(sets, {"code": "", "name": "Final Fantasy"})
        self.assertEqual(st.sets_summary(sets), "OTJ · Final Fantasy")
        self.assertEqual(st.sets_toggled(sets, {"code": "", "name": "final fantasy"}), sets)   # no second spelling
        self.assertEqual(st.sets_toggled(sets, {"code": "", "name": "Final Fantasy"}), sets[:1])
        self.assertEqual(st.sets_toggled(sets, {"code": "otj", "name": "x"}), [{"code": "", "name": "Final Fantasy"}])

    def test_menu_switches_and_takes_text(self):
        info = {"sets": [{"code": "mh3", "name": "Modern Horizons 3"}]}
        sess = types.SimpleNamespace(info=info, set_info=lambda **kw: info.update(kw))
        ctrl = types.SimpleNamespace(session=sess, catalog_sets=self.CATALOG)
        seen = {}
        with mock.patch("ui.qdialogs.menu", lambda title, items, pick, **kw: seen.update(items=items, pick=pick, **kw)):
            st.pick_sets(ctrl)
        self.assertTrue(seen["multi"])
        self.assertEqual([i["on"] for i in seen["items"]], [True, False])   # chosen first and lit, no double
        seen["pick"](1)
        seen["pick"](0)
        self.assertEqual(info["sets"], [{"code": "otj", "name": "Outlaws of Thunder Junction"}])
        seen["on_text"](" Final Fantasy ")
        self.assertEqual(info["sets"][-1], {"code": "", "name": "Final Fantasy"})


if __name__ == "__main__":
    unittest.main()


class EndAndUndo(unittest.TestCase):
    """"End scan" ends right away (no question): "✓ Saved in Logs – name · 22 cards · 137,18 €" with Open and Undo for a
    moment; Undo goes once the next log has a card; nothing scanned: no log, a short note."""

    def setUp(self):
        self.cards = 22   # the log being ended
        self.calls = []
        started = time.mktime((2026, 10, 30, 12, 13, 0, 0, 0, -1))
        sess = types.SimpleNamespace(id="2026-10-30_12-13-00", info={"title": ""}, active=True, cards_view=lambda: [],
                                     started=started, lock=mock.MagicMock(),
                                     to_dict=lambda: {"stats": {"cards": self.cards, "total": 137.18}})

        def end(name):
            self.calls.append(("end", name))
            done, self.cards = bool(self.cards), 0   # the new log right after ending: empty
            return done
        ctrl = types.SimpleNamespace(session=sess, settings={}, snap={}, settings_changed=lambda: None,
                                     end_session_now=end, undo_end_session=lambda: self.calls.append(("undo",)) or True,
                                     show_trade_session=lambda key, sid: self.calls.append(("open", sid)))
        with mock.patch.object(st.TilesBackend, "_poll", lambda self: None):
            self.b = st.TilesBackend(ctrl)
        patch = mock.patch.object(st, "scan_title", lambda: "SCAN° – Pokémon")
        patch.start()
        self.addCleanup(patch.stop)

    def test_end_names_and_offers_open_and_undo(self):
        self.b.endSession()
        self.assertEqual(self.calls, [("end", "SCAN° – Pokémon 12:13")])   # no name typed: brand, game, start time
        e = self.b.session["ended"]
        self.assertEqual(e["text"], "Saved in Logs")
        self.assertIn("SCAN° – Pokémon 12:13 · 22 cards", e["detail"])
        self.assertIn("137", e["detail"])
        self.assertTrue(e["undo"])
        self.b.openEnded()
        self.assertEqual(self.calls[-1], ("open", "2026-10-30_12-13-00"))
        self.b.undoEnd()
        self.assertEqual(self.calls[-1], ("undo",))
        self.assertEqual(self.b.session["ended"], {})

    def test_undo_goes_with_the_next_card(self):
        self.b.endSession()
        self.assertTrue(self.b.session["ended"])
        self.cards = 1
        self.b._poll()   # the next log has its first card: no undo any more
        self.assertEqual(self.b.session["ended"], {})

    def test_nothing_scanned_no_log(self):
        self.cards = 0
        self.b.endSession()
        e = self.b.session["ended"]
        self.assertEqual((e["id"], e["undo"]), ("", False))
        self.assertIn("no log saved", e["text"])


class PackList(unittest.TestCase):
    """Opening boosters: one list per pack, the newest pack first; the pack being opened is there while still empty."""

    def test_groups_newest_first(self):
        view = [{"name": "C", "pack": 2, "idx": 0, "price": 2.0}, {"name": "B", "pack": 1, "idx": 1, "price": 0.5},
                {"name": "A", "pack": 1, "idx": 0, "price": None}]
        out = st.pack_list(view, 2)
        self.assertEqual([(p["n"], p["cards"]) for p in out], [(2, 1), (1, 2)])
        self.assertEqual([r["name"] for r in out[1]["rows"]], ["B", "A"])
        self.assertEqual(out[1]["total"], st.eur(0.5))

    def test_new_pack_still_empty(self):
        out = st.pack_list([{"name": "A", "pack": 1, "idx": 0, "price": 1.0}], 2)
        self.assertEqual([(p["n"], p["cards"], p["rows"]) for p in out[:1]], [(2, 0, [])])
        self.assertEqual(st.pack_list([], 1)[0]["n"], 1)


class EditAnyPack(unittest.TestCase):
    """A click on a card of the scan tile edits it – also in an older pack (the card window works on that pack)."""

    def setUp(self):
        from ui import streamwindow as sw
        self.calls = []
        self.packs = [{"cards": [{"name": "Old", "id": "o"}]}, {"cards": [{"name": "New", "id": "n"}]}]
        sess = types.SimpleNamespace(packs=self.packs, lock=mock.MagicMock(),
                                     replace=lambda card, i, p=None, **kw: self.calls.append(("replace", i, p)),
                                     undo=lambda i, p=None: self.calls.append(("undo", i, p)))
        ctrl = types.SimpleNamespace(session=sess, snap={"pack": self.packs[-1]["cards"]},
                                     removed_soon=lambda e: self.calls.append(("soon", e["name"])),
                                     scan_correction=lambda old, card: self.calls.append(("fix", old["name"])))

        class Fake:
            _pack_cards, edit_entry = sw.StreamWindow._pack_cards, sw.StreamWindow.edit_entry
            card_chosen, card_removed = sw.StreamWindow.card_chosen, sw.StreamWindow.card_removed

            def close_card_panel(self):
                pass
        self.w = Fake()
        self.w.ctrl, self.w.edit_index, self.w.edit_pack = ctrl, 0, 0
        self.w.card_panel = types.SimpleNamespace(finish="", edition="", wrong_scan=False, question=None,
                                                  cond=None, edit_orig=None)

    def test_entry_of_the_older_pack(self):
        self.assertEqual(self.w.edit_entry()["name"], "Old")
        self.w.edit_pack = None   # the current pack
        self.assertEqual(self.w.edit_entry()["name"], "New")
        self.w.edit_index = 5
        self.assertIsNone(self.w.edit_entry())

    def test_replace_and_remove_go_to_that_pack(self):
        self.w.card_chosen({"name": "Other"}, False, "en")
        self.assertEqual(self.calls, [("replace", 0, 0), ("fix", "Old")])
        self.calls.clear()
        self.w.card_removed()
        self.assertEqual(self.calls, [("soon", "Old"), ("undo", 0, 0)])

class RemoveWithUndo(unittest.TestCase):
    """The scan list's ✕: the card goes right away, "Undo" puts the very same entry back at its place."""

    def test_remove_and_put_back(self):
        import threading
        from scanner import core
        a, b, c = {"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"}
        sess = types.SimpleNamespace(packs=[{"cards": [a]}, {"cards": [b, c]}], lock=threading.RLock(), current=None,
                                     recent=[], rev=0, last_counted=None)
        sess._entry = lambda p, i: core.Session._entry(sess, p, i)
        core.Session.undo(sess, 0, p=1)
        self.assertEqual(sess.packs[1]["cards"], [c])
        core.Session.put_back(sess, b, 0, 1)
        self.assertIs(sess.packs[1]["cards"][0], b)
        self.assertEqual(sess.rev, 2)


class NeverInTheMiddle(unittest.TestCase):
    """Oliver: a hit never pops up in the middle – the Biggest-Hit moment is the "Last hit" tile's own jump, nothing on
    the page's top layer; a card of the scan list is previewed right beside the list."""

    def setUp(self):
        from PySide6 import QtCore
        from ui import overlay_paint
        self.QtCore = QtCore
        self.ov = overlay_paint.Overlay({"hit": 0.5, "hold": 3})
        self.ov._canvas, self.ov._s = QtCore.QRectF(0, 0, 1920, 1080), 1.0

    def test_no_moment_on_the_top_layer(self):
        """A new Biggest Hit paints nothing over the page (it jumps into the "Last hit" tile – QML, one sequence)."""
        self.ov.big_hit, self.ov.big_hit_t = {"id": "x", "price": 9.0, "img": ""}, 10.0
        self.assertFalse(self.ov.has_fx(10.5))
        p = mock.MagicMock()
        with mock.patch.object(self.ov, "_paint_big_hit") as big:
            self.ov._paint_effects(p, 1920, 1080, 10.5, 1.0, 1.0)
        big.assert_not_called()

    def test_list_preview_beside_the_list(self):
        self.ov.list_tile = self.QtCore.QRectF(20, 80, 380, 740)
        cx, cy, h = self.ov._beside_list(1920, 1080)
        self.assertGreater(cx - h * 0.716 / 2, 400)      # right of the tile, not over it
        self.assertLess(cx, 960)                         # and not in the middle of the page

class FinishInTheList(unittest.TestCase):
    """The scan list shows the finish the printing really has (Oliver: Pokémon holo-only showed as "Normal")."""

    def row(self, opts, **e):
        from cards import finishes
        with mock.patch.object(finishes, "options", lambda card: opts):
            return st.card_row(dict({"name": "Snivy", "set": "bw1", "number": "1", "price": 1.0}, **e))

    def test_holo_only_is_holo(self):
        r = self.row([{"key": "holo", "label": "Holo", "short": "H", "foil": False}], foil=False, finish="holo")
        self.assertEqual((r["finish"], r["finishes"]), ("Holo", 1))
        self.assertIn("Holo", r["sub"])   # never "Normal", and the list says it

    def test_normal_is_not_mentioned(self):
        opts = [{"key": "normal", "label": "Normal", "short": "N", "foil": False},
                {"key": "reverse", "label": "Reverse Holo", "short": "RH", "foil": True}]
        r = self.row(opts, foil=False)
        self.assertEqual((r["finish"], r["fancy"], r["finishes"]), ("Normal", "", 2))
        self.assertEqual(self.row(opts, foil=True)["fancy"], "Reverse Holo")
