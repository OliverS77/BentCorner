"""Exchange via the Bent°Corner mailbox (server/box): add friends by their ID, send trade/want lists
to all friends. Design and security: docs/server-austausch.md.

- One key per installation (Ed25519, PyNaCl/libsodium), stored in the settings (settings["relay"]);
  the encryption key (Curve25519) is derived from it too. Your own address = prefix of the SHA-256 of the public
  key, shown as "7F3A-21C9-0B44-E1D2" – that is what you give to friends.
- Every parcel: envelope {"v", "kind", "game", "from", "to", "t", "body"} → signed by the sender → encrypted for the
  recipient (Sealed Box). The server only sees addresses, size, time.
- Kinds: "friend" (request: name, card back, profile ID), "friend_ok" (accepted), "friend_no" (declined),
  "list" (trade file as in the export, trade.build_export).
- Friends: settings["relay"]["friends"] = {address: {"name", "back", "pid", "sign_pk", "status", "t"}} with status
  "out" (requested), "in" (request received), "ok", "blocked"; plus "hide_back" (card back hidden).
- Protection: hide card back, block (accept nothing more), report (to the server, with what you see).
Nothing from a parcel is ever executed: JSON only, size limited, every kind checked individually.
"""
import base64
import contextlib
import hashlib
import json
import logging
import re
import threading
import time
import zlib

from system import contacts
from system.i18n import tr

log = logging.getLogger("booster")

URL = contacts.SERVER   # old address as a fallback: netpolite
CODE_LEN = 16
MAX_PLAIN = 60 * 1024        # compressed (zlib) – fits into the server's 64 KB
MAX_UNPACKED = 4 * 1024 * 1024   # at most 4 MB decompressed (protection against "zip bombs")
KINDS = ("friend", "friend_ok", "friend_no", "list", "board_key", "team", "list_delta", "board_gone", "ticket",
         "ticket_gone", "rekey")
DELTA_MAX = 400   # more changed entries since the last full snapshot: better post everything anew
BOARD_LISTS = "lists"   # slot for trade and want lists (binders get their own slots "binder-<id>")
BOARD_DAYS = 180   # posted content stays 6 months (without re-posting), withdrawing deletes it immediately


class RelayError(Exception):
    """status: the server's HTTP status (0 = no answer) – 507 the friend's box is full, 403 not allowed, 410 the
    address moved (data: {"moved": note} for a friend, {"fwd"} / {"gone"} for the address itself)"""
    def __init__(self, message="", status=0, data=None):
        super().__init__(message)
        self.status = status
        self.data = data or {}


# ---------- Key and address ----------
def state(settings):
    return settings.setdefault("relay", {})


def enabled(settings):
    return bool(state(settings).get("on"))


def url(settings):
    """The box for the mailbox – decided in ONE place (net/boxbase.py: Ship = live, DEV = the test instance)."""
    from net import boxbase
    return boxbase.base(settings)


def _signing(settings):
    from nacl.signing import SigningKey
    st = state(settings)
    if not st.get("seed"):
        import nacl.utils
        st["seed"] = base64.b64encode(nacl.utils.random(32)).decode()
    return SigningKey(base64.b64decode(st["seed"]))


def _b64(b):
    return base64.b64encode(bytes(b)).decode()


def code_of_key(sign_pk_b64):
    return hashlib.sha256(base64.b64decode(sign_pk_b64)).hexdigest()[:CODE_LEN].upper()


def my_code(settings):
    return code_of_key(_b64(_signing(settings).verify_key))


def _short(code):
    """A friend in the program log: the first 6 characters of the ID – not the name (third-party data, the log may be
    mailed to us), not the whole ID."""
    return norm(code)[:6] + "…"


def pretty(code):
    """7F3A21C90B44E1D2 -> 7F3A-21C9-0B44-E1D2"""
    c = norm(code)
    return "-".join(c[i:i + 4] for i in range(0, len(c), 4))


def norm(code):
    """Input (with dashes, spaces, lowercase) -> 16 uppercase characters, otherwise ""."""
    c = "".join(ch for ch in str(code or "").upper() if ch in "0123456789ABCDEF")
    return c if len(c) == CODE_LEN else ""


# ---------- Network ----------
# A 410 on these answers about MY OWN address (moved / removed / deleted) – only then does relay.moved_away follow it
# or give up the identity. Everything else (a friend's board, reporting/blocking someone, sending to someone) answers
# about the OTHER address: a friend who deleted Bent°Corner must never cost me my own identity (review 08.11., S1).
OWN_PATHS = frozenset({"/v1/fetch", "/v1/ack", "/v1/board/put", "/v1/board/del", "/v1/rekey", "/v1/forget",
                       "/v1/vault/get", "/v1/vault/put", "/v1/vault/del", "/v1/rescue/put", "/v1/rescue/del",
                       "/v1/guard/set", "/v1/guard/request", "/v1/guard/decline", "/v1/pair/put", "/v1/pair/state",
                       "/v1/dev/add", "/v1/dev/list", "/v1/dev/decide", "/v1/dev/leave"})


def _post(settings, path, payload, again=True):
    from net import boxbase, vault
    try:
        r = vault.gated("POST", url(settings) + path, 20, json=payload)   # the gate cookie only for the test instance
    except vault.GateMissing:
        raise RelayError(tr("The access code for the test server is missing."), 401) from None
    except boxbase.Blocked:
        raise RelayError(tr(boxbase.BLOCKED_TEXT), boxbase.BLOCKED_STATUS) from None
    except Exception as e:  # noqa: BLE001
        raise RelayError(tr(f"Server unreachable ({e.__class__.__name__})")) from None
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code != 200:
        from net import boxbase
        if again and d.get("unknown") and path != "/v1/register" and boxbase.full():   # never outside Full Orbit
            # the server no longer knows my address (removed after a year without use): register anew, once
            state(settings).pop("registered", None)
            register(settings)
            return _post(settings, path, payload, again=False)
        if (r.status_code == 410 and path in OWN_PATHS
                and (d.get("gone") or d.get("fwd") or d.get("per_device"))
                and str(payload.get("code") or "").upper() == my_code(settings)):
            moved_away(settings, d)   # this device's own address moved: follow, or a new identity (PAIRING §3)
            d = dict(d, handled=True)
        raise RelayError(d.get("error") or tr(f"Error {r.status_code}"), r.status_code, d)
    return d


def _signed(settings, msg):
    return _b64(_signing(settings).sign(msg.encode("utf-8")).signature)


def _dev(settings, payload, msg):
    """Once this device is in the identity's device registry: dev_id + sig_dev over the same line (box 01e8440: with a
    registry, board/*, block, pair/put, vault/put and rescue/put need it – a seed alone, e.g. from a backup ZIP, isn't
    enough; review 08.11.). Before that: the payload as it is."""
    from net import devkeys
    return devkeys.attach(settings, payload, msg)


def register(settings):
    """Register your own address with the server (once per server; silent afterwards). After this device's identity
    was removed (identity_gone) its new one sends NOTHING by itself – not even registering – until the user acts
    (pairs again, turns the backup on, or reads the hint: identity_gone goes) – lead 07.11., the web alike."""
    st = state(settings)
    from net import forget
    if forget.pending_file().exists():   # „delete everything online“ still waits for a connection: nothing new
        raise RelayError(tr("No connection – we'll delete your online data as soon as this device is back online. "
                            "Until then Bent°Corner won't set up anything new."), 409, {"forget_pending": True})
    if st.get("identity_gone"):
        raise RelayError(tr("This device was removed – nothing is sent until you decide."), 410, {"removed": True})
    if st.get("registered") == url(settings):
        return
    sk = _signing(settings)
    code, t = my_code(settings), int(time.time())
    try:
        _post(settings, "/v1/register", {"code": code, "sign_pk": _b64(sk.verify_key), "t": t,
                                         "sig": _signed(settings, f"register|{code}|{t}")})
    except RelayError as e:
        if e.status == 410 and moved_away(settings, e.data) and not st.get("identity_gone"):
            return register(settings)   # followed the move („Neuer Code“): the identity this device now has
        raise
    st["registered"] = url(settings)


# S7 (Prüfkette 08.11.): this device's OWN key change (remove one device / new code) and the background network jobs
# (sync, mailbox, minute question, device registry) never overlap. The change waits until running jobs are done; jobs
# that want to start meanwhile wait until it is over. A 410 that still arrives during the change is about the address
# this device itself is leaving – moved_away ignores it (it would destroy the new seed or call this device removed).
_jobs = threading.Condition()
_count = {"jobs": 0, "change": 0}
JOB_WAIT = 60.0


class Busy(RuntimeError):
    """The own key change could not start: a background job didn't finish in time."""


@contextlib.contextmanager
def job(wait=None):
    """One background network job – waits while this device changes its own key."""
    with _jobs:
        _jobs.wait_for(lambda: _count["change"] == 0, timeout=JOB_WAIT if wait is None else wait)
        _count["jobs"] += 1
    try:
        yield
    finally:
        with _jobs:
            _count["jobs"] -= 1
            _jobs.notify_all()


@contextlib.contextmanager
def own_change(wait=None):
    """Around rekey.change / rekey.remove_one: no job runs meanwhile. Busy if one doesn't end within `wait`."""
    with _jobs:
        _count["change"] += 1
        if not _jobs.wait_for(lambda: _count["jobs"] == 0, timeout=JOB_WAIT if wait is None else wait):
            _count["change"] -= 1
            _jobs.notify_all()
            raise Busy("a sync job is still running")
    try:
        yield
    finally:
        with _jobs:
            _count["change"] -= 1
            _jobs.notify_all()


def changing():
    return _count["change"] > 0


def moved_away(settings, data):
    """The server says this device's own address moved (rekey, PAIRING.md §3): with "per_device" („Gerät entfernen“
    elsewhere) this device's own signed letter (S6) – take the new seed and go on; otherwise (removed, or a backup of
    an identity that was removed/deleted – legal 07.11.; an old-style "fwd" counts the same, FUNDE A9): this identity is
    dead for good – a NEW one, the data stays, the page says so (state "identity_gone"). -> True if this device now has
    another identity."""
    if changing():   # S7: the answer is about the address this device is leaving right now – nothing to follow
        log.info("Mailbox: 410 during the own key change – ignored")
        return False
    st = state(settings)
    if st.get("rekey_inflight"):   # M4: my own key change whose answer got lost – did it go through?
        from net import rekey
        done = rekey.confirm_inflight(settings)
        if done:
            data["fwd"] = "device"   # followed (sync_ctl: not removed)
            return True
        if done is None:   # can't tell now: nothing changes, the next request asks again
            return False
    old = st.get("seed")
    if data.get("per_device") and old:   # B5 „remove one“: this device's own envelope, sealed for its device key
        from net import devkeys, vault
        old_code = my_code(settings)
        try:
            got = devkeys.fetch_fwd(settings, old_code)
        except vault.VaultError:   # offline: nothing changes now, the next request asks again
            return False
        if got is not None:
            st["seed"] = got["seed"]
            for k in ("registered", "test_registered"):
                st.pop(k, None)
            devkeys.moved(settings, got["code"])
            data["fwd"] = "device"   # the callers read „followed“ from fwd (sync_ctl: not removed)
            return True
        data["gone"] = True   # no envelope for this device: it was removed
        st["removed_here"] = time.time()   # D (lead 12.11.): removed from a group that goes on – it empties itself
    if data.get("fwd") is not None and data.get("fwd") != "device":
        # FUNDE A9 (lead/ports 08.11.): a 410 {fwd} sealed with the OLD vault key is never followed – anyone with the old
        # seed could have sent it („Neuer Code“ is gone). Own devices follow only via their signed letter (S6).
        data.pop("fwd", None)
        data["gone"] = True
    if (data.get("gone") and data.get("by") or data.get("removed")) and old:   # D: another own device removed this one
        st["removed_here"] = time.time()   # („by“ the old way; „removed“ the box's mark – ports/lead 12.11., box patch A)
    if data.get("gone") or data.get("fwd") is not None:
        import nacl.utils
        st["removed_by"] = ""
        if data.get("by") and old:   # which own device removed this one (sealed with the old vault key)
            from net import pairing
            try:
                st["removed_by"] = str((pairing.vault_open(old, data["by"]) or {}).get("name") or "")[:60]
            except Exception:  # noqa: BLE001 – unreadable: „another device“
                pass
        st["seed"] = base64.b64encode(nacl.utils.random(32)).decode()
        st["identity_gone"] = time.time()
        from net import devkeys
        devkeys.forget()   # its device key belonged to the old identity's device list
        for k in ("registered", "test_registered"):
            st.pop(k, None)
        return True
    return False


def lookup(settings, code):
    """Public key of an address – verified: it must match the address (the server cannot swap it)."""
    from net import boxbase, vault
    code = norm(code)
    try:
        r = vault.gated("GET", f"{url(settings)}/v1/key/{code}", 20)
    except vault.GateMissing:
        raise RelayError(tr("The access code for the test server is missing."), 401) from None
    except boxbase.Blocked:
        raise RelayError(tr(boxbase.BLOCKED_TEXT), boxbase.BLOCKED_STATUS) from None
    except Exception as e:  # noqa: BLE001
        raise RelayError(tr(f"Server unreachable ({e.__class__.__name__})")) from None
    if r.status_code == 404:
        raise RelayError(tr("The server doesn't know this ID – has your friend turned on the exchange yet?"))
    if r.status_code != 200:
        raise RelayError(tr(f"Error {r.status_code}"))
    pk = str(r.json().get("sign_pk") or "")
    if code_of_key(pk) != code:
        raise RelayError(tr("The server's answer doesn't match the ID"))
    return pk


def _box_pk(sign_pk_b64):
    from nacl.signing import VerifyKey
    return VerifyKey(base64.b64decode(sign_pk_b64)).to_curve25519_public_key()


def send(settings, to, kind, body, game=None, sign_pk=None, slot=""):
    """Parcel to an address: sign, encrypt, drop it in. slot: replaces an older parcel with the same slot on the
    server (list changes – only the newest counts)."""
    import games
    to = norm(to)
    if kind not in KINDS:
        raise ValueError(kind)
    register(settings)
    pk = sign_pk or lookup(settings, to)
    data = pack(settings, to, pk, kind, body, game or games.current().key)
    frm, t = my_code(settings), int(time.time())
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    msg = {"from": frm, "to": to, "t": t, "data": data,
           "sig": _signed(settings, f"send|{frm}|{to}|{digest}|{t}" + (f"|{slot}" if slot else ""))}
    if slot:
        msg["slot"] = slot
    try:
        return _post(settings, "/v1/send", msg)
    except RelayError as e:
        if e.status == 410 and (e.data or {}).get("moved"):   # the friend moved: their note, kept for me (§3)
            env = unpack(settings, e.data["moved"])
            if env is not None and env.get("kind") == "rekey":
                ev = _moved_note(settings, env.get("body") or {}, env.get("from"), env.get("_sign_pk"),
                                 old_gone=True)
                if ev:
                    e.data = dict(e.data, event=ev)
        raise


def pack(settings, to, sign_pk, kind, body, game="*"):
    """A parcel's data: signed by this identity, sealed for the receiver's key (send, and rekey's notes)."""
    from nacl.public import SealedBox
    env = {"v": 1, "kind": kind, "game": game, "from": my_code(settings), "to": norm(to), "t": int(time.time()),
           "body": body}
    raw = zlib.compress(json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    if len(raw) > MAX_PLAIN:
        raise RelayError(tr("Too big for the mailbox (shorten the list)"))
    signed = bytes(_signing(settings).sign(raw))
    return _b64(SealedBox(_box_pk(sign_pk)).encrypt(signed))


def unpack(settings, data, frm=None):
    """A parcel's data -> its verified envelope (or None: broken, forged, not for me)."""
    from nacl.public import SealedBox
    from nacl.signing import VerifyKey
    try:
        signed = SealedBox(_signing(settings).to_curve25519_private_key()).decrypt(base64.b64decode(data))
        dec = zlib.decompressobj()
        raw = dec.decompress(signed[64:], MAX_UNPACKED)
        if dec.unconsumed_tail:
            return None
        env = json.loads(raw.decode("utf-8"))
        sender = norm(env.get("from"))
        if not sender or (frm and sender != norm(frm)) or env.get("to") != my_code(settings) \
                or env.get("kind") not in KINDS:
            return None
        pk = ((state(settings).get("friends") or {}).get(sender) or {}).get("sign_pk") or lookup(settings, sender)
        VerifyKey(base64.b64decode(pk)).verify(signed)
        env["_sign_pk"] = pk
        return env
    except Exception:  # noqa: BLE001 – broken or forged
        return None


def fetch(settings):
    """Fetch your own parcels, decrypt them, verify the signature. -> ([envelope], [IDs to acknowledge]).
    Broken, foreign or forged parcels are silently discarded (but acknowledged)."""
    from nacl.public import SealedBox
    from nacl.signing import VerifyKey
    register(settings)
    code, t = my_code(settings), int(time.time())
    d = _post(settings, "/v1/fetch", {"code": code, "t": t, "sig": _signed(settings, f"fetch|{code}|{t}")})
    box = SealedBox(_signing(settings).to_curve25519_private_key())
    out, ids = [], []
    known = state(settings).setdefault("friends", {})
    for it in d.get("items") or []:
        ids.append(str(it.get("id")))
        try:
            signed = box.decrypt(base64.b64decode(it["data"]))
            dec = zlib.decompressobj()
            raw = dec.decompress(signed[64:], MAX_UNPACKED)
            if dec.unconsumed_tail:
                continue   # too large when decompressed
            env = json.loads(raw.decode("utf-8"))
            frm = norm(env.get("from"))
            if not frm or frm != norm(it.get("from")) or env.get("to") != code or env.get("kind") not in KINDS:
                continue
            pk = (known.get(frm) or {}).get("sign_pk") or lookup(settings, frm)
            VerifyKey(base64.b64decode(pk)).verify(signed)
            env["_sign_pk"] = pk
            out.append(env)
        except Exception:  # noqa: BLE001 – broken or forged: throw it away
            log.info("Mailbox: parcel discarded")
    return out, ids


def ack(settings, ids):
    if not ids:
        return
    code, t = my_code(settings), int(time.time())
    _post(settings, "/v1/ack", {"code": code, "ids": ids, "t": t,
                                "sig": _signed(settings, f"ack|{code}|{','.join(ids)}|{t}")})


# ---------- Friends ----------
def friends(settings):
    return state(settings).setdefault("friends", {})


def _me(settings):
    from system import userprofile
    p = userprofile.ensure(settings)
    return {"name": p.get("name") or "", "back": p.get("back"), "pid": p.get("id")}


def _clean_person(body):
    """Take over only what is expected, truncated."""
    from system import userprofile
    back = body.get("back") if isinstance(body.get("back"), str) and len(body.get("back")) < 4000 else None
    if back is not None and userprofile.parse(back) is None:
        back = None
    pid = str(body.get("pid") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid):   # becomes a file name later: harmless characters or nothing
        pid = ""
    return {"name": str(body.get("name") or "")[:40], "back": back, "pid": pid}


def _person_for(fs, code, f, person):
    """A friend's profile ID is fixed once known: lists, binders and tickets are filed by it. A later parcel can change
    name and card back, never the ID – and never take an ID another friend already has (else that friend could
    overwrite someone else's lists on this PC and get their tickets filed as his; review 08.11., H2-1)."""
    person = dict(person)
    had = (f or {}).get("pid") or ""
    if had:
        person["pid"] = had
    elif person.get("pid") and any(c != code and (o or {}).get("pid") == person["pid"] for c, o in fs.items()):
        person["pid"] = ""
    return person


def request_friend(settings, code):
    """Send a friend request to an ID."""
    code = norm(code)
    if not code:
        raise RelayError(tr("That's not a valid ID (16 characters, e.g. 7F3A-21C9-0B44-E1D2)."))
    if code == my_code(settings):
        raise RelayError(tr("That's your own ID."))
    pk = lookup(settings, code)
    send(settings, code, "friend", _me(settings), sign_pk=pk)
    f = friends(settings).setdefault(code, {})
    if f.get("status") != "ok":
        f.update(status="out", sign_pk=pk, t=time.time())
    return f


def answer_friend(settings, code, accept):
    code = norm(code)
    f = friends(settings).get(code)
    if not f:
        return None
    if accept:
        send(settings, code, "friend_ok", _me(settings), sign_pk=f.get("sign_pk"))
        f.update(status="ok", t=time.time())
    else:
        try:
            send(settings, code, "friend_no", {}, sign_pk=f.get("sign_pk"))
        except RelayError:
            pass
        if accept is None:   # block right on the request: same as block() (back off, nothing of theirs stays)
            block(settings, code)
            server_block(settings, code, True)
        else:
            f.update(status="no", t=time.time())
    return f


def remove_friend(settings, code):
    friends(settings).pop(norm(code), None)
    _leave_audience(settings, code)


# ---------- Protection: hide card back, block, report ----------
REPORT_REASONS = (("illegal", "Rechtswidrig (z. B. verbotene Symbole)"), ("sexual", "Anstößig / sexuell"),
                  ("hate", "Beleidigend / Hass"), ("harass", "Belästigung"), ("other", "Etwas anderes"))


def _patch_friend_files(pid, back):
    """Stored lists of this friend (all games): set or remove the card back."""
    import json as _json
    import games
    if not pid:
        return
    for key, _n, ready in games.GAMES:
        if not ready:
            continue
        folder = games.mine(key) / "friends"
        for p in folder.glob("*.json") if folder.exists() else []:
            try:
                d = _json.loads(p.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if d.get("id") == pid and d.get("back") != back:
                d["back"] = back
                p.write_text(_json.dumps(d, ensure_ascii=False), "utf-8")


def _drop_friend_files(pid):
    import games
    import json as _json
    if not pid:
        return
    for key, _n, ready in games.GAMES:
        if not ready:
            continue
        folder = games.mine(key) / "friends"
        for p in folder.glob("*.json") if folder.exists() else []:
            try:
                if _json.loads(p.read_text("utf-8")).get("id") == pid:
                    p.unlink()
            except (OSError, ValueError):
                continue


def shown_back(f):
    """A friend's card back as it is shown (hidden/blocked: default)."""
    return None if f.get("hide_back") or f.get("status") == "blocked" else f.get("back")


def set_hide_back(settings, code, on):
    """Stop showing this friend's card back (everywhere: sidebar, tickets, profile) – or show it again."""
    f = friends(settings).get(norm(code))
    if not f:
        return None
    f["hide_back"] = bool(on)
    _patch_friend_files(f.get("pid"), shown_back(f))
    return f


def block(settings, code):
    """Block: accept nothing more (no new requests either), drop their lists, card back off."""
    code = norm(code)
    f = friends(settings).setdefault(code, {})
    f.update(status="blocked", hide_back=True, t=time.time())
    _leave_audience(settings, code)
    f.pop("boards", None)
    _drop_friend_files(f.get("pid"))
    return f


def block_on_server(settings, code):
    """Does this block (maybe) lie on the server? Marked when the server took it; an older block without the mark
    counts if the person came through the mailbox (a sign key) – only a block that never left this PC (a file import,
    or blocked while the mailbox was off) is purely local."""
    f = friends(settings).get(norm(code)) or {}
    return bool(f.get("on_server") or ("on_server" not in f and f.get("sign_pk")))


def unblock(settings, code):
    """Unblock: remove the entry – afterwards both sides can send new requests again."""
    friends(settings).pop(norm(code), None)


def server_block(settings, code, on, strict=False):
    """Tell the server too (per-recipient block): the blocked ID can no longer drop parcels into my mailbox nor fetch
    what I posted. Best effort – the local block applies anyway. -> True if the server took it.
    strict: raise instead (unblocking goes server first – lead 08.11.: nothing changes here until the server took it)"""
    code = norm(code)
    if not code or not enabled(settings):
        return False
    try:
        register(settings)
        me, t, on = my_code(settings), int(time.time()), int(bool(on))
        msg = f"block|{me}|{code}|{on}|{t}"
        _post(settings, "/v1/block", _dev(settings, {"code": me, "about": code, "on": on, "t": t,
                                                     "sig": _signed(settings, msg)}, msg))
        f = friends(settings).get(code)
        if on and f is not None:   # the block lies on the server too: unblocking must go there (lead 08.11.)
            f["on_server"] = True
        return True
    except Exception as e:  # noqa: BLE001
        log.info("Mailbox: block on the server (%s): %s", "on" if on else "off", e)
        if strict:
            raise
        return False


def rekey_plan(settings, game):
    """After blocking/removing a friend: which posted lists need a new key. -> (lists of the open game posted?,
    lists of other games ["game/lists"]). Only the open game's lists can be built now – the others are taken off the
    server (retire) and posted again when that game is opened. Binders: qbinder.auto_share(force=True), all games."""
    keys = list((state(settings).get("posted") or {}))
    others = [k for k in keys if k.partition("/")[2] == BOARD_LISTS and k.partition("/")[0] != game]
    return f"{game}/{BOARD_LISTS}" in keys, others


def retire(settings, keys):
    """Delete posted content from the server without telling the friends (they keep their copy) and mark it, so the
    next lists tick posts it anew with a fresh key (see rekey_plan). -> number deleted"""
    register(settings)
    code, n = my_code(settings), 0
    posted = state(settings).setdefault("posted", {})
    for k in keys:
        game, _, slot = k.partition("/")
        t = int(time.time())
        try:
            msg = f"board_del|{code}|{game}|{slot}|{t}"
            _post(settings, "/v1/board/del", _dev(settings, {"code": code, "game": game, "slot": slot, "t": t,
                                                             "sig": _signed(settings, msg)}, msg))
        except RelayError as e:
            log.info("Mailbox: retire %s: %s", k, e)
            continue
        if k in posted:
            posted[k]["stale"] = True
        n += 1
    return n


def report(settings, code, reason, note="", content=None):
    """Report a friend. content: what the reporter has seen (name, card back …) – sent along deliberately,
    the server cannot read any of it otherwise. -> report ID"""
    code = norm(code)
    if not code:
        raise RelayError("Unbekannte ID.")
    register(settings)
    me, t = my_code(settings), int(time.time())
    reason, note = str(reason or "other")[:40], str(note or "")[:2000]
    content = content or {}
    raw = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256((reason + "|" + note + "|" + raw).encode("utf-8")).hexdigest()
    d = _post(settings, "/v1/report", {"code": me, "about": code, "reason": reason, "note": note, "content": content,
                                       "t": t, "sig": _signed(settings, f"report|{me}|{code}|{digest}|{t}")})
    return d.get("id")


def report_content(settings, code):
    """What is currently visible of a friend – for the report: name, card back (text + image), titles of
    what they posted."""
    f = friends(settings).get(norm(code)) or {}
    out = {"name": f.get("name") or "", "back": f.get("back") or "",
           "shared": sorted({str(b.get("title") or k) for k, b in (f.get("boards") or {}).items()})[:40]}
    if f.get("back"):
        try:
            from system import userprofile
            from PySide6 import QtCore
            pm = userprofile.back_pixmap(f["back"], 240)
            buf = QtCore.QBuffer()
            buf.open(QtCore.QIODevice.WriteOnly)
            pm.save(buf, "PNG")
            out["back_png"] = base64.b64encode(bytes(buf.data())).decode()
        except Exception:  # noqa: BLE001 – the report works without the image too
            pass
    return out


def ok_friends(settings):
    return {c: f for c, f in friends(settings).items() if f.get("status") == "ok"}


def send_lists(settings, data, game=None, audience=None):
    """Post the trade file (board_put, 6 months, without card names) and send the key to the friends
    (audience: addresses, None = all accepted ones). -> (friends with key, errors)"""
    import games
    game = game or games.current().key
    return board_put(settings, game, BOARD_LISTS, slim_export(data), audience)


# ---------- Posting (lists, later binders) ----------
def slim_export(data):
    """Trade file without card names (the recipient looks them up in their card database) – that way even
    large collections fit into 1 MB. Wants keep their name (they apply to every printing)."""
    d = dict(data)
    for key in ("c", "lib"):
        if isinstance(d.get(key), list):
            d[key] = [list(c[:5]) if isinstance(c, (list, tuple)) else c for c in d[key]]
    return d


# ---------- Who gets what I share (lead/legal 06.11.2026) ----------
# settings["relay"]["audience"] = {"mode": "only", "codes": [...]}: only these friends get the keys of what I share
# (lists, library, binders – one key per slot, board_put) and the list deltas (send_delta, per friend). New friends are
# not in it: they see nothing but my name and card back (part of the friend request) until I switch them on
# ("Shared with friends" in Orbit). No audience = NOBODY (a new device), never everybody.
# Before 06.11. everybody got everything ("all"): migrate_audience() takes over exactly the friends of that day – once,
# and only on a device that has shared something before (state["posted"]).
# SYNC: the audience stays on this device and never travels in a parcel (board_key / board_gone / list_delta keep
# their format). With several devices of one identity (pairing, docs/SYNC-PLAN.md) it MUST travel along as device data –
# otherwise a second device shares with nobody, or – with an old "all" – with everybody.
AUDIENCE_V = 2
MAX_SLOTS = 20   # posts per address on the mailbox (box.py MAX_SLOTS) – lists per game + each shared binder
# review H2-6 (as the web, ports 10.11.): what strangers and friends can make this device keep is bounded – at most
# MAX_IN open requests (the oldest go), a "no" comes back as a request only after NO_WAIT, a friend's boards at most
# MAX_SLOTS (an existing one may still change)
MAX_IN, NO_WAIT = 50, 7 * 86400
_SLOT_OK = re.compile(r"[A-Za-z0-9_-]{1,40}")


def migrate_audience(settings):
    """Once: "everybody" of before 06.11. becomes exactly today's friends (nothing changes for them) – only where this
    device shared something; anywhere else nobody. -> True if it ran now"""
    st = state(settings)
    if st.get("audience_v") == AUDIENCE_V:
        return False
    aud = st.get("audience") or {}
    if aud.get("mode") in ("only", "except"):
        codes = audience_codes(settings, aud["mode"], aud.get("codes") or ())
    else:
        codes = list(ok_friends(settings)) if st.get("posted") else []
    st["audience"] = {"mode": "only", "codes": codes}
    st["audience_v"] = AUDIENCE_V
    return True


def share_codes(settings):
    """The friends who get what I share: accepted friends switched on – nobody without an audience."""
    st = state(settings)
    if st.get("audience_v") != AUDIENCE_V:
        migrate_audience(settings)
    return audience_codes(settings, "only", (st.get("audience") or {}).get("codes") or ())


def set_share(settings, code, on):
    """Switch a friend on or off for everything I share. Save this FIRST, then give the new keys (relay_rekey) – so no
    list delta of the regular tick reaches a friend switched off in between (ports 06.11.)."""
    share_codes(settings)
    code = norm(code)
    codes = [c for c in state(settings)["audience"]["codes"] if c != code]
    if on:
        codes.append(code)
    state(settings)["audience"]["codes"] = codes


def _leave_audience(settings, code):
    """A removed or blocked friend: out of the audience – added again later, they start off like any new friend."""
    aud = state(settings).get("audience") or {}
    if aud.get("codes"):
        aud["codes"] = [c for c in aud["codes"] if c != norm(code)]


def revoke_plan(settings, code):
    """A friend switched off: the posts they had ("game/slot") – and they are taken off each post's list right away.
    Decided before the new posts (relay_rekey) rewrite who had what."""
    code, had = norm(code), []
    for k, info in (state(settings).get("posted") or {}).items():
        if code in (info.get("to") or []):
            had.append(k)
            info["to"] = [c for c in info["to"] if c != code]
    return had


def revoke(settings, code, keys):
    """Ask the switched-off friend's app to delete my shared content: board_gone for each post they had (the format
    the web reads too). -> number of parcels sent"""
    code = norm(code)
    f = friends(settings).get(code) or {}
    n = 0
    for k in keys:
        game, _, slot = k.partition("/")
        try:
            send(settings, code, "board_gone", {"game": game, "slot": slot}, game=game, sign_pk=f.get("sign_pk"))
            n += 1
        except RelayError as e:
            log.info("Mailbox: revoke %s: %s", k, e)
    return n


def slots_used(settings):
    """Posts on the mailbox right now (lists per game, each binder) – at most MAX_SLOTS."""
    return len(state(settings).get("posted") or {})


def audience_codes(settings, mode="all", codes=()):
    """Who gets to see something: "all" (all friends), "except" (all except codes), "only" (only codes)."""
    ok = list(ok_friends(settings))
    codes = {norm(c) for c in codes}
    if mode == "only":
        return [c for c in ok if c in codes]
    if mode == "except":
        return [c for c in ok if c not in codes]
    return ok


def board_put(settings, game, slot, payload, audience=None, title=""):
    """Post: upload once, encrypted with a new random key, then send the key to every friend in audience
    via the mailbox. -> (friends with key, errors)"""
    import nacl.utils
    from nacl.secret import SecretBox
    if f"{game}/{slot}" not in (state(settings).get("posted") or {}) and slots_used(settings) >= MAX_SLOTS:
        raise RelayError(tr(f"The mailbox holds at most {MAX_SLOTS} shared things (lists per game and binders) – "
                            "take something back first."))
    register(settings)
    key = nacl.utils.random(SecretBox.KEY_SIZE)
    raw = zlib.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    data = _b64(SecretBox(key).encrypt(raw))
    code, t = my_code(settings), int(time.time())
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    msg = f"board_put|{code}|{game}|{slot}|{digest}|{t}"
    res = _post(settings, "/v1/board/put", _dev(settings, {"code": code, "game": game, "slot": slot, "t": t,
                                                           "data": data, "sig": _signed(settings, msg)}, msg))
    until = int(res.get("until") or t + BOARD_DAYS * 86400)
    t = server_time(res, t)   # the time friends get when they fetch it – the base of every later list delta
    summary = {"c": len(payload.get("c") or []), "w": len(payload.get("w") or [])}
    n, errors = 0, []
    targets = share_codes(settings) if audience is None else audience
    for c in targets:
        f = friends(settings).get(c) or {}
        try:
            send(settings, c, "board_key", {"game": game, "slot": slot, "key": _b64(key), "t": t, "until": until,
                                            "n": summary, "title": str(title or "")[:60]}, game=game,
                 sign_pk=f.get("sign_pk"))
            n += 1
        except RelayError as e:
            errors.append(f"friend {_short(c)}: {e}")   # ends up in the program log: no names (legal)
    posted = state(settings).setdefault("posted", {})
    posted[f"{game}/{slot}"] = {"t": t, "until": until, "to": list(targets), "n": summary,
                                "lib": bool(payload.get("lib"))}   # with the library? (relay_share_library_off)
    return n, errors


BASE_SLACK = 2   # s: the server stamps the post and computes "until" a moment apart – a second can tick in between


def server_time(res, t_local):
    """The server's time of a post: "t" if it says so, else "until" minus the 6 months the server keeps it (box.py
    BOARD_TTL). The PC's clock is often a few seconds off – with its own time as the base every list delta missed
    the friend's fetched time and was thrown away (refetch of the old post). Implausible (more than a day from the PC's
    time, e.g. the server keeps posts for another span now): the PC's time – then a delta only means "fetch it anew",
    never something applied wrongly."""
    try:
        srv = int(res["t"]) if res.get("t") else int(res["until"]) - BOARD_DAYS * 86400
    except (KeyError, TypeError, ValueError):
        return t_local
    return srv if abs(srv - t_local) <= 86400 else t_local


def same_base(fetched, base):
    """Does a list delta refer to the post I fetched? (server time on both sides, BASE_SLACK apart at most)"""
    return bool(fetched) and abs(int(fetched or 0) - int(base or 0)) <= BASE_SLACK


def board_get(settings, owner, game, slot, key_b64):
    """Fetch and decrypt what a friend posted. -> (content, time)"""
    from nacl.secret import SecretBox
    register(settings)
    code, t = my_code(settings), int(time.time())
    owner = norm(owner)
    msg = f"board_get|{code}|{owner}|{game}|{slot}|{t}"
    res = _post(settings, "/v1/board/get", _dev(settings, {"code": code, "owner": owner, "game": game, "slot": slot,
                                                           "t": t, "sig": _signed(settings, msg)}, msg))
    box = SecretBox(base64.b64decode(key_b64))
    dec = zlib.decompressobj()
    raw = dec.decompress(box.decrypt(base64.b64decode(res["data"])), MAX_UNPACKED * 8)
    if dec.unconsumed_tail:
        raise RelayError(tr("Posted content too big"))
    return json.loads(raw.decode("utf-8")), int(res.get("t") or 0)


def withdraw(settings, game, slot=BOARD_LISTS):
    """Withdraw shared content: delete it from the server immediately and notify the friends who had it (they delete
    their copy). -> number of notified friends"""
    register(settings)
    code, t = my_code(settings), int(time.time())
    msg = f"board_del|{code}|{game}|{slot}|{t}"
    _post(settings, "/v1/board/del", _dev(settings, {"code": code, "game": game, "slot": slot, "t": t,
                                                     "sig": _signed(settings, msg)}, msg))
    posted = state(settings).setdefault("posted", {})
    info = posted.pop(f"{game}/{slot}", None) or {}
    n = 0
    for c in info.get("to") or []:
        f = friends(settings).get(c) or {}
        if f.get("status") != "ok":
            continue
        try:
            send(settings, c, "board_gone", {"game": game, "slot": slot}, game=game, sign_pk=f.get("sign_pk"))
            n += 1
        except RelayError:
            pass
    return n


def withdraw_all(settings):
    """Exchange off: withdraw everything shared (all games, lists and binders)."""
    n = 0
    for key in list((state(settings).get("posted") or {})):
        game, _, slot = key.partition("/")
        try:
            n += withdraw(settings, game, slot)
        except RelayError:
            pass
    return n


def posted(settings, game, slot=BOARD_LISTS):
    return (state(settings).get("posted") or {}).get(f"{game}/{slot}")


LIB_KEY = "|l"   # library entries: printing|language|foil|l – five parts, so older apps skip them (apply_delta)


def fingerprint(data):
    """Short form of a trade file for comparison: {printing|language|foil: count, "w:"name: count,
    printing|language|foil|l: count (the shared library, only if it is in the file)}."""
    out = {}
    for c in data.get("c") or []:
        if isinstance(c, (list, tuple)) and len(c) >= 5:
            out[f"{c[0]}|{c[1]}|{c[2]}|{int(bool(c[3]))}"] = int(c[4] or 0)
    for w in data.get("w") or []:
        if isinstance(w, (list, tuple)) and w:
            out["w:" + str(w[0])] = int(w[1] if len(w) > 1 else 1)
    for c in data.get("lib") or []:
        if isinstance(c, (list, tuple)) and len(c) >= 5:
            k = f"{c[0]}|{c[1]}|{c[2]}|{int(bool(c[3]))}{LIB_KEY}"
            out[k] = out.get(k, 0) + int(c[4] or 0)
    return out


def has_lib(fp):
    """Does a fingerprint carry the library?"""
    return any(k.endswith(LIB_KEY) and not k.startswith("w:") for k in fp)


def changes(old, new):
    """How many entries changed since posting (added, removed, different count)."""
    return sum(1 for k in set(old) | set(new) if old.get(k) != new.get(k))


def delta(old, new):
    """Changes since the full snapshot as new counts: {key: count} (0 = gone). Absolute values – applying them
    twice or having missed a change still ends up at the same state."""
    return {k: int(new.get(k) or 0) for k in set(old) | set(new) if old.get(k) != new.get(k)}


def send_delta(settings, game, base, d, pid, audience=None):
    """Send only the changes to the friends (instead of re-posting everything): one small parcel per friend.
    base = time of the full snapshot the changes refer to. -> (friends, errors)"""
    n, errors = 0, []
    targets = share_codes(settings) if audience is None else audience
    for c in targets:
        f = friends(settings).get(c) or {}
        try:
            send(settings, c, "list_delta", {"base": int(base), "d": d, "id": pid}, game=game, sign_pk=f.get("sign_pk"),
                 slot=f"delta-{game}")
            n += 1
        except RelayError as e:
            errors.append(f"friend {_short(c)}: {e}")   # ends up in the program log: no names (legal)
    return n, errors


# ---------- Trade tickets through the mailbox (lead/legal 06.11.2026, Oliver: 0.9.7) ----------
# A ticket (collection/ticket.py, the same dict the image carries) goes as a one-off parcel to exactly one friend:
# deleted on the server once fetched, at the latest after 14 days. slot "tk-<trade ID>": a newer version of the same
# trade (counter-offer, closing) replaces one not fetched yet – and "ticket_gone" (withdrawn) replaces the offer itself,
# so a withdrawn offer nobody fetched is gone from the server. Accepted only from friends ("ok") whose profile ID is the
# ticket's issuer, and only tickets issued to me.
TICKET_MAX = 2000   # cards per ticket (an image holds far fewer – this only keeps parcels sane)


def ticket_slot(trade_id):
    return "tk-" + re.sub(r"[^A-Za-z0-9_-]", "", str(trade_id or ""))[:37]


def friend_of_profile(settings, profile_id):
    """The mailbox address of the friend ("ok") with this profile ID, or None (then the image is the way)."""
    if not profile_id:
        return None
    for code, f in friends(settings).items():
        if f.get("status") == "ok" and f.get("pid") == profile_id:
            return code
    return None


def send_ticket(settings, code, t):
    """An offer, counter-offer or closing ticket to one friend. Raises RelayError (.status 507 = their box is full,
    403 = not allowed – the page says only "couldn't be delivered")."""
    f = friends(settings).get(norm(code)) or {}
    return send(settings, code, "ticket", {"tk": t}, game=t.get("g"), sign_pk=f.get("sign_pk"),
                slot=ticket_slot(t.get("x") or t.get("id")))


def send_ticket_gone(settings, code, trade_id, version, why="withdrawn"):
    """Withdrawn (my offer) or declined (theirs, lead 06.11.: otherwise the friend waits for ever): replaces the offer
    on the server if it wasn't fetched yet, otherwise the friend's app marks it."""
    f = friends(settings).get(norm(code)) or {}
    return send(settings, code, "ticket_gone", {"x": str(trade_id), "n": int(version or 1),
                                                "why": "declined" if why == "declined" else "withdrawn"},
                sign_pk=f.get("sign_pk"), slot=ticket_slot(trade_id))


def _clean_ticket(tk, f, my_pid):
    """A ticket from a friend's parcel – only if it's well-formed, issued by that friend and to me; else None."""
    if not isinstance(tk, dict):
        return None
    fr, to = tk.get("f"), tk.get("o")
    if not (isinstance(fr, list) and isinstance(to, list) and len(fr) == 2 and len(to) == 2):
        return None
    if not (isinstance(tk.get("a"), list) and isinstance(tk.get("b"), list)) or len(tk["a"]) + len(tk["b"]) > TICKET_MAX:
        return None
    if not tk.get("id") or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", str(tk.get("x") or tk.get("id"))):
        return None
    if not f.get("pid") or str(fr[0]) != f["pid"] or not my_pid or str(to[0]) != my_pid:
        return None   # issued by someone else, or not to me: never filed
    from collection import ticket
    if not ticket.valid(tk):   # game, ids, fields, counts (review 08.11. T1: the game becomes part of file paths)
        return None
    return tk


def apply_delta(game, pid, d):
    """Apply a friend's changes to their stored list (the game's folder): trade list, wants and – keys ending in "|l" –
    the library they share. -> True if the list existed (False also if library changes arrive for a list without one:
    the full post is fetched instead)."""
    import games
    from collection import trade
    folder = trade.friends_folder(game)
    try:
        f = trade.friend_path(folder, pid)
        data = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return False
    cards = {}
    for c in data.get("cards") or []:
        if isinstance(c, list) and len(c) >= 5:
            cards[f"{c[0]}|{c[1]}|{c[2]}|{int(bool(c[3]))}"] = c
    wants = {str(w[0]): w for w in data.get("wants") or [] if isinstance(w, list) and w}
    lib = None
    if isinstance(data.get("library"), list):
        lib = {}
        for c in data["library"]:
            if isinstance(c, list) and len(c) >= 5:
                lib[f"{c[0]}|{c[1]}|{c[2]}|{int(bool(c[3]))}"] = c
    for k, v in d.items():
        v = max(0, min(9999, int(v or 0)))
        if k.startswith("w:"):
            name = k[2:][:200]
            if v == 0:
                wants.pop(name, None)
            elif name in wants:
                w = wants[name]
                if len(w) > 1:
                    w[1] = v
                else:
                    w.append(v)
            else:
                wants[name] = [name, v]
            continue
        parts = k.split("|")
        if len(parts) == 5 and k.endswith(LIB_KEY):   # the library
            if lib is None:
                return False
            k = k[:-len(LIB_KEY)]
            if v == 0:
                lib.pop(k, None)
            elif k in lib:
                lib[k][4] = v
            else:
                lib[k] = [parts[0], parts[1], parts[2], int(parts[3] == "1"), v]
            continue
        if len(parts) != 4:
            continue
        if v == 0:
            cards.pop(k, None)
        elif k in cards:
            cards[k][4] = v
        else:
            cards[k] = [parts[0], parts[1], parts[2], int(parts[3] == "1"), v]
    data["cards"], data["wants"] = list(cards.values()), list(wants.values())
    if lib is not None:
        data["library"] = list(lib.values())
    data["imported"] = data["date"] = time.time()
    old = trade.FRIENDS
    trade.FRIENDS = folder
    try:
        if game == games.current().key:
            fill_names(data)
        trade.save_friend(data)
    finally:
        trade.FRIENDS = old
    return True


MOVE_PROBE = "move-check"   # a board name nobody posts under: the read only asks „moved?“ (box: [A-Za-z0-9-_:])


def _move_confirmed(settings, old, new):
    """M8 (review 08.11.): a move note that came as a parcel is only signed with the friend's OLD key – whoever still
    holds that seed (a removed device, a stolen backup) could send one. The server knows the truth: reading the old
    address's board answers 410 with the note the friend's real /v1/rekey left for me. -> True (that note names `new`)
    | False (not moved, or moved elsewhere) | None (no answer now)."""
    code, t = my_code(settings), int(time.time())
    msg = f"board_get|{code}|{norm(old)}|{MOVE_PROBE}|{BOARD_LISTS}|{t}"
    try:
        _post(settings, "/v1/board/get", _dev(settings, {"code": code, "owner": norm(old), "game": MOVE_PROBE,
                                                         "slot": BOARD_LISTS, "t": t, "sig": _signed(settings, msg)},
                                              msg))
    except RelayError as e:
        if e.status == 0:
            return None
        if e.status == 410 and (e.data or {}).get("moved"):
            env = unpack(settings, e.data["moved"])
            body = (env or {}).get("body") or {}
            return bool(env and env.get("kind") == "rekey" and norm(body.get("old")) == norm(old)
                        and norm(body.get("new")) == norm(new))
        return False
    return False


def _moved_note(settings, body, sender, sender_pk, old_gone=False, confirm=False):
    """A rekey note from a friend's NEW address: genuine only with the OLD key's signature over
    "rekey_friend|old|new|<me>|t" and a new key that is the new address – and, for a note that came as a parcel
    (confirm), only if the server confirms the move (M8). A move already waiting for the user's answer is never
    replaced by another one. Marked at the old entry ("moved"), the user decides (move_answer). -> UI event or None."""
    from nacl.signing import VerifyKey
    old, new = norm(body.get("old")), norm(body.get("new"))
    f = friends(settings).get(old)
    if f is None or f.get("status") != "ok" or not f.get("sign_pk") or new != norm(sender) or not new:
        return None
    npk = str(body.get("new_sign_pk") or "")
    try:
        if code_of_key(npk) != new or npk != sender_pk:
            return None
        msg = f"rekey_friend|{old}|{new}|{my_code(settings)}|{int(body.get('t') or 0)}"
        VerifyKey(base64.b64decode(f["sign_pk"])).verify(msg.encode("utf-8"), base64.b64decode(body.get("sig_old") or ""))
    except Exception:  # noqa: BLE001 – forged: nothing happens
        return None
    waiting = (f.get("moved") or {}).get("new")
    if waiting and waiting != new:   # the first move waits for the user – a second note never replaces it (M8)
        log.info("Mailbox: a second move note for %s ignored", _short(old))
        return None
    if confirm and not old_gone and not _move_confirmed(settings, old, new):
        log.info("Mailbox: move note of %s not confirmed by the server – ignored", _short(old))
        return None
    f["moved"] = {"new": new, "new_sign_pk": npk, "t": int(body.get("t") or 0), "old_gone": bool(old_gone)}
    return {"kind": "moved", "code": old, "name": f.get("name")}


def move_answer(settings, old, accept):
    """The user's answer to a friend's move. Accept: the entry goes to the new address (name, back, status, boards
    stay); the caller sends my board keys there. Decline: nothing moves (old_gone: sharing waits for a new
    connection). -> the friend's address now."""
    fs = friends(settings)
    old = norm(old)
    f = fs.get(old)
    if f is None or not f.get("moved"):
        return old
    mv = f.pop("moved")
    if not accept:
        f["move_declined"] = mv["new"]
        return old
    f.update(sign_pk=mv["new_sign_pk"], t=time.time())
    f.pop("move_declined", None)
    fs[mv["new"]] = f
    del fs[old]
    return mv["new"]


def apply(settings, env):
    """Process a verified parcel. -> event for the UI {"kind", "code", "name", …} or None.
    Lists are written to the friends folder of the matching game."""
    code, kind = norm(env.get("from")), env.get("kind")
    body = env.get("body") if isinstance(env.get("body"), dict) else {}
    fs = friends(settings)
    f = fs.get(code)
    if f is not None and f.get("status") == "blocked":
        return None
    if kind == "friend":
        person = _person_for(fs, code, f, _clean_person(body))
        if f is not None and f.get("status") in ("ok", "out"):   # both sent a request at the same time
            f.update(person, status="ok", sign_pk=env["_sign_pk"], t=time.time())
            return {"kind": "friend_ok", "code": code, "name": person["name"]}
        if f is not None and f.get("status") == "no" and time.time() - float(f.get("t") or 0) < NO_WAIT:
            return None   # asked again too soon after a "no" (H2-6)
        if f is None or f.get("status") != "in":   # a new open request: the oldest go beyond MAX_IN (H2-6)
            open_ = sorted((c for c, x in fs.items() if isinstance(x, dict) and x.get("status") == "in"),
                           key=lambda c: float(fs[c].get("t") or 0))
            for c in open_[:max(0, len(open_) - MAX_IN + 1)]:
                fs.pop(c, None)
        fs[code] = dict(person, status="in", sign_pk=env["_sign_pk"], t=time.time())
        return {"kind": "friend", "code": code, "name": person["name"]}
    if kind == "rekey":   # a friend moved (PAIRING.md §3) – legal 07.11.: shown with Accept / Decline, never silent
        return _moved_note(settings, body, code, env.get("_sign_pk"), confirm=True)
    if kind == "team":   # message from the Bent°Corner team: genuine only with the team key, there are no replies
        from net import teamnews
        if teamnews.is_team(env.get("_sign_pk")) and teamnews.add(settings, body, "direct"):
            return {"kind": "team", "code": code, "name": teamnews.SENDER, "title": str(body.get("title") or "")}
        return None
    if f is None:
        return None   # lists and replies only from known addresses
    if kind == "friend_ok" and f.get("status") in ("out", "ok"):
        f.update(_person_for(fs, code, f, _clean_person(body)), status="ok", t=time.time())
        return {"kind": "friend_ok", "code": code, "name": f.get("name")}
    if kind == "friend_no" and f.get("status") == "out":
        f.update(status="no", t=time.time())
        return {"kind": "friend_no", "code": code, "name": f.get("name")}
    if kind == "board_key" and f.get("status") == "ok":
        game, slot = str(body.get("game") or ""), str(body.get("slot") or "")
        key = body.get("key")
        if (game not in {k for k, *_ in __import__("games").GAMES} or not _SLOT_OK.fullmatch(slot)
                or not isinstance(key, str) or len(key) > 100):
            return None   # as the web (H2-5/H2-6): a known game, a harmless slot name, a key of sane length
        if f"{game}/{slot}" not in (f.get("boards") or {}) and len(f.get("boards") or {}) >= MAX_SLOTS:
            return None   # H2-6: a friend's boards at most MAX_SLOTS – an existing one may still change
        f.setdefault("boards", {})[f"{game}/{slot}"] = {"key": body["key"], "t": int(body.get("t") or 0),
                                                        "until": int(body.get("until") or 0),
                                                        "title": str(body.get("title") or "")[:60]}
        return {"kind": "board_key", "code": code, "name": f.get("name"), "game": game, "slot": slot}
    if kind == "board_gone" and f.get("status") == "ok":   # friend withdrew something: my copy goes
        game, slot = str(body.get("game") or ""), str(body.get("slot") or "")
        (f.get("boards") or {}).pop(f"{game}/{slot}", None)
        if slot == BOARD_LISTS and f.get("pid") and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", f["pid"]):
            # if they share again later, they land in the same folder (folders exist per game)
            f.setdefault("folders", {})[game], had = _drop_list(game, f["pid"])
            return {"kind": "board_gone", "code": code, "name": f.get("name"), "game": game, "slot": slot, "had": had}
        return {"kind": "board_gone", "code": code, "name": f.get("name"), "game": game, "slot": slot}
    if kind == "list_delta" and f.get("status") == "ok":
        game = str(env.get("game") or "")
        d, pid = body.get("d"), str(body.get("id") or "")
        if not game or not isinstance(d, dict) or len(d) > DELTA_MAX * 2 or (f.get("pid") and pid != f["pid"]) \
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid) or game not in {k for k, *_ in __import__("games").GAMES}:
            return None   # (pid becomes a file name: harmless characters only)
        b = (f.get("boards") or {}).get(f"{game}/{BOARD_LISTS}") or {}
        if not same_base(b.get("fetched"), body.get("base")):
            # I lack their full snapshot (or have an older one): fetch it first – it already includes the changes
            return {"kind": "list_delta", "code": code, "name": f.get("name"), "game": game, "refetch": True}
        ok = apply_delta(game, pid, d)
        f["last_list"] = time.time()
        return {"kind": "list_delta", "code": code, "name": f.get("name"), "game": game, "refetch": not ok}
    if kind == "ticket" and f.get("status") == "ok":
        from system import userprofile
        tk = _clean_ticket(body.get("tk"), f, (settings.get("profile") or {}).get("id") or userprofile.ensure(settings).get("id"))
        if tk is None:
            return None
        return {"kind": "ticket", "code": code, "name": f.get("name"), "ticket": tk}
    if kind == "ticket_gone" and f.get("status") == "ok":
        x = str(body.get("x") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", x):
            return None
        return {"kind": "ticket_gone", "code": code, "name": f.get("name"), "x": x, "n": int(body.get("n") or 1),
                "pid": f.get("pid") or "", "why": "declined" if body.get("why") == "declined" else "withdrawn"}
    if kind == "list" and f.get("status") == "ok":
        game = str(env.get("game") or "mtg")
        if game not in {k for k, *_ in __import__("games").GAMES}:
            return None   # the game becomes a folder: only known ones
        d = _clean_list(body, f)
        if d is None:
            return None
        change = _store_list(game, d, (f.get("folders") or {}).get(game))
        f["last_list"] = time.time()
        return {"kind": "list", "code": code, "name": f.get("name"), "game": game, "n": len(d.get("c") or []),
                "change": change}
    return None


def _clean_list(body, f):
    """Check a trade file: only lists of card rows, the profile ID must match the friend."""
    if body.get("app") != "BentCorner" or not isinstance(body.get("c"), list) or not isinstance(body.get("w", []), list):
        return None
    pid = str(body.get("id") or "")
    if (f.get("pid") and pid != f.get("pid")) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid):
        return None   # (the id becomes a file name: harmless characters only, as with list_delta)
    d = {k: body[k] for k in ("v", "app", "id", "date", "what", "c", "w", "lib") if k in body}
    d["name"], d["back"] = f.get("name") or str(body.get("name") or "")[:40], shown_back(f)
    for key in ("c", "w", "lib"):
        if key in d and not all(isinstance(x, (list, dict)) for x in d[key]):
            return None
    return d


def fetch_board(settings, code, game, slot=BOARD_LISTS):
    """Fetch a friend's posted list and store it as a friend in the game's trade. -> number of cards"""
    f = friends(settings).get(norm(code)) or {}
    b = (f.get("boards") or {}).get(f"{game}/{slot}")
    if not b:
        raise RelayError(tr("This friend hasn't posted anything for you."))
    body, t = board_get(settings, code, game, slot, b["key"])
    d = _clean_list(body, f)
    if d is None:
        raise RelayError(tr("Posted content doesn't match this friend"))
    d["date"] = t or d.get("date")
    f["last_change"] = _store_list(game, d, (f.get("folders") or {}).get(game))   # only genuinely new things get announced
    f["last_list"] = time.time()
    b["fetched"] = t
    return len(d.get("c") or [])


def friend_binders(settings, code, game):
    """Binders a friend has posted for me: [(slot, title, time, expired?)]."""
    f = friends(settings).get(norm(code)) or {}
    out = []
    for k, b in (f.get("boards") or {}).items():
        g, _, slot = k.partition("/")
        if g == game and slot.startswith("binder-"):
            out.append((slot, b.get("title") or "Binder", b.get("t") or 0, (b.get("until") or 0) < time.time()))
    return sorted(out, key=lambda x: x[1].lower())


def fetch_binder(settings, code, game, slot):
    """Fetch a friend's posted binder. -> content (binders.share_payload)"""
    f = friends(settings).get(norm(code)) or {}
    b = (f.get("boards") or {}).get(f"{game}/{slot}")
    if not b:
        raise RelayError(tr("This binder isn't posted (anymore)."))
    body, _t = board_get(settings, code, game, slot, b["key"])
    if body.get("kind") != "binder" or not isinstance(body.get("slots"), list):
        raise RelayError(tr("That's not a binder"))
    body["slots"] = [s if (s is None or (isinstance(s, list) and len(s) >= 4)) else None for s in body["slots"]][:4000]
    return body


def fill_names(d):
    """Fill in card names (posted content arrives without them) – from the card database of the open game."""
    rows = [c for c in (d.get("cards") or []) + (d.get("library") or [])
            if isinstance(c, list) and len(c) >= 2 and (len(c) < 6 or not c[5])]
    if not rows:
        return d
    try:
        from cards import carddb
        db = carddb.by_prints([(c[0], c[1]) for c in rows])
    except Exception:  # noqa: BLE001 – no card database: then simply without names
        return d
    for c in rows:
        r = db.get((str(c[0]).lower(), str(c[1])))
        name = (r or {}).get("name") or ""
        if len(c) < 6:
            c.append(name)
        else:
            c[5] = name
    return d


def _drop_list(game, pid):
    """Delete a friend's stored list in one game (they no longer share anything there). -> (their folder in
    my friends sidebar or "" – the caller remembers it for next time, was anything visible?)"""
    import games
    from collection import trade
    if game not in {k for k, *_ in games.GAMES}:
        return "", False
    try:
        path = trade.friend_path(trade.friends_folder(game), pid)
    except ValueError:   # not a harmless id: there is no such file
        return "", False
    try:
        d = json.loads(path.read_text("utf-8"))
        kept, had = d.get("folder") or "", bool(d.get("cards") or d.get("wants") or d.get("library"))
    except (OSError, ValueError, AttributeError):
        kept, had = "", False
    try:
        path.unlink()
    except OSError:
        pass
    return kept, had


def _change(old, new):
    """What is really new at the friend's? -> "lists" (list cards changed and not empty), "library" (collection
    shared for the first time) or None (nothing visible – e.g. an empty list toggled back and forth)."""
    def rows(d, *keys):   # card data only – names filled in later (fill_names) do not count as new
        return sorted(json.dumps(r[:5] if isinstance(r, list) else r, ensure_ascii=False, sort_keys=True)
                      for k in keys for r in (d or {}).get(k) or [])
    if (new.get("cards") or new.get("wants")) and rows(old, "cards", "wants") != rows(new, "cards", "wants"):
        return "lists"
    if new.get("library") and not (old or {}).get("library"):
        return "library"
    return None


def _store_list(game, d, folder_hint=""):
    """Like "import friend" – but into the folder of the list's game. folder_hint: their earlier folder (in case
    the file has been gone in the meantime). -> _change (what is new?)"""
    import games
    from collection import trade
    folder = trade.friends_folder(game)
    old = trade.FRIENDS
    trade.FRIENDS = folder
    try:
        before = trade.friend(d["id"])
        out = trade.friend_from_import({"kind": "bentcorner", "data": d})
        if game == games.current().key:
            fill_names(out)
        out["source"] = "relay"
        if before is None and folder_hint:
            out["folder"] = folder_hint
        trade.save_friend(out)
    finally:
        trade.FRIENDS = old
    return _change(before, out)
