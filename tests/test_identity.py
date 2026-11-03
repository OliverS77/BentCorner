"""Identity and signatures (net/identity.py): the fixed vectors the web app checks, and that the reference does
exactly what net/relay.py and net/pairing.py do (address, signed lines, parcels, posted content).

    python -m unittest discover -t . -s tests -p test_identity.py
"""
import base64
import json
import pathlib
import unittest
from unittest import mock

from net import identity, pairing, relay

ROOT = pathlib.Path(__file__).resolve().parents[1]
V = json.loads((ROOT / "docs" / "web" / "identity-vectors.json").read_text("utf-8"))
SEED = {"A": V["ids"][0]["seed_b64"], "B": V["ids"][1]["seed_b64"]}


class Vectors(unittest.TestCase):
    def test_file_is_current(self):
        from tools import make_identity_vectors
        self.assertEqual(make_identity_vectors.build(V), V)

    def test_ids(self):
        for i in V["ids"]:
            self.assertEqual(identity.sign_pk(i["seed_b64"]), i["sign_pk_b64"])
            self.assertEqual(identity.address(i["seed_b64"]), i["address"])
            self.assertEqual(identity.box_keys(i["seed_b64"]), (i["box_pk_b64"], i["box_sk_b64"]))

    def test_signatures(self):
        pk = V["ids"][0]["sign_pk_b64"]
        self.assertEqual(identity.digest(V["digest"]["data_b64"]), V["digest"]["sha256"])
        for s in V["signatures"]:
            self.assertEqual(identity.sign(SEED[s["seed"]], s["line"]), s["sig_b64"])
            self.assertTrue(identity.verify(pk, s["line"], s["sig_b64"]))
        bad = V["bad_signature"]
        self.assertFalse(identity.verify(pk, bad["line"], bad["sig_b64"]))
        self.assertFalse(identity.verify(V["ids"][1]["sign_pk_b64"], V["signatures"][0]["line"],
                                         V["signatures"][0]["sig_b64"]))

    def test_parcel_opens(self):
        p = V["parcel"]
        env = identity.parcel_open(SEED["B"], p["data_b64"], identity.sign_pk(SEED["A"]))
        self.assertEqual(env, p["env"])
        with self.assertRaises(identity.IdentityError):   # not signed by B
            identity.parcel_open(SEED["B"], p["data_b64"], identity.sign_pk(SEED["B"]))
        with self.assertRaises(identity.IdentityError):   # not for A
            identity.parcel_open(SEED["A"], p["data_b64"], identity.sign_pk(SEED["A"]))

    def test_parcel_claiming_another_sender(self):
        env = dict(V["parcel"]["env"], **{"from": V["ids"][1]["address"]})
        data = identity.parcel_seal(SEED["A"], identity.sign_pk(SEED["B"]), env)
        with self.assertRaises(identity.IdentityError):
            identity.parcel_open(SEED["B"], data, identity.sign_pk(SEED["A"]))

    def test_board(self):
        b = V["board"]
        self.assertEqual(identity.board_open(b["key_b64"], b["data_b64"]), b["payload"])
        self.assertEqual(identity.board_seal(b["key_b64"], b["payload"], bytes.fromhex(b["nonce_hex"])), b["data_b64"])
        with self.assertRaises(identity.IdentityError):
            identity.board_open(base64.b64encode(bytes(32)).decode(), b["data_b64"])


class SameAsRelay(unittest.TestCase):
    """The reference must not drift from the code the desktop really runs."""

    def settings(self, seed):
        return {"relay": {"seed": seed}}

    def test_address_and_signature(self):
        s = self.settings(SEED["A"])
        self.assertEqual(relay.my_code(s), identity.address(SEED["A"]))
        self.assertEqual(pairing.code_of_seed(SEED["A"]), identity.address(SEED["A"]))
        self.assertEqual(relay.code_of_key(identity.sign_pk(SEED["A"])), identity.address(SEED["A"]))
        ln = V["signatures"][2]["line"]
        self.assertEqual(relay._signed(s, ln), identity.sign(SEED["A"], ln))

    def test_relay_parcel_opens_with_identity(self):
        posted = {}

        def fake_post(_settings, path, payload, again=True):
            posted[path] = payload
            return {}
        env = V["parcel"]["env"]
        with mock.patch.object(relay, "_post", fake_post), mock.patch.object(relay, "register", lambda s: None), \
                mock.patch.object(relay.time, "time", return_value=env["t"]):
            relay.send(self.settings(SEED["A"]), env["to"], env["kind"], env["body"], game=env["game"],
                       sign_pk=identity.sign_pk(SEED["B"]))
        msg = posted["/v1/send"]
        self.assertEqual(identity.parcel_open(SEED["B"], msg["data"], identity.sign_pk(SEED["A"])), env)
        line = identity.line("send", msg["from"], msg["to"], identity.digest(msg["data"]), msg["t"])
        self.assertTrue(identity.verify(identity.sign_pk(SEED["A"]), line, msg["sig"]))

    def test_identity_parcel_opens_with_relay(self):
        env = V["parcel"]["env"]
        data = identity.parcel_seal(SEED["A"], identity.sign_pk(SEED["B"]), env)
        s = self.settings(SEED["B"])
        s["relay"]["friends"] = {env["from"]: {"sign_pk": identity.sign_pk(SEED["A"]), "status": "ok"}}

        def fake_post(_settings, path, payload, again=True):
            return {"items": [{"id": "1", "from": env["from"], "data": data}]}
        with mock.patch.object(relay, "_post", fake_post), mock.patch.object(relay, "register", lambda s: None):
            out, ids = relay.fetch(s)
        self.assertEqual(ids, ["1"])
        self.assertEqual({k: v for k, v in out[0].items() if k != "_sign_pk"}, env)

    def test_board_same_as_relay(self):
        b = V["board"]
        with mock.patch.object(relay, "_post", lambda *_a, **_k: {"data": b["data_b64"], "t": 5}), \
                mock.patch.object(relay, "register", lambda s: None):
            got, t = relay.board_get(self.settings(SEED["B"]), V["ids"][0]["address"], "mtg", "lists", b["key_b64"])
        self.assertEqual((got, t), (b["payload"], 5))


if __name__ == "__main__":
    unittest.main()
