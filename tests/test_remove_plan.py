"""Review 08.11. (M7): „Remove device“ sends exactly the plan the page showed. Before, remove_one read a fresh list and
removed whatever chain hung on the device by then – a device added meanwhile went along without asking.

    python -m unittest tests.test_remove_plan
"""
import base64
import unittest
from unittest import mock

from net import rekey, relay

ME = {"dev_id": "dA", "sign_pk": "", "box_pk": ""}


def _settings():
    return {"relay": {"on": True, "seed": base64.b64encode(b"\x11" * 32).decode()}}


def _rows(*extra):
    rows = [{"dev_id": "dA", "added_by": ""}, {"dev_id": "dB", "added_by": "dA"}] + list(extra)
    return [dict(r, box_pk="") for r in rows]


class RemovePlan(unittest.TestCase):
    def _remove(self, listing, plan):
        sent = []
        with mock.patch("net.devkeys.mine", lambda create=True: ME), \
                mock.patch("net.devkeys.listing", lambda s: listing), \
                mock.patch("net.relay.register"), mock.patch("net.relay._post", lambda *a, **k: sent.append(a[1])), \
                mock.patch("net.devkeys.seal_for", lambda pk, letter: "x"), \
                mock.patch("net.devkeys.attach", lambda s, p, m: p), mock.patch("net.devkeys.moved"):
            res = rekey.remove_one(_settings(), "dB", None, None, plan)
        return res, sent

    def test_device_added_meanwhile_stops_it(self):
        listing = {"reg_version": 8, "list": _rows({"dev_id": "dC", "added_by": "dB"})}
        with self.assertRaises(relay.RelayError) as cm:
            self._remove(listing, {"rv": 7, "gone": ["dB"]})
        self.assertEqual(cm.exception.status, 409)

    def test_same_version_other_chain_stops_it(self):
        listing = {"reg_version": 7, "list": _rows({"dev_id": "dC", "added_by": "dB"})}
        with self.assertRaises(relay.RelayError):
            self._remove(listing, {"rv": 7, "gone": ["dB"]})

    def test_the_plan_shown_is_sent(self):
        listing = {"reg_version": 7, "list": _rows()}
        res, sent = self._remove(listing, {"rv": 7, "gone": ["dB"]})
        self.assertEqual(res["gone"], ["dB"])
        self.assertEqual(sent, ["/v1/rekey"])


class Controller(unittest.TestCase):
    def test_plan_is_kept_and_passed(self):
        from net import devices_ctl
        c = mock.Mock()
        c._dev_reg = {"reg_version": 7, "list": _rows()}
        c.sync_devices.return_value = [{"dev": "x1", "rid": "dA", "name": "A"}, {"dev": "x2", "rid": "dB", "name": "B"}]
        c._rid_of = lambda dev: devices_ctl.DevicesControl._rid_of(c, dev)
        c.guard_on.return_value = False
        c._remove_plans = None
        devices_ctl.DevicesControl.sync_remove_plan(c, "x2")
        self.assertEqual(c._remove_plans["dB"], {"rv": 7, "gone": ["dB"]})
        c.sync_status = {}
        c._rekey_n = 0
        got = {}
        c._sync_bg = lambda step, fn: got.update(step=step, fn=fn)
        with mock.patch("collection.syncrun.available", lambda: True), \
                mock.patch("net.rekey.remove_one", lambda *a: got.update(args=a) or {"gone": []}), \
                mock.patch("net.rekey.finish"):
            devices_ctl.DevicesControl.sync_remove(c, "x2")
            got["fn"]()
        self.assertEqual(got["args"][4], {"rv": 7, "gone": ["dB"]})


if __name__ == "__main__":
    unittest.main()
