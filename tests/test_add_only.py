"""lead 09.11. (ports' find): [Add with protection code] on a restored device ONLY adds it (dev/add with the code) –
it removes nobody. A freshly restored device has no device list yet (it would have removed all the OWN devices), and the
sealed list can be written by anyone with the seed (legal). A foreign device goes afterwards with ✕ in the list.
The real box: tools/boxchecks/takeover_check.py (X and K stay).

    python -m unittest tests.test_add_only
"""
import base64
import unittest
from unittest import mock

from net import devices_ctl

SEED = base64.b64encode(b"\x11" * 32).decode()


class AddOnly(unittest.TestCase):
    def test_restored_device_with_the_code_removes_nobody(self):
        s = {"relay": {"on": True, "seed": SEED, "guard_salt": "S" * 24}}
        rows = {"list": [{"dev_id": "dMine1"}, {"dev_id": "dMine2"}, {"dev_id": "dNew"}]}
        with mock.patch("net.devkeys.registered", lambda st: False), \
                mock.patch("net.devkeys.register", return_value="ok") as reg, \
                mock.patch("net.devkeys.mine", lambda create=True: {"dev_id": "dNew"}), \
                mock.patch("net.devkeys.listing", return_value=rows), \
                mock.patch("net.rekey.remove_one", side_effect=AssertionError("removed someone")) as rm:
            res = devices_ctl.add_with_code(s, "MEIN-CODE", set())   # no device list yet (a fresh restore)
        self.assertEqual(res, {"gone": []})
        reg.assert_called_once_with(s, None, "MEIN-CODE")
        rm.assert_not_called()

    def test_not_an_own_key_change(self):
        from net import sync_ctl
        self.assertNotIn("add_code", sync_ctl.OWN_CHANGE, "only adds a device: no key change, no lock on the jobs")


if __name__ == "__main__":
    unittest.main()
