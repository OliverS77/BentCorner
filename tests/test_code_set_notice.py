"""„A protection code was set up on {device}“ (Oliver 13.11., confirmed by Gordon; lead: the box field "by"): the poll's
guard = {"set", "salt", "t", "by"} -> sync_status["guard_set_by"] once on the OTHER devices. Never on the setter, not on
a changed code or a move, not on a device that joined later, not for an unknown device, nothing with an older box.
Stand-in ctrl, no network.

    python -m unittest tests.test_code_set_notice
"""
import unittest
from unittest import mock

from net import poll_ctl

LIST = [{"dev": "me", "me": True, "rid": "R-ME", "n": 1},
        {"dev": "pc2", "me": False, "rid": "R-PC2", "name": "Wohnzimmer-PC", "n": 2},
        {"dev": "ph", "me": False, "rid": "R-PH", "nick": None, "n": 3}]


def _ctl(seen="absent"):
    c = mock.Mock()
    c.settings = {} if seen == "absent" else {"sync_code_seen": seen}
    c.sync_status = {}
    c.sync_devices = lambda: LIST
    c._my_rid = lambda: "R-ME"
    return c


def _cls():
    return next(v for v in vars(poll_ctl).values() if isinstance(v, type) and hasattr(v, "_code_set_check"))


def run(c, guard):
    _cls()._code_set_check(c, guard)


class CodeSetNotice(unittest.TestCase):
    def test_second_device_once_also_after_a_restart(self):
        c = _ctl()
        run(c, None)                                    # no code yet: this device knows „none“
        self.assertEqual(c.settings["sync_code_seen"], 0)
        g = {"set": True, "salt": "S", "t": 1000, "by": "R-PC2"}
        run(c, g)
        self.assertEqual(c.sync_status["guard_set_by"], {"name": "Wohnzimmer-PC", "n": 2, "key": 1000})
        c.sync_status = {}                              # a restart before the page drew it: shown again
        run(c, g)
        self.assertEqual(c.sync_status["guard_set_by"]["key"], 1000)
        _cls().code_set_seen(c, 1000)                   # drawn
        self.assertEqual(c.settings["sync_code_seen"], 1000)
        self.assertNotIn("guard_set_by", c.sync_status)
        c.sync_status = {}                              # restart after drawing: never again
        run(c, g)
        self.assertNotIn("guard_set_by", c.sync_status)

    def test_no_name_gives_the_number(self):
        c = _ctl(0)
        run(c, {"set": True, "t": 5, "by": "R-PH"})
        self.assertEqual(c.sync_status["guard_set_by"], {"name": "", "n": 3, "key": 5})

    def test_never_on_the_setter(self):
        c = _ctl(0)
        run(c, {"set": True, "t": 1000, "by": "R-ME"})
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], 1000)

    def test_no_line_on_a_changed_code(self):
        c = _ctl(1000)                                  # knew the first code
        run(c, {"set": True, "t": 2000, "by": "R-PC2"})
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], 2000)

    def test_a_move_keeps_t_nothing_new(self):
        c = _ctl(1000)
        run(c, {"set": True, "t": 1000, "by": "R-PC2"})
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], 1000)

    def test_a_later_device_takes_it_silently(self):
        c = _ctl()                                      # joined/updated: never saw anything
        run(c, {"set": True, "t": 1000, "by": "R-PC2"})
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], 1000)

    def test_unknown_device_nothing(self):
        c = _ctl(0)
        run(c, {"set": True, "t": 1000, "by": "R-FREMD"})
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], 1000)

    def test_older_box_without_t_or_by_nothing(self):
        c = _ctl(0)
        run(c, {"set": True, "salt": "S"})
        self.assertNotIn("guard_set_by", c.sync_status)
        self.assertEqual(c.settings["sync_code_seen"], 0, "still „none known“ – a newer box can name it later")


if __name__ == "__main__":
    unittest.main()
