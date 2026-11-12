"""The code with a salt per ID (S5 = b, A2 – Oliver 08.11.): net/pairing.py against docs/web/code-vectors-v2.json, the
file the web checks against too (ports 08.11.: byte for byte the same).

    python -m unittest tests.test_code_vectors_v2
"""
import base64
import json
import pathlib
import unittest

from nacl.signing import SigningKey

from net import pairing

ROOT = pathlib.Path(__file__).resolve().parents[1]
VEC = json.loads((ROOT / "docs" / "web" / "code-vectors-v2.json").read_text("utf-8"))


def _sig(key, line):
    return base64.b64encode(key.sign(line.encode("utf-8")).signature).decode()


class Vectors(unittest.TestCase):
    def test_parameters(self):
        self.assertEqual(VEC["stage1"], {"salt_ascii": pairing.STAGE1_SALT.decode(), "ops": pairing.STAGE1_OPS,
                                         "mem_bytes": pairing.STAGE1_MEM})
        self.assertEqual(VEC["stage2"], {"ops": pairing.CODE_OPS, "mem_bytes": pairing.CODE_MEM})
        self.assertEqual(VEC["infos"], {"rid": pairing.RESCUE_ID_INFO.decode(), "rk": pairing.RESCUE_INFO.decode(),
                                        "main": pairing.MAIN_INFO.decode()})

    def test_cases(self):
        salt = VEC["salt_b64"]
        for c in VEC["cases"]:
            with self.subTest(c["name"]):
                self.assertEqual(pairing.norm_rescue(c["code_typed"]), c["code_norm"])
                k = pairing.code_keys(c["code_typed"], salt)
                self.assertEqual(k["rid"], c["rid"])
                self.assertEqual(k["rk"].hex(), c["rk_hex"])
                self.assertEqual(k["main"].hex(), c["main_seed_hex"])
                main = pairing.main_signing(c["code_typed"], salt)
                self.assertEqual(base64.b64encode(bytes(main.verify_key)).decode(), c["main_pk_b64"])
                env = pairing.rescue_seal(c["code_typed"], VEC["seed_b64"], salt, bytes.fromhex(VEC["nonce_hex"]), k)
                self.assertEqual(env, c["envelope"])
                self.assertEqual(pairing.rescue_open(c["code_typed"], c["envelope"]), (VEC["seed_b64"], salt))
                self.assertEqual(_sig(main, c["guard_set_line"]), c["guard_set_sig_main"])
                self.assertEqual(_sig(main, c["dev_add"]["line"]), c["dev_add"]["sig_main"])

    def test_swapped_header_salt_does_not_open(self):
        c = VEC["cases"][0]
        head = json.loads(base64.b64decode(c["envelope"]))
        head["salt"] = base64.b64encode(bytes(16)).decode()
        bad = base64.b64encode(json.dumps(head, separators=(",", ":"), sort_keys=True).encode()).decode()
        with self.assertRaises(pairing.PairError):
            pairing.rescue_open(c["code_typed"], bad)

    def test_v1_envelope_refused(self):
        with self.assertRaises(pairing.PairError):
            pairing.rescue_open("ABCDE", base64.b64encode(b"\x00" * 80).decode())


if __name__ == "__main__":
    unittest.main()
