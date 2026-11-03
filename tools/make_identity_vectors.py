"""Writes docs/web/identity-vectors.json: fixed test vectors for identity, signatures, parcels and posted content
(net/identity.py = net/relay.py's rules). The web app's JS core checks the same file. Test seeds only.

Sealed boxes are random (a fresh key per parcel): the parcel sample is made once and kept as long as it still opens –
the JS side tests OPENING it, and its own sealing by a round trip. zlib output may differ between libraries: the
board sample is fixed (nonce given) for opening; JS sealing is tested by a round trip too.

    python tools/make_identity_vectors.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from net import identity  # noqa: E402

OUT = ROOT / "docs" / "web" / "identity-vectors.json"
PAIR = json.loads((ROOT / "docs" / "web" / "pairing-vectors.json").read_text("utf-8"))
SEED_A = PAIR["seed_b64"]                                   # the same test seed as the pairing vectors
SEED_B = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="       # bytes 0..31
BOARD_KEY = "QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8="     # bytes 64..95, test value  gitleaks:allow
NONCE = bytes(range(0x60, 0x78))


def build(old=None):
    a, b = SEED_A, SEED_B
    env = {"v": 1, "kind": "friend", "game": "mtg", "from": identity.address(a), "to": identity.address(b),
           "t": 1793600000, "body": {"name": "Anna – Ä", "pid": ""}}
    parcel = (old or {}).get("parcel", {}).get("data_b64")
    try:
        if not parcel or identity.parcel_open(b, parcel, identity.sign_pk(a)) != env:
            raise identity.IdentityError("new")
    except identity.IdentityError:
        parcel = identity.parcel_seal(a, identity.sign_pk(b), env)
    data = "ZGF0YQ=="
    lines = [identity.line("register", identity.address(a), 1793600000),
             identity.line("send", identity.address(a), identity.address(b), identity.digest(data), 1793600000),
             identity.line("fetch", identity.address(a), 1793600000),
             identity.line("board_put", identity.address(a), "mtg", "lists", identity.digest(data), 1793600000),
             identity.line("pair_put", identity.address(a), "0" * 32, identity.digest(data), 1793600000),
             "umlaut äöü °"]
    board = {"c": [["x_0", 2]], "w": [], "title": "Tausch – Ä"}
    return {
        "about": "Test vectors for identity and signatures (net/identity.py, the rules of net/relay.py). Base64 "
                 "standard alphabet with padding. address = SHA-256(Ed25519 public key) hex, first 16, upper case. "
                 "Signatures: Ed25519 detached over the UTF-8 line. digest = sha256 hex of the base64 TEXT. "
                 "parcel: open with seed B, sender = A (sealing is random: test it by a round trip). board: zlib "
                 "output may differ per library – test opening the sample and a round trip.",
        "ids": [{"seed_b64": s, "sign_pk_b64": identity.sign_pk(s), "address": identity.address(s),
                 "box_pk_b64": identity.box_keys(s)[0], "box_sk_b64": identity.box_keys(s)[1]} for s in (a, b)],
        "digest": {"data_b64": data, "sha256": identity.digest(data)},
        "signatures": [{"seed": "A", "line": ln, "sig_b64": identity.sign(a, ln)} for ln in lines],
        "bad_signature": {"seed": "A", "line": lines[0] + "x", "sig_b64": identity.sign(a, lines[0])},
        "parcel": {"from": "A", "to": "B", "env": env, "data_b64": parcel},
        "board": {"key_b64": BOARD_KEY, "nonce_hex": NONCE.hex(), "payload": board,
                  "data_b64": identity.board_seal(BOARD_KEY, board, NONCE)},
    }


def current():
    return json.loads(OUT.read_text("utf-8")) if OUT.exists() else None


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(current()), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("written", OUT)
