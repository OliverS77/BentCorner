"""„Your devices“ outside Full Orbit (Oliver/lead 07.11., legal's wording; performance' sync_orbit_ok): no sphere, no
code, no „Remove device“ – legal's sentence and [Switch to Full Orbit]; a coupled device says the sync is paused (with
the 183 days). In memory, stand-in ctrl.

    python -m unittest tests/test_fullorbit_ui.py
"""
import unittest

from tests.test_device_switch import find, page, setup
from ui import qsync


def labels(p):
    return [x[1][0] for k in ("label", "note") for x in find(p, k)]


def groups(p):
    return [g[1] for g in find(p, "group")]


class FullOrbitTest(unittest.TestCase):
    def ctrl(self, full, on):
        b, _ = setup("leave")
        c = b.ctrl
        c.sync_orbit_ok = lambda: full
        c.sync_engine.on = lambda: on
        c.sync_join_code = lambda code: None                       # the join group is built in
        c.sync_rekey = lambda mode, guard=None: None
        opened = []
        c.stream = type("S", (), {"show_page": lambda self, k, back=False: opened.append(k)})()
        c.show_settings = lambda k: opened.append(k)
        return b, opened

    def test_outside_not_coupled(self):
        b, opened = self.ctrl(full=False, on=False)
        p = page(b)
        self.assertIn(qsync.ORBIT_NEED, labels(p))
        self.assertNotIn("Couple with your phone", groups(p))     # no sphere / code
        # PLAN-EINFACH: the same layout – „Add a device“ stays, its keys dimmed
        keys = [x for x in find(p, "button") if x[1][0] in (qsync.SHOW_CODE, qsync.ENTER_CODE)]
        self.assertEqual(len(keys), 2)
        self.assertTrue(all(k[2].get("enabled") is False for k in keys))
        self.assertNotIn(qsync.ORBIT_PAUSED, labels(p))
        from ui import backupui   # one wording with Backup (lead 07.11.)
        next(x for x in find(p, "button") if x[1][0] == backupui.ORBIT_SETTINGS)[1][1]()
        self.assertEqual(opened, ["settings", "privacy"])          # the Orbit slider

    def test_outside_coupled_paused(self):
        b, _ = self.ctrl(full=False, on=True)
        p = page(b)
        self.assertIn(qsync.ORBIT_PAUSED, labels(p))
        self.assertIn("183 days", qsync.ORBIT_PAUSED)              # legal: visible while paused
        self.assertIn(qsync.ORBIT_NEED, labels(p))
        self.assertNotIn(qsync.RM_KEY, groups(p))
        self.assertNotIn("Sync now", [x[1][0] for x in find(p, "button")])   # nothing runs

    def test_full_orbit_as_before(self):
        b, _ = self.ctrl(full=True, on=True)
        p = page(b)
        self.assertNotIn(qsync.ORBIT_NEED, labels(p))
        self.assertIn(qsync.ADD_TITLE, groups(p))
        self.assertNotIn(qsync.RM_KEY, groups(p))   # B5: the ✕ in each row instead of the box


if __name__ == "__main__":
    unittest.main()
