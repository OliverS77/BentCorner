"""Legal notices of new games: only visible once the game is ready, placed after Yu-Gi-Oh!, Riot text verbatim.

    python -m unittest tests/test_game_legal.py
"""
import unittest
from unittest import mock

import app
import games
from locales import de


class GameLegal(unittest.TestCase):
    def test_hidden_until_ready(self):
        ready = {k for k, _, r in games.GAMES if r}
        shown = [t for t, _ in app.legal_entries()]
        for key, title, _ in app.GAME_LEGAL:
            self.assertEqual(title in shown, key in ready)

    def test_after_yugioh_when_ready(self):
        # every game ready, whatever games.GAMES says today (flags derived, not hard-coded)
        all_ready = tuple((k, n, True) for k, n, _ in games.GAMES)
        keys = {k for k, _, _ in games.GAMES}
        legal = [title for key, title, _ in app.GAME_LEGAL if key in keys]
        self.assertTrue(legal)
        with mock.patch.object(games, "GAMES", all_ready):
            titles = [t for t, _ in app.legal_entries()]
        i = titles.index("Yu-Gi-Oh!")
        self.assertEqual(titles[i + 1:i + 1 + len(legal)], legal)
        self.assertEqual(len(titles), len(app.LEGAL_TEXT) + len(legal))

    def test_sources_follow_ready_games(self):
        """“Sources” and “Datenschutz” name only the games that are ready – a withdrawn game (games.WITHDRAWN) comes
        back by itself."""
        texts = [t for ti, t in app.legal_entries() if ti in ("Sources", "Datenschutz")]
        self.assertEqual(len(texts), 2)
        for t in texts:
            self.assertIn(t, de.TEXTS)
        for ready in (False, True):
            flags = tuple((k, n, ready if k == "lorcana" else r) for k, n, r in games.GAMES)
            with mock.patch.object(games, "GAMES", flags):
                for t in texts:
                    shown = app.legal_text(t)
                    self.assertNotIn("{", shown)
                    self.assertEqual("Disney Lorcana" in shown, ready)
                    self.assertIn("Yu-Gi-Oh!", shown)

    def test_publisher_wording(self):
        text = {k: t for k, _, t in app.GAME_LEGAL}
        riot = ("Bent°Corner was created under Riot Games' \"Legal Jibber Jabber\" policy using assets owned by Riot "
                "Games. Riot Games does not endorse or sponsor this project.")
        self.assertIn(riot, text["riftbound"])
        self.assertIn(riot, de.TEXTS[text["riftbound"]])   # verbatim in German mode too
        self.assertIn("expressly prohibited from charging you", de.TEXTS[text["lorcana"]])


if __name__ == "__main__":
    unittest.main()
