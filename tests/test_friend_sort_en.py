"""The friends' sort menu (qtrade_friends.SORTS): English msgids, German only through locales/de.py – "Zuletzt
importiert" stood there in German and showed so in the English UI (ports, 03.11.2026)."""
import unittest

from system import i18n
from ui.qtrade_friends import FriendsBackend


class FriendSortTexts(unittest.TestCase):
    def test_english_msgids_with_german(self):
        lang = i18n.LANG
        self.addCleanup(i18n.set_language, lang)
        for key, text in FriendsBackend.SORTS:
            i18n.set_language("en")
            self.assertEqual(i18n.tr(text), text, key)
            i18n.set_language("de")
            self.assertNotEqual(i18n.tr(text), text if text != "Name" else "", key)
        i18n.set_language("de")
        self.assertEqual(i18n.tr("Recently imported"), "Zuletzt importiert")


if __name__ == "__main__":
    unittest.main()
