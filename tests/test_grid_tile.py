"""Library grid: a tile's values come in one call (role "tile", cached per row). The cache must never show something
old – after a change of quantity/price/version (in place), of lists or decks (state outside the row), when an image
arrives, or when someone else reports a change; choosing cards (role "picked") alone leaves the tile as it is.

    python -m unittest tests/test_grid_tile.py
"""
import types
import unittest
from unittest import mock

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from ui import qlibrary

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Check:
    def __init__(self, on):
        self.on = on

    def isChecked(self):
        return self.on


def _backend():
    lib = types.SimpleNamespace(mode="mine", own_lang=_Check(True), mark_owned=_Check(False), list_any=set(),
                                ctrl=types.SimpleNamespace(settings={}))
    return types.SimpleNamespace(lib=lib, disp={}, sel_b=types.SimpleNamespace(keys=set()), ctrl=None)


def _row(key, price=1.0, count=1, version="normal"):
    return {"key": key, "sid": key, "name": f"Card {key}", "price": price, "count": count, "set": "abc",
            "number": "1", "version": version}


class Tile(unittest.TestCase):
    def setUp(self):
        self.images = {"a": "image://cards/a_en_n", "b": "image://cards/b_en_n"}
        self.decks = {}
        patches = [
            mock.patch.object(qlibrary, "card_source", lambda r, own: self.images[r["key"]]),
            mock.patch.object(qlibrary, "sets_text", lambda r, disp: r["version"]),
            mock.patch.object(qlibrary, "chip_texts", lambda r, disp, mode: [f"{r['count']}x"]),
            mock.patch("collection.deckcore.usage_chips", lambda ctrl, r: self.decks.get(r["key"], [])),
            mock.patch.object(qlibrary.quickimages, "pending", lambda key: False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.b = _backend()
        with mock.patch.object(qlibrary.quickimages, "on_ready", lambda fn: None):
            self.m = qlibrary.CardGridModel(None)
        self.m.b = self.b
        with mock.patch.object(self.m, "prefetch", lambda: None):
            self.m.sync([_row("a"), _row("b")])
        self.prefetch = mock.patch.object(self.m, "prefetch", lambda: None)
        self.prefetch.start()
        self.addCleanup(self.prefetch.stop)

    def tile(self, i=0):
        return self.m.data(self.m.index(i), Qt.UserRole + self.m.ROLES.index("tile"))

    def test_quantity_price_and_version_in_place(self):
        self.tile()
        self.m.sync([_row("a", price=2.5, count=3, version="foil"), _row("b")])
        t = self.tile()
        self.assertEqual(t["price"], qlibrary.eur(2.5))
        self.assertEqual(t["chips"], ["3x"])
        self.assertEqual(t["setLine"], "foil")

    def test_list_membership_with_identical_rows(self):
        self.tile()
        self.b.lib.list_any.add("a")            # a wish for any version – the row itself is unchanged
        self.m.sync([_row("a"), _row("b")])
        self.assertIn("Any version", self.tile()["chips"][0])

    def test_decks_from_someone_elses_report(self):
        self.tile()
        self.decks["a"] = ["Deck 1"]
        self.m.dataChanged.emit(self.m.index(0), self.m.index(1))   # like holders_changed / a price update
        self.assertEqual(self.tile()["decks"], ["Deck 1"])

    def test_image_arrives(self):
        self.tile()
        self.images["a"] = "file:///rund/a.webp"
        self.m._images_ready()
        self.assertEqual(self.tile()["img"], "file:///rund/a.webp")

    def test_new_search_rebuilds(self):
        self.tile()
        self.m.sync([_row("b"), _row("a")])
        self.assertEqual(self.tile()["name"], "Card b")

    def test_choosing_leaves_the_tile_and_changes_picked(self):
        before = self.tile()
        self.b.sel_b.keys = {"a"}
        self.m.picked_changed({"a"})
        self.assertIs(self.tile(), before)      # not recomputed
        self.assertTrue(self.m.data(self.m.index(0), Qt.UserRole + self.m.ROLES.index("picked")))


if __name__ == "__main__":
    unittest.main()
