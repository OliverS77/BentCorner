"""The own vault (Fach) on the mailbox server: /v1/vault/get · put · del (docs/web/PAIRING.md §4, SYNC-PLAN §3).

Only transport – what goes in is collection/syncrun.py (sealed packages, the server sees Base64 only).

    get(settings, since)                 -> {"version", "snap", "items": [{"seq", "kind", "data", "t"}], ...}
    put(settings, kind, base, data)      -> {"version", ...}; a snapshot over 1 MB goes in parts (same sid)
    clear(settings)                      empties the vault
    server_ms()                          the server's time of the last answer (HTTP Date) – for the clock, or None

Errors keep their meaning (VaultError.status): 409 another device wrote first (fetch, then again), 413 full or a
part too big (compact: a snap), 429 enough for today, 503 paused (the server's emergency switch) – nothing is lost.
Requests are signed with the identity's key like every mailbox request (net/relay.py).

Sync test (SYNC-TESTPLAN, lead/Gordon 06.11.): from the source with BC_SYNC=1 the vault, coupling and registration go
to BC_SYNC_BASE (syncrun.test_base) instead of the mailbox. Gordon's test instance sits behind a gate: its code is typed
in by hand (set_gate), lives ONLY in this process's memory and goes ONLY as the cookie bc_gate, over https, to
bentcorner.app/testapp/box – never into a file, a log, a crash report or the settings, and no switch pre-fills it.
"""
import email.utils
import secrets
import time
from urllib.parse import urlparse

from net import relay
from system import contacts
from system.i18n import tr

PART = 1_000_000          # raw bytes per part (the server's VAULT_PART); Base64 text is split at 4/3 of it
PART_TEXT = PART // 3 * 4
_server_ms = None
GATE_HOST = urlparse(contacts.SERVER).hostname   # the gated test instance lives on our server, under GATE_PATH
GATE_PATH, GATE_COOKIE = "/testapp/box", "bc_gate"
REREGISTER_GAP = 900      # s: registering anew uses one of the server's 5 new addresses an hour – at most every 15 min
_reregistered = [0.0]
_gate = [None]            # the test server's gate TOKEN (from /v1/gate) – memory only; the code itself is never kept
GATE_URL = contacts.SERVER + "/v1/gate"   # code -> token, like the browser's code.html (Gordon 06.11.)


def set_gate(code):
    """The access code typed in by hand -> exchanged at /v1/gate for the token the server expects as cookie bc_gate;
    only the token stays (in memory), the code is forgotten at once. Empty forgets the token. Blocking (network):
    call it in the background. -> None; VaultError(403) wrong code, (429) too many tries, (0) unreachable."""
    code = str(code or "").strip()
    _gate[0] = None
    if not code:
        return
    import requests
    from net import netpolite
    try:
        r = requests.post(GATE_URL, json={"code": code}, timeout=20, allow_redirects=False,
                          headers={"User-Agent": netpolite.UA, netpolite.CHECK_HEADER[0]: netpolite.CHECK_HEADER[1]})
    except Exception as e:  # noqa: BLE001   (only the class name: the message could carry the request)
        raise VaultError(0, tr(f"Server unreachable ({e.__class__.__name__})")) from None
    finally:
        code = None
    if r.status_code == 403:
        raise VaultError(403, tr("Wrong access code."))
    if r.status_code == 429:
        raise VaultError(429, tr("Too many tries – please try again later."))
    token = r.cookies.get(GATE_COOKIE) if r.status_code == 200 else None
    if not token:
        raise VaultError(r.status_code or 0, tr(f"Error {r.status_code}"))
    _gate[0] = token


def _gated(url):
    """Is this a request to the gated test instance (and only that: https, exactly this host, below this path)?"""
    u = urlparse(url)
    path = u.path or "/"
    return (u.scheme == "https" and (u.hostname or "").lower() == GATE_HOST
            and (path == GATE_PATH or path.startswith(GATE_PATH + "/")))


def _base(settings):
    """Where the vault, the minute question and the device registry go: the test server only from the source; a Ship
    build always the live server (contacts.SERVER = bentcorner.app, Gordon 08.11.) – never an address stored in older
    settings (the old domain points at the same box only until ~2027-01-29)."""
    from collection import syncrun
    test = syncrun.test_base()
    if test:
        return test
    if syncrun.ship_build():
        return contacts.SERVER.rstrip("/")
    return relay.url(settings)


def gate_needed(settings=None):
    """The test server wants its access code and none is typed in yet (the settings page asks for it)."""
    from collection import syncrun
    base = syncrun.test_base()
    return bool(base) and _gated(base + "/v1/vault") and not _gate[0]


class GateMissing(Exception):
    """A request to the gated test instance, but no access code typed in yet (nothing was sent)."""


def gated(method, url, timeout, **kw):
    """Every request of this app to our server goes through here when it may be the test instance (vault, mailbox,
    forget – Gordon 07.11.: the instance lets nothing through without the gate): ONLY there (https, GATE_HOST,
    below GATE_PATH) the token goes along as cookie bc_gate – never to the live mailbox or any other host, never into
    a log (nothing here logs; the request is sent directly, without redirects). Elsewhere: netpolite as always."""
    from net import netpolite
    if not _gated(url):
        return (netpolite.post if method == "POST" else netpolite.get)(url, timeout=timeout, **kw)
    if not _gate[0]:
        raise GateMissing()
    # directly, not through netpolite: its fallback to the old server name would take the cookie along; no redirects
    import requests
    return (requests.post if method == "POST" else requests.get)(
        url, timeout=timeout, allow_redirects=False, cookies={GATE_COOKIE: _gate[0]},
        headers={"User-Agent": netpolite.UA, netpolite.CHECK_HEADER[0]: netpolite.CHECK_HEADER[1]}, **kw)


def _send(url, payload):
    try:
        return gated("POST", url, 30, json=payload)
    except GateMissing:
        raise VaultError(401, tr("The access code for the test server is missing.")) from None


class VaultError(Exception):
    def __init__(self, status, msg, data=None):
        super().__init__(msg)
        self.status = status
        self.data = data or {}


def server_ms():
    return _server_ms


def _post(settings, path, payload, again=True):
    global _server_ms
    try:
        r = _send(_base(settings) + path, payload)
    except VaultError:
        raise
    except Exception as e:  # noqa: BLE001   (only the class name: the message could carry the request)
        raise VaultError(0, tr(f"Server unreachable ({e.__class__.__name__})")) from None
    try:
        when = email.utils.parsedate_to_datetime(r.headers.get("Date") or "")
        _server_ms = int(when.timestamp() * 1000)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = r.json()
    except ValueError:
        d = {}
    if not 200 <= r.status_code < 300:   # 202: a join request was taken (B5)
        if again and d.get("unknown") and path != "/v1/register" and time.time() - _reregistered[0] > REREGISTER_GAP:
            # the server no longer knows my address (the mailbox after a year without use, the test instance when
            # it was emptied): register anew, once, then this request again – like relay._post
            from collection import syncrun
            relay.state(settings).pop("test_registered" if syncrun.test_base() else "registered", None)
            _reregistered[0] = time.time()
            _me(settings)
            return _post(settings, path, payload, again=False)
        if r.status_code == 410 and path in relay.OWN_PATHS and (d.get("gone") or d.get("fwd") or d.get("per_device")) and payload.get("code")                 and str(payload["code"]).upper() == relay.my_code(settings):
            relay.moved_away(settings, d)   # removed / moved: follow, or a new identity (PAIRING §3)
        raise VaultError(r.status_code, d.get("error") or tr(f"Error {r.status_code}"), d)
    return d


def _me(settings):
    from collection import syncrun
    base = syncrun.test_base()
    if base is None:
        relay.register(settings)   # once per server, silent afterwards
    else:
        _register_test(settings, base)
    return relay.my_code(settings), int(time.time())


def _register_test(settings, base):
    """The same registration as relay.register, but at the test server – once per test server (it allows 5 an hour)."""
    st = relay.state(settings)
    if st.get("test_registered") == base:
        return
    sk = relay._signing(settings)
    code, t = relay.my_code(settings), int(time.time())
    _post(settings, "/v1/register", {"code": code, "sign_pk": relay._b64(sk.verify_key), "t": t,
                                     "sig": relay._signed(settings, f"register|{code}|{t}")})
    st["test_registered"] = base


def get(settings, since):
    code, t = _me(settings)
    since = int(since or 0)
    return _post(settings, "/v1/vault/get", {"code": code, "since": since, "t": t,
                                            "sig": relay._signed(settings, f"vault_get|{code}|{since}|{t}")})


def _put_one(settings, kind, base, data, sid="", part=0, parts=1):
    import hashlib
    code, t = _me(settings)
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    msg = f"vault_put|{code}|{kind}|{base}|{sid}|{part}|{parts}|{digest}|{t}"
    payload = {"code": code, "kind": kind, "base": int(base), "t": t, "data": data, "sig": relay._signed(settings, msg)}
    if parts > 1:
        payload.update(sid=sid, part=part, parts=parts)
    return _post(settings, "/v1/vault/put", relay._dev(settings, payload, msg))


def put(settings, kind, base, data):
    """data: the sealed item (Base64 text). An add must fit one part; a snap is split into parts of the text."""
    if kind == "add" or len(data) <= PART_TEXT:
        return _put_one(settings, kind, base, data)
    chunks = [data[i:i + PART_TEXT] for i in range(0, len(data), PART_TEXT)]
    sid = secrets.token_hex(8)
    d = {}
    for i, c in enumerate(chunks):
        d = _put_one(settings, kind, base, c, sid, i, len(chunks))
    return d


# ---------- Coupling, the old device (PAIRING.md §2): this PC shows the code, the other device enters it ----------
def pair_extra(settings, next_n=None, dev=None, invite=None, dev_nick=None):
    """What the new device needs at once (PAIRING §2 payload "extra"): the friends with their board keys, the name, and
    what kind of device offers the code ("pc" here, "phone" on the web) – the joining one names it right in its
    question („Stand vom PC behalten“; performance' Teil-A run 07.11.: a PC joining a PC said „Handy“)."""
    out = {"device": "pc"}
    from net import guard
    salt = guard.salt_of(settings, ask=False)
    if salt:   # A2: the joining device signs its entry with the code – and needs the ID's salt for it (S5 = b)
        out["guard_salt"] = salt
    if invite:   # B5: the joining device enters the registry with it (signed by this device, 15 min, once)
        out["invite"] = invite
    if dev:   # this device's id in the device list: the joining one names it („keep Device 2's state“)
        out["dev"] = str(dev)
    if dev_nick:   # C (lead 12.11.): this device's nickname – the joining one names it in its pairing step
        out["dev_nick"] = [int(x) for x in dev_nick]
    if settings.get("device_name"):   # … or its own name, if it has one
        out["dev_name"] = str(settings["device_name"])[:60]
    if next_n:   # the joining device's number in the device list – it prefills „Device N“ (lead/Oliver 07.11.)
        out["next_n"] = int(next_n)
    friends = (settings.get("relay") or {}).get("friends")
    if friends:
        out["friends"] = friends
    name = (settings.get("profile") or {}).get("name")
    if name:
        out["name"] = name
    return out


def pair_offer(settings, next_n=None, dev=None, invite=None, dev_nick=None):
    """A new code; the sealed identity waits under its slot (10 min, once). -> (code, pid, until unix s).
    The code itself never goes to the server – only the pid derived from it (Argon2id)."""
    import hashlib
    from net import pairing
    seed = (settings.get("relay") or {}).get("seed")
    if not seed:   # no identity yet – the first sync makes it (sync_ctl.pair_show waits for that)
        raise VaultError(0, tr("Sync once first – then show a code for a new device."))
    code = pairing.new_code()
    pid, key = pairing.slot(code)   # one Argon2id run for the slot and the seal
    data = pairing.seal(code, pairing.payload_of(seed, pair_extra(settings, next_n, dev, invite, dev_nick)), key=key)
    me, t = _me(settings)
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    msg = f"pair_put|{me}|{pid}|{digest}|{t}"
    d = _post(settings, "/v1/pair/put", relay._dev(settings, {"code": me, "pid": pid, "data": data, "t": t,
                                                              "sig": relay._signed(settings, msg)}, msg))
    return code, pid, int(d.get("until") or (t + 600))


def pair_fetched(settings, pid):
    """Has the other device fetched it? True / False; VaultError 404 = expired (or replaced by a newer code)."""
    me, t = _me(settings)
    d = _post(settings, "/v1/pair/state", {"code": me, "pid": pid, "t": t,
                                           "sig": relay._signed(settings, f"pair_state|{me}|{pid}|{t}")})
    return bool(d.get("fetched"))


def pair_take(settings, code):
    """The NEW device (this PC joins, PAIRING §2): fetch the sealed identity under the code's slot – once, the server
    deletes it then. -> the payload {"v", "code", "seed", "extra"}; PairError: the code doesn't open it; VaultError
    404: no such code (expired, already fetched, mistyped). settings only for the server address."""
    from net import pairing
    pid, key = pairing.slot(code)
    d = _post(settings, "/v1/pair/get", {"pid": pid})
    return pairing.open_sealed(code, d.get("data") or "", key=key)


def _main(payload, guard_code, msg, settings=None):
    """With a protection code set, the server wants the same message signed with it too (sig_main; Gordon faf6385)."""
    if guard_code:
        from net import guard
        payload["sig_main"] = guard.sign(guard_code, msg, salt=guard.salt_of(settings))
    return payload


def clear(settings, guard_code=None):
    """„Online-Sicherung löschen“: the vault AND the rescue envelope (legal, Datenschutz 5a) – vault/del alone left the
    envelope until it expired. Both must succeed; a failure raises (the caller tries again). A protection code set:
    both only with it (lead 07.11.) – without, VaultError 403 {"main_required"}."""
    code, t = _me(settings)
    msg = f"vault_del|{code}|{t}"
    from net import devkeys
    d = _post(settings, "/v1/vault/del", devkeys.attach(
        settings, _main({"code": code, "t": t, "sig": relay._signed(settings, msg)}, guard_code, msg, settings), msg))
    rescue_del(settings, guard_code)
    return d


# ---------- Rescue envelope (SYNC-PLAN §2): the seed sealed with the rescue code, one per address ----------
def rescue_put(settings, rescue_code, keys=None):
    """Seal this identity's seed with the rescue code and store it (replaces the address's old envelope at once – the
    old code finds nothing any more). The rescue code itself never leaves the device, only rid (derived)."""
    import hashlib
    from net import guard, pairing
    salt = (keys or {}).get("salt") or guard.setup_salt(settings)
    keys = keys or pairing.code_keys(rescue_code, salt)   # both stages: rid, envelope key and the protection key
    rid = keys["rid"]
    relay._signing(settings)   # the identity (seed) – made now if this device has none yet
    data = pairing.rescue_seal(rescue_code, settings["relay"]["seed"], salt, keys=keys)
    me, t = _me(settings)
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    msg = f"rescue_put|{me}|{rid}|{digest}|{t}"
    # one code (lead 07.11.): the envelope's code IS the protection code – with one set the server wants sig_main
    # (Gordon 07.11.: else a sneaked-in device could overwrite the envelope); before it is set it is ignored
    res = _post(settings, "/v1/rescue/put", relay._dev(settings, {"code": me, "rid": rid, "data": data, "t": t,
                                                                   "sig": relay._signed(settings, msg),
                                                                   "sig_main": guard.sign(rescue_code, msg, keys)}, msg))
    relay.state(settings)["guard_salt"] = salt   # the ID's salt from now on (the first code brought it)
    return res


def rescue_del(settings, guard_code=None):
    me, t = _me(settings)
    msg = f"rescue_del|{me}|{t}"
    from net import devkeys
    return _post(settings, "/v1/rescue/del", devkeys.attach(
        settings, _main({"code": me, "t": t, "sig": relay._signed(settings, msg)}, guard_code, msg, settings), msg))


def rescue_fetch(settings, rescue_code):
    """Restore without the old device: -> the seed from the envelope (PairError: the code doesn't open it; VaultError
    404: no envelope for this code; 429: too many tries, the box brakes rescue/get). settings only for the server
    address – nothing is signed (no identity yet); the ID's salt from the envelope is remembered there."""
    from net import pairing
    rid = pairing.rescue_rid(rescue_code)   # stage 1 (64 MiB): only where the envelope lies
    d = _post(settings, "/v1/rescue/get", {"rid": rid})
    seed, salt = pairing.rescue_open(rescue_code, d.get("data") or "")   # stage 2 with the salt of its header
    relay.state(settings)["guard_salt"] = salt
    return seed
