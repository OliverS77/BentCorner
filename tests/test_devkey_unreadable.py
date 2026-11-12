"""Review 08.11. (M3): devkey.json that is there but can't be read (locked, damaged) is never replaced by new keys – that
would cost this device its registration and its envelope. Only a missing file makes new keys.

    python -m unittest tests.test_devkey_unreadable
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from net import devkeys


class DevkeyUnreadable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.p = mock.patch("system.datahome.HOME", self.home)
        self.p.start()
        devkeys._cache.clear()
        self.f = self.home / devkeys.FILE

    def tearDown(self):
        devkeys._cache.clear()
        self.p.stop()
        self.tmp.cleanup()

    def test_missing_file_makes_keys(self):
        k = devkeys._load()
        self.assertTrue(k["dev_id"])
        self.assertEqual(json.loads(self.f.read_text("utf-8"))["dev_id"], k["dev_id"])

    def test_damaged_file_stays(self):
        self.f.write_text('{"dev_id": "dkeep", "sign_', "utf-8")   # half written
        with self.assertRaises(devkeys.Unreadable):
            devkeys._load()
        self.assertIsNone(devkeys._load(False))
        self.assertIsNone(devkeys.mine(create=False))
        self.assertEqual(self.f.read_text("utf-8"), '{"dev_id": "dkeep", "sign_')

    def test_locked_file_stays_and_reads_later(self):
        good = devkeys._load()
        devkeys._cache.clear()
        before = self.f.read_text("utf-8")
        with mock.patch.object(pathlib.Path, "read_text", side_effect=PermissionError("locked")):
            with self.assertRaises(devkeys.Unreadable):
                devkeys.mine()
            self.assertFalse(devkeys.registered({}))
        self.assertEqual(self.f.read_text("utf-8"), before)
        self.assertEqual(devkeys._load()["dev_id"], good["dev_id"], "once readable again: the same keys")


if __name__ == "__main__":
    unittest.main()
