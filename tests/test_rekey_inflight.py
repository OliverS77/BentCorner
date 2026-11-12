"""Review 08.11. (M4): the answer to /v1/rekey gets lost although the server moved the address. Before, this device
kept the old seed, the old address answered 410 and relay.moved_away destroyed it – were it the last device, nobody
had the new seed. Now the new seed is kept before the POST and taken over once the new address lists this device.

    python -m unittest tests.test_rekey_inflight
"""
import base64
import unittest
from unittest import mock

from net import rekey, relay

OLD = base64.b64encode(b"\x11" * 32).decode()
NEW = base64.b64encode(b"\x22" * 32).decode()
ME = {"dev_id": "dme", "sign_pk": "", "box_pk": ""}


def _settings():
    return {"relay": {"on": True, "seed": OLD, "url": "https://example.invalid"}}


def _new_st():
    return {"relay": {"seed": NEW, "registered": 5}}


def _pending(s):
    new = relay.my_code(_new_st())
    return {"old": relay.my_code(s), "new": new, "t": 1, "mode": "remove_one", "friends": {}}


def lost(*a, **kw):
    raise relay.RelayError("timeout", 0)


class Inflight(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch("net.devkeys.mine", lambda create=True: ME),
                  mock.patch("net.devkeys.moved"), mock.patch("net.devkeys.forget")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()

    def test_lost_answer_but_moved_follows(self):
        s = _settings()
        with mock.patch("net.relay._post", lost), \
                mock.patch("net.devkeys.listing", lambda st: {"list": [{"dev_id": "dme"}, {"dev_id": "dother"}]}):
            rekey._send(s, {}, _new_st(), _pending(s))
        st = s["relay"]
        self.assertEqual(st["seed"], NEW)
        self.assertEqual(st["registered"], 5)
        self.assertEqual(st["rekey_pending"]["new"], relay.my_code(_new_st()))
        self.assertNotIn("rekey_inflight", st)

    def test_offline_keeps_it_and_the_next_410_follows(self):
        s = _settings()
        with mock.patch("net.relay._post", lost), mock.patch("net.devkeys.listing", side_effect=lost):
            with self.assertRaises(relay.RelayError):
                rekey._send(s, {}, _new_st(), _pending(s))
            self.assertEqual(s["relay"]["seed"], OLD)
            self.assertIn("rekey_inflight", s["relay"])
            self.assertFalse(relay.moved_away(s, {"moved": True, "per_device": True}), "still can't tell: nothing")
            self.assertEqual(s["relay"]["seed"], OLD)
        with mock.patch("net.devkeys.listing", lambda st: {"list": [{"dev_id": "dme"}]}):
            data = {"moved": True, "per_device": True}
            self.assertTrue(relay.moved_away(s, data))
        self.assertEqual(s["relay"]["seed"], NEW)
        self.assertNotIn("identity_gone", s["relay"])
        self.assertEqual(data.get("fwd"), "device")

    def test_server_said_no(self):
        s = _settings()
        with mock.patch("net.relay._post", side_effect=relay.RelayError("no", 403)):
            with self.assertRaises(relay.RelayError):
                rekey._send(s, {}, _new_st(), _pending(s))
        self.assertEqual(s["relay"]["seed"], OLD)
        self.assertNotIn("rekey_inflight", s["relay"])

    def test_not_moved_with_me_forgets_and_410_works_as_before(self):
        s = _settings()
        s["relay"]["rekey_inflight"] = dict(_pending(s), seed=NEW)
        with mock.patch("net.devkeys.listing", lambda st: {"list": [{"dev_id": "dother"}]}):
            self.assertTrue(relay.moved_away(s, {"gone": True}))
        self.assertTrue(s["relay"].get("identity_gone"), "removed by someone else: as before")
        self.assertNotIn("rekey_inflight", s["relay"])
        self.assertNotIn(s["relay"]["seed"], (OLD, NEW))

    def test_success_unchanged(self):
        s = _settings()
        with mock.patch("net.relay._post", return_value={"ok": True}):
            rekey._send(s, {}, _new_st(), _pending(s))
        self.assertEqual(s["relay"]["seed"], NEW)
        self.assertNotIn("rekey_inflight", s["relay"])


if __name__ == "__main__":
    unittest.main()
