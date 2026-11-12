"""Review 08.11. (S1): a 410 changes MY identity only when it answers about my own address. A friend who deleted
Bent°Corner (or moved without a note for me) answers board/get with 410 {gone} – that must never cost me my seed,
my device key or my friends.

    python -m unittest tests.test_own410
"""
import base64
import unittest
from unittest import mock

from net import relay, vault


class R:
    def __init__(self, status, d):
        self.status_code, self._d, self.headers = status, d, {}

    def json(self):
        return self._d


def settings():
    return {"relay": {"seed": base64.b64encode(b"\x01" * 32).decode(), "url": "https://example.invalid",
                      "registered": "https://example.invalid",
                      "friends": {"AAAAAAAAAAAAAAAA": {"status": "ok", "sign_pk": "x", "boards": {
                          "mtg/lists": {"key": base64.b64encode(b"k" * 32).decode()}}}}}}


class FriendGone(unittest.TestCase):
    def run_410(self, call):
        s = settings()
        seed, code = s["relay"]["seed"], relay.my_code(s)
        forgot = []
        with mock.patch.object(vault, "gated", lambda *a, **k: R(410, {"error": "x", "gone": True})), \
                mock.patch.object(relay, "register", lambda st: None), \
                mock.patch("net.devkeys.forget", lambda: forgot.append(1)):
            with self.assertRaises((relay.RelayError, vault.VaultError)):
                call(s)
        return s, seed, code, forgot

    def test_friends_board_gone_keeps_my_identity(self):
        s, seed, code, forgot = self.run_410(lambda s: relay.fetch_board(s, "AAAAAAAAAAAAAAAA", "mtg"))
        self.assertEqual(s["relay"]["seed"], seed)
        self.assertEqual(relay.my_code(s), code)
        self.assertNotIn("identity_gone", s["relay"])
        self.assertEqual(forgot, [], "my device key stays")

    def test_my_own_fetch_still_follows(self):
        s, seed, _code, forgot = self.run_410(lambda s: relay.fetch(s))
        self.assertNotEqual(s["relay"]["seed"], seed, "my own address gone: a new identity, as before")
        self.assertTrue(s["relay"].get("identity_gone"))

    def test_lists(self):
        for p in ("/v1/board/get", "/v1/send", "/v1/report", "/v1/block", "/v1/register", "/v1/rescue/get",
                  "/v1/pair/get"):
            self.assertNotIn(p, relay.OWN_PATHS, p)
        for p in ("/v1/fetch", "/v1/vault/get", "/v1/rekey", "/v1/dev/list"):
            self.assertIn(p, relay.OWN_PATHS, p)


if __name__ == "__main__":
    unittest.main()
