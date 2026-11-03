"""Pairing v2 (net/pairing.py, docs/web/PAIRING.md): one 10-character code (picture or typed) -> the same identity
on a second device. Reference functions, the fixed test vectors (the web app's JS checks the same file) and the mailbox
endpoints /v1/pair/* – no network."""
import base64
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "box"))
from net import pairing  # noqa: E402
from tests.optional_games import needs_server  # noqa: E402

try:
    import box  # noqa: E402
except ImportError:   # the server is not part of the public source
    box = None

VECTORS = json.loads((ROOT / "docs" / "web" / "pairing-vectors.json").read_text("utf-8"))


class Reference(unittest.TestCase):
    def test_vectors(self):
        v = VECTORS
        self.assertEqual(v["version"], pairing.VERSION)
        self.assertEqual(pairing.picture_bytes(v["code"]).hex(), v["picture_hex"])
        self.assertEqual(pairing.code_of_picture(bytes.fromhex(v["picture_hex"])), v["code"])
        self.assertEqual(pairing._slow(v["code"]).hex(), v["argon2id_hex"])
        self.assertEqual(pairing.slot(v["code"]), (v["pid"], bytes.fromhex(v["key_hex"])))
        self.assertEqual(pairing.pair_id(v["code"].lower().replace("-", " ")), v["pid"])   # typed loosely
        payload = json.loads(v["payload_json"])
        self.assertEqual(pairing.seal(v["code"], payload, bytes.fromhex(v["nonce_hex"])), v["sealed_b64"])
        self.assertEqual(pairing.open_sealed(v["code"], v["sealed_b64"]), payload)
        self.assertEqual(pairing.code_of_seed(v["seed_b64"]), v["code_of_seed"])
        with self.assertRaises(pairing.PairError):
            pairing.open_sealed(v["wrong_code"], v["sealed_b64"])
        self.assertNotEqual(pairing.pair_id(v["wrong_code"]), v["pid"])   # a wrong code looks in another slot

    def test_vault_vectors(self):
        v = VECTORS
        self.assertEqual(pairing.vault_key(v["seed_b64"]).hex(), v["vault_key_hex"])
        item = json.loads(v["vault_item_json"])
        self.assertEqual(pairing.vault_seal(v["seed_b64"], item, bytes.fromhex(v["nonce_hex"])), v["vault_sealed_b64"])
        self.assertEqual(pairing.vault_open(v["seed_b64"], v["vault_sealed_b64"]), item)
        other = base64.b64encode(os.urandom(32)).decode()
        with self.assertRaises(pairing.PairError):   # another identity can't read it
            pairing.vault_open(other, v["vault_sealed_b64"])

    def test_same_address_as_relay(self):
        from net import relay
        s = {"relay": {"seed": VECTORS["seed_b64"]}}
        self.assertEqual(relay.my_code(s), VECTORS["code_of_seed"])

    def test_roundtrip_random(self):
        code = pairing.new_code()
        self.assertRegex(code, r"^[2-9A-HJKMNP-Z]{5}-[2-9A-HJKMNP-Z]{5}$")
        self.assertEqual(pairing.norm_code(code.lower().replace("-", " ")), code.replace("-", ""))
        self.assertEqual(pairing.code_of_picture(pairing.picture_bytes(code)), code)
        seed = base64.b64encode(os.urandom(32)).decode()
        data = pairing.seal(code, pairing.payload_of(seed))
        self.assertEqual(pairing.open_sealed(code, data)["seed"], seed)

    def test_picture_edges(self):
        top = "Z" * 10
        self.assertEqual(pairing.code_of_picture(pairing.picture_bytes(top)), "ZZZZZ-ZZZZZ")
        self.assertEqual(pairing.picture_bytes("2" * 10), bytes([2]) + bytes(7))
        for bad in (b"", bytes([1]) + bytes(7), bytes([2]) + bytes([255]) * 7, bytes([2]) + bytes(8)):
            with self.assertRaises(pairing.PairError):
                pairing.code_of_picture(bad)

    def test_bad_input(self):
        for bad in ("", "7K3M-9QXA", "ABCDE-EFGH0", "ABCDE-FGHJK-M"):   # old 8 chars, 0 not in the alphabet, too long
            with self.assertRaises(pairing.PairError):
                pairing.norm_code(bad)

    def test_identity_must_match_address(self):
        code = "22222-22222"
        p = pairing.payload_of(base64.b64encode(os.urandom(32)).decode())
        p["code"] = "0" * 16
        with self.assertRaises(pairing.PairError):
            pairing.open_sealed(code, pairing.seal(code, p))


@needs_server
class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._db = box.DB
        box.DB = os.path.join(self.tmp.name, "box.sqlite")
        box._reg_hits.clear()
        box._seen_day.clear()
        box._last_day[0] = 0
        from test_box import Who, register
        self.a = Who()
        self.assertEqual(register(self.a)[0], 200)
        box._pair_hits.clear()
        self.pid = os.urandom(16).hex()

    def tearDown(self):
        box.DB = self._db
        self.tmp.cleanup()

    def call(self, path, d):
        from test_box import call
        return call(path, d)

    def put(self, data="QUJD", pid=None):
        t = int(time.time())
        pid = pid or self.pid
        digest = hashlib.sha256(data.encode("ascii")).hexdigest()
        return self.call("/v1/pair/put", {"code": self.a.code, "pid": pid, "data": data, "t": t,
                                          "sig": self.a.sig(f"pair_put|{self.a.code}|{pid}|{digest}|{t}")})

    def state(self):
        t = int(time.time())
        return self.call("/v1/pair/state", {"code": self.a.code, "pid": self.pid, "t": t,
                                            "sig": self.a.sig(f"pair_state|{self.a.code}|{self.pid}|{t}")})

    def test_fetch_once_and_state(self):
        self.assertEqual(self.put()[0], 200)
        self.assertEqual(self.state()[1], {"fetched": False})
        self.assertEqual(self.call("/v1/pair/get", {"pid": self.pid}), (200, {"data": "QUJD"}))
        self.assertEqual(self.call("/v1/pair/get", {"pid": self.pid})[0], 404)   # never twice
        self.assertEqual(self.state()[1], {"fetched": True})

    def test_expires(self):
        self.put()
        con = box.connect()
        con.execute("UPDATE pair SET t = ?", (int(time.time()) - box.PAIR_TTL - 1,))
        con.commit()
        con.close()
        self.assertEqual(self.call("/v1/pair/get", {"pid": self.pid})[0], 404)

    def test_one_per_address(self):
        self.put()
        other = os.urandom(16).hex()
        self.put(pid=other)
        self.assertEqual(self.call("/v1/pair/get", {"pid": self.pid})[0], 404)
        self.assertEqual(self.call("/v1/pair/get", {"pid": other})[0], 200)

    def test_guessing_limited_per_ip(self):
        import unittest.mock as um

        def get():
            try:
                return box.handle("POST", "/v1/pair/get", json.dumps({"pid": os.urandom(16).hex()}).encode(), "203.0.113.7")[0]
            except box.Fail as e:
                return e.status
        with um.patch.object(box, "MAX_PAIR_IP_HOUR", 3):
            codes = [get() for _ in range(5)]
        self.assertEqual(codes[:3], [404] * 3)
        self.assertEqual(codes[3:], [429] * 2)

    def test_checks(self):
        self.assertEqual(self.call("/v1/pair/get", {"pid": "nothex"})[0], 400)
        self.assertEqual(self.put(data=base64.b64encode(b"x" * (box.PAIR_MAX + 10)).decode())[0], 413)
        t = int(time.time())
        st, _ = self.call("/v1/pair/put", {"code": self.a.code, "pid": self.pid, "data": "QUJD", "t": t, "sig": "AAAA"})
        self.assertEqual(st, 403)


if __name__ == "__main__":
    unittest.main()


RESCUE = json.loads((ROOT / "docs" / "web" / "rescue-vectors.json").read_text("utf-8"))


class RescueCode(unittest.TestCase):
    """The rescue code (docs/SYNC-PLAN.md §2): fixed vectors (web app and server check the same file), typos caught by
    the check character, the envelope only opens with the right code and its seed must fit its address."""

    def test_vectors(self):
        v = RESCUE
        self.assertEqual(pairing.norm_rescue(v["code_shown"]), v["code"])
        self.assertEqual(pairing.norm_rescue(v["code_typed"]), v["code"])
        rid, rk = pairing.rescue_keys(v["code"])
        self.assertEqual((rid, rk.hex()), (v["rid"], v["rk_hex"]))
        self.assertEqual(pairing.rescue_seal(v["code"], v["seed_b64"], bytes.fromhex(v["nonce_hex"])), v["data_b64"])
        self.assertEqual(pairing.rescue_open(v["code"], v["data_b64"]), v["seed_b64"])
        self.assertEqual(pairing.code_of_seed(v["seed_b64"]), v["address"])

    def test_vectors_file_is_current(self):
        from tools import make_rescue_vectors
        self.assertEqual(make_rescue_vectors.build(), RESCUE)

    def test_typos_rejected(self):
        for bad in (RESCUE["typo_rejected"], RESCUE["swap_rejected"], RESCUE["code"][:-1], RESCUE["code"] + "2",
                    RESCUE["code"][:-1] + "0"):
            with self.assertRaises(pairing.PairError):
                pairing.norm_rescue(bad)

    def test_every_single_typo_and_swap_caught(self):
        code = pairing.norm_rescue(RESCUE["code"])
        for i in range(25):
            for ch in pairing.ALPHABET:
                if ch != code[i]:
                    with self.assertRaises(pairing.PairError):
                        pairing.norm_rescue(code[:i] + ch + code[i + 1:])
        for i in range(24):
            if code[i] != code[i + 1]:
                with self.assertRaises(pairing.PairError):
                    pairing.norm_rescue(code[:i] + code[i + 1] + code[i] + code[i + 2:])

    def test_roundtrip_and_wrong_code(self):
        from nacl.signing import SigningKey
        import base64
        seed = base64.b64encode(bytes(SigningKey.generate())).decode()
        code, other = pairing.new_rescue_code(), pairing.new_rescue_code()
        data = pairing.rescue_seal(code, seed)
        self.assertLessEqual(len(data), pairing.MAX_RESCUE)
        self.assertEqual(pairing.rescue_open(code, data), seed)
        self.assertNotEqual(pairing.rescue_keys(code)[0], pairing.rescue_keys(other)[0])
        with self.assertRaises(pairing.PairError):
            pairing.rescue_open(other, data)
