"""GPL notices in Settings → Legal (ui/qsetpages.gpl_notice): the source code line only once SOURCE_URL is set, the
required attribution word for word in every language, the bundled LICENSE readable without internet.

    python -m unittest tests/test_gpl_notice.py
"""
import types
import unittest
from unittest import mock

from system import contacts
from system import i18n
from ui import qform
from ui import qsetpages


def _texts(node):
    """All label texts and button captions of a form tree."""
    out = []
    if isinstance(node, dict):
        if node.get("t") == "label":
            out.append(node["html"])
        for key in ("text", "title"):
            if isinstance(node.get(key), str):
                out.append(node[key])
        for v in node.values():
            if isinstance(v, (list, dict)):
                out += _texts(v)
    elif isinstance(node, list):
        for v in node:
            out += _texts(v)
    return out


class GplNotice(unittest.TestCase):
    def setUp(self):
        self.ui = qform.UI(types.SimpleNamespace(_cb={}, _keys={}))
        self.addCleanup(i18n.set_language, i18n.LANG)

    SOURCE = "https://example.org/bentcorner"

    def _notice(self, lang="en", source=SOURCE):
        i18n.set_language(lang)
        with mock.patch.object(contacts, "SOURCE_URL", source):
            return "\n".join(_texts(qsetpages.gpl_notice(self.ui)))

    def test_no_block_at_all_while_the_repo_is_not_public(self):
        """Switch: without SOURCE_URL (repository not public yet) the Legal page looks as before."""
        with mock.patch.object(contacts, "SOURCE_URL", ""):
            self.assertIsNone(qsetpages.gpl_notice(self.ui))

    def test_source_url_is_a_repository_not_a_profile(self):
        """GPL § 6 (legal 03.11.2026): the link leads to the repository, best to the release tag – never to a profile."""
        import re
        ok = ["https://github.com/OliverS77/bentcorner", "https://github.com/OliverS77/bentcorner/",
              "https://github.com/OliverS77/bentcorner/tree/v0.9.8"]
        bad = ["https://github.com/OliverS77", "https://github.com/OliverS77/", "https://github.com/",
               "http://github.com/OliverS77/bentcorner", "https://example.org/OliverS77/bentcorner"]
        for url in ok:
            self.assertRegex(url, contacts.SOURCE_PATTERN)
        for url in bad:
            self.assertIsNone(re.match(contacts.SOURCE_PATTERN, url), url)
        self.assertTrue(contacts.SOURCE_URL == "" or re.match(contacts.SOURCE_PATTERN, contacts.SOURCE_URL))

    def test_release_links_its_tag(self):
        import version
        with mock.patch.object(version, "VERSION", "0.9.8"):
            text = self._notice(source="https://github.com/OliverS77/BentCorner")
        self.assertIn("<a href='https://github.com/OliverS77/BentCorner/tree/v0.9.8'>", text)
        with mock.patch.object(version, "VERSION", "0.9.8.3"):   # a working version has no tag: the repository
            text = self._notice(source="https://github.com/OliverS77/BentCorner")
        self.assertIn("<a href='https://github.com/OliverS77/BentCorner'>", text)

    def test_source_line_with_link_once_set(self):
        text = self._notice(source="https://example.org/bentcorner")
        self.assertIn("Source code: <a href='https://example.org/bentcorner'>", text)
        self.assertIn("Quellcode: <a href='https://example.org/bentcorner'>", self._notice("de", "https://example.org/bentcorner"))

    def test_attribution_word_for_word_in_german_too(self):
        for lang in ("en", "de"):
            self.assertIn("Based on Bent°Corner – https://bentcorner.app", self._notice(lang))

    def test_warranty_keeps_the_legal_limit(self):
        self.assertIn("to the extent permitted by law", self._notice("en"))
        self.assertIn("Soweit gesetzlich zulässig", self._notice("de"))

    def test_german_texts_are_all_translated(self):
        de = self._notice("de")
        for english in ("is free software", "ABSOLUTELY NO WARRANTY", "additional terms", "not covered by"):
            self.assertNotIn(english, de)

    def test_license_is_bundled_and_readable(self):
        text = qsetpages._license_text(("LICENSE",), None)
        self.assertIn("===== LICENSE =====", text)
        self.assertNotIn("missing", text)


if __name__ == "__main__":
    unittest.main()
