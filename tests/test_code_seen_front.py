"""desk-codeseen (lead 14.11., after ports' web findings): a note on „Your devices“ counts as seen only when the window is
really on the screen (not minimized, not in the tray), and a code setter the device list doesn't know yet is waited
for (up to 24 h) instead of being noted silently. Stand-ins only – no window, no network.

    python -m unittest tests.test_code_seen_front
"""
import os
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui  # noqa: E402

from net import poll_ctl  # noqa: E402
from ui import qsettings, qsync  # noqa: E402


class Win:
    def __init__(self, visible=True, vis=QtGui.QWindow.Windowed):
        self.v, self.vis = visible, vis

    def isVisible(self):
        return self.v

    def visibility(self):
        return self.vis


def ctrl(win):
    return types.SimpleNamespace(shell=types.SimpleNamespace(window=win) if win is not False else None,
                                 settings_page="devices", settings={})


class InFront(unittest.TestCase):
    def test_states(self):
        self.assertTrue(qsettings.in_front(ctrl(Win())))
        self.assertTrue(qsettings.in_front(ctrl(Win(vis=QtGui.QWindow.Maximized))))
        self.assertTrue(qsettings.in_front(ctrl(Win(vis=QtGui.QWindow.FullScreen))))
        self.assertFalse(qsettings.in_front(ctrl(Win(vis=QtGui.QWindow.Minimized))))
        self.assertFalse(qsettings.in_front(ctrl(Win(visible=False, vis=QtGui.QWindow.Hidden))))   # in the tray
        self.assertTrue(qsettings.in_front(ctrl(False)))                                          # no shell (tests)

    def build(self, win, active=True):
        seen = []
        b = types.SimpleNamespace(_query="", ctrl=ctrl(win), _active=active, _flash="", _flash_page="")
        with mock.patch.object(qsettings.qsetpages, "build", lambda page, ui, host: {"kind": "col"}), \
                mock.patch.object(qsettings, "_flatten", lambda node: None), \
                mock.patch.object(qsync, "join_request_seen", lambda c: seen.append("join")), \
                mock.patch.object(qsync, "code_set_seen", lambda c, host: seen.append("code")):
            qsettings.SettingsBackend._build(b, None)
        return seen

    def test_minimized_or_tray_notes_nothing(self):
        self.assertEqual(self.build(Win(vis=QtGui.QWindow.Minimized)), [])
        self.assertEqual(self.build(Win(visible=False, vis=QtGui.QWindow.Hidden)), [])
        self.assertEqual(self.build(Win(), active=False), [])                  # another page in front
        self.assertEqual(self.build(Win()), ["join", "code"])                   # really seen


LIST = [{"dev": "me", "me": True, "rid": "R-ME", "n": 1},
        {"dev": "pc2", "me": False, "rid": "R-PC2", "name": "Wohnzimmer-PC", "n": 2}]
NEW = {"dev": "lap", "me": False, "rid": "R-NEW", "name": "Laptop", "n": 3}


def _ctl(devices):
    c = mock.Mock()
    c.settings = {"sync_code_seen": 0}
    c.sync_status = {}
    c.sync_devices = lambda: devices
    c._my_rid = lambda: "R-ME"
    return c


def run(c, guard):
    cls = next(v for v in vars(poll_ctl).values() if isinstance(v, type) and hasattr(v, "_code_set_check"))
    cls._code_set_check(c, guard)


class UnknownSetter(unittest.TestCase):
    def test_waits_then_shows_once_the_list_knows_it(self):
        devices = list(LIST)
        c = _ctl(devices)
        g = {"set": True, "t": int(time.time()), "by": "R-NEW"}               # just joined, set the first code
        run(c, g)
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], 0)                       # nothing noted – asks again
        devices.append(NEW)                                                     # next poll: the device sync came
        run(c, g)
        self.assertEqual(c.sync_status["guard_set_by"], {"name": "Laptop", "n": 3, "key": g["t"]})

    def test_after_24_hours_taken_over_silently(self):
        c = _ctl(list(LIST))
        t = int(time.time()) - poll_ctl.CODE_SET_WAIT - 60
        run(c, {"set": True, "t": t, "by": "R-NEW"})
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], t)

    def test_a_shown_line_whose_device_left_is_cleared(self):
        devices = list(LIST) + [NEW]
        c = _ctl(devices)
        g = {"set": True, "t": int(time.time()), "by": "R-NEW"}
        run(c, g)
        self.assertIn("guard_set_by", c.sync_status)
        devices.remove(NEW)                                                     # removed before anyone looked
        run(c, g)
        self.assertNotIn("guard_set_by", c.sync_status)                         # no pulse forever
        self.assertEqual(c.settings["sync_code_seen"], g["t"])


if __name__ == "__main__":
    unittest.main()
