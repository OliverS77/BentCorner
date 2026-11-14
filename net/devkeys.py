"""Device keys (B5, docs/web/DEVICE-KEYS.md; Gordon's box b9d84c2): every own device has its OWN key pair besides the
shared identity – Ed25519 to sign, X25519 to open what is sealed for it alone. Removing ONE device then works: the new
seed is sealed for each remaining device's box key; the removed one gets no envelope (/v1/dev/fwd) and cannot read on.

The keys live only in <data folder>/devkey.json – next to settings.json, NOT in a backup (system/datastore.personal_roots),
not in the vault, not in the rescue envelope. A seed from a backup ZIP alone therefore cannot act as one of the devices.

    mine(settings)                   this device's keys (made on first use) -> {"dev_id", "sign_pk", "box_pk"}
    attach(settings, payload, msg)   dev_id + sig_dev for a device write (rekey, vault/del, guard … – box 403 dev_required)
    invite(settings)                 the signed invitation for a joining device (in the sealed pairing payload)
    register(settings, invite_=None, guard_code=None)   /v1/dev/add -> "ok" | {"pending": True, "until"}
    listing(settings)                /v1/dev/list -> {"list", "reg_version", "dev_request", "devices"}
    decide(settings, about, ok, guard_code=None)   /v1/dev/decide – a join request: allow / decline
    leave(settings)                  /v1/dev/leave – this device signs itself out, then its keys are forgotten
    chain(rows, dev_id)              the device and every device it added (added_by, recursively)
    fetch_fwd(settings, old_code)    after „remove one“: this device's envelope from /v1/dev/fwd, opened -> {"seed", "code"}

Restoring a backup with ANOTHER identity (library F1, lead 08.11.: the backup's identity wins, no question):
    identity_of(settings)            short fingerprint of relay.seed (the ID shown in the profile) or None – never makes one
    device_bits_off(settings)        drops what belongs to THIS device or the old identity's device list (DEVICE_BITS)
    drop_device_state(data_dir)      removes <data_dir>/devkey.json and <data_dir>/sync – nothing else
"""
import base64
import json
import logging
import os
import pathlib
import secrets
import shutil
import threading
import time

from net import relay

log = logging.getLogger("booster")

FILE = "devkey.json"
_lock = threading.Lock()
_cache = {}


def _path():
    from system import datahome
    return datahome.HOME / FILE


def _b64(b):
    return base64.b64encode(bytes(b)).decode()


class Unreadable(OSError):
    """devkey.json is there but can't be read (locked by a virus scanner/OneDrive, damaged): never made anew – new keys
    would cost this device its registration and its envelope (review 08.11., M3). The next try reads it again."""


def _load(create=True):
    """-> the keys; None if there are none (create=False) or the file can't be read now (create=False);
    create=True: new keys ONLY when the file is missing, Unreadable when it is there but unreadable."""
    p = _path()
    with _lock:
        got = _cache.get(str(p))
        if got is not None:
            return got
        try:
            got = json.loads(p.read_text("utf-8"))
            if not (isinstance(got, dict) and got.get("dev_id") and got.get("sign_sk") and got.get("box_sk")):
                raise ValueError("keys missing")
        except FileNotFoundError:
            got = None
        except (OSError, ValueError) as e:
            log.warning("Device key: %s can't be read now (%s) – left as it is", FILE, e.__class__.__name__)
            if create:
                raise Unreadable(f"{FILE} unreadable") from e
            return None
        if got is None and create:
            got = {"dev_id": "d" + secrets.token_hex(8), "sign_sk": _b64(secrets.token_bytes(32)),
                   "box_sk": _b64(secrets.token_bytes(32)), "code": ""}
            _save(p, got)
        if got is not None:
            _cache[str(p)] = got
        return got


def _save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data), "utf-8")
    os.replace(tmp, p)


def _update(**kw):
    """Change the bookkeeping fields (code, pending) – never without the keys: read from the file first."""
    k = _load(False)
    if k is None:
        return
    p = _path()
    with _lock:
        data = dict(k)
        data.update(kw)
        _save(p, data)
        _cache[str(p)] = data


def forget():
    """Leaving / removed: the keys go (legal 07.11.: signing out deletes seed AND device key on this device)."""
    p = _path()
    with _lock:
        _cache.pop(str(p), None)
        try:
            p.unlink()
        except OSError:
            pass


def _signing(k):
    from nacl.signing import SigningKey
    return SigningKey(base64.b64decode(k["sign_sk"]))


def _box(k):
    from nacl.public import PrivateKey
    return PrivateKey(base64.b64decode(k["box_sk"]))


def unreadable():
    """devkey.json is there but can't be read now (M3: never made anew) – the devices page says so (lead 08.11.)."""
    if _load(False) is not None:
        return False
    try:
        return _path().exists()
    except OSError:
        return True


def mine(settings=None, create=True):
    k = _load(create)
    if k is None:
        return None
    return {"dev_id": k["dev_id"], "sign_pk": _b64(_signing(k).verify_key), "box_pk": _b64(_box(k).public_key)}


def registered(settings):
    """Is this device in the registry of its CURRENT address (as far as it knows)?"""
    k = _load(False)
    return bool(k and k.get("code") and k["code"] == relay.my_code(settings))


def sign(msg):
    return _b64(_signing(_load()).sign(msg.encode("utf-8")).signature)


def attach(settings, payload, msg):
    """A device write: dev_id + sig_dev over the same line – only if this device is registered at this address
    (before that the box has no registry and doesn't ask). -> payload."""
    if registered(settings):
        k = _load()
        payload["dev_id"] = k["dev_id"]
        payload["sig_dev"] = sign(msg)
    return payload


def _post(settings, path, payload):
    from net import vault
    return vault._post(settings, path, payload)


def invite(settings):
    """The device showing a pairing code invites the joining one (box 7fe65d1): {by, nonce, t, sig} – inside the sealed
    pairing payload, valid 15 min, once. None if this device isn't registered (an older pairing: a join request)."""
    from net import vault
    if not registered(settings):
        return None
    k = _load()
    code, t = vault._me(settings)
    nonce = secrets.token_urlsafe(16)
    return {"by": k["dev_id"], "nonce": nonce, "t": t, "sig": sign(f"dev_invite|{code}|{k['dev_id']}|{nonce}|{t}")}


def register(settings, invite_=None, guard_code=None, keys=None):
    """/v1/dev/add (box 7fe65d1). invite_: from the pairing payload -> added by that device. guard_code: moving from a
    backup with the protection code -> at once. Neither: as the first device (an empty registry); with devices there the
    box turns it into a join request (202, valid after 14 days unless a device declines).
    -> "ok" | {"pending": True, "until"}. Remembers the address it is registered at."""
    from net import vault
    me = mine()
    code, t = vault._me(settings)
    if invite_:
        by, nonce = str(invite_.get("by") or ""), str(invite_.get("nonce") or "")
    elif guard_code:
        by, nonce = "", ""
    else:
        by, nonce = me["dev_id"], ""
    msg = f"dev_add|{code}|{me['dev_id']}|{me['sign_pk']}|{me['box_pk']}|{by}|{nonce}|{t}"
    payload = {"code": code, "dev_id": me["dev_id"], "sign_pk": me["sign_pk"], "box_pk": me["box_pk"], "by": by,
               "t": t, "sig_id": relay._signed(settings, msg), "sig_dev": sign(msg)}
    if invite_:
        payload["invite"] = invite_
    if guard_code:
        from net import guard
        payload["sig_main"] = guard.sign(guard_code, msg, keys, salt=guard.salt_of(settings) if keys is None else None)
    d = _post(settings, "/v1/dev/add", payload)
    if d.get("pending"):
        _update(code="", pending=code)
        return {"pending": True, "until": int(d.get("until") or 0)}
    _update(code=code, pending="")
    return "ok"


def listing(settings):
    """/v1/dev/list. Rows without a dev_id (or not a dict) are left out – the page and „remove“ index them (review
    08.11.: a missing field was a KeyError)."""
    from net import vault
    code, t = vault._me(settings)
    d = _post(settings, "/v1/dev/list", {"code": code, "t": t, "sig_id": relay._signed(settings, f"dev_list|{code}|{t}")})
    if isinstance(d, dict):
        for key in ("list", "dev_request"):
            if key in d:
                d[key] = [r for r in (d.get(key) or []) if isinstance(r, dict) and isinstance(r.get("dev_id"), str)
                          and r["dev_id"]]
    return d


def decide(settings, about, ok, guard_code=None):
    """A join request: decline (any registered device) or allow (+ the protection code if one is set)."""
    from net import vault
    code, t = vault._me(settings)
    msg = f"dev_decide|{code}|{about}|{int(bool(ok))}|{t}"
    payload = {"code": code, "about": str(about), "ok": int(bool(ok)), "t": t, "sig_id": relay._signed(settings, msg)}
    if ok and guard_code:
        from net import guard
        payload["sig_main"] = guard.sign(guard_code, msg, salt=guard.salt_of(settings))
    return _post(settings, "/v1/dev/decide", attach(settings, payload, msg))


def leave(settings):
    """Sign this device out of the registry (only its own key may) – the caller then forgets seed and keys."""
    k = _load(False)
    if not k or not registered(settings):
        return False
    code, t = relay.my_code(settings), int(time.time())   # no register first: the leave is the only call (legal 14.11.)
    msg = f"dev_leave|{code}|{k['dev_id']}|{t}"
    _post(settings, "/v1/dev/leave", {"code": code, "dev_id": k["dev_id"], "t": t,
                                      "sig_id": relay._signed(settings, msg), "sig_dev": sign(msg)})
    return True


def leave_seed(seed, url=None):
    """Sign this device out of the registry of ANOTHER identity (seed): cancelling at the comparison table after it was
    added there (lead/ports 11.11., U5 T3/T5) – the device's own bookkeeping already points back to its old address, so
    no registered() check here; raises VaultError on an answer (403/404/410: not there any more), OSError offline."""
    k = _load(False)
    if not k or not seed:
        return False
    s = {"relay": {"seed": str(seed), "url": url}}
    code, t = relay.my_code(s), int(time.time())   # no register first: the leave is the only call (legal 14.11.)
    msg = f"dev_leave|{code}|{k['dev_id']}|{t}"
    _post(s, "/v1/dev/leave", {"code": code, "dev_id": k["dev_id"], "t": t,
                               "sig_id": relay._signed(s, msg), "sig_dev": sign(msg)})
    return True


def chain(rows, dev_id):
    """[dev_id, …every device it added, recursively] – the box refuses a removal without them („Mit entfernt“)."""
    by = {}
    for r in rows:
        if r.get("added_by") and r["added_by"] != r["dev_id"]:
            by.setdefault(r["added_by"], []).append(r["dev_id"])
    out, todo = [], [dev_id]
    while todo:
        d = todo.pop(0)
        if d in out:
            continue
        out.append(d)
        todo += by.get(d, [])
    return out


def seal_for(box_pk, data):
    from nacl.public import PublicKey, SealedBox
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64(SealedBox(PublicKey(base64.b64decode(box_pk))).encrypt(raw))


FWD_V = 3   # the signed letter (review 08.11., S6) – v2 (unsigned) is never accepted


def fwd_line(old, new, dev_id, t, seed):
    """What the remover signs with the OLD identity key: only a holder of the old seed can write a letter the remaining
    devices take – the server (which knows every box key) can't slip them a seed of its own."""
    import hashlib
    return f"fwd{FWD_V}|{old}|{new}|{dev_id}|{int(t)}|{hashlib.sha256(str(seed).encode('ascii')).hexdigest()}"


def letter_for(settings, old, new, new_seed, dev_id, t):
    """The letter for one remaining device (sealed for its box key by the caller)."""
    return {"v": FWD_V, "seed": new_seed, "code": new, "old": old, "dev": dev_id, "t": int(t),
            "sig": relay._signed(settings, fwd_line(old, new, dev_id, t, new_seed))}


def open_fwd(settings, sealed):
    """The envelope the remover sealed for this device -> {"seed", "code"} – only if it is the signed letter for THIS
    device from THIS identity (old key = the seed this device still has), and the new code belongs to the new seed."""
    k = _load(False)
    if not k or not sealed:
        return None
    try:
        from nacl.public import SealedBox
        from nacl.signing import VerifyKey
        from net import pairing
        got = json.loads(SealedBox(_box(k)).decrypt(base64.b64decode(sealed)))
        if not isinstance(got, dict) or got.get("v") != FWD_V:
            return None
        old = relay.my_code(settings)
        if got.get("old") != old or got.get("dev") != k["dev_id"]:
            return None
        line = fwd_line(old, got.get("code"), k["dev_id"], int(got.get("t")), got.get("seed"))
        VerifyKey(bytes(relay._signing(settings).verify_key)).verify(line.encode("utf-8"),
                                                                    base64.b64decode(got.get("sig") or ""))
        if got.get("seed") and pairing.code_of_seed(got["seed"]) == got.get("code"):
            return {"seed": got["seed"], "code": got["code"]}
    except Exception:  # noqa: BLE001 – not for this device, not from this identity, or forged
        return None
    return None


def fetch_fwd(settings, old_code):
    """After „remove one“ the old address answers 410 {"moved", "per_device"}: fetch this device's own envelope
    (/v1/dev/fwd, signed with the device key – the old identity key is gone on the server) and open it.
    -> {"seed", "code"} | None (removed: 410 gone, or not for this device)."""
    from net import vault
    k = _load(False)
    if not k:
        if unreadable():   # the keys are there but locked right now: no answer yet – never „removed“ (M3/M5)
            raise vault.VaultError(0, "device key unreadable")
        return None
    t = int(time.time())
    payload = {"code": old_code, "dev_id": k["dev_id"], "t": t, "sig_dev": sign(f"dev_fwd|{old_code}|{k['dev_id']}|{t}")}
    try:   # directly: vault._post would treat the 410 of a removed device as „moved“ again (relay.moved_away)
        r = vault._send(vault._base(settings) + "/v1/dev/fwd", payload)
        d = r.json() if r.status_code == 200 else {}
    except Exception:  # noqa: BLE001 – offline: try again at the next question
        raise vault.VaultError(0, "offline") from None
    if r.status_code in (404, 410):
        return None
    if r.status_code != 200:
        raise vault.VaultError(r.status_code, "dev/fwd")
    return open_fwd(settings, d.get("fwd"))


def moved(settings, new_code):
    """After following an envelope: the registry moved along (box: keep without gone) – registered at the new address."""
    _update(code=new_code, pending="", t=int(time.time()))


# relay.* and top-level settings that belong to this device's place in ONE identity's device list – from a backup of
# another identity they would be wrong (registered there, a request/decline/removal of the old list, „paired“).
RELAY_DEVICE_BITS = ("registered", "dev_request", "join_wait", "removed_by", "identity_gone")
DEVICE_BITS = ("sync_paired", "sync_guard_mine", "sync_rescue_ok", "sync_rescue_missing")


def identity_of(settings):
    """The identity a settings dict carries: its ID (relay.my_code, 16 characters) or None without a seed. Read only –
    unlike relay.my_code it never creates a seed."""
    seed = ((settings or {}).get("relay") or {}).get("seed")
    if not seed:
        return None
    try:
        from nacl.signing import SigningKey
        return relay.code_of_key(_b64(SigningKey(base64.b64decode(seed)).verify_key))
    except (ValueError, TypeError):
        return None


def device_bits_off(settings):
    """In place: drop the device-list bits (see RELAY_DEVICE_BITS / DEVICE_BITS); the seed, the switch and the rest stay."""
    st = settings.get("relay")
    if isinstance(st, dict):
        for k in RELAY_DEVICE_BITS:
            st.pop(k, None)
    for k in DEVICE_BITS:
        settings.pop(k, None)
    return settings


def drop_device_state(data_dir):
    """After taking another identity from a backup: this device's keys (devkey.json) and the sync engine's state
    (sync/) belong to the old identity – both go, nothing else in data_dir is touched. -> list of removed names"""
    d = pathlib.Path(data_dir)
    gone = []
    f = d / FILE
    with _lock:
        _cache.pop(str(f), None)
        if f.is_file():
            f.unlink()
            gone.append(FILE)
    s = d / "sync"
    if s.is_dir() and not s.is_symlink():
        shutil.rmtree(s)
        gone.append("sync")
    return gone
