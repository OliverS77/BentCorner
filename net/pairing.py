"""Pairing (Koppeln) – reference of docs/web/PAIRING.md (version 2): the desktop and the web app become the SAME
identity (the Ed25519 seed of net/relay.py). Pure functions, no network, not wired into the app yet (the desktop part
comes after Oliver's review); the web app implements the same steps and checks them against the test
vectors.

    old device (has the identity)              new device (phone)
    code = 10 chars, shown as "XXXXX XXXXX" (a space since 0.9.8, lead 13.11.; typed with dash/space as you like)
    and as the picture code (NewGuy's 2D code,
    carries the same 10 characters)     ---->  camera reads the picture – or the user types the code
    POST /v1/pair/put {pid, sealed}            POST /v1/pair/get {pid} (once – the server deletes it on fetch)
    polls /v1/pair/state -> "fetched"          payload = open_sealed(code, data) -> seed (+ extras)

ONE secret for both ways in (camera or typing): a 256-bit QR secret next to a typed way would add nothing, the
weaker way decides. The server only ever sees pid and the sealed bytes, never the code.
slow = Argon2id(norm_code(code), salt=SALT, ops 2, mem 64 MiB, 32 B)
pid  = BLAKE2b-128(key=slow, msg="bentcorner-pair-id-v2")      key = BLAKE2b-256(key=slow, msg="bentcorner-pair-v2")
sealed = base64(nonce(24) + crypto_secretbox(payload JSON, nonce, key))     (libsodium: crypto_secretbox_easy)
picture = picture_bytes(code): 1 byte VERSION + the code as a 7-byte number (base 31, big-endian) – NewGuy adds RS.
"""
import base64
import hashlib
import json
import secrets

VERSION = 2                           # v1 (QR + PIN) was never released; a new code format = a new version
SALT = b"bentcorner-pair2"            # 16 bytes, fixed: every code is random and used once
KEY_INFO = b"bentcorner-pair-v2"
ID_INFO = b"bentcorner-pair-id-v2"
OPS, MEM = 2, 64 * 1024 * 1024        # Argon2id "interactive" (libsodium OPSLIMIT/MEMLIMIT_INTERACTIVE) – fixed per version
MAX_PAYLOAD = 48 * 1024               # JSON before sealing (the server takes 64 KB)
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"   # no 0 O 1 I L: nothing to mix up when typing
CODE_LEN = 10                         # 31^10 ≈ 2^49.5 – see PAIRING.md §2


class PairError(Exception):
    pass


def new_code():
    """10 characters, shown as "XXXXX XXXXX" (lead 13.11.: a space like the protection code; only the display –
    the keys come from norm_code, so devices with the old dash pair as before)."""
    c = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
    return c[:5] + " " + c[5:]


def norm_code(code):
    """What the user typed -> the 10 characters (dash, spaces, lowercase allowed). Wrong -> PairError."""
    c = "".join(str(code or "").upper().split()).replace("-", "")
    if len(c) != CODE_LEN or any(ch not in ALPHABET for ch in c):
        raise PairError("the code has 10 characters (letters and digits)")
    return c


def picture_bytes(code):
    """Content of the picture code: VERSION + the code as a number (31^10 < 2^56: 7 bytes, big-endian)."""
    n = 0
    for ch in norm_code(code):
        n = n * 31 + ALPHABET.index(ch)
    return bytes([VERSION]) + n.to_bytes(7, "big")


def code_of_picture(data):
    """Bytes read from the picture code (after RS) -> "XXXXX XXXXX". Other version or no code -> PairError."""
    data = bytes(data)
    if len(data) != 8 or data[0] != VERSION:
        raise PairError("not a Bent°Corner pairing code (or from a newer version)")
    n = int.from_bytes(data[1:], "big")
    if n >= 31 ** CODE_LEN:
        raise PairError("damaged pairing code")
    out = ""
    for _ in range(CODE_LEN):
        n, r = divmod(n, 31)
        out = ALPHABET[r] + out
    return out[:5] + " " + out[5:]


def _slow(code):
    from nacl.pwhash import argon2id
    return argon2id.kdf(32, norm_code(code).encode("ascii"), SALT, opslimit=OPS, memlimit=MEM)


def pair_id(code, slow=None):
    """Mailbox slot of this pairing: 32 hex characters (needs the Argon2id step – no cheap check of a guess)."""
    return hashlib.blake2b(ID_INFO, digest_size=16, key=slow or _slow(code)).hexdigest()


def derive_key(code, slow=None):
    return hashlib.blake2b(KEY_INFO, digest_size=32, key=slow or _slow(code)).digest()


def slot(code):
    """-> (pid, key) with one Argon2id run (36 ms on the dev PC, a few hundred on a phone)."""
    s = _slow(code)
    return pair_id(code, s), derive_key(code, s)


def seal(code, payload, nonce=None, key=None):
    """payload (dict with at least "seed") -> sealed text for /v1/pair/put. key: from slot(code) – no second run."""
    from nacl.secret import SecretBox
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(raw) > MAX_PAYLOAD:
        raise PairError("too much to pair at once")
    box = SecretBox(key or derive_key(code))
    sealed = box.encrypt(raw, nonce) if nonce is not None else box.encrypt(raw)
    return base64.b64encode(bytes(sealed)).decode()


def open_sealed(code, data, key=None):
    """Sealed text from /v1/pair/get -> payload. Wrong code or damaged data -> PairError (the server has already
    deleted it: pair again)."""
    from nacl.exceptions import CryptoError
    from nacl.secret import SecretBox
    try:
        raw = SecretBox(key or derive_key(code)).decrypt(base64.b64decode(data))
        payload = json.loads(raw.decode("utf-8"))
    except (CryptoError, ValueError, TypeError):
        raise PairError("wrong code or damaged data") from None
    if not isinstance(payload, dict) or payload.get("v") != 1 or not isinstance(payload.get("seed"), str)             or not payload.get("seed"):
        raise PairError("unknown pairing data")
    try:   # a damaged seed is a PairError too – never another error that leaves the pairing half done (review 08.11.)
        same = code_of_seed(payload["seed"]) == payload.get("code")
    except (ValueError, TypeError):
        same = False
    if not same:
        raise PairError("identity does not match its address")
    return payload


def code_of_seed(seed_b64):
    """Address of an identity (as net/relay.my_code): SHA-256 of the Ed25519 public key, 16 hex characters."""
    from nacl.signing import SigningKey
    pk = bytes(SigningKey(base64.b64decode(seed_b64)).verify_key)
    return hashlib.sha256(pk).hexdigest()[:16].upper()


def payload_of(seed_b64, extra=None):
    """What the old device sends: {"v": 1, "code", "seed", "extra": {…}} – extra = the relay state the new device
    needs too (friends with their board keys; format of net/relay settings["relay"]["friends"])."""
    out = {"v": 1, "code": code_of_seed(seed_b64), "seed": seed_b64}
    if extra:
        out["extra"] = extra
    return out


# ---------- Vault (Fach, /v1/vault): the content is sealed with a key only the identity's devices have ----------
VAULT_INFO = b"bentcorner-vault-v1"


def vault_key(seed_b64):
    """Key of the own vault: BLAKE2b-256(key=seed, msg="bentcorner-vault-v1") – every paired device derives the same."""
    return hashlib.blake2b(VAULT_INFO, digest_size=32, key=base64.b64decode(seed_b64)).digest()


def vault_seal_bytes(seed_b64, raw, nonce=None):
    """Bytes -> base64(nonce(24) + crypto_secretbox). The sync packages (collection/syncops.pack: zlib of canonical
    JSON) go through this one."""
    from nacl.secret import SecretBox
    box = SecretBox(vault_key(seed_b64))
    return base64.b64encode(bytes(box.encrypt(raw, nonce) if nonce is not None else box.encrypt(raw))).decode()


def vault_open_bytes(seed_b64, data):
    from nacl.exceptions import CryptoError
    from nacl.secret import SecretBox
    try:
        return SecretBox(vault_key(seed_b64)).decrypt(base64.b64decode(data))
    except (CryptoError, ValueError):
        raise PairError("vault item not readable with this identity") from None


def vault_seal(seed_b64, obj, nonce=None):
    """One vault item as JSON (the rescue envelope): JSON -> base64(nonce(24) + crypto_secretbox)."""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return vault_seal_bytes(seed_b64, raw, nonce)


def vault_open(seed_b64, data):
    try:
        return json.loads(vault_open_bytes(seed_b64, data).decode("utf-8"))
    except ValueError:
        raise PairError("vault item not readable with this identity") from None


# ---------- Rescue code (Wiederherstellungscode, docs/SYNC-PLAN.md §2): all devices gone, the vault still there ----------
# The code opens a small envelope on the server that holds the CURRENT seed – the code is not the seed, so it stays
# the same when the seed changes ("new code" / "remove device"). Generated: 24 random characters (31^24 ≈ 2^119) + 1
# check character, shown in blocks of 5, typed with dashes/spaces/lowercase as you like; or chosen by the user (Oliver
# 07.11., minimum strength: collection/codestrength). Either way one Argon2id run (code_keys).
RESCUE_LEN = 24
MAX_RESCUE = 4096                     # the sealed envelope on the server (base64)


def _check_char(chars):
    """Alphabet[(Σ (i+1)·index) mod 31] – 31 is prime and the weights 1..24 differ: any single wrong character and any
    two neighbours swapped change it."""
    return ALPHABET[sum((i + 1) * ALPHABET.index(ch) for i, ch in enumerate(chars)) % 31]


def new_rescue_code():
    c = "".join(secrets.choice(ALPHABET) for _ in range(RESCUE_LEN))
    c += _check_char(c)
    # blocks with spaces, not dashes (Oliver 12.11., after the 0.9.7 ship): „XXXXX XXXXX …“ – the same 25 characters,
    # the same strength; norm_rescue drops spaces and dashes, so codes made earlier with dashes stay valid
    return " ".join(c[i:i + 5] for i in range(0, 25, 5))


def norm_rescue(code):
    """Typed code -> the text the keys come from. In the generated format (25 characters of the alphabet, dashes/spaces/
    lowercase as you like) -> those 25 characters, a typo (check character) -> PairError. Anything else is a code the
    user chose (Oliver 07.11.): Unicode NFKC, outer spaces away, inner runs of spaces as one – upper/lower case count.
    Empty -> PairError."""
    raw = str(code or "")
    c = "".join(raw.upper().split()).replace("-", "")
    if len(c) == RESCUE_LEN + 1 and all(ch in ALPHABET for ch in c):
        if _check_char(c[:-1]) != c[-1]:
            raise PairError("the code has a typo")
        return c
    import unicodedata
    own = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not own:
        raise PairError("no code")
    return own


# The code with a salt per ID (S5 = b, Oliver 08.11.; docs/web/PAIRING.md §4a, vectors docs/web/code-vectors-v2.json).
# Two stages so a restore without a device still works with the code alone:
#   finding: a fixed salt, 64 MiB – it only says where the envelope lies (the box brakes rescue/get, a rid of another
#            address -> 409); legal's floor (>= 64 MiB, >= 3)
#   keys:    the ID's own 16-byte salt, 128 MiB (lead 07.11.) – the seed is attackable offline, now only per ID
STAGE1_SALT = b"bentcorner-code2"   # 16 bytes
STAGE1_OPS, STAGE1_MEM = 3, 64 * 1024 * 1024
CODE_OPS, CODE_MEM = 3, 128 * 1024 * 1024
RESCUE_ID_INFO = b"bentcorner-rescue-id-v2"
RESCUE_INFO = b"bentcorner-rescue-v2"
MAIN_INFO = b"bentcorner-main-v2"
SALT_LEN = 16


def new_salt():
    """The ID's salt (standard base64) – made by the device that sets the FIRST code of the ID."""
    return base64.b64encode(secrets.token_bytes(SALT_LEN)).decode()


def _salt_bytes(salt_b64):
    try:
        raw = base64.b64decode(str(salt_b64 or ""), validate=True)
    except (ValueError, TypeError):
        raw = b""
    if len(raw) != SALT_LEN:
        raise PairError("no valid salt for this ID")
    return raw


def rescue_rid(code):
    """Stage 1: the envelope's number (32 lowercase hex) – finding only."""
    from nacl.pwhash import argon2id
    s1 = argon2id.kdf(32, norm_rescue(code).encode("utf-8"), STAGE1_SALT, opslimit=STAGE1_OPS, memlimit=STAGE1_MEM)
    return hashlib.blake2b(RESCUE_ID_INFO, digest_size=16, key=s1).hexdigest()


def guard_keys(code, salt_b64):
    """Stage 2: -> {"rk": 32 B envelope key, "main": 32 B Ed25519 seed of the protection key, "salt"}."""
    from nacl.pwhash import argon2id
    s2 = argon2id.kdf(32, norm_rescue(code).encode("utf-8"), _salt_bytes(salt_b64), opslimit=CODE_OPS,
                      memlimit=CODE_MEM)
    return {"rk": hashlib.blake2b(RESCUE_INFO, digest_size=32, key=s2).digest(),
            "main": hashlib.blake2b(MAIN_INFO, digest_size=32, key=s2).digest(), "salt": str(salt_b64)}


def code_keys(code, salt_b64):
    """Both stages: -> {"rid", "rk", "main", "salt"} (setting a code: its envelope and its key in one go)."""
    return dict(guard_keys(code, salt_b64), rid=rescue_rid(code))


def main_signing(code, salt_b64):
    """The protection code (= the rescue code, one code) -> the Ed25519 key whose public half the server keeps."""
    from nacl.signing import SigningKey
    return SigningKey(guard_keys(code, salt_b64)["main"])


def _js(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def rescue_seal(code, seed_b64, salt_b64, nonce=None, keys=None):
    """Envelope v2: base64(JSON {"box": b64(nonce + secretbox(inner)), "salt", "v": 2}),
    inner = JSON {"code": address, "salt", "seed", "v": 2} – the salt in the clear for a device without the ID, inside
    it must be the same. keys: guard_keys/code_keys already made (one Argon2id run per stage)."""
    from nacl.secret import SecretBox
    keys = keys or guard_keys(code, salt_b64)
    inner = _js({"code": code_of_seed(seed_b64), "salt": str(salt_b64), "seed": seed_b64, "v": 2}).encode("utf-8")
    box = SecretBox(keys["rk"])
    sealed = bytes(box.encrypt(inner, nonce) if nonce is not None else box.encrypt(inner))
    out = base64.b64encode(_js({"box": base64.b64encode(sealed).decode(), "salt": str(salt_b64), "v": 2})
                           .encode("utf-8")).decode()
    if len(out) > MAX_RESCUE:
        raise PairError("rescue envelope too large")
    return out


def rescue_header(data):
    """-> the clear header {"box", "salt", "v": 2} of an envelope, PairError if it is none (v1, damaged)."""
    try:
        head = json.loads(base64.b64decode(str(data or ""), validate=True).decode("utf-8"))
    except (ValueError, TypeError):
        head = None
    if not isinstance(head, dict) or head.get("v") != 2 or not isinstance(head.get("box"), str):
        raise PairError("rescue envelope not readable with this code")
    _salt_bytes(head.get("salt"))
    return head


def rescue_open(code, data, keys=None):
    """-> (seed b64, salt b64). Checked: the envelope opens with this code (and the salt of its header), the salt inside
    is the same, and its seed belongs to its address. A v1 envelope (no salt) is not opened any more."""
    from nacl.exceptions import CryptoError
    from nacl.secret import SecretBox
    head = rescue_header(data)
    keys = keys or guard_keys(code, head["salt"])
    try:
        d = json.loads(SecretBox(keys["rk"]).decrypt(base64.b64decode(head["box"])).decode("utf-8"))
        ok = (isinstance(d, dict) and d.get("v") == 2 and d.get("salt") == head["salt"]
              and isinstance(d.get("seed"), str) and code_of_seed(d.get("seed") or "") == d.get("code"))
    except (CryptoError, ValueError, TypeError):
        raise PairError("rescue envelope not readable with this code") from None
    if not ok:
        raise PairError("rescue envelope does not match its address")
    return d["seed"], head["salt"]


