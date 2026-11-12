"""Writes docs/web/guard-vectors.json: the key change's note to a friend for the web's JS port (net/rekey.py,
net/relay.py; PAIRING.md §3). The protection code itself (derivation, envelope, guard lines) moved to
docs/web/code-vectors-v2.json with the salt per ID (S5 = b, Oliver 08.11.; tools/make_code_vectors_v2.py).

  by       the remover's name sealed with the OLD vault key (fixed nonce here – the app uses a random one)
  rekey    one real note to a friend, as the desktop makes it: seeds of old/new/friend, the body, the sealed data
           (SealedBox has a random ephemeral key: the data is a sample – open it with the friend's seed and check)
           and a tampered copy that must be refused

    python tools/make_guard_vectors.py
"""
import base64
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from net import pairing, relay  # noqa: E402

OUT = ROOT / "docs" / "web" / "guard-vectors.json"
SEEDS = {"old": bytes(range(32)), "new": bytes(range(32, 64)), "friend": bytes(range(64, 96))}
T = 1793600000


def settings_of(seed):
    return {"relay": {"seed": base64.b64encode(seed).decode()}}


def rekey_case():
    old, new, friend = (settings_of(SEEDS[k]) for k in ("old", "new", "friend"))
    o, n, f = relay.my_code(old), relay.my_code(new), relay.my_code(friend)
    npk = relay._b64(relay._signing(new).verify_key)
    body = {"old": o, "new": n, "new_sign_pk": npk, "t": T,
            "sig_old": relay._signed(old, f"rekey_friend|{o}|{n}|{f}|{T}")}
    fpk = relay._b64(relay._signing(friend).verify_key)
    import unittest.mock as m
    with m.patch.object(relay.time, "time", lambda: T):
        data = relay.pack(new, f, fpk, "rekey", body)
        bad_body = dict(body, new=o)   # pretends the move goes elsewhere – sig_old no longer fits
        tampered = relay.pack(new, f, fpk, "rekey", bad_body)
    by = pairing.vault_seal(old["relay"]["seed"], {"v": 1, "name": "Olivers PC"}, nonce=bytes(24))
    return {"seeds": {k: base64.b64encode(v).decode() for k, v in SEEDS.items()},
            "codes": {"old": o, "new": n, "friend": f}, "new_sign_pk": npk, "body": body,
            "sig_old_message": f"rekey_friend|{o}|{n}|{f}|{T}", "data": data, "tampered": tampered,
            "by": {"name": "Olivers PC", "sealed": by, "sha256": hashlib.sha256(by.encode("ascii")).hexdigest()}}


def build():
    return {"about": "The key change's note to a friend (net/rekey.py). data/tampered are samples (SealedBox is "
                     "random): data must open with the friend's seed and pass every check; tampered must be refused "
                     "(sig_old). The protection code: docs/web/code-vectors-v2.json.",
            "t": T, "rekey": rekey_case()}


def main():
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")
    print(f"{OUT.relative_to(ROOT)} written")


if __name__ == "__main__":
    main()
