"""T2 07.11.: Test-PC 2 ran without the test server's access code after a restart and still said „Coupled ✓“.
sync_status["gate"] = "missing" (test builds only) and ["reached"] (the vault ever answered) for the page.

    python -m unittest tests.test_gate_state
"""
import unittest
from unittest import mock

from net import sync_ctl, vault

from tests import livebox  # noqa: E402
setUpModule, tearDownModule = livebox.module()   # the live box, as a Ship build (DEV split 13.11.)


def ctl(meta):
    c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
    c.settings = {}
    c.sync_status = {"busy": False}
    c.sync_engine = mock.Mock()
    c.sync_engine.meta = meta
    c._sync_changed = mock.Mock()
    return c


class GateState(unittest.TestCase):
    def test_missing_and_back(self):
        c = ctl({})
        with mock.patch.object(vault, "gate_needed", return_value=True):
            sync_ctl.SyncControl._gate_state(c)
        self.assertEqual(c.sync_status["gate"], "missing")
        self.assertFalse(c.sync_status["reached"])
        with mock.patch.object(vault, "gate_needed", return_value=False):
            sync_ctl.SyncControl._sync_done(c, "gate", None, None)
        self.assertNotIn("gate", c.sync_status)

    def test_reached_from_vault_seen(self):
        c = ctl({"vault_seen": 1794000000000})
        with mock.patch.object(vault, "gate_needed", return_value=False):
            sync_ctl.SyncControl._gate_state(c)
        self.assertTrue(c.sync_status["reached"])
        self.assertNotIn("gate", c.sync_status)

    def test_live_never_missing(self):   # no test server: gate_needed is False whatever is typed
        with mock.patch("collection.syncrun.test_base", return_value=None):
            self.assertFalse(vault.gate_needed())


if __name__ == "__main__":
    unittest.main()
