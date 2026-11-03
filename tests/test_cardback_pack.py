"""The card-back filter of the SCAN° index (scanner/fingerprint.Index._drop_card_backs): its fingerprint comes with the
Magic data pack (cards/packs.py, extra "cardback.npy", 03.11.2026) – with it, entries that only show the card back
are dropped; without it (pack not updated yet, public source) nothing is filtered and nothing breaks.

    python -m unittest tests/test_cardback_pack.py
"""
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from cards import packs
from scanner import fingerprint


def unit(v):
    v = np.asarray(v, np.float32)
    return v / np.linalg.norm(v)


class CardBackFilter(unittest.TestCase):
    def setUp(self):
        self.back = unit([1, 0, 0, 0])
        self.index = SimpleNamespace(ids=["a", "back", "b"],
                                     mat=np.stack([unit([0, 1, 0, 0]), self.back, unit([0, 0, 1, 0])]))

    def test_in_the_magic_pack_as_extra(self):
        self.assertIn(fingerprint.CARDBACK, packs.PACKS["mtg"]["extra"])
        self.assertNotIn(fingerprint.CARDBACK, packs.PACKS["mtg"]["files"])   # "installed" doesn't wait for it

    def test_drops_entries_that_only_show_the_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / fingerprint.CARDBACK
            np.save(f, self.back)
            with mock.patch.object(packs, "path_of", lambda key, name: f if (key, name) == ("mtg", fingerprint.CARDBACK)
                                   else None):
                fingerprint.Index._drop_card_backs(self.index)
        self.assertEqual(self.index.ids, ["a", "b"])
        self.assertEqual(len(self.index.mat), 2)

    def test_without_the_file_nothing_is_filtered(self):
        with mock.patch.object(packs, "path_of", lambda key, name: None):
            fingerprint.Index._drop_card_backs(self.index)
        self.assertEqual(self.index.ids, ["a", "back", "b"])


if __name__ == "__main__":
    unittest.main()
