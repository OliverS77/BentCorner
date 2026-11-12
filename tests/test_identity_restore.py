"""Restoring a backup with another identity (library F1, lead 08.11.): the helpers library calls.

    python -m unittest tests.test_identity_restore
"""
import base64
import pathlib
import tempfile
import unittest

from net import devkeys, relay


def _settings(byte):
    return {"relay": {"on": True, "seed": base64.b64encode(bytes([byte]) * 32).decode(), "registered": 3,
                      "dev_request": {"dev_id": "dx"}, "join_wait": {"declined": True}, "removed_by": "d1",
                      "identity_gone": True, "audience": "friends"},
            "sync_paired": True, "sync_guard_mine": {"until": 1}, "sync_rescue_ok": True, "sync_rescue_missing": True,
            "sync_backup": True, "device_name": "Laptop"}


class IdentityOf(unittest.TestCase):
    def test_same_as_my_code_and_never_creates(self):
        s = _settings(0x11)
        self.assertEqual(devkeys.identity_of(s), relay.my_code(_settings(0x11)))
        self.assertNotEqual(devkeys.identity_of(s), devkeys.identity_of(_settings(0x22)))
        empty = {}
        self.assertIsNone(devkeys.identity_of(empty))
        self.assertEqual(empty, {}, "reading never makes a seed")
        self.assertIsNone(devkeys.identity_of({"relay": {"seed": "kaputt!"}}))
        self.assertIsNone(devkeys.identity_of(None))


class DeviceBits(unittest.TestCase):
    def test_only_the_device_list_bits_go(self):
        s = devkeys.device_bits_off(_settings(0x11))
        self.assertEqual(set(s["relay"]), {"on", "seed", "audience"})
        self.assertEqual(set(s), {"relay", "sync_backup", "device_name"})


class DropDeviceState(unittest.TestCase):
    def test_removes_only_devkey_and_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "devkey.json").write_text("{}", "utf-8")
            (d / "sync").mkdir()
            (d / "sync" / "state.json").write_text("{}", "utf-8")
            (d / "settings.json").write_text("{}", "utf-8")
            (d / "collection.sqlite").write_bytes(b"x")
            (d / "sync.txt").write_text("keep", "utf-8")
            self.assertEqual(devkeys.drop_device_state(d), ["devkey.json", "sync"])
            self.assertEqual(sorted(p.name for p in d.iterdir()), ["collection.sqlite", "settings.json", "sync.txt"])
            self.assertEqual(devkeys.drop_device_state(d), [], "twice is fine")

    def test_forgets_the_cached_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = str(pathlib.Path(tmp) / "devkey.json")
            devkeys._cache[f] = {"dev_id": "dold"}
            devkeys.drop_device_state(tmp)
            self.assertNotIn(f, devkeys._cache)


if __name__ == "__main__":
    unittest.main()
