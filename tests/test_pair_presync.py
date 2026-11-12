"""T2 07.11. (Oliver/lead): the device showing a code syncs first – the joining device then sees its data and asks
„merge / keep“; a failed sync shows an error and no code. After „Remove device“ no „Coupled ✓“ from an old code.

    python -m unittest tests.test_pair_presync
"""
import unittest
from unittest import mock

from collection import syncrun
from net import sync_ctl


def ctl():
    c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
    c.settings = {"relay": {"on": True}}
    c.sync_status = {"busy": False}
    c.sync_engine = mock.Mock()
    c.sync_engine.meta = {"seeded": True, "guard": True}   # A2: a code is set (else no code is shown)
    c.sync_engine.devices.return_value = [{"n": 1}]
    for n in ("_sync_changed", "settings_changed", "_pair_drop_images", "relay_rekey", "sync_now"):
        setattr(c, n, mock.Mock())
    c.sync_on = c.sync_orbit_ok = mock.Mock(return_value=True)
    return c


class PreSync(unittest.TestCase):
    def run_offer(self, c):
        got = []
        c._sync_bg = lambda step, fn: got.append((step, fn))
        sync_ctl.SyncControl.pair_show(c)
        (step, fn), = got
        self.assertEqual(step, "pair_offer")
        return fn

    def test_sync_before_the_code(self):
        c = ctl()
        order = []
        c.sync_engine.fetch.side_effect = lambda: order.append("fetch")
        c.sync_engine.push.side_effect = lambda: order.append("push")
        with mock.patch.object(sync_ctl, "_offer", lambda s, n=None, dev=None, invite=None, **kw: order.append("offer") or "res"):
            self.assertEqual(self.run_offer(c)(), "res")
        self.assertEqual(order, ["fetch", "push", "offer"])

    def test_failed_sync_no_code(self):
        from net.vault import VaultError
        c = ctl()
        c.sync_engine.fetch.side_effect = VaultError(500, "down", {})
        offer = mock.Mock()
        with mock.patch.object(sync_ctl, "_offer", offer):
            fn = self.run_offer(c)
            with self.assertRaises(VaultError):
                fn()
        offer.assert_not_called()
        try:
            fn()
        except VaultError as e:
            err = e
        self.assertTrue(err.presync)
        with mock.patch.object(sync_ctl, "problem_text", lambda e: "Fehler"):
            sync_ctl.SyncControl._pair_done(c, "pair_offer", None, err)
        self.assertEqual(c.pair["error"], "Couldn't sync this device first – no code yet. Try again once you're online.")
        with mock.patch.object(sync_ctl, "problem_text", lambda e: "Fehler"):   # the offer itself failed: general
            sync_ctl.SyncControl._pair_done(c, "pair_offer", None, VaultError(500, "down", {}))
        self.assertEqual(c.pair["error"], "Fehler")
        self.assertEqual(c.pair["code"], "")


class RemovedNoCoupled(unittest.TestCase):
    def test_pair_state_reset_after_remove(self):
        c = ctl()
        c.pair = {"busy": False, "code": "", "until": 0, "fetched": True, "shown": True, "error": ""}
        c._pair_t = mock.Mock()
        c.sync_engine.on.return_value = True
        c.sync_engine.lock = mock.MagicMock()
        sync_ctl.SyncControl._rekey_done(c, {"mode": "remove", "rescued": False}, None)
        self.assertFalse(c.pair["fetched"])
        c._pair_t.stop.assert_called()
        c.sync_engine.drop_other_devices.assert_called_once()


if __name__ == "__main__":
    unittest.main()
