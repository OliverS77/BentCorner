"""„Another device is signed in with your ID“ (legal/lead 08.11.): when it shows, and [Create new ID] keeps only this
device's own data. [Take over with protection code] against the real box: tools/boxchecks/takeover_check.py.

    python -m unittest tests.test_foreign_device
"""
import base64
import pathlib
import tempfile
import unittest
from unittest import mock

from net import devices_ctl


def _ctl():
    c = mock.Mock()
    c.sync_status = {}
    c._dev_cooldown = 0
    return c


class Detect(unittest.TestCase):
    def test_plain_request_pending_shows_the_line(self):
        c = _ctl()
        c._dev_add_plain = True
        devices_ctl.DevicesControl._dev_done(c, "dev_add", {"pending": True, "until": 5}, None)
        self.assertEqual(set(c.sync_status["foreign_device"]), {"dev", "since"})

    def test_pairing_or_code_never_shows_it(self):
        c = _ctl()
        c._dev_add_plain = False
        devices_ctl.DevicesControl._dev_done(c, "dev_add", {"pending": True, "until": 5}, None)
        self.assertNotIn("foreign_device", c.sync_status)

    def test_let_in_clears_it(self):
        c = _ctl()
        c.sync_status["foreign_device"] = {"dev": None, "since": 1}
        devices_ctl.DevicesControl._dev_done(c, "dev_add", "ok", None)
        self.assertNotIn("foreign_device", c.sync_status)


class IdentityNew(unittest.TestCase):
    def test_only_own_data_stays(self):
        seed = base64.b64encode(b"\x11" * 32).decode()
        c = _ctl()
        c.sync_status = {"foreign_device": {"dev": None, "since": 1}, "join_wait": {"until": 5}}
        c.settings = {"relay": {"on": True, "url": "u", "seed": seed, "friends": {"A": {}}, "posted": {"x": {}},
                                "audience": {}, "registered": 1, "join_wait": {}, "rekey_pending": {}},
                      "sync_paired": True, "sync_backup": True, "device_name": "Laptop", "profile": {"name": "Me"}}
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp) / "friends"
            folder.mkdir()
            (folder / "AAAA.json").write_text("{}", "utf-8")
            (pathlib.Path(tmp) / "collection.json").write_text("{}", "utf-8")
            with mock.patch("games.mine", lambda key, *p: pathlib.Path(tmp).joinpath(*p)), \
                    mock.patch("games.GAMES", [("mtg", "Magic", True)]), mock.patch("net.devkeys.forget") as forget:
                devices_ctl.DevicesControl.identity_new(c)
            self.assertEqual(list(folder.iterdir()), [])
            self.assertTrue((pathlib.Path(tmp) / "collection.json").exists())
        rel = c.settings["relay"]
        self.assertNotEqual(rel["seed"], seed)
        self.assertEqual(set(rel), {"on", "url", "seed"})
        self.assertEqual(c.settings["profile"], {"name": "Me"})
        self.assertEqual(c.settings["device_name"], "Laptop")
        self.assertFalse(c.settings["sync_backup"])
        self.assertNotIn("sync_paired", c.settings)
        forget.assert_called_once()
        c.sync_engine.switch_off.assert_called_once()
        self.assertEqual(c.sync_status.get("identity_new"), "ok")
        self.assertNotIn("foreign_device", c.sync_status)


if __name__ == "__main__":
    unittest.main()
