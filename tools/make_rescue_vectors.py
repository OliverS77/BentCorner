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


def build():
    code = BODY + pairing._check_char(BODY)
    shown = "-".join(code[i:i + 5] for i in range(0, 25, 5))
    typo = code[:3] + ("3" if code[3] != "3" else "4") + code[4:]
    swap = code[:6] + code[7] + code[6] + code[8:]
    return {
        "about": "The rescue code's FORMAT (net/pairing.py, docs/SYNC-PLAN.md §2): code = 24 characters + check "
                 "character Alphabet[(sum of (i+1)*index) mod 31], typos and swaps rejected. The keys, the envelope "
                 "and the guard lines (salt per ID, S5 = b): docs/web/code-vectors-v2.json.",
        "alphabet": pairing.ALPHABET,
        "code": code,
        "code_shown": shown,
        "code_typed": shown.lower().replace("-", " "),
        "seed_b64": SEED,
        "address": pairing.code_of_seed(SEED),
        "typo_rejected": typo,
        "swap_rejected": swap,
        "sign": {"put": "rescue_put|<address>|<rid>|<sha256 hex of the data string (its base64 text as ASCII, as /v1/send)>|<t>", "del": "rescue_del|<address>|<t>"},
    }


if __name__ == "__main__":
    out = ROOT / "docs" / "web" / "rescue-vectors.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("written", out)
