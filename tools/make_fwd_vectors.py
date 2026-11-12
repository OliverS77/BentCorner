r"""Writes docs/web/fwd-vectors.json: the signed letter after „remove one device“ (B5, review 08.11. S6) – the line the
remover signs with the OLD identity key and its signature, for fixed made-up seeds (no real keys). The web checks its
own signing against it (tests/test_b5.py Vectors does the same here).
    .venv\Scripts\python tools\make_fwd_vectors.py"""
import base64
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from net import devkeys, pairing, relay  # noqa: E402

old_seed = base64.b64encode(bytes(range(32))).decode()
new_seed = base64.b64encode(bytes(range(32, 64))).decode()
s = {"relay": {"seed": old_seed}}
old, new, dev, t = relay.my_code(s), pairing.code_of_seed(new_seed), "d00112233445566778", 1800000000
line = devkeys.fwd_line(old, new, dev, t, new_seed)
out = {"_comment": "B5 letter (DEVICE-KEYS §2, review 08.11. S6): sig = Ed25519 of line with the OLD identity key "
                   "(the seed's signing key); the receiving device checks v, old == its address, dev == its device id, "
                   "the signature with its own (old) seed, code_of_seed(seed) == code. Made-up seeds.",
       "v": devkeys.FWD_V, "old_seed": old_seed, "old": old, "new_seed": new_seed, "new": new, "dev": dev, "t": t,
       "line": line, "sig": relay._signed(s, line)}
(ROOT / "docs" / "web" / "fwd-vectors.json").write_text(json.dumps(out, indent=1) + "\n", "utf-8")
print("docs/web/fwd-vectors.json:", line)
