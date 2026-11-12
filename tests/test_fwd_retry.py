"""Review 08.11. (M5): after „remove one device“ elsewhere, this device fetches its own envelope (/v1/dev/fwd). A short
failure there (offline, 429, 5xx, a locked key file) used to count as „removed“ – sync off, the removed line shown.
Now nothing is decided until the server answers: the sync stays on and asks again.

    python -m unittest tests.test_fwd_retry
"""
import base64
import pathlib
import tempfile
import unittest
from unittest import mock

from net import devkeys, relay, sync_ctl, vault


def _ctl():
    c = mock.Mock()
    c.sync_status = {}
    c._rekey_n = 0
    c.settings = {"relay": {"on": True}}
    return c


class SyncDone(unittest.TestCase):
    def _done(self, c, err):
        with mock.patch.object(sync_ctl, "QtCore"):
            sync_ctl.SyncControl._sync_done(c, "fetch", None, err)

    def test_envelope_not_fetched_is_not_removed(self):
        c = _ctl()
        self._done(c, vault.VaultError(410, "moved", {"moved": True, "per_device": True}))
        c.sync_engine.switch_off.assert_not_called()
        self.assertNotIn("removed", c.sync_status)
        self.assertNotIn("removed", c.settings["relay"])
        self.assertTrue(c.sync_status["text"])

    def test_removed_still_counts(self):
        c = _ctl()
        self._done(c, vault.VaultError(410, "moved", {"moved": True, "per_device": True, "gone": True}))
        c.sync_engine.switch_off.assert_called_once()
        self.assertIn("removed", c.sync_status)


class LockedKeys(unittest.TestCase):
    def test_locked_key_file_is_no_answer(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("system.datahome.HOME", pathlib.Path(tmp)):
            devkeys._cache.clear()
            (pathlib.Path(tmp) / devkeys.FILE).write_text("{kaputt", "utf-8")
            s = {"relay": {"on": True, "seed": base64.b64encode(b"\x11" * 32).decode()}}
            seed = s["relay"]["seed"]
            with self.assertRaises(vault.VaultError):
                devkeys.fetch_fwd(s, relay.my_code(s))
            data = {"moved": True, "per_device": True}
            self.assertFalse(relay.moved_away(s, data))
            self.assertEqual(s["relay"]["seed"], seed)
            self.assertNotIn("gone", data)
            devkeys._cache.clear()


if __name__ == "__main__":
    unittest.main()
