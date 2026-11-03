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
import hashlib
import json
import logging
import re
import time
import zlib

from system import contacts
from system.i18n import tr

log = logging.getLogger("booster")

URL = contacts.SERVER   # old address as a fallback: netpolite
CODE_LEN = 16
MAX_PLAIN = 60 * 1024        # compressed (zlib) – fits into the server's 64 KB
MAX_UNPACKED = 4 * 1024 * 1024   # at most 4 MB decompressed (protection against "zip bombs")
KINDS = ("friend", "friend_ok", "friend_no", "list", "board_key", "team", "list_delta", "board_gone")
DELTA_MAX = 400   # more changed entries since the last full snapshot: better post everything anew
BOARD_LISTS = "lists"   # slot for trade and want lists (binders get their own slots "binder-<id>")
BOARD_DAYS = 180   # posted content stays 6 months (without re-posting), withdrawing deletes it immediately


class RelayError(Exception):
    pass


# ---------- Key and address ----------
def state(settings):
    return settings.setdefault("relay", {})


def enabled(settings):
    return bool(state(settings).get("on"))


def url(settings):
    return (state(settings).get("url") or URL).rstrip("/")


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
def _post(settings, path, payload, again=True):
    from net import netpolite
    try:
        r = netpolite.post(url(settings) + path, json=payload, timeout=20)
    except Exception as e:  # noqa: BLE001
        raise RelayError(tr(f"Server unreachable ({e.__class__.__name__})")) from None
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code != 200:
        if again and d.get("unknown") and path != "/v1/register":
            # the server no longer knows my address (removed after a year without use): register anew, once
            state(settings).pop("registered", None)
            register(settings)
            return _post(settings, path, payload, again=False)
        raise RelayError(d.get("error") or tr(f"Error {r.status_code}"))
    return d


def _signed(settings, msg):
    return _b64(_signing(settings).sign(msg.encode("utf-8")).signature)


def register(settings):
    """Register your own address with the server (once per server; silent afterwards)."""
    st = state(settings)
    if st.get("registered") == url(settings):
        return
    sk = _signing(settings)
    code, t = my_code(settings), int(time.time())
    _post(settings, "/v1/register", {"code": code, "sign_pk": _b64(sk.verify_key), "t": t,
                                     "sig": _signed(settings, f"register|{code}|{t}")})
    st["registered"] = url(settings)


def lookup(settings, code):
    """Public key of an address – verified: it must match the address (the server cannot swap it)."""
    from net import netpolite
    code = norm(code)
    try:
        r = netpolite.get(f"{url(settings)}/v1/key/{code}", timeout=20)
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
    from nacl.public import SealedBox
    to = norm(to)
    if kind not in KINDS:
        raise ValueError(kind)
    register(settings)
    pk = sign_pk or lookup(settings, to)
    env = {"v": 1, "kind": kind, "game": game or games.current().key, "from": my_code(settings), "to": to,
           "t": int(time.time()), "body": body}
    raw = zlib.compress(json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    if len(raw) > MAX_PLAIN:
        raise RelayError(tr("Too big for the mailbox (shorten the list)"))
    signed = bytes(_signing(settings).sign(raw))
    data = _b64(SealedBox(_box_pk(pk)).encrypt(signed))
    frm, t = env["from"], int(time.time())
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    msg = {"from": frm, "to": to, "t": t, "data": data,
           "sig": _signed(settings, f"send|{frm}|{to}|{digest}|{t}" + (f"|{slot}" if slot else ""))}
    if slot:
        msg["slot"] = slot
    return _post(settings, "/v1/send", msg)


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
    f.pop("boards", None)
    _drop_friend_files(f.get("pid"))
    return f


def unblock(settings, code):
    """Unblock: remove the entry – afterwards both sides can send new requests again."""
    friends(settings).pop(norm(code), None)


def server_block(settings, code, on):
    """Tell the server too (per-recipient block): the blocked ID can no longer drop parcels into my mailbox nor fetch
    what I posted. Best effort – the local block applies anyway. -> True if the server took it"""
    code = norm(code)
    if not code or not enabled(settings):
        return False
    try:
        register(settings)
        me, t, on = my_code(settings), int(time.time()), int(bool(on))
        _post(settings, "/v1/block", {"code": me, "about": code, "on": on, "t": t,
                                      "sig": _signed(settings, f"block|{me}|{code}|{on}|{t}")})
        return True
    except Exception as e:  # noqa: BLE001
        log.info("Mailbox: block on the server (%s): %s", "on" if on else "off", e)
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
            _post(settings, "/v1/board/del", {"code": code, "game": game, "slot": slot, "t": t,
                                              "sig": _signed(settings, f"board_del|{code}|{game}|{slot}|{t}")})
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
    register(settings)
    key = nacl.utils.random(SecretBox.KEY_SIZE)
    raw = zlib.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    data = _b64(SecretBox(key).encrypt(raw))
    code, t = my_code(settings), int(time.time())
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    res = _post(settings, "/v1/board/put", {"code": code, "game": game, "slot": slot, "t": t, "data": data,
                                            "sig": _signed(settings, f"board_put|{code}|{game}|{slot}|{digest}|{t}")})
    until = int(res.get("until") or t + BOARD_DAYS * 86400)
    summary = {"c": len(payload.get("c") or []), "w": len(payload.get("w") or [])}
    n, errors = 0, []
    targets = audience_codes(settings) if audience is None else audience
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
    posted[f"{game}/{slot}"] = {"t": t, "until": until, "to": list(targets), "n": summary}
    return n, errors


def board_get(settings, owner, game, slot, key_b64):
    """Fetch and decrypt what a friend posted. -> (content, time)"""
    from nacl.secret import SecretBox
    register(settings)
    code, t = my_code(settings), int(time.time())
    owner = norm(owner)
    res = _post(settings, "/v1/board/get", {"code": code, "owner": owner, "game": game, "slot": slot, "t": t,
                                            "sig": _signed(settings, f"board_get|{code}|{owner}|{game}|{slot}|{t}")})
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
    _post(settings, "/v1/board/del", {"code": code, "game": game, "slot": slot, "t": t,
                                      "sig": _signed(settings, f"board_del|{code}|{game}|{slot}|{t}")})
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


def fingerprint(data):
    """Short form of a trade file for comparison: {printing|language|foil: count, "w:"name: count}."""
    out = {}
    for c in data.get("c") or []:
        if isinstance(c, (list, tuple)) and len(c) >= 5:
            out[f"{c[0]}|{c[1]}|{c[2]}|{int(bool(c[3]))}"] = int(c[4] or 0)
    for w in data.get("w") or []:
        if isinstance(w, (list, tuple)) and w:
            out["w:" + str(w[0])] = int(w[1] if len(w) > 1 else 1)
    return out


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
    targets = audience_codes(settings) if audience is None else audience
    for c in targets:
        f = friends(settings).get(c) or {}
        try:
            send(settings, c, "list_delta", {"base": int(base), "d": d, "id": pid}, game=game, sign_pk=f.get("sign_pk"),
                 slot=f"delta-{game}")
            n += 1
        except RelayError as e:
            errors.append(f"friend {_short(c)}: {e}")   # ends up in the program log: no names (legal)
    return n, errors


def apply_delta(game, pid, d):
    """Apply a friend's changes to their stored list (the game's folder). -> True if the list existed."""
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
        if len(parts) != 4:
            continue
        if v == 0:
            cards.pop(k, None)
        elif k in cards:
            cards[k][4] = v
        else:
            cards[k] = [parts[0], parts[1], parts[2], int(parts[3] == "1"), v]
    data["cards"], data["wants"] = list(cards.values()), list(wants.values())
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
        person = _clean_person(body)
        if f is not None and f.get("status") in ("ok", "out"):   # both sent a request at the same time
            f.update(person, status="ok", sign_pk=env["_sign_pk"], t=time.time())
            return {"kind": "friend_ok", "code": code, "name": person["name"]}
        fs[code] = dict(person, status="in", sign_pk=env["_sign_pk"], t=time.time())
        return {"kind": "friend", "code": code, "name": person["name"]}
    if kind == "team":   # message from the Bent°Corner team: genuine only with the team key, there are no replies
        from net import teamnews
        if teamnews.is_team(env.get("_sign_pk")) and teamnews.add(settings, body, "direct"):
            return {"kind": "team", "code": code, "name": teamnews.SENDER, "title": str(body.get("title") or "")}
        return None
    if f is None:
        return None   # lists and replies only from known addresses
    if kind == "friend_ok" and f.get("status") in ("out", "ok"):
        f.update(_clean_person(body), status="ok", t=time.time())
        return {"kind": "friend_ok", "code": code, "name": f.get("name")}
    if kind == "friend_no" and f.get("status") == "out":
        f.update(status="no", t=time.time())
        return {"kind": "friend_no", "code": code, "name": f.get("name")}
    if kind == "board_key" and f.get("status") == "ok":
        game, slot = str(body.get("game") or ""), str(body.get("slot") or "")
        if not game or not slot or not isinstance(body.get("key"), str):
            return None
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
        if not b.get("fetched") or int(b.get("fetched") or 0) != int(body.get("base") or 0):
            # I lack their full snapshot (or have an older one): fetch it first – it already includes the changes
            return {"kind": "list_delta", "code": code, "name": f.get("name"), "game": game, "refetch": True}
        ok = apply_delta(game, pid, d)
        f["last_list"] = time.time()
        return {"kind": "list_delta", "code": code, "name": f.get("name"), "game": game, "refetch": not ok}
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
