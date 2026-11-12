"""Writes docs/web/code-vectors-v2.json: the protection/rescue code with a salt per ID (S5 = b, Oliver 08.11.; A2: a new
device joins with the code). The PC and the web check against the same file BEFORE either builds (lead 08.11.).
Made-up codes and a test seed only – never real ones.

Two stages (docs/web/PAIRING.md §4a):
  stage 1 (finding):  s1 = Argon2id(norm(code), salt "bentcorner-code2", ops 3, mem 64 MiB, 32 B)
                      rid = BLAKE2b-128(key=s1, msg="bentcorner-rescue-id-v2") as 32 lowercase hex
  stage 2 (the keys): s2 = Argon2id(norm(code), salt = the ID's 16 random bytes, ops 3, mem 128 MiB, 32 B)
                      rk   = BLAKE2b-256(key=s2, msg="bentcorner-rescue-v2")   (envelope key, secretbox)
                      main = BLAKE2b-256(key=s2, msg="bentcorner-main-v2")     (Ed25519 seed of the protection key)
  salt: 16 random bytes, made by the device that sets the FIRST code of the ID; standard base64 (24 characters).
  envelope v2 = base64( JSON sorted, no spaces: {"box": b64(nonce + secretbox(inner)), "salt": salt_b64, "v": 2} )
     inner    =          JSON sorted, no spaces: {"code": address, "salt": salt_b64, "seed": seed_b64, "v": 2}
     (the salt in the clear header lets a device without the ID derive rk; inside the box it must be the same)
  lines (signed by the ID key; with the code also by main as sig_main):
     guard_set|<address>|<main_pk b64>|<t>|<salt_b64>
     guard_req|<address>|<new main_pk b64>|<rid>|<sha256 hex of the envelope text>|<t>|<salt_b64>
     dev_add|<address>|<dev_id>|<dev sign_pk b64>|<dev box_pk b64>|||<t>   (net/devkeys.register; joining with the
              code: by and nonce empty) – sig_id (ID key), sig_dev (the new device's own key) and sig_main (A2)

    python tools/make_code_vectors_v2.py
"""
import base64
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nacl.pwhash import argon2id  # noqa: E402
from nacl.secret import SecretBox  # noqa: E402
from nacl.public import PrivateKey  # noqa: E402
from nacl.signing import SigningKey  # noqa: E402

from net import pairing  # noqa: E402

STAGE1_SALT = b"bentcorner-code2"                      # 16 bytes, fixed: only for finding the envelope
STAGE1_OPS, STAGE1_MEM = 3, 64 * 1024 * 1024
STAGE2_OPS, STAGE2_MEM = 3, 128 * 1024 * 1024
RID_INFO, RK_INFO, MAIN_INFO = b"bentcorner-rescue-id-v2", b"bentcorner-rescue-v2", b"bentcorner-main-v2"

PAIR = json.loads((ROOT / "docs" / "web" / "pairing-vectors.json").read_text("utf-8"))
SEED = PAIR["seed_b64"]
SALT = bytes(range(0xA0, 0xB0))                         # 16 bytes – a made-up ID salt
NONCE = bytes(range(0x30, 0x48))                        # 24 bytes
T = 1793600000
DEV_ID = "d0123456789abcdef"                            # a made-up joining device
DEV_SIGN = SigningKey(bytes(range(0x50, 0x70)))
DEV_BOX = PrivateKey(bytes(range(0x70, 0x90)))
CODES = {"generated": "23456-789AB-CDEFG-HJKMN-PQRS" + pairing._check_char("23456789ABCDEFGHJKMNPQRS"),
         "own": "  Mein   Garten 2026!  "}


def _js(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def keys(code, salt):
    n = pairing.norm_rescue(code).encode("utf-8")
    s1 = argon2id.kdf(32, n, STAGE1_SALT, opslimit=STAGE1_OPS, memlimit=STAGE1_MEM)
    s2 = argon2id.kdf(32, n, salt, opslimit=STAGE2_OPS, memlimit=STAGE2_MEM)
    return {"rid": hashlib.blake2b(RID_INFO, digest_size=16, key=s1).hexdigest(),
            "rk": hashlib.blake2b(RK_INFO, digest_size=32, key=s2).digest(),
            "main": hashlib.blake2b(MAIN_INFO, digest_size=32, key=s2).digest()}


def one(name, code):
    k = keys(code, SALT)
    salt_b64 = base64.b64encode(SALT).decode()
    address = pairing.code_of_seed(SEED)
    inner = _js({"code": address, "salt": salt_b64, "seed": SEED, "v": 2})
    box = base64.b64encode(bytes(SecretBox(k["rk"]).encrypt(inner.encode("utf-8"), NONCE))).decode()
    envelope = base64.b64encode(_js({"box": box, "salt": salt_b64, "v": 2}).encode("utf-8")).decode()
    main = SigningKey(k["main"])
    main_pk = base64.b64encode(bytes(main.verify_key)).decode()
    ident = SigningKey(base64.b64decode(SEED))
    set_line = f"guard_set|{address}|{main_pk}|{T}|{salt_b64}"
    req_line = f"guard_req|{address}|{main_pk}|{k['rid']}|{hashlib.sha256(envelope.encode('ascii')).hexdigest()}|{T}|{salt_b64}"
    sig = lambda key, line: base64.b64encode(key.sign(line.encode("utf-8")).signature).decode()  # noqa: E731
    dev_spk = base64.b64encode(bytes(DEV_SIGN.verify_key)).decode()
    dev_bpk = base64.b64encode(bytes(DEV_BOX.public_key)).decode()
    add_line = f"dev_add|{address}|{DEV_ID}|{dev_spk}|{dev_bpk}|||{T}"
    return {"name": name, "code_typed": code, "code_norm": pairing.norm_rescue(code),
            "rid": k["rid"], "rk_hex": k["rk"].hex(), "main_seed_hex": k["main"].hex(), "main_pk_b64": main_pk,
            "inner_json": inner, "envelope": envelope,
            "guard_set_line": set_line, "guard_set_sig": sig(ident, set_line), "guard_set_sig_main": sig(main, set_line),
            "guard_req_line": req_line, "guard_req_sig": sig(ident, req_line),
            "dev_add": {"dev_id": DEV_ID, "dev_sign_seed_hex": bytes(DEV_SIGN).hex(), "dev_sign_pk_b64": dev_spk,
                        "dev_box_sk_hex": bytes(DEV_BOX).hex(), "dev_box_pk_b64": dev_bpk, "line": add_line,
                        "sig_id": sig(ident, add_line), "sig_dev": sig(DEV_SIGN, add_line),
                        "sig_main": sig(main, add_line)}}


def build():
    return {"about": __doc__.split("    python")[0].strip(),
            "seed_b64": SEED, "address": pairing.code_of_seed(SEED), "salt_hex": SALT.hex(),
            "salt_b64": base64.b64encode(SALT).decode(), "nonce_hex": NONCE.hex(), "t": T,
            "stage1": {"salt_ascii": STAGE1_SALT.decode(), "ops": STAGE1_OPS, "mem_bytes": STAGE1_MEM},
            "stage2": {"ops": STAGE2_OPS, "mem_bytes": STAGE2_MEM},
            "infos": {"rid": RID_INFO.decode(), "rk": RK_INFO.decode(), "main": MAIN_INFO.decode()},
            "cases": [one(n, c) for n, c in CODES.items()]}


if __name__ == "__main__":
    out = ROOT / "docs" / "web" / "code-vectors-v2.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(out)
