"""Writes docs/web/rescue-vectors.json: fixed test vectors for the rescue code (net/pairing.py, docs/SYNC-PLAN.md §2).
The web app and the server (rid/data checks) test against the same file. Test seed only – never a real one.

    python tools/make_rescue_vectors.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from net import pairing  # noqa: E402

PAIR = json.loads((ROOT / "docs" / "web" / "pairing-vectors.json").read_text("utf-8"))
SEED = PAIR["seed_b64"]                       # the same test seed as the pairing vectors
BODY = "23456789ABCDEFGHJKMNPQRS"              # 24 characters, the first of the alphabet
NONCE = bytes(range(0x30, 0x48))               # 24 bytes


def build():
    code = BODY + pairing._check_char(BODY)
    shown = "-".join(code[i:i + 5] for i in range(0, 25, 5))
    rid, rk = pairing.rescue_keys(code)
    typo = code[:3] + ("3" if code[3] != "3" else "4") + code[4:]
    swap = code[:6] + code[7] + code[6] + code[8:]
    return {
        "about": "Test vectors for the rescue code (net/pairing.py, docs/SYNC-PLAN.md §2). Bytes as hex unless noted. "
                 "code = 24 characters + check character Alphabet[(sum of (i+1)*index) mod 31]; key of both BLAKE2b = "
                 "the 25 normalised characters as ASCII; data = base64(nonce + secretbox(JSON sorted, no spaces)).",
        "alphabet": pairing.ALPHABET,
        "code": code,
        "code_shown": shown,
        "code_typed": shown.lower().replace("-", " "),
        "rid": rid,
        "rk_hex": rk.hex(),
        "seed_b64": SEED,
        "address": pairing.code_of_seed(SEED),
        "nonce_hex": NONCE.hex(),
        "envelope_json": json.dumps({"code": pairing.code_of_seed(SEED), "seed": SEED, "v": 1},
                                    separators=(",", ":"), sort_keys=True),
        "data_b64": pairing.rescue_seal(code, SEED, NONCE),
        "typo_rejected": typo,
        "swap_rejected": swap,
        "sign": {"put": "rescue_put|<address>|<rid>|<sha256 hex of the data string (its base64 text as ASCII, as /v1/send)>|<t>", "del": "rescue_del|<address>|<t>"},
    }


if __name__ == "__main__":
    out = ROOT / "docs" / "web" / "rescue-vectors.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("written", out)
