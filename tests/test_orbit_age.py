"""0.9.7.26 – Full Orbit and age (legal 2026-11-03-minderjaehrige-wortlaut.md, Oliver's OK): without the one-time
confirmation Full Orbit stays off; only "confirmed" is stored locally (settings["orbit_age"] = {ok, t}, the same key as
the web); who is already on Full Orbit keeps running until they confirm once."""
import types
import unittest
from unittest import mock

from system import i18n, orbit


def ctrl(settings):
    c = types.SimpleNamespace(settings=settings, toggled=[], changed=0)
    c.relay_toggle = lambda on: c.toggled.append(on)
    c.settings_changed = lambda: setattr(c, "changed", c.changed + 1)
    return c


class OrbitAge(unittest.TestCase):
    def test_full_needs_the_confirmation(self):
        s = {"orbit": "near"}
        c = ctrl(s)
        with mock.patch("net.relay.enabled", lambda st: False):
            self.assertFalse(orbit.set_level(c, "full"))
            self.assertEqual(c.toggled, [])
            orbit.confirm_age(s, now=1762000000)
            self.assertEqual(s["orbit_age"], {"ok": True, "t": 1762000000})
            self.assertTrue(orbit.age_ok(s))
            self.assertTrue(orbit.set_level(c, "full"))
        self.assertEqual(c.toggled, [True])

    def test_already_full_keeps_running_and_can_leave(self):
        s = {"orbit": "near"}
        c = ctrl(s)
        with mock.patch("net.relay.enabled", lambda st: True):   # the exchange is on: Full Orbit from before
            self.assertEqual(orbit.level(s), "full")
            self.assertFalse(orbit.age_ok(s))
            self.assertFalse(orbit.set_level(c, "full"))        # nothing changes – it keeps running
            self.assertTrue(orbit.set_level(c, "near"))         # leaving is always possible
        self.assertEqual(c.toggled, [False])

    def test_not_ok_values(self):
        for v in (None, True, {"ok": False}, {"ok": "yes"}, {}):
            self.assertFalse(orbit.age_ok({"orbit_age": v}), v)

    def test_texts_in_german(self):
        lang = i18n.LANG
        self.addCleanup(i18n.set_language, lang)
        i18n.set_language("de")
        self.assertEqual(i18n.tr(orbit.AGE), "Ich bin mindestens 13. Bin ich unter 18, sind meine Eltern einverstanden.")
        self.assertTrue(i18n.tr(orbit.TRADE_TIP).startswith("Tipp: Tausch nur mit Leuten, die du kennst"))
        self.assertEqual(i18n.tr(orbit.AGE_NOTE), "Wir können dein Alter nicht prüfen und fragen deshalb nur dieses eine "
                                                  "Mal. Die Antwort bleibt auf deinem Gerät.")


if __name__ == "__main__":
    unittest.main()
