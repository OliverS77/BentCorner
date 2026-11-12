"""M3 follow-up (lead 08.11.): a devkey.json that can't be read is never replaced – but the devices page says so instead
of failing silently, and no registration is tried meanwhile.

    python -m unittest tests.test_devkey_line
"""
import pathlib
import tempfile
import unittest
from unittest import mock

from net import devices_ctl, devkeys


class DevkeyLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch("system.datahome.HOME", pathlib.Path(self.tmp.name))
        self.p.start()
        devkeys._cache.clear()

    def tearDown(self):
        devkeys._cache.clear()
        self.p.stop()
        self.tmp.cleanup()

    def _ctl(self):
        c = mock.Mock()
        c.sync_status = {}
        c._dev_busy = False
        c._dev_cooldown = 0
        c._dev_reg = {}
        c.sync_engine.on.return_value = True
        c.sync_engine.meta = {"seeded": True}
        c.settings = {"relay": {"on": True}}
        return c

    def _ensure(self, c):
        with mock.patch("collection.syncrun.available", lambda: True):
            devices_ctl.DevicesControl._dev_ensure(c)

    def test_unreadable_shows_and_does_not_register(self):
        (pathlib.Path(self.tmp.name) / devkeys.FILE).write_text("{kaputt", "utf-8")
        self.assertTrue(devkeys.unreadable())
        c = self._ctl()
        self._ensure(c)
        self.assertTrue(c.sync_status["devkey_unreadable"])
        c._sync_bg.assert_not_called()
        from ui import qsync
        ui = mock.Mock()
        ui.label.side_effect = lambda text, **kw: text
        self.assertEqual(qsync.join_wait_items(ui, c), [qsync.tr(qsync.DEVKEY_UNREADABLE)])

    def test_readable_again_clears_the_line(self):
        f = pathlib.Path(self.tmp.name) / devkeys.FILE
        f.write_text("{kaputt", "utf-8")
        c = self._ctl()
        self._ensure(c)
        f.unlink()
        devkeys._load()   # readable keys again
        self.assertFalse(devkeys.unreadable())
        self._ensure(c)
        self.assertFalse(c.sync_status["devkey_unreadable"])

    def test_both_lines_stay_visible(self):
        """library 08.11.: the key line comes first, a waiting/declined line stays below it."""
        from ui import qsync
        ui = mock.Mock()
        ui.label.side_effect = lambda text, **kw: text
        c = self._ctl()
        c.sync_status.update(devkey_unreadable=True, join_wait={"declined": True})
        self.assertEqual(qsync.join_wait_items(ui, c), [qsync.tr(qsync.DEVKEY_UNREADABLE), qsync.tr(qsync.JOIN_DECLINED)])
        self.assertNotIn("devkey", qsync.DEVKEY_UNREADABLE, "no file name for the user – only in the log")

    def test_missing_file_is_not_unreadable(self):
        self.assertFalse(devkeys.unreadable())


if __name__ == "__main__":
    unittest.main()
