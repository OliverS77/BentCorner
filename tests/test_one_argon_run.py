"""Ballast (review 08.11.): pairing and restoring derive the slow key ONCE – before, slot() and seal()/open_sealed() and
rescue_keys() and rescue_open() each ran Argon2id (64 / 128 MiB, seconds on a phone) for the same code.

    python -m unittest tests.test_one_argon_run
"""
import base64
import unittest
from unittest import mock

from net import pairing, vault

SEED = base64.b64encode(b"\x11" * 32).decode()


class OneRun(unittest.TestCase):
    def test_pair_put_and_get(self):
        real = pairing._slow
        with mock.patch.object(pairing, "_slow", side_effect=real) as slow, \
                mock.patch.object(vault, "_post", return_value={"until": 1}) as post, \
                mock.patch("net.devkeys.attach", lambda s, p, m: p):
            code = vault.pair_offer({"relay": {"seed": SEED}})[0]
            self.assertEqual(slow.call_count, 1, "pair/put: one Argon2id run")
            data = post.call_args_list[-1].args[2]["data"]
            slow.reset_mock()
            post.return_value = {"data": data}
            self.assertEqual(vault.pair_take({}, code)["seed"], SEED)
            self.assertEqual(slow.call_count, 1, "pair/get: one Argon2id run")

    def test_rescue_fetch(self):
        code = pairing.new_rescue_code()
        env = pairing.rescue_seal(code, SEED, pairing.new_salt())
        rid, gk = pairing.rescue_rid, pairing.guard_keys
        with mock.patch.object(pairing, "rescue_rid", side_effect=rid) as r1, \
                mock.patch.object(pairing, "guard_keys", side_effect=gk) as r2, \
                mock.patch.object(vault, "_post", return_value={"data": env}):
            self.assertEqual(vault.rescue_fetch({}, code), SEED)
        self.assertEqual((r1.call_count, r2.call_count), (1, 1), "restore: one run per stage (S5 = b)")

    def test_seal_open_with_key(self):
        code = "ABCDEFGHJK"
        pid, key = pairing.slot(code)
        real = pairing._slow
        with mock.patch.object(pairing, "_slow", side_effect=real) as slow:
            data = pairing.seal(code, pairing.payload_of(SEED, {}), key=key)
            self.assertEqual(pairing.open_sealed(code, data, key=key)["seed"], SEED)
        self.assertEqual(slow.call_count, 0)


if __name__ == "__main__":
    unittest.main()
