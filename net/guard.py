"""The protection code (Schutz-Code, Oliver 07.11.2026: optional, offered when pairing; lead: the SAME code as the rescue
code – one code). Set, „Gerät entfernen“ / „Neuer Code“ (rekey) and deleting everything online (forget) need it; not
set, every own device may remove every other one.

The server keeps only the public key derived from the code (/v1/guard, Gordon 07.11.) and never hands it out; vault/get
says only whether one is set and whether a request to replace it runs. The code itself is never stored – not here
either: it is typed in for the one action and dropped (legal 07.11.).

    salt_of(settings)                the ID's salt (S5 = b): relay.guard_salt, learnt from vault/get, poll, the envelope or
                                     the pairing payload; asked with the minute question if unknown – None if no code is set
    main_pk(code, salt)              the public key (pairing.guard_keys: Argon2id with the ID's salt + BLAKE2b -> Ed25519)
    sign(code, msg, keys, salt)      sig_main over the same message as the seed's "sig"
    request(settings, new_code)      also carries the new code's envelope (pending until the request takes effect)
    set_code(settings, code, old)    /v1/guard/set – the first one with the seed alone, a change with the old code
    request(settings, new_code)      /v1/guard/request – „code lost“: any own device; takes effect after 14 days
    decline(settings, code)          /v1/guard/decline – only with the (current) code
Errors: VaultError 403 {"main_required"} – the code is needed or wrong; 429 {"retry_after"} – too many wrong tries for
now (a right code still goes through – Gordon/legal 07.11.).
"""
import time

from net import pairing, relay


def salt_of(settings, ask=True):
    """The ID's salt (S5 = b, docs/web/PAIRING.md §4a) or None (no code set yet). ask: unknown here -> the minute
    question (/v1/poll gives guard.salt)."""
    st = relay.state(settings)
    if st.get("guard_salt") or not ask:
        return st.get("guard_salt") or None
    try:
        from net import poll
        learn(settings, (poll.ask(settings) or {}).get("guard"))
    except Exception:  # noqa: BLE001 – offline: unknown for now (signing with a code then fails cleanly)
        pass
    return st.get("guard_salt") or None


def learn(settings, info):
    """guard = {"set", "salt"} from vault/get, board/get or poll -> remembered for this ID."""
    salt = (info or {}).get("salt") if isinstance(info, dict) else None
    if salt and relay.state(settings).get("guard_salt") != salt:
        relay.state(settings)["guard_salt"] = str(salt)


def _signing(code, keys=None, salt=None):
    from nacl.signing import SigningKey
    if keys is None:
        try:
            pairing.norm_rescue(code)
        except pairing.PairError:
            # a typo (the check character) or nothing typed: for the page the same as a wrong code – nothing was sent
            # (guide run 09.11.: joining showed an error and dropped the field)
            from net.vault import VaultError
            raise VaultError(403, "wrong protection code", {"main_required": True, "guard_wrong": True}) from None
        if not salt:
            raise pairing.PairError("the protection code's salt is unknown – online once first")
        keys = pairing.guard_keys(code, salt)
    return SigningKey(keys["main"])


def main_pk(code, salt=None, keys=None):
    return relay._b64(_signing(code, keys, salt).verify_key)


def sign(code, msg, keys=None, salt=None):
    """keys: pairing.guard_keys/code_keys(code, salt) when the caller has them already (one Argon2id run per action);
    else salt: the ID's (salt_of)."""
    return relay._b64(_signing(code, keys, salt).sign(msg.encode("utf-8")).signature)


def _post(settings, path, payload):
    from net import vault
    return vault._post(settings, path, payload)


def set_code(settings, code, old=None, keys=None):
    """keys: pairing.code_keys(code, salt) already made (sync_ctl: one run per stage for the code and its envelope).
    The salt is the ID's (keys["salt"]): a first code brings a new one (setup_salt), a change keeps it.
    409 {guard_first_only_alone}: a first code only while at most one device is registered (Gordon 8597915)."""
    me, t = relay.my_code(settings), int(time.time())
    salt = (keys or {}).get("salt") or salt_of(settings) or pairing.new_salt()   # none yet: the ID's first code
    pk = main_pk(code, salt, keys)
    msg = f"guard_set|{me}|{pk}|{t}|{salt}"
    payload = {"code": me, "main_pk": pk, "t": t, "salt": salt, "sig": relay._signed(settings, msg)}
    if old:
        payload["sig_main"] = sign(old, msg, salt=salt)
    from net import devkeys
    res = _post(settings, "/v1/guard/set", devkeys.attach(settings, payload, msg))
    relay.state(settings)["guard_salt"] = salt
    return res


def setup_salt(settings):
    """The salt for setting a code: the ID's if it has one, else a new one (the first code of the ID). Not asked from the
    server here – the sync's vault/get and the minute question bring it before any code is set or changed."""
    return salt_of(settings, ask=False) or pairing.new_salt()


def request(settings, new_code):
    """„Code lost“: the new code's key AND its envelope (Gordon 07.11.: kept hidden as pending, it replaces the old
    envelope when the request takes effect after 14 days; dropped on decline) – otherwise a rescue without a device
    with the new code would find nothing. One Argon2id run; the code itself never leaves this call."""
    import hashlib
    salt = salt_of(settings) or pairing.new_salt()   # the ID keeps its salt (asked if unknown here); the replacing
    # code is derived with it – only an ID that never had a code gets a new one
    keys = pairing.code_keys(new_code, salt)
    relay._signing(settings)
    data = pairing.rescue_seal(new_code, settings["relay"]["seed"], salt, keys=keys)
    me, t = relay.my_code(settings), int(time.time())
    pk, rid = main_pk(new_code, salt, keys), keys["rid"]
    msg = f"guard_req|{me}|{pk}|{rid}|{hashlib.sha256(data.encode('ascii')).hexdigest()}|{t}|{salt}"
    from net import devkeys
    return _post(settings, "/v1/guard/request", devkeys.attach(
        settings, {"code": me, "new_pk": pk, "rid": rid, "data": data, "t": t, "salt": salt,
                   "sig": relay._signed(settings, msg)}, msg))


def decline(settings, code):
    me, t = relay.my_code(settings), int(time.time())
    msg = f"guard_decline|{me}|{t}"
    from net import devkeys
    return _post(settings, "/v1/guard/decline", devkeys.attach(
        settings, {"code": me, "t": t, "sig": relay._signed(settings, msg),
                   "sig_main": sign(code, msg, salt=salt_of(settings))}, msg))
