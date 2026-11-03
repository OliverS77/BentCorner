"""03.11.2026 (v16 tour): a copy from an import says "imported on 02.11.2026", not the raw log id
"import_2026-11-02_11-25-41"; a scanned copy stays "pulled on …", one by hand "added by hand · …".

    python -m unittest tests/test_source_text.py
"""
import time
import unittest

from system import i18n
from ui.librarycore import source_text


class SourceText(unittest.TestCase):
    def setUp(self):
        self.addCleanup(i18n.set_language, i18n.LANG)

    def text(self, item, lang):
        i18n.set_language(lang)
        return source_text(item)

    def test_import(self):
        it = {"src": "import_2026-11-02_11-25-41/1762082741.0"}
        self.assertEqual(self.text(it, "en"), "imported on 02.11.2026")
        self.assertEqual(self.text(it, "de"), "importiert am 02.11.2026")

    def test_scanned(self):
        it = {"src": "2026-11-02_11-25-41/1762082741.0"}
        self.assertEqual(self.text(it, "en"), "pulled on 02.11.2026")
        self.assertEqual(self.text(it, "de"), "gezogen am 02.11.2026")

    def test_detached_import_and_by_hand(self):
        self.assertEqual(self.text({"from_session": "import_2026-01-05_08-00-00"}, "de"), "importiert am 05.01.2026")
        added = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
        self.assertEqual(self.text({"added": added}, "de"), "von Hand · 02.11.2026")


if __name__ == "__main__":
    unittest.main()
