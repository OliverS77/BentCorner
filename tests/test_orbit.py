"""Bent°Corner Orbit (system/orbit.py): the level from today's settings, what Core switches off, and that nobody is
moved up to Full Orbit silently – no UI, no network.

    python -m unittest tests/test_orbit.py
"""
import unittest
from unittest import mock

from net import relay
from system import orbit


class Ctrl:
    """Stand-in for the main window: settings and the exchange switch."""

    def __init__(self, settings):
        self.settings, self.toggled = settings, []

    def relay_toggle(self, on):
        self.toggled.append(on)
        relay.state(self.settings)["on"] = bool(on)

    def settings_changed(self):
        pass


class Level(unittest.TestCase):
    def test_derived_for_users_from_before(self):
        self.assertEqual(orbit.level({"price_update": "start"}), "near")
        self.assertEqual(orbit.level({"price_update": "manual"}), "core")
        s = {"price_update": "manual"}
        relay.state(s)["on"] = True
        self.assertEqual(orbit.level(s), "full")   # exchange on = Full Orbit, whatever the prices say

    def test_exchange_off_elsewhere_falls_back(self):
        s = {"orbit": "near"}
        relay.state(s)["on"] = True
        self.assertEqual(orbit.level(s), "full")
        relay.state(s)["on"] = False
        self.assertEqual(orbit.level(s), "near")

    def test_core_fetches_no_prices(self):
        s = {"orbit": "core", "price_update": "daily"}
        self.assertFalse(orbit.prices_on(s))
        self.assertEqual(orbit.price_mode(s), "manual")
        s["orbit"] = "near"
        self.assertEqual(orbit.price_mode(s), "daily")   # Near keeps the user's own price setting


class SetLevel(unittest.TestCase):
    def test_up_to_full_turns_the_exchange_on(self):
        c = Ctrl({"price_update": "start"})
        self.assertFalse(orbit.set_level(c, "full"))   # 0.9.7.26: not without the age confirmation (legal 03.11.)
        orbit.confirm_age(c.settings)
        self.assertTrue(orbit.set_level(c, "full"))
        self.assertEqual(c.toggled, [True])
        self.assertEqual(orbit.level(c.settings), "full")
        self.assertTrue(orbit.asked(c.settings))

    def test_down_from_full_never_opens_a_sheet(self):
        # the consequence stands under the slider – a sheet from the slider's release covered the Orbit sheet
        c = Ctrl({})
        relay.state(c.settings)["on"] = True
        from ui import qdialogs
        with mock.patch.object(qdialogs, "question") as q, mock.patch.object(qdialogs, "ask") as a:
            self.assertTrue(orbit.set_level(c, "core"))
        q.assert_not_called(), a.assert_not_called()
        self.assertEqual(c.toggled, [False])
        self.assertEqual(orbit.level(c.settings), "core")

    def test_leaving_only_below_full_while_on(self):
        s = {"orbit": "near"}
        self.assertFalse(orbit.leaving(s, "core"))      # not in Full Orbit: nothing to leave
        relay.state(s)["on"] = True
        self.assertTrue(orbit.leaving(s, "near"))
        self.assertTrue(orbit.leaving(s, "core"))
        self.assertFalse(orbit.leaving(s, "full"))

    def test_between_core_and_near_leaves_the_exchange_alone(self):
        c = Ctrl({})
        orbit.set_level(c, "core")
        orbit.set_level(c, "near")
        self.assertEqual(c.toggled, [])
        self.assertEqual(orbit.level(c.settings), "near")

    def test_never_moved_up_silently(self):
        # every way to Full Orbit goes through set_level("full") – deriving a level never switches anything on
        s = {"price_update": "start"}
        for _ in range(3):
            orbit.level(s), orbit.index(s), orbit.describe(s)
        self.assertFalse(relay.enabled(s))

    def test_unknown_level_refused(self):
        self.assertFalse(orbit.set_level(Ctrl({}), "moon"))


if __name__ == "__main__":
    unittest.main()
