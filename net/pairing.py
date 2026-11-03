"""Pairing (Koppeln) – reference of docs/web/PAIRING.md (version 2): the desktop and the web app become the SAME
identity (the Ed25519 seed of net/relay.py). Pure functions, no network, not wired into the app yet (the desktop part
comes after Oliver's review); the web app implements the same steps and checks them against the test
vectors.

    old device (has the identity)              new device (phone)
    code = 10 chars, shown as "XXXXX-XXXXX"
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
    """10 characters, shown as "XXXXX-XXXXX"."""
    c = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
    return c[:5] + "-" + c[5:]


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
    """Bytes read from the picture code (after RS) -> "XXXXX-XXXXX". Other version or no code -> PairError."""
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
    return out[:5] + "-" + out[5:]


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


def seal(code, payload, nonce=None):
    """payload (dict with at least "seed") -> sealed text for /v1/pair/put."""
    from nacl.secret import SecretBox
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(raw) > MAX_PAYLOAD:
        raise PairError("too much to pair at once")
    box = SecretBox(derive_key(code))
    sealed = box.encrypt(raw, nonce) if nonce is not None else box.encrypt(raw)
    return base64.b64encode(bytes(sealed)).decode()


def open_sealed(code, data):
    """Sealed text from /v1/pair/get -> payload. Wrong code or damaged data -> PairError (the server has already
    deleted it: pair again)."""
    from nacl.exceptions import CryptoError
    from nacl.secret import SecretBox
    try:
        raw = SecretBox(derive_key(code)).decrypt(base64.b64decode(data))
        payload = json.loads(raw.decode("utf-8"))
    except (CryptoError, ValueError):
        raise PairError("wrong code or damaged data") from None
    if not isinstance(payload, dict) or payload.get("v") != 1 or not payload.get("seed"):
        raise PairError("unknown pairing data")
    if code_of_seed(payload["seed"]) != payload.get("code"):
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


def vault_seal(seed_b64, obj, nonce=None):
    """One vault item ("add" package or "snap" snapshot): JSON -> base64(nonce(24) + crypto_secretbox)."""
    from nacl.secret import SecretBox
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    box = SecretBox(vault_key(seed_b64))
    return base64.b64encode(bytes(box.encrypt(raw, nonce) if nonce is not None else box.encrypt(raw))).decode()


def vault_open(seed_b64, data):
    from nacl.exceptions import CryptoError
    from nacl.secret import SecretBox
    try:
        return json.loads(SecretBox(vault_key(seed_b64)).decrypt(base64.b64decode(data)).decode("utf-8"))
    except (CryptoError, ValueError):
        raise PairError("vault item not readable with this identity") from None


# ---------- Rescue code (Wiederherstellungscode, docs/SYNC-PLAN.md §2): all devices gone, the vault still there ----------
# The code opens a small envelope on the server that holds the CURRENT seed – the code is not the seed, so it stays
# the same when the seed changes ("new code" / "remove device"). 24 random characters (31^24 ≈ 2^119, no Argon2
# needed) + 1 check character; shown as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX, typed with dashes/spaces/lowercase as you like.
RESCUE_LEN = 24
RESCUE_INFO = b"bentcorner-rescue-v1"
RESCUE_ID_INFO = b"bentcorner-rescue-id-v1"
MAX_RESCUE = 4096                     # the sealed envelope on the server (base64)


def _check_char(chars):
    """Alphabet[(Σ (i+1)·index) mod 31] – 31 is prime and the weights 1..24 differ: any single wrong character and any
    two neighbours swapped change it."""
    return ALPHABET[sum((i + 1) * ALPHABET.index(ch) for i, ch in enumerate(chars)) % 31]


def new_rescue_code():
    c = "".join(secrets.choice(ALPHABET) for _ in range(RESCUE_LEN))
    c += _check_char(c)
    return "-".join(c[i:i + 5] for i in range(0, 25, 5))


def norm_rescue(code):
    """Typed rescue code -> the 25 characters. Wrong length/characters or a typo (check character) -> PairError."""
    c = "".join(str(code or "").upper().split()).replace("-", "")
    if len(c) != RESCUE_LEN + 1 or any(ch not in ALPHABET for ch in c):
        raise PairError("the rescue code has 25 characters (letters and digits)")
    if _check_char(c[:-1]) != c[-1]:
        raise PairError("the rescue code has a typo")
    return c


def rescue_keys(code):
    """-> (rid: 32 lowercase hex – the envelope's number on the server, rk: 32-byte key). Keyed BLAKE2b, key = the 25
    characters as ASCII."""
    k = norm_rescue(code).encode("ascii")
    rid = hashlib.blake2b(RESCUE_ID_INFO, digest_size=16, key=k).hexdigest()
    rk = hashlib.blake2b(RESCUE_INFO, digest_size=32, key=k).digest()
    return rid, rk


def rescue_seal(code, seed_b64, nonce=None):
    """The envelope: base64(nonce(24) + secretbox({"code": address, "seed", "v": 1})) – JSON sorted, no spaces."""
    from nacl.secret import SecretBox
    raw = json.dumps({"code": code_of_seed(seed_b64), "seed": seed_b64, "v": 1}, separators=(",", ":"),
                     sort_keys=True).encode("utf-8")
    box = SecretBox(rescue_keys(code)[1])
    out = base64.b64encode(bytes(box.encrypt(raw, nonce) if nonce is not None else box.encrypt(raw))).decode()
    if len(out) > MAX_RESCUE:
        raise PairError("rescue envelope too large")
    return out


def rescue_open(code, data):
    """-> the seed (base64). Checked: the envelope opens with this code and its seed belongs to its address."""
    from nacl.exceptions import CryptoError
    from nacl.secret import SecretBox
    try:
        d = json.loads(SecretBox(rescue_keys(code)[1]).decrypt(base64.b64decode(data)).decode("utf-8"))
    except (CryptoError, ValueError):
        raise PairError("rescue envelope not readable with this code") from None
    if d.get("v") != 1 or code_of_seed(d.get("seed") or "") != d.get("code"):
        raise PairError("rescue envelope does not match its address")
    return d["seed"]
