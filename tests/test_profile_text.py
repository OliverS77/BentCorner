"""„Who's scanning?" (legal 16.11.): name and card back do NOT stay on the computer – they go out with a friend request
or its acceptance (net/relay.py request_friend/answer_friend) and with the sync to your own devices (syncops
"profile"). The sheet says legal's wording, never the old „stay on your computer" sentence.

    python -m unittest tests/test_profile_text.py
"""
import pathlib
import unittest

from locales import de

EN = "Others see your name and card back as soon as you send or accept a friend request."
DE = "Andere sehen Namen und Kartenrückseite, sobald du eine Freundschaftsanfrage schickst oder annimmst."


class ProfileText(unittest.TestCase):
    def test_legal_wording(self):
        src = pathlib.Path("system/userprofile.py").read_text("utf-8")
        self.assertIn(EN, src)
        self.assertNotIn("stay on your computer until you share", src)
        key = next(k for k in de.TEXTS if EN in k)
        self.assertTrue(de.TEXTS[key].endswith(DE))
        self.assertNotIn("bleibt auf deinem Rechner, bis du selbst etwas teilst", de.TEXTS[key])


if __name__ == "__main__":
    unittest.main()
