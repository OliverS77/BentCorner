"""Sessions: packs, stake and balance add up to the counted cards' values – also after foil switches, undo, a pack
merged into the previous one and for single purchases (no packs, no average per pack).

    python -m unittest tests/test_session_sums.py
"""
import itertools
import unittest

from scanner import core

_n = itertools.count(1)


def card(name, eur, eur_foil=None, rarity="common"):
    i = next(_n)
    return {"id": f"t{i}", "name": name, "set": "TST", "number": str(i), "rarity": rarity, "eur": eur,
            "eur_foil": eur_foil, "img": f"data/card-images/tst/{i}_0.jpg", "finishes": ["nonfoil", "foil"],
            "booster": True}


def session(*packs, paid=0.0, kind="packs"):
    """packs: lists of (card, foil) – each list one pack (opening boosters unless kind says otherwise)."""
    s = core.Session()
    s._price_later = lambda entry: None   # no network: prices come with the card
    s.set_info(paid=paid, kind=kind)
    for i, pack in enumerate(packs):
        if i:
            s.new_pack()
        for c, foil in pack:
            s.add_manual(c, foil=foil)
    return s


class Sums(unittest.TestCase):
    def test_totals_average_best_pack_and_balance(self):
        a, b, c, d = card("A", 0.50), card("B", 12.00, 30.00, "rare"), card("C", 1.25), card("D", 4.10, rarity="mythic")
        s = session([(a, False), (b, True)], [(c, False), (d, False)], paid=20.0)
        st = s.to_dict()["stats"]
        self.assertEqual(st["packs"], 2)
        self.assertEqual(st["cards"], 4)
        self.assertEqual(st["total"], 35.85)              # 0.50 + 30.00 (foil) + 1.25 + 4.10
        self.assertEqual(st["avg_pack"], 17.93)           # 35.85 / 2, rounded
        self.assertEqual(st["best_pack"], {"number": 1, "total": 30.5})
        self.assertEqual(st["biggest_hit"]["name"], "B")
        self.assertEqual(st["counts"], {"mythic": 1, "rare": 1, "foil": 1})
        self.assertEqual(st["paid"], 20.0)
        self.assertEqual(st["profit"], 15.85)

    def test_no_stake_no_balance(self):
        st = session([(card("A", 2.0), False)]).to_dict()["stats"]
        self.assertIsNone(st["profit"])

    def test_loss_is_negative(self):
        st = session([(card("A", 2.0), False)], paid=5.0).to_dict()["stats"]
        self.assertEqual(st["profit"], -3.0)

    def test_foil_switch_reprices(self):
        b = card("B", 12.00, 30.00, "rare")
        s = session([(b, False)])
        self.assertEqual(s.to_dict()["stats"]["total"], 12.0)
        s.toggle_foil()
        self.assertEqual(s.to_dict()["stats"]["total"], 30.0)

    def test_unknown_price_counts_as_zero_and_is_no_hit(self):
        st = session([(card("A", None), False), (card("B", 1.0), False)]).to_dict()["stats"]
        self.assertEqual(st["total"], 1.0)
        self.assertEqual(st["biggest_hit"]["name"], "B")

    def test_undo_removes_the_card_from_the_sums(self):
        s = session([(card("A", 2.0), False), (card("B", 3.0), False)])
        s.undo()
        st = s.to_dict()["stats"]
        self.assertEqual((st["cards"], st["total"]), (1, 2.0))

    def test_merge_into_previous_keeps_the_sum(self):
        s = session([(card("A", 2.0), False)], [(card("B", 3.0), False)])
        before = s.to_dict()["stats"]["total"]
        s.merge_into_previous(1)
        st = s.to_dict()["stats"]
        self.assertEqual((st["packs"], st["total"]), (1, before))

    def test_singles_have_no_packs_and_no_average(self):
        s = session([(card("A", 2.0), False), (card("B", 3.0), False)], paid=4.0, kind="singles")
        s.new_pack()   # singles: everything stays in one list
        st = s.to_dict()["stats"]
        self.assertEqual((st["packs"], st["avg_pack"], st["best_pack"]), (0, 0.0, None))
        self.assertEqual((st["total"], st["profit"]), (5.0, 1.0))

    def test_scanning_cards_is_one_list_without_pack_figures(self):
        s = session([(card("A", 2.0), False), (card("B", 3.0, rarity="rare"), False)], paid=4.0, kind="cards")
        s.new_pack()   # scanning cards: everything stays in one list
        st = s.to_dict()["stats"]
        self.assertEqual(len(s.packs), 1)
        self.assertEqual((st["packs"], st["avg_pack"], st["best_pack"]), (0, 0.0, None))
        self.assertEqual((st["cards"], st["total"], st["profit"], st["biggest_hit"]["name"]), (2, 5.0, 1.0, "B"))

    def test_saved_stats_equal_recomputed(self):
        s = session([(card("A", 2.0), False)], [(card("B", 3.0, 7.0), True)], paid=1.0)
        d = s.to_dict()
        again = core.Session(data=d)
        self.assertEqual(core.session_stats(again.packs, again.info), d["stats"])


if __name__ == "__main__":
    unittest.main()


class Kinds(unittest.TestCase):
    """What a session is: new ones scan cards, saved ones without a kind stay packs, packs only when opening boosters."""

    def test_new_session_scans_cards(self):
        s = core.Session()
        self.assertEqual(s.info["kind"], "cards")
        snap = s.snapshot()
        self.assertEqual((snap["kind"], snap["packs_shown"], snap["can_cards"]), ("cards", False, True))

    def test_saved_session_without_kind_stays_packs(self):
        d = session([(card("A", 2.0), False)], [(card("B", 3.0), False)]).to_dict()
        d["info"].pop("kind")
        old = core.Session(data=d)
        self.assertEqual((core.kind_of(old.info), old.snapshot()["packs_shown"]), ("packs", True))
        self.assertEqual(core.session_stats(old.packs, old.info)["packs"], 2)
        old.add_manual(card("C", 1.0))
        old.new_pack()
        self.assertEqual(len(old.packs), 3)

    def test_to_cards_only_with_at_most_one_pack(self):
        s = session([(card("A", 2.0), False)], [(card("B", 3.0), False)])
        self.assertFalse(s.snapshot()["can_cards"])
        self.assertFalse(s.set_kind("cards"))
        self.assertEqual(s.info["kind"], "packs")
        s.merge_into_previous(1)
        self.assertTrue(s.set_kind("cards"))
        self.assertEqual(s.to_dict()["stats"]["packs"], 0)

    def test_cards_to_packs_makes_the_list_pack_one(self):
        s = session([(card("A", 2.0), False)], kind="cards")
        self.assertTrue(s.set_kind("packs"))
        s.new_pack()
        s.add_manual(card("B", 3.0))
        st = s.to_dict()["stats"]
        self.assertEqual((st["packs"], st["best_pack"]), (2, {"number": 2, "total": 3.0}))

    def test_unknown_kind_is_refused(self):
        self.assertFalse(core.Session().set_kind("box"))

    def test_cards_view_newest_first_with_pack_and_place(self):
        a, b, c = card("A", 1.0), card("B", 2.0), card("C", 3.0)
        s = session([(a, False), (b, False)], [(c, False)])
        self.assertEqual([(e["name"], e["pack"], e["idx"]) for e in s.cards_view()], [("C", 2, 0), ("B", 1, 1), ("A", 1, 0)])


class StatsMembership(unittest.TestCase):
    """Which saved sessions count where: value figures for cards + packs, pack figures only for packs."""

    def test_counts(self):
        from collection import sessions
        d = lambda **info: {"info": info}
        rows = {"cards": d(kind="cards"), "packs": d(kind="packs"), "old": d(), "singles": d(kind="singles"),
                "import": d(kind="packs", **{"import": True})}
        self.assertEqual({k for k, v in rows.items() if sessions.counts_in_stats(v)}, {"cards", "packs", "old"})
        self.assertEqual({k for k, v in rows.items() if sessions.counts_for_packs(v)}, {"packs", "old"})
