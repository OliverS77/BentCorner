"""A normal build (no ship flag, collection/syncrun.available() False): sync_setup makes no engine, but sync_status
exists – the backup badge and the Settings page ask for join requests (sync_join_request_info) on every start
(13.11.2026: a 0.9.8.0 test build threw AttributeError 'sync_status' at start and on every Settings page).

    python -m unittest tests.test_nosync_status
"""
import unittest
from unittest import mock

from net import devices_ctl, sync_ctl


class NoSyncBuild(unittest.TestCase):
    def test_status_exists_without_the_engine(self):
        class Ctl(sync_ctl.SyncControl, devices_ctl.DevicesControl):
            pass
        c = Ctl.__new__(Ctl)   # no Qt object needed: nothing else is touched without the sync
        with mock.patch("collection.syncrun.available", lambda: False):
            sync_ctl.SyncControl.sync_setup(c)
        self.assertIsNone(getattr(c, "sync_engine", None))
        self.assertIsInstance(c.sync_status, dict)
        self.assertIsNone(c.sync_join_request_info())


if __name__ == "__main__":
    unittest.main()
