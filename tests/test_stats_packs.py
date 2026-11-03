"""Stats: pack figures (Ø per pack, hit rate, pack values, pack types, pack by pack, best pack) only from sessions
that open boosters (sessions.counts_for_packs) – scanning cards adds to value, cards and hits, never to the packs.
Without any booster session the pack parts are hidden instead of showing "0 packs".

    python -m unittest tests/test_stats_packs.py
"""
import itertools
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scanner import core  # noqa: E402

_n = itertools.count(1)


def card(name, eur, rarity="common"):
    i = next(_n)
    return {"id": f"t{i}", "name": name, "set": "TST", "number": str(i), "rarity": rarity, "eur": eur,
            "eur_foil": None, "img": f"data/card-images/tst/{i}_0.jpg", "finishes": ["nonfoil"], "booster": True}


def session(*packs, kind="packs", started=0.0, pack_type=None):
    """packs: lists of prices – each list one pack -> saved session dict (Session.to_dict)."""
    s = core.Session()
    s._price_later = lambda entry: None   # no network: prices come with the card
    s.set_info(kind=kind, **({"pack_type": pack_type} if pack_type else {}))
    for i, prices in enumerate(packs):
        if i:
            s.new_pack()
        for eur in prices:
            s.add_manual(card(f"C{next(_n)}", eur))
    d = s.to_dict()
    d["id"], d["started"] = f"s{next(_n)}", started
    if pack_type:
        for pk in d["packs"]:
            pk["type"] = pack_type
    return d


def page(all_sessions):
    from ui import statsview
    sp = statsview.StatsPage(settings={"hit": 10})
    sp.set_sessions(all_sessions)
    return sp


class StatsPagePacks(unittest.TestCase):
    def setUp(self):
        # a scanning-cards session with one expensive list and a booster session with two packs
        self.cards = session([50.0, 30.0, 20.0], kind="cards", started=1.0)
        self.packs = session([1.0, 3.0], [2.0, 14.0], kind="packs", started=2.0)

    def test_pack_figures_only_from_the_booster_session(self):
        sp = page([self.cards, self.packs])
        self.assertTrue(sp.has_packs)
        self.assertTrue(sp.packs_on)
        self.assertAlmostEqual(sp.s_kpis.items[0][1], 10.0)   # Ø per pack: (1 + 3 + 2 + 14) / 2 – not 120 / 2
        self.assertAlmostEqual(sp.s_kpis.items[1][1], 50.0)   # hit rate: 1 of 2 packs has a 10 €+ card
        self.assertAlmostEqual(sp._overall_avg, 10.0)
        self.assertEqual(sum(sp.s_hist.bins), 2)        # pack values: the two packs, not the card list
        self.assertEqual([r[1] for r in sp.s_types.rows], [10.0])   # Ø by pack type from the booster packs only
        facts = dict(sp.s_hero.facts)
        self.assertEqual(facts[sp.s_hero.facts[1][0]], "2")         # "Packs" = 2
        self.assertEqual(facts[sp.s_hero.facts[2][0]], "7")         # cards: both sessions (3 + 4)
        self.assertAlmostEqual(sp.s_hero._value, 120.0)              # value: both sessions
        self.assertIn(sp.s_packs, [x for e in sp.layout("sessions") for x in e[1:] if not isinstance(x, (int, str))])

    def test_no_booster_session_hides_the_pack_parts(self):
        sp = page([self.cards])
        self.assertFalse(sp.has_packs)
        self.assertFalse(sp.packs_on)
        shown = [x for e in sp.layout("sessions") for x in e[1:] if not isinstance(x, (int, str))]
        for c in (sp.s_packs, sp.s_types, sp.s_hist, sp.s_sets):
            self.assertNotIn(c, shown)
        self.assertEqual(len(sp.s_hero.facts), 3)         # sessions, cards, since – no "packs"
        self.assertNotIn("packs", sp.s_hero.sentence)
        self.assertAlmostEqual(sp.s_kpis.items[0][1], 100.0 / 3)  # Ø per card instead of Ø per pack
        self.assertEqual(sp.s_kpis.items[1][1], 3)        # hits: cards worth 10 €+
        self.assertFalse(sp.detail_packs)
        self.assertEqual(sp.s_packs.rows, [])

    def test_pack_type_filter_does_not_drop_scanning_sessions(self):
        cards = session([5.0, 6.0], kind="cards", started=3.0, pack_type="nope")   # type not in the default filter
        sp = page([cards, self.packs])
        self.assertIn(cards["id"], [s["id"] for s in sp.filtered])
        self.assertAlmostEqual(sp.s_hero._value, 31.0)

    def test_detail_of_a_scanning_session_has_no_pack_by_pack(self):
        sp = page([self.cards, self.packs])
        sp.pick_session(self.cards["id"])
        self.assertFalse(sp.detail_packs)
        self.assertEqual(sp.s_packs.rows, [])
        self.assertEqual(sp.layout("sessions")[-1], ("full", sp.s_one_pulls))
        sp.pick_session(self.packs["id"])
        self.assertTrue(sp.detail_packs)
        self.assertEqual(len(sp.s_packs.rows), 2)
        self.assertAlmostEqual(sp.s_one_kpis.items[1][1], 10.0)   # Ø per pack of the booster session

    def test_saved_session_without_kind_counts_as_packs(self):
        old = session([4.0], [6.0], kind="packs", started=4.0)
        old["info"].pop("kind")
        sp = page([old])
        self.assertTrue(sp.packs_on)
        self.assertAlmostEqual(sp.s_kpis.items[0][1], 5.0)


class _Ctrl:
    def __init__(self, sess):
        self.session, self.settings = sess, {"hit": 10}

    def save_session(self):
        pass


class ScanStatsPanel(unittest.TestCase):
    def _panel(self, current_kind, saved):
        from ui import panels
        s = core.Session()
        s._price_later = lambda entry: None
        s.set_info(kind=current_kind)
        s.add_manual(card("X", 2.0))
        s.add_manual(card("Y", 4.0))
        p = panels.StatsPanel(_Ctrl(s), None)
        with mock.patch.object(panels.sessions, "load_all", return_value=saved), \
                mock.patch.object(panels.qstate, "_changed", lambda: None):
            p.refresh()
        return p

    def test_scanning_cards_shows_no_pack_tiles(self):
        p = self._panel("cards", [session([50.0, 30.0], kind="cards", started=1.0)])
        titles = [t for t, _, _ in p.s_tiles.data["items"]]
        self.assertEqual(len(titles), 4)                 # value, spent, balance, cards
        self.assertNotIn(p.s_packs, p.layout())
        p.tab = 1
        self.assertEqual(len(p.g_tiles.data["items"]), 4)   # sessions, total, spent, balance
        self.assertNotIn((p.g_avg, p.g_sets), p.layout())

    def test_total_pack_figures_only_from_booster_sessions(self):
        saved = [session([50.0, 30.0], kind="cards", started=1.0), session([1.0, 3.0], [2.0, 14.0], started=2.0)]
        p = self._panel("packs", saved)
        self.assertEqual(len(p.s_tiles.data["items"]), 6)
        self.assertIn(p.s_packs, p.layout())
        items = p.g_tiles.data["items"]
        self.assertEqual(items[1][1], "2")               # packs: only the booster session
        self.assertEqual(items[-1][1], core_eur(10.0))   # Ø per pack: 20 € / 2 packs
        self.assertEqual(p.g_avg.data["values"], [10.0])
        p.tab = 1
        self.assertIn((p.g_avg, p.g_sets), p.layout())


def core_eur(v):
    from ui.scanlook import eur
    return eur(v)


class ShareCard(unittest.TestCase):
    def _texts(self, d):
        from PySide6 import QtGui
        from collection import share
        app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
        self.assertIsNotNone(app)
        seen = []

        class Rec(QtGui.QPainter):
            def drawText(self, *a):
                seen.extend(x for x in a if isinstance(x, str))
                return super().drawText(*a)
        with mock.patch.object(QtGui, "QPainter", Rec):
            share.render(d, {})
        return seen

    def test_pack_kpis_only_when_opening_boosters(self):
        from system.i18n import tr
        cards = self._texts(session([5.0, 6.0], kind="cards"))
        packs = self._texts(session([1.0], [3.0], kind="packs"))
        for label in (tr("Packs"), tr("Ø per pack")):
            self.assertNotIn(label.upper(), cards)
            self.assertIn(label.upper(), packs)
        self.assertIn(tr("Cards").upper(), cards)


if __name__ == "__main__":
    unittest.main()
