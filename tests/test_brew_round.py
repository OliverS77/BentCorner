"""0.9.7.22 – the small round after Brew (03.11.2026): an opened list in "For friends" shows the same print once
with its count; "1 matching card" in the singular; the play style in a Brew deck name in German like the list."""
import unittest

from collection import trade
from system import i18n


class MergedEntries(unittest.TestCase):
    def test_same_print_once_with_count(self):
        e = lambda n, s="c21", lang="en", foil=False: {"name": n, "set": s, "number": "263", "count": 1, "lang": lang,  # noqa: E731
                                                      "foil": foil, "uid": None}
        got = trade.merged_entries([e("Sol Ring"), e("Bolt"), e("Sol Ring"), e("Sol Ring", foil=True),
                                    e("Sol Ring", lang="de"), e("Sol Ring"), e("Sol Ring", s="cmr")])
        self.assertEqual([(x["name"], x["set"], x["lang"], x["foil"], x["count"]) for x in got],
                         [("Sol Ring", "c21", "en", False, 3), ("Bolt", "c21", "en", False, 1),
                          ("Sol Ring", "c21", "en", True, 1), ("Sol Ring", "c21", "de", False, 1),
                          ("Sol Ring", "cmr", "en", False, 1)])


class Texts(unittest.TestCase):
    def setUp(self):
        self._lang = i18n.LANG
        i18n.set_language("de")

    def tearDown(self):
        i18n.set_language(self._lang)

    def test_singular_and_style(self):
        self.assertEqual(i18n.tr("matching card"), "passende Karte")
        self.assertEqual(i18n.tr("Artifacts"), "Artefakte")


if __name__ == "__main__":
    unittest.main()
