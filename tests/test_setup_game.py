"""The game in the setup (scanner/library 13.11.2026): when the download finishes WHILE playing, the page keeps its
structure (qform rebuilds only on a new structure – a rebuild would start the game anew); the game gets done=True as a
value and on_go („Let's go“) – the finish page ends the setup, the play view goes back to the step.

    python -m unittest tests/test_setup_game.py
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui import onboarding, qform  # noqa: E402


def ob(step, loading):
    o = onboarding.Onboarding.__new__(onboarding.Onboarding)
    o.s = {"onboarding": step, "setup_steps": 5}
    o.st = {"name": "", "back": "", "more": False, "backs": False, "play": step != "finish"}
    o.ctrl = types.SimpleNamespace(setup_error="", settings_changed=lambda: None, current=None, jobs=[])
    o.dlg = types.SimpleNamespace(refresh=lambda: None)
    o.had_download = True
    o._loading = lambda: loading
    o._progress = lambda: (0.42, "")
    o._what = lambda: "Card data"
    o.finished = []
    o.finish = lambda: o.finished.append(1)
    return o


def build(o):
    form = types.SimpleNamespace(_cb={}, _keys={})
    ui = qform.UI(form)
    tree = o.build(ui, None)
    vals = {}
    return qform._split([tree], "", vals), vals, form


def game(vals):
    return next(v for v in vals.values() if v.get("t") == "game")


class SameStructureTest(unittest.TestCase):
    def test_finish_page_loading_then_done(self):
        before, v1, _ = build(ob("finish", True))
        after, v2, form = build(ob("finish", False))
        self.assertEqual(before, after)                                   # no rebuild – the game keeps running
        self.assertFalse(game(v1)["done"])
        self.assertTrue(game(v2)["done"])
        hidden = {v.get("t"): v.get("hidden") for v in v2.values() if v.get("t") == "progress"}
        self.assertTrue(hidden["progress"])                              # the bar only hidden

    def test_play_view_loading_then_done(self):
        before, _, _ = build(ob("profile", True))
        after, v2, _ = build(ob("profile", False))
        self.assertEqual(before, after)
        self.assertTrue(game(v2)["done"])

    def test_lets_go_from_the_game(self):
        o = ob("finish", False)
        _, vals, form = build(o)
        form._cb[game(vals)["id"]](["go"])
        self.assertEqual(o.finished, [1])                                # finish page: the setup ends
        p = ob("profile", False)
        _, vals, form = build(p)
        form._cb[game(vals)["id"]](["go"])
        self.assertFalse(p.st["play"])                                   # play view: back to the step


if __name__ == "__main__":
    unittest.main()
