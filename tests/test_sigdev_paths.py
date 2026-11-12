"""Review 08.11. + box 01e8440: once this device is in its identity's device registry, every device write carries
dev_id + sig_dev over the same line – also board/put|del|get, block, pair/put, vault/put, rescue/put (a seed alone, e.g.
from a backup ZIP, isn't enough). Before registration nothing changes. And A3: a declined join request waits for the
server's date (429 cooldown_until) – a friendly line, no new request before then.

    python -m unittest tests.test_sigdev_paths
"""
import base64
import pathlib
import tempfile
import unittest
from unittest import mock

from net import devkeys, relay, vault


def identity():
    return {"relay": {"on": True, "seed": base64.b64encode(b"\x11" * 32).decode(), "url": "https://example.invalid",
                      "registered": "https://example.invalid", "friends": {}, "posted": {}}}


class Paths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch("system.datahome.HOME", pathlib.Path(self.tmp.name))
        self.p.start()
        devkeys._cache.clear()

    def tearDown(self):
        devkeys._cache.clear()
        self.p.stop()
        self.tmp.cleanup()

    def calls(self, registered):
        s = identity()
        devkeys.mine()
        if registered:
            devkeys._update(code=relay.my_code(s))
        sent = {}
        rec = lambda st, path, payload, *a, **k: sent.setdefault(path, payload) or {"ok": True}   # noqa: E731
        with mock.patch.object(relay, "_post", rec), mock.patch.object(vault, "_post", rec), \
                mock.patch.object(relay, "register", lambda st: None), \
                mock.patch("net.vault._me", lambda st: (relay.my_code(st), 1700000000)):
            relay.server_block(s, "BBBBBBBBBBBBBBBB", True)
            relay.withdraw(s, "mtg", "lists")
            vault._put_one(s, "add", 0, "QUJD")
            try:
                relay.board_get(s, "BBBBBBBBBBBBBBBB", "mtg", "lists", base64.b64encode(b"k" * 32).decode())
            except Exception:  # noqa: BLE001 – the fake answer has no data: only the request matters here
                pass
        return sent

    def test_registered_device_signs(self):
        sent = self.calls(True)
        for path in ("/v1/block", "/v1/board/del", "/v1/vault/put", "/v1/board/get"):
            self.assertIn(path, sent, path)
            self.assertTrue(sent[path].get("dev_id") and sent[path].get("sig_dev"), path)

    def test_before_registration_unchanged(self):
        sent = self.calls(False)
        for path, payload in sent.items():
            self.assertNotIn("sig_dev", payload, path)


class Cooldown(unittest.TestCase):
    def test_declined_waits_for_the_servers_date(self):
        import time
        from net import devices_ctl
        c = mock.Mock()
        c.sync_status = {}
        err = vault.VaultError(429, "abgelehnt", {"cooldown_until": int(time.time()) + 7 * 86400})
        devices_ctl.DevicesControl._dev_done(c, "dev_add", None, err)
        self.assertEqual(c.sync_status["join_wait"]["declined"], True)
        self.assertGreater(c._dev_cooldown, time.time() + 6 * 86400)


if __name__ == "__main__":
    unittest.main()
