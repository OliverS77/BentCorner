"""Deck rules with example decks per game: legal decks give no warning, each kind of violation gives exactly its own.
Magic through decks.analyze (Commander, 60-card formats), Pokémon and Yu-Gi-Oh! through decks.rule_warnings with the
game's deck_rules (Lorcana: at least 60, 4 per full name, at most 2 inks, Core/Infinity by name, card limits).

    python -m unittest tests/test_deck_rules.py
"""
import itertools
import json
import unittest
from unittest import mock

from collection import decks
from games import lorcana, mtg, pokemon, yugioh

_ids = itertools.count(1)


def card(name, type_line, legal=(), **kw):
    """A card database row as decks expects it (legalities: JSON of the legal formats only, like carddb)."""
    return dict({"id": f"c{next(_ids)}", "name": name, "type_line": type_line, "oracle_text": "", "cmc": 0,
                 "mana_cost": "", "keywords": "", "color_identity": "", "colors": "",
                 "legalities": json.dumps({f: "legal" for f in legal}) if not isinstance(legal, dict)
                 else json.dumps(legal)}, **kw)


def deck(fmt, entries, commanders=()):
    """entries: [(row, count[, board])] -> (deck, rows)."""
    rows = {r["id"]: r for r, *_ in entries}
    rows.update({r["id"]: r for r in commanders})
    cards = [{"sid": r["id"], "count": n, "board": rest[0] if rest else "main"} for r, n, *rest in entries]
    return {"format": fmt, "commanders": [r["id"] for r in commanders], "cards": cards}, rows


# ---------- Magic ----------
CMD = ("commander",)
STD = ("standard", "pioneer", "modern", "legacy", "vintage", "commander")


def basic(name="Forest"):
    return card(name, "Basic Land — " + name, STD)


def spell(name, ident="G", legal=STD, **kw):
    return card(name, "Instant", legal, color_identity=ident, **kw)


class MagicRules(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(decks, "_G", mtg.GAME)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def warn(self, d, rows):
        return decks.analyze(d, rows)["warnings"]

    def commander_deck(self, n_spells=60, extra=()):
        cmd = card("Omnath, Locus of Mana", "Legendary Creature — Elemental", CMD, color_identity="G")
        entries = [(spell(f"Green Spell {i}"), 1) for i in range(n_spells)] + [(basic(), 99 - n_spells)]
        return deck("commander", entries + list(extra), commanders=[cmd])

    def test_commander_legal(self):
        self.assertEqual(self.warn(*self.commander_deck()), [])

    def test_commander_size(self):
        d, rows = self.commander_deck()
        d["cards"][-1]["count"] -= 1   # 98 basics + commander = 99 … one short
        self.assertIn("99 of 100 cards", self.warn(d, rows))

    def test_commander_singleton_and_exceptions(self):
        d, rows = self.commander_deck(n_spells=58, extra=[(spell("Llanowar Elves"), 2)])
        w = self.warn(d, rows)
        self.assertIn("Llanowar Elves appears 2× (Commander: each card only once)", w)
        self.assertFalse(any("Forest" in x for x in w))   # basic lands: any number
        rats = spell("Relentless Rats", "B", oracle_text="A deck can have any number of cards named Relentless Rats.")
        d, rows = self.commander_deck(n_spells=58, extra=[(rats, 2)])
        self.assertFalse(any("Relentless Rats appears" in x for x in self.warn(d, rows)))

    def test_commander_color_identity(self):
        d, rows = self.commander_deck(n_spells=59, extra=[(spell("Lightning Bolt", "R"), 1)])
        self.assertIn("Lightning Bolt doesn't match the color identity", self.warn(d, rows))

    def test_commander_must_be_legendary_and_legal(self):
        d, rows = self.commander_deck()
        bad = card("Grizzly Bears", "Creature — Bear", ("standard",), color_identity="G")
        rows[bad["id"]] = bad
        d["commanders"] = [bad["id"]]
        w = self.warn(d, rows)
        self.assertIn("Grizzly Bears is not a legendary creature", w)
        self.assertIn("Grizzly Bears is not legal in Commander", w)
        d["commanders"] = []
        self.assertTrue(any(x.startswith("No commander chosen yet") for x in self.warn(d, rows)))

    def test_standard_legal_and_violations(self):
        entries = [(spell(f"Spell {i}"), 4) for i in range(10)] + [(basic(), 20)]
        d, rows = deck("standard", entries)
        self.assertEqual(self.warn(d, rows), [])
        d["cards"][0]["count"] = 5
        self.assertIn("Spell 0 appears 5× (at most 4)", self.warn(d, rows))
        d["cards"][0]["count"] = 3   # 59 in the main deck
        self.assertIn("59 of at least 60 cards", self.warn(d, rows))

    def test_standard_illegal_card_and_sideboard_not_counted(self):
        old = spell("Black Lotus", "", legal=("vintage",))
        entries = [(spell(f"Spell {i}"), 4) for i in range(10)] + [(basic(), 19), (old, 1), (spell("Side"), 15, "side")]
        d, rows = deck("standard", entries)
        w = self.warn(d, rows)
        self.assertIn("Black Lotus is not legal in Standard", w)
        self.assertFalse(any("cards" in x and "of at least" in x for x in w))   # 60 main, sideboard ignored
        self.assertEqual(decks.analyze(d, rows)["count"], 60)


# ---------- Pokémon ----------
STD_PK = ("standard", "expanded")
PK = pokemon.GAME


def pk_basic(name, legal=STD_PK, **kw):
    return card(name, "Pokémon — Basic", legal, **kw)


def pk_trainer(name, legal=STD_PK, **kw):
    return card(name, "Trainer — Item", legal, **kw)


def energy(name="Basic Lightning Energy"):
    return card(name, "Energy — Normal", STD_PK)


class PokemonRules(unittest.TestCase):
    def warn(self, d, rows, legal_names=None):
        names = legal_names if legal_names is not None else {r["name"] for r in rows.values()
                                                            if '"' + d["format"] + '"' in r["legalities"]}
        with mock.patch.object(PK, "deck_legal_names", lambda n, fmt: set(names) & set(n)):
            return decks.rule_warnings(d, rows, PK.deck_rules[d["format"]], PK)

    def legal_60(self):
        return [(pk_basic("Pikachu ex"), 4), (pk_basic("Raichu"), 4)] + \
               [(pk_trainer(f"Trainer {i}"), 4) for i in range(8)] + [(energy(), 20)]

    def test_legal(self):
        self.assertEqual(self.warn(*deck("standard", self.legal_60())), [])

    def test_exact_60(self):
        e = self.legal_60()
        e[-1] = (e[-1][0], 19)
        self.assertIn("59 of 60 cards", self.warn(*deck("standard", e)))
        e[-1] = (e[-1][0], 21)
        self.assertIn("61 of 60 cards", self.warn(*deck("standard", e)))

    def test_copies_and_basic_energy_unlimited(self):
        e = self.legal_60()
        e[0] = (e[0][0], 5)
        e[-1] = (e[-1][0], 19)
        w = self.warn(*deck("standard", e))
        self.assertIn("Pikachu ex appears 5× (at most 4)", w)
        self.assertFalse(any("Energy" in x for x in w))
        old = card("Lightning Energy", "Energy", STD_PK)   # old print without "— Normal": recognized by name
        self.assertTrue(PK.deck_unlimited(old))
        special = card("Double Turbo Energy", "Energy — Special", STD_PK)
        self.assertFalse(PK.deck_unlimited(special))

    def test_ace_spec_and_radiant(self):
        e = self.legal_60()[:-1] + [(energy(), 18), (pk_trainer("Prime Catcher", keywords="ACE SPEC"), 1),
                                    (pk_trainer("Hero's Cape", keywords="ACE SPEC"), 1)]
        self.assertIn("2 ACE SPEC cards (at most 1 in the deck)", self.warn(*deck("standard", e)))

    def test_needs_basic_pokemon(self):
        e = [(pk_trainer(f"Trainer {i}"), 4) for i in range(10)] + [(energy(), 20)]
        self.assertIn("Kein Basis-Pokémon im Deck", self.warn(*deck("standard", e)))

    def test_legal_by_name_reprint(self):
        old = pk_trainer("Professor's Research", legal=())   # this print is old – a reprint is legal
        e = self.legal_60()[:-1] + [(energy(), 16), (old, 4)]
        d, rows = deck("standard", e)
        self.assertEqual(self.warn(d, rows, legal_names={r["name"] for r in rows.values()}), [])
        w = self.warn(d, rows, legal_names={r["name"] for r in rows.values()} - {"Professor's Research"})
        self.assertIn("Professor's Research is not legal in Standard", w)

    def test_casual_minimum_only(self):
        e = self.legal_60() + [(pk_basic("Extra"), 2)]
        self.assertEqual(self.warn(*deck("casual", e)), [])


# ---------- Yu-Gi-Oh! ----------
YG = yugioh.GAME


def monster(name, ban=None, kind="Effect"):
    legal = {"advanced": "legal"}
    if ban:
        legal[ban] = 1
    return card(name, f"Monster — {kind}", legal)


def spell_yg(name):
    return card(name, "Spell — Normal", {"advanced": "legal"})


class YugiohRules(unittest.TestCase):
    def warn(self, d, rows):
        return decks.rule_warnings(d, rows, YG.deck_rules[d["format"]], YG)

    def main40(self):
        return [(monster(f"Monster {i}"), 3) for i in range(8)] + [(spell_yg(f"Spell {i}"), 2) for i in range(8)]

    def test_legal(self):
        e = self.main40() + [(monster("Fusion Boss", kind="Fusion"), 3), (spell_yg("Side Card"), 3, "side")]
        self.assertEqual(self.warn(*deck("advanced", e)), [])

    def test_main_size(self):
        e = self.main40()
        e[-1] = (e[-1][0], 1)
        self.assertIn("Main Deck: 39 cards (allowed: 40–60)", self.warn(*deck("advanced", e)))
        e = self.main40() + [(spell_yg(f"More {i}"), 3) for i in range(7)]
        self.assertIn("Main Deck: 61 cards (allowed: 40–60)", self.warn(*deck("advanced", e)))

    def test_extra_counted_from_main_board_and_side_max(self):
        extra = [(monster(f"Link {i}", kind="Link"), 2) for i in range(8)]   # 16 on the main board = Extra Deck
        side = [(spell_yg(f"Side {i}"), 2, "side") for i in range(8)]
        w = self.warn(*deck("advanced", self.main40() + extra + side))
        self.assertIn("Extra Deck: 16 cards (at most 15)", w)
        self.assertIn("Side Deck: 16 cards (at most 15)", w)
        self.assertFalse(any(x.startswith("Main Deck") for x in w))

    def test_three_copies_across_main_and_side(self):
        e = self.main40()
        e[0] = (e[0][0], 2)
        e.append((spell_yg("Filler"), 1))
        e.append((e[0][0], 2, "side"))
        self.assertIn("Monster 0 appears 4× (at most 3)", self.warn(*deck("advanced", e)))

    def test_banlist(self):
        e = self.main40()[:-2] + [(monster("Forbidden One", "tcg_banned"), 1), (monster("Limited One", "tcg_limited"), 2),
                                  (monster("Semi One", "tcg_semi"), 2), (spell_yg("Filler"), 1)]
        d, rows = deck("advanced", e)
        w = self.warn(d, rows)
        self.assertIn("Forbidden One is forbidden", w)
        self.assertIn("Limited One appears 2× (banlist: at most 1)", w)
        self.assertFalse(any("Semi One" in x for x in w))   # semi-limited: 2 allowed
        d["format"] = "casual"   # no banlist in casual
        self.assertFalse(any("forbidden" in x or "banlist" in x for x in self.warn(d, rows)))



# ---------- Lorcana ----------
LO = lorcana.GAME
CORE_LO = ("core", "infinity")


def lo(name, ink="A", legal=CORE_LO, type_line="Character — Storyborn · Hero"):
    return card(name, type_line, legal, colors=ink)


class LorcanaRules(unittest.TestCase):
    LIMITS = {"Dalmatian Puppy - Tail Wagger": 99, "The Glass Slipper": 2, "Microbots": None}

    def warn(self, d, rows):
        names = {r["name"] for r in rows.values() if '"' + (d["format"] or "") + '"' in r["legalities"]}
        with mock.patch.object(lorcana.Lorcana, "_limits", self.LIMITS), \
                mock.patch.object(LO, "deck_legal_names", lambda n, fmt: names & set(n)):
            return decks.rule_warnings(d, rows, LO.deck_rules[d["format"]], LO)

    def legal_60(self):   # Amber/Steel, 15 × 4
        return [(lo(f"Amber {i}", "A"), 4) for i in range(8)] + [(lo(f"Steel {i}", "T"), 4) for i in range(7)]

    def test_legal(self):
        self.assertEqual(self.warn(*deck("core", self.legal_60())), [])
        self.assertEqual(self.warn(*deck("core", self.legal_60() + [(lo("Amber 99"), 4)])), [])   # more than 60 is fine

    def test_at_least_60(self):
        e = self.legal_60()
        e[-1] = (e[-1][0], 3)
        self.assertIn("59 of at least 60 cards", self.warn(*deck("core", e)))

    def test_four_per_full_name_across_prints(self):
        e = self.legal_60()
        hades = lo("Hades - King of Olympus")
        e += [(hades, 3), (dict(hades, id="enchanted-hades"), 2)]   # base print + Enchanted: one full name
        self.assertIn("Hades - King of Olympus appears 5× (at most 4)", self.warn(*deck("core", e)))

    def test_at_most_two_inks_dual_ink_counts_both(self):
        e = self.legal_60()
        e[0] = (lo("Ruby One", "R"), 4)
        self.assertIn("3 inks in the deck (at most 2)", self.warn(*deck("core", e)))
        e = self.legal_60()
        e[0] = (lo("Amber-Ruby Card", "AR"), 4)   # dual ink brings its second ink
        self.assertIn("3 inks in the deck (at most 2)", self.warn(*deck("core", e)))

    def test_card_limits(self):
        e = self.legal_60() + [(lo("Dalmatian Puppy - Tail Wagger"), 20), (lo("The Glass Slipper", "T"), 3),
                               (lo("Microbots", "T"), 12)]
        w = self.warn(*deck("core", e))
        self.assertIn("The Glass Slipper appears 3× (at most 2)", w)
        self.assertFalse(any("Dalmatian" in x or "Microbots" in x for x in w), w)

    def test_core_and_infinity_legality(self):
        e = self.legal_60()[:-1] + [(lo("Rotated Card", "T", ("infinity",)), 4)]
        self.assertIn("Rotated Card is not legal in Core", self.warn(*deck("core", e)))
        self.assertEqual(self.warn(*deck("infinity", e)), [])
        e[-1] = (lo("Banned Everywhere", "T", ()), 4)
        self.assertIn("Banned Everywhere is not legal in Infinity", self.warn(*deck("infinity", e)))
        self.assertEqual(self.warn(*deck("casual", e)), [])   # casual: no legality, but size and inks still count


# ---------- Magic: the simple formats Constructed (60) and Limited (40) – no legality list ----------
class MagicSimpleFormats(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(decks, "_G", mtg.GAME)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def warn(self, d, rows):
        return decks.analyze(d, rows)["warnings"]

    def test_limited_40_and_constructed_60_minimum(self):
        old = spell("Ancient Card", legal=())   # legal nowhere – doesn't matter here
        for fmt, least in (("limited", 40), ("constructed", 60)):
            with self.subTest(fmt=fmt):
                ok = [(old, 4), (basic(), least - 4)]
                self.assertEqual(self.warn(*deck(fmt, ok)), [])
                short = [(old, 4), (basic(), least - 5)]
                self.assertIn(f"{least - 1} of at least {least} cards", self.warn(*deck(fmt, short)))

    def test_four_copies_basic_lands_free(self):
        w = self.warn(*deck("limited", [(spell("Bolt", legal=()), 5), (basic(), 35)]))
        self.assertEqual(w, ["Bolt appears 5× (at most 4)"])


if __name__ == "__main__":
    unittest.main()
