"""Test page: exact opening-hand chances (hypergeometric) against known values, cards seen per turn by the games'
rules, and the solo table's dealing (Pokémon prizes).

    python -m unittest tests/test_playtest_chances.py
"""
import random
import unittest

from collection import playtest
from games import lorcana, mtg, pokemon, yugioh

# (deck, copies, cards seen) -> chance of at least one – computed independently (product of the misses, fractions)
KNOWN = {
    (60, 4, 7): 0.3995,     # the classic "4-of in a 60-card opening hand"
    (40, 4, 7): 0.5522,
    (60, 1, 7): 0.1167,     # = 7/60
    (60, 12, 7): 0.8094,    # 12 Basic Pokémon
    (50, 4, 5): 0.3530,     # 4-of, 50 cards, 5 in hand
    (60, 4, 8): 0.4448,
    (40, 3, 5): 0.3376,     # Yu-Gi-Oh!: 3-of, 40 cards, 5 in hand
    (60, 4, 9): 0.4875,
}


class Chances(unittest.TestCase):
    def test_known_values_to_four_places(self):
        for (n, k, seen), p in KNOWN.items():
            with self.subTest(deck=n, copies=k, seen=seen):
                self.assertAlmostEqual(playtest.p_at_least(n, k, seen), p, places=4)

    def test_at_least_two(self):
        self.assertAlmostEqual(playtest.p_at_least(60, 4, 7, k=2), 0.0632, places=4)

    def test_edges(self):
        self.assertEqual(playtest.p_at_least(60, 0, 7), 0.0)
        self.assertEqual(playtest.p_at_least(60, 60, 7), 1.0)
        self.assertEqual(playtest.p_at_least(10, 4, 20), 1.0)   # more cards seen than in the deck
        self.assertEqual(playtest.p_at_least(60, 4, 7, k=0), 1.0)

    def test_cards_seen_by_turn_per_game(self):
        # opening hand + one draw per turn; Pokémon draws on its first turn, the others don't
        self.assertEqual([playtest.seen_by_turn(mtg.GAME.playtest, t) for t in (1, 2, 3)], [7, 8, 9])
        self.assertEqual([playtest.seen_by_turn(pokemon.GAME.playtest, t) for t in (1, 2, 3)], [8, 9, 10])
        self.assertEqual([playtest.seen_by_turn(yugioh.GAME.playtest, t) for t in (1, 2, 3)], [5, 6, 7])
        self.assertEqual([playtest.seen_by_turn(lorcana.GAME.playtest, t) for t in (1, 2, 3)], [7, 8, 9])

    def test_chances_row(self):
        row = playtest.chances(60, 4, mtg.GAME.playtest, (2, 3))
        for got, want in zip(row, (0.3995, 0.4448, 0.4875)):
            self.assertAlmostEqual(got, want, places=4)

    def test_group_stats_skips_empty_groups(self):
        cards = [{"t": "a"}] * 4 + [{"t": "b"}] * 56
        out = playtest.group_stats(cards, mtg.GAME.playtest, [("A", lambda r: r["t"] == "a"),
                                                              ("C", lambda r: r["t"] == "c")])
        self.assertEqual([x["name"] for x in out], ["A"])
        self.assertEqual(out[0]["count"], 4)
        self.assertAlmostEqual(out[0]["p"][0], 0.3995, places=4)


def library(n, prefix="c"):
    return [{"id": f"{prefix}{i}", "name": f"{prefix}{i}"} for i in range(n)]


class Table(unittest.TestCase):
    def test_pokemon_prizes_and_first_draw(self):
        g = playtest.Goldfish(library(60), pokemon.GAME.playtest, rng=random.Random(1))
        self.assertEqual(len(g.prizes), 6)
        self.assertEqual(len(g.hand), 8)   # 7 + draw on the first turn
        self.assertEqual(len(g.library), 60 - 6 - 8)

    def test_cards_are_neither_lost_nor_doubled(self):
        for game in (mtg.GAME, pokemon.GAME, yugioh.GAME, lorcana.GAME):
            with self.subTest(game=game.key):
                g = playtest.Goldfish(library(60), game.playtest, rng=random.Random(3))
                g.mulligan()
                g.next_turn()
                zones = g.library + g.hand + g.play + g.discard + g.prizes + g.inkwell + list(g.aside)
                self.assertEqual(sorted(c["id"] for c in zones), sorted(c["id"] for c in library(60)))


class DeckInfoChances(unittest.TestCase):
    """Deck info → Chances (ui/qtesting.chance_items): singleton decks show only the rows that say something."""

    class Ui:   # records what the form would show
        def __getattr__(self, name):
            return lambda *a, **k: (name, a)

    def _single_rows(self, cards):
        from unittest import mock
        from ui import qtesting
        lib = [{"id": f"{n}{i}", "name": n, "type_line": "Land" if n == "Forest" else "Creature", "oracle_text": ""}
               for n, k in cards for i in range(k)]
        qtesting._CHANCES.clear()
        with mock.patch.object(qtesting, "library", return_value=(lib, [])):
            items = qtesting.chance_items(self.Ui(), {"id": "d", "cards": [{"sid": n, "count": k} for n, k in cards]})
        qtesting._CHANCES.clear()
        tables = [x for x in items if x and x[0] == "table"]
        return [row[0] for row in tables[-1][1][1]]

    def test_commander_one_row_for_all_single_cards(self):
        rows = self._single_rows([("Forest", 30)] + [(f"Card {i}", 1) for i in range(70)])
        self.assertEqual(rows[0], "Forest")
        self.assertEqual(len(rows), 2)
        self.assertIn("(70)", rows[1])

    def test_sixty_cards_every_card(self):
        rows = self._single_rows([("Forest", 24)] + [(f"Card {i}", 4) for i in range(9)])
        self.assertEqual(len(rows), 10)


if __name__ == "__main__":
    unittest.main()
