"""Price alerts: the section titles are English in the code (tr) and German in locales/de.py – "Genau dein Exemplar"
used to show in the English UI (30.10.).

    python -m unittest tests/test_alarm_sections_i18n.py
"""
import unittest

from locales import de
from ui.qtrade_alarms import AlarmsBackend

GERMAN = ("Ganze", "Wunsch", "Tausch", "Genau", "Exemplar", "Günstig")


class AlarmSections(unittest.TestCase):
    def test_english_in_code_german_in_de(self):
        for _key, title, sub in AlarmsBackend.ALARM_SECTIONS:
            for text in (title, sub):
                self.assertFalse(any(w in text for w in GERMAN), text)
                self.assertIn(text, de.TEXTS, text)


if __name__ == "__main__":
    unittest.main()
