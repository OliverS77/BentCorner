"""Protection among friends (net/relay.py): block, unblock, hide card back – without network.

    python -m unittest tests/test_relay_block.py
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from net import relay  # noqa: E402

CODE = "7F3A21C90B44E1D2"
OTHER = "0123456789ABCDEF"


def settings_with(status="ok", **extra):
    f = {"name": "Mia", "back": "back-text", "pid": "pid-mia", "sign_pk": "pk", "status": status,
         "boards": {"mtg/lists": {"key": "k"}}}
    f.update(extra)
    return {"relay": {"on": True, "registered": relay.URL, "seed": "A" * 43 + "=", "friends": {CODE: f}}}


class RelayBlockTest(unittest.TestCase):
    def setUp(self):
        self.drop = mock.patch.object(relay, "_drop_friend_files").start()
        self.patch = mock.patch.object(relay, "_patch_friend_files").start()
        self.send = mock.patch.object(relay, "send").start()
        self.post = mock.patch.object(relay, "_post", return_value={"ok": True}).start()
        self.addCleanup(mock.patch.stopall)

    def test_block_local(self):
        s = settings_with()
        f = relay.block(s, CODE)
        self.assertEqual(f["status"], "blocked")
        self.assertTrue(f["hide_back"])
        self.assertNotIn("boards", f)
        self.drop.assert_called_once_with("pid-mia")
        self.assertIsNone(relay.shown_back(f))
        self.assertNotIn(CODE, relay.ok_friends(s))
        self.assertEqual(relay.audience_codes(s), [])
        # nothing of theirs is taken any more
        self.assertIsNone(relay.apply(s, {"from": CODE, "kind": "friend", "body": {"name": "x"}, "_sign_pk": "pk"}))
        self.assertIsNone(relay.apply(s, {"from": CODE, "kind": "board_key",
                                          "body": {"game": "mtg", "slot": "lists", "key": "k"}}))

    def test_unblock_removes_entry(self):
        s = settings_with()
        relay.block(s, CODE)
        relay.unblock(s, CODE)
        self.assertNotIn(CODE, relay.friends(s))

    def test_hide_back(self):
        s = settings_with()
        f = relay.set_hide_back(s, CODE, True)
        self.assertIsNone(relay.shown_back(f))
        self.patch.assert_called_with("pid-mia", None)
        f = relay.set_hide_back(s, CODE, False)
        self.assertEqual(relay.shown_back(f), "back-text")
        self.patch.assert_called_with("pid-mia", "back-text")
        self.assertIsNone(relay.set_hide_back(s, OTHER, True))   # unknown: nothing happens

    def test_lists_from_hidden_friend_have_no_back(self):
        f = settings_with(hide_back=True)["relay"]["friends"][CODE]
        d = relay._clean_list({"app": "BentCorner", "id": "pid-mia", "c": [], "w": [], "back": "x"}, f)
        self.assertIsNone(d["back"])

    def test_answer_block_is_a_full_block(self):
        s = settings_with(status="in")
        f = relay.answer_friend(s, CODE, None)
        self.assertEqual(f["status"], "blocked")
        self.assertTrue(f["hide_back"])
        self.assertNotIn("boards", f)
        self.drop.assert_called_once_with("pid-mia")
        self.assertEqual(self.post.call_args[0][1], "/v1/block")   # the server gets told too
        self.assertEqual(self.post.call_args[0][2]["on"], 1)

    def test_answer_decline_is_not_a_block(self):
        s = settings_with(status="in")
        f = relay.answer_friend(s, CODE, False)
        self.assertEqual(f["status"], "no")
        self.assertFalse(f.get("hide_back"))
        self.drop.assert_not_called()

    def test_server_block_signed_payload(self):
        from nacl.signing import VerifyKey
        import base64
        s = settings_with()
        self.assertTrue(relay.server_block(s, CODE, True))
        path, payload = self.post.call_args[0][1:3]
        self.assertEqual(path, "/v1/block")
        me = relay.my_code(s)
        msg = f"block|{me}|{CODE}|1|{payload['t']}"
        VerifyKey(bytes(relay._signing(s).verify_key)).verify(msg.encode(), base64.b64decode(payload["sig"]))
        relay.server_block(s, CODE, False)
        self.assertEqual(self.post.call_args[0][2]["on"], 0)

    def test_server_block_best_effort(self):
        s = settings_with()
        self.post.side_effect = relay.RelayError("down")
        self.assertFalse(relay.server_block(s, CODE, True))   # no exception: the local block stands
        s["relay"]["on"] = False
        self.post.reset_mock()
        self.assertFalse(relay.server_block(s, CODE, True))   # exchange off: no network
        self.post.assert_not_called()

    def test_rekey_plan_and_retire(self):
        s = settings_with()
        s["relay"]["posted"] = {"mtg/lists": {"t": 1}, "pokemon/lists": {"t": 1}, "mtg/binder-1": {"t": 1}}
        cur, others = relay.rekey_plan(s, "mtg")
        self.assertTrue(cur)
        self.assertEqual(others, ["pokemon/lists"])
        self.assertEqual(relay.retire(s, others), 1)
        self.assertEqual(self.post.call_args[0][1], "/v1/board/del")
        self.assertTrue(s["relay"]["posted"]["pokemon/lists"]["stale"])
        self.send.assert_not_called()   # friends keep their copy: no board_gone

    def test_post_registers_again_when_unknown(self):
        s = settings_with()
        mock.patch.stopall()   # the real _post this time, only the HTTP call is faked
        calls = []

        class R:
            def __init__(self, status, d):
                self.status_code, self._d = status, d

            def json(self):
                return self._d

        def fake_post(url, json=None, timeout=None):
            calls.append(url.rsplit("/v1", 1)[1])
            if url.endswith("/v1/register"):
                return R(200, {"ok": True})
            return R(200, {"ok": True}) if "/register" in calls else R(403, {"error": "x", "unknown": True})
        with mock.patch("net.netpolite.post", side_effect=fake_post):
            self.assertEqual(relay._post(s, "/v1/fetch", {"a": 1}), {"ok": True})
        self.assertEqual(calls, ["/fetch", "/register", "/fetch"])
        self.assertEqual(s["relay"]["registered"], relay.url(s))


if __name__ == "__main__":
    unittest.main()
