"""Identity and signatures as pure functions – the reference the web app's JS core checks against
(docs/web/identity-vectors.json, tools/make_identity_vectors.py). Same rules as net/relay.py and net/pairing.py,
which keep their own code; tests/test_identity.py checks that both agree.

- identity: a 32-byte seed (base64) -> Ed25519 signing key; address = SHA-256(public key) hex, first 16, upper case;
  the encryption key pair (Curve25519) is derived from the same key (libsodium crypto_sign_ed25519_*_to_curve25519)
- request signatures: Ed25519 over a "|"-joined line, e.g. "send|FROM|TO|<sha256 hex of data>|t" – data hashed
  as its base64 TEXT (ASCII), never the decoded bytes
- parcel (mailbox): envelope JSON (compact) -> zlib -> signed (Ed25519, signature + message) -> sealed box for the
  recipient's Curve25519 key -> base64. Opening checks size, signature and that "from" fits the sender's key
- board (posted lists/binders): JSON -> zlib -> secretbox with a random key (nonce + box) -> base64
"""
import base64
import hashlib
import json
import zlib

ADDRESS_LEN = 16
MAX_PLAIN = 60 * 1024            # compressed parcel (the server takes 64 KB)
MAX_UNPACKED = 4 * 1024 * 1024   # decompressed parcel at most 4 MB (zip bombs)


class IdentityError(Exception):
    pass


def _b64(b):
    return base64.b64encode(bytes(b)).decode()


def _sk(seed_b64):
    from nacl.signing import SigningKey
    seed = base64.b64decode(seed_b64)
    if len(seed) != 32:
        raise IdentityError("seed must be 32 bytes")
    return SigningKey(seed)


def sign_pk(seed_b64):
    return _b64(_sk(seed_b64).verify_key)


def address_of_key(sign_pk_b64):
    return hashlib.sha256(base64.b64decode(sign_pk_b64)).hexdigest()[:ADDRESS_LEN].upper()


def address(seed_b64):
    return address_of_key(sign_pk(seed_b64))


def box_keys(seed_b64):
    """-> (Curve25519 public, Curve25519 private) as base64 – what parcels are sealed for / opened with."""
    sk = _sk(seed_b64)
    return _b64(sk.verify_key.to_curve25519_public_key()), _b64(sk.to_curve25519_private_key())


def digest(data_b64):
    """sha256 hex of a data string as the server signs it: over the base64 text (ASCII)."""
    return hashlib.sha256(str(data_b64).encode("ascii")).hexdigest()


def line(*parts):
    """The signed line of a request: parts joined with "|" (e.g. line("fetch", code, t))."""
    return "|".join(str(p) for p in parts)


def sign(seed_b64, text):
    """Detached Ed25519 signature of a line (UTF-8) -> base64. Ed25519 is deterministic: same seed + text, same sig."""
    return _b64(_sk(seed_b64).sign(str(text).encode("utf-8")).signature)


def verify(sign_pk_b64, text, sig_b64):
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
    try:
        VerifyKey(base64.b64decode(sign_pk_b64)).verify(str(text).encode("utf-8"), base64.b64decode(sig_b64))
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


def parcel_seal(seed_b64, to_sign_pk_b64, env):
    """A parcel for the mailbox (net/relay.send without the network). Sealed boxes use a fresh key each time: the
    result differs every call, only opening is fixed in the vectors."""
    from nacl.public import SealedBox
    from nacl.signing import VerifyKey
    raw = zlib.compress(json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    if len(raw) > MAX_PLAIN:
        raise IdentityError("parcel too big")
    signed = bytes(_sk(seed_b64).sign(raw))
    pk = VerifyKey(base64.b64decode(to_sign_pk_b64)).to_curve25519_public_key()
    return _b64(SealedBox(pk).encrypt(signed))


def parcel_open(seed_b64, data_b64, sender_sign_pk_b64):
    """-> the envelope. Raises IdentityError if it can't be opened, is too big, isn't signed by the sender's key
    or claims another sender ("from" must be the address of that key)."""
    from nacl.public import SealedBox
    from nacl.signing import VerifyKey
    try:
        signed = SealedBox(_sk(seed_b64).to_curve25519_private_key()).decrypt(base64.b64decode(data_b64))
        VerifyKey(base64.b64decode(sender_sign_pk_b64)).verify(signed)
        dec = zlib.decompressobj()
        raw = dec.decompress(signed[64:], MAX_UNPACKED)
        if dec.unconsumed_tail:
            raise IdentityError("parcel too big when unpacked")
        env = json.loads(raw.decode("utf-8"))
    except IdentityError:
        raise
    except Exception:  # noqa: BLE001 – broken or forged
        raise IdentityError("parcel not readable or not signed by the sender") from None
    if not isinstance(env, dict) or env.get("from") != address_of_key(sender_sign_pk_b64):
        raise IdentityError("parcel claims another sender")
    return env


def board_seal(key_b64, payload, nonce=None):
    from nacl.secret import SecretBox
    raw = zlib.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    box = SecretBox(base64.b64decode(key_b64))
    return _b64(box.encrypt(raw, nonce) if nonce is not None else box.encrypt(raw))


def board_open(key_b64, data_b64, limit=MAX_UNPACKED * 8):
    from nacl.secret import SecretBox
    try:
        dec = zlib.decompressobj()
        raw = dec.decompress(SecretBox(base64.b64decode(key_b64)).decrypt(base64.b64decode(data_b64)), limit)
        if dec.unconsumed_tail:
            raise IdentityError("posted content too big")
        return json.loads(raw.decode("utf-8"))
    except IdentityError:
        raise
    except Exception:  # noqa: BLE001
        raise IdentityError("posted content not readable with this key") from None
