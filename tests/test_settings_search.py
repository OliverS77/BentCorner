"""Settings search (ui/qsettings.py): finds the smallest matching part of a section, knows synonyms (tray →
notification area), skips long reading lists (patch history) and marks the first hit for the jump ("flash").

    python -m unittest tests/test_settings_search.py
"""
import unittest

from ui import qsettings


def check(text, tip=""):
    return {"t": "check", "text": text, "tip": tip}


PAGE = {"t": "row", "items": [
    {"t": "col", "items": [
        {"t": "group", "title": "Im Hintergrund", "items": [check("Im Infobereich weiterlaufen"), check("Mit Windows starten")]},
        {"t": "group", "title": "Datenordner", "items": [{"t": "label", "html": "<b>C:\Daten</b>"}]},
    ]},
    {"t": "group", "title": "Patch-Historie", "items": [{"t": "scroll", "items": [{"t": "label", "html": "Infobereich …"}]}]},
    {"t": "form", "items": [{"t": "formrow", "label": {"t": "label", "html": "Startseite"},
                             "field": {"t": "combo", "items": ["Bibliothek", "Scannen"]}}]},
]}


class Search(unittest.TestCase):
    def test_synonym_finds_the_row_not_the_whole_group(self):
        hits = qsettings._hits(PAGE, qsettings._terms("Tray"))
        self.assertEqual([(g, n["text"]) for g, n in hits], [("Im Hintergrund", "Im Infobereich weiterlaufen")])

    def test_group_heading_brings_its_rows(self):
        hits = qsettings._hits(PAGE, qsettings._terms("datenordner"))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], "Datenordner")

    def test_choices_and_form_rows(self):
        hits = qsettings._hits(PAGE, qsettings._terms("scannen"))
        self.assertEqual([n["t"] for _, n in hits], ["formrow"])

    def test_reading_lists_are_skipped(self):
        texts = [n.get("text") for _, n in qsettings._hits(PAGE, qsettings._terms("infobereich"))]
        self.assertEqual(texts, ["Im Infobereich weiterlaufen"])   # not the patch history

    def test_markup_is_not_searched(self):
        self.assertEqual(qsettings._hits(PAGE, qsettings._terms("<b>")), [])

    def test_flash_marks_the_first_hit(self):
        import copy
        page = copy.deepcopy(PAGE)
        qsettings._mark(page, qsettings._terms("windows"))
        rows = page["items"][0]["items"][0]["items"]
        self.assertEqual([r.get("flash") for r in rows], [None, True])


class NoBoxesInBoxes(unittest.TestCase):
    def test_inner_groups_become_flat(self):
        tree = {"t": "col", "items": [{"t": "group", "title": "A", "items": [
            {"t": "group", "title": "Preview", "items": []}, {"t": "row", "items": [{"t": "group", "title": "B", "items": []}]}]}]}
        qsettings._flatten(tree)
        outer = tree["items"][0]
        self.assertNotIn("flat", outer)
        self.assertTrue(outer["items"][0]["flat"])
        self.assertTrue(outer["items"][1]["items"][0]["flat"])


if __name__ == "__main__":
    unittest.main()
