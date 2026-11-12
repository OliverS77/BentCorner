"""The online backup's expiry warning on the PC (legal 07.11.2026; performance' sync_status["expiry"]): legal's line
(before / after the date), the start notice twice (day 150, day 176) and once after the date, closed per stage; the
frame on „Your devices“ stays; the key: Full Orbit → sync now, else the Orbit slider. Stand-in ctrl.

    python -m unittest tests/test_expiryui.py
"""
import types
import unittest

from ui import expiryui

DAY = expiryui.DAY_MS
SEEN = 1_790_000_000_000


def ctrl(days, full=True):
    calls = []
    c = types.SimpleNamespace(sync_status={"expiry": {"seen": SEEN, "until": SEEN + 183 * DAY}}, settings={},
                              settings_changed=lambda: None, sync_orbit_ok=lambda: full,
                              sync_now=lambda manual=False: calls.append("sync"),
                              show_settings=lambda k: calls.append(k))
    c.stream = types.SimpleNamespace(show_page=lambda k, back=False: calls.append(k))
    return c, SEEN + days * DAY, calls


class ExpiryTest(unittest.TestCase):
    def test_line_and_stages(self):
        c, now, _ = ctrl(151)
        i = expiryui.info(c, now)
        self.assertEqual(i["stage"], 1)
        self.assertIn("If none of your other devices uses it either", i["text"])   # only this device is known
        self.assertEqual(expiryui.info(*ctrl(177)[:2])["stage"], 2)
        past = expiryui.info(*ctrl(184)[:2])
        self.assertEqual(past["stage"], 3)
        self.assertIn("was deleted on", past["text"])
        c.sync_status = {}
        self.assertIsNone(expiryui.info(c, now))                    # no field: no warning

    def test_start_notice_twice_then_after(self):
        c, now, _ = ctrl(151)
        self.assertTrue(expiryui.notice_due(c, now))
        expiryui.notice_closed(c, now)
        self.assertIsNone(expiryui.notice_due(c, now))              # closed: not again at the next start …
        self.assertTrue(expiryui.notice_due(c, SEEN + 177 * DAY))   # … but once more a week before
        expiryui.notice_closed(c, SEEN + 177 * DAY)
        self.assertIsNone(expiryui.notice_due(c, SEEN + 180 * DAY))
        self.assertTrue(expiryui.notice_due(c, SEEN + 184 * DAY))   # and once after the date

    def test_key(self):
        c, now, calls = ctrl(151, full=True)   # lead 07.11.: no key in Full Orbit – the app syncs at opening
        self.assertEqual(expiryui.info(c, now)["key"], "")
        c, now, calls = ctrl(151, full=False)
        self.assertEqual(expiryui.info(c, now)["key"], expiryui.TO_ORBIT)
        expiryui.act(c)
        self.assertEqual(calls, ["settings", "privacy"])

    def test_frame_on_your_devices(self):
        from tests.test_device_switch import find, page, setup
        b, _ = setup("leave")
        b.ctrl.sync_status["expiry"] = {"seen": SEEN, "until": SEEN + 183 * DAY}
        b.ctrl.sync_orbit_ok = lambda: True
        p = page(b)
        first = find(p, "group")[0]
        self.assertEqual(first[1], "Online backup")                 # its own frame, at the top
        self.assertTrue(any("hasn't used your online backup" in str(x) for x in first[2]))

    def test_german(self):
        from locales import de
        for k in (expiryui.BEFORE, expiryui.AFTER, expiryui.TO_ORBIT, expiryui.SYNC_NOW):
            self.assertIn(k, de.TEXTS)


if __name__ == "__main__":
    unittest.main()
