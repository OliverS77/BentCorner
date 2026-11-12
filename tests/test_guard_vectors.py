"""Protection code and key change vectors (docs/web/guard-vectors.json, the web checks the same file): the derivation
and the signatures are exact; the sample rekey note opens with the friend's seed and is shown as a move; the tampered
one is refused.

    python -m unittest tests/test_guard_vectors.py
"""
import json
import pathlib
import unittest
from unittest import mock

from net import guard, pairing, relay  # noqa: F401

VEC = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs" / "web" / "guard-vectors.json")
                 .read_text("utf-8"))


class FileCurrent(unittest.TestCase):
    def test_file_is_current_where_deterministic(self):
        from tools import make_guard_vectors as mv
        got = json.loads(json.dumps(mv.build()))
        self.assertEqual(got["rekey"]["body"], VEC["rekey"]["body"])
        self.assertEqual(got["rekey"]["by"], VEC["rekey"]["by"])
        self.assertNotIn("derive", VEC, "the code's derivation lives in code-vectors-v2.json now (S5 = b)")


class Note(unittest.TestCase):
    def friend(self):
        r = VEC["rekey"]
        old_pk = relay._b64(relay._signing({"relay": {"seed": r["seeds"]["old"]}}).verify_key)
        return {"relay": {"seed": r["seeds"]["friend"],
                          "friends": {r["codes"]["old"]: {"status": "ok", "name": "Max", "sign_pk": old_pk}}}}

    def test_the_note_is_shown_as_a_move(self):
        r = VEC["rekey"]
        s = self.friend()
        with mock.patch.object(relay, "lookup", lambda _s, _c: r["new_sign_pk"]),                 mock.patch.object(relay, "_move_confirmed", lambda _s, o, n: (o, n) == (r["codes"]["old"], r["codes"]["new"])):
            env = relay.unpack(s, r["data"], r["codes"]["new"])
            ev = relay.apply(s, env)   # as a parcel: only with the server's confirmation (M8)
        self.assertEqual(ev, {"kind": "moved", "code": r["codes"]["old"], "name": "Max"})
        self.assertEqual(s["relay"]["friends"][r["codes"]["old"]]["moved"]["new"], r["codes"]["new"])

    def test_unconfirmed_parcel_note_is_not_shown(self):
        """M8: the same genuine note as a parcel, but the server doesn't confirm the move -> nothing."""
        r = VEC["rekey"]
        s = self.friend()
        with mock.patch.object(relay, "lookup", lambda _s, _c: r["new_sign_pk"]),                 mock.patch.object(relay, "_move_confirmed", lambda _s, o, n: False):
            self.assertIsNone(relay.apply(s, relay.unpack(s, r["data"], r["codes"]["new"])))
        self.assertNotIn("moved", s["relay"]["friends"][r["codes"]["old"]])

    def test_a_tampered_note_is_refused(self):
        r = VEC["rekey"]
        s = self.friend()
        with mock.patch.object(relay, "lookup", lambda _s, _c: r["new_sign_pk"]):
            env = relay.unpack(s, r["tampered"], r["codes"]["new"])
            self.assertIsNone(relay.apply(s, env) if env else None)
        self.assertNotIn("moved", s["relay"]["friends"][r["codes"]["old"]])

    def test_by_opens_with_the_old_seed(self):
        r = VEC["rekey"]
        self.assertEqual(pairing.vault_open(r["seeds"]["old"], r["by"]["sealed"])["name"], r["by"]["name"])


class FreshNonce(unittest.TestCase):
    """lead 07.11.: every envelope (rescue/put and the pending one of „code lost“) gets a fresh random nonce – two seals
    of the same seed with the same code differ; both carry the ID's salt (S5 = b)."""

    def test_two_requests_differ(self):
        seed, code = VEC["rekey"]["seeds"]["old"], pairing.new_rescue_code()
        sent = []
        s = {"relay": {"seed": seed, "guard_salt": pairing.new_salt()}}
        with mock.patch.object(guard, "_post", lambda _s, path, d: sent.append(d)):
            guard.request(s, code)
            guard.request(s, code)
        a, b = sent[0]["data"], sent[1]["data"]
        self.assertNotEqual(a, b)
        self.assertEqual(pairing.rescue_open(code, a)[0], seed)
        self.assertEqual(pairing.rescue_open(code, b)[0], seed)
        self.assertEqual(sent[0]["salt"], s["relay"]["guard_salt"], "the request carries the ID's salt")

    def test_rescue_put_differs(self):
        from net import vault
        seed, code = VEC["rekey"]["seeds"]["old"], pairing.new_rescue_code()
        sent = []
        s = {"relay": {"seed": seed, "registered": "x", "guard_salt": pairing.new_salt()}}
        with mock.patch.object(vault, "_post", lambda _s, path, d: sent.append(d)):
            vault.rescue_put(s, code)
            vault.rescue_put(s, code)
        self.assertNotEqual(sent[0]["data"], sent[1]["data"])


if __name__ == "__main__":
    unittest.main()
