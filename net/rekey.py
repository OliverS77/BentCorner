"""„Gerät entfernen“ / „Neuer Code“ = key change (docs/web/PAIRING.md §3; lead/legal 07.11.2026).

Both give this identity a NEW seed – a new address, a new vault key, a new mailbox. The difference is who follows:
    "remove"  nobody of the old key: the old address answers only 410 {"gone"}; a removed (lost, foreign) device
              keeps nothing it can read with – the own devices pair again with a new code
    "new"     the own devices follow: the server hands them the new seed sealed with the old vault key ("fwd")
Friends: each friend with status ok gets a note (a parcel from the NEW address, signed by the OLD key over
"rekey_friend|old|new|<friend>|t") – at once as a parcel, and at the server for those away longer. Their app asks
before moving (legal 07.11.: [Accept] [Decline]), never silently.

    change(settings, mode) -> {"old", "new"}       steps 2–3: register the new address, one /v1/rekey call
    finish(settings) -> friends told               step 4: the parcels (also at the next start: rekey_pending)
The vault and rescue envelope of the old address are deleted by the server with the change (box.py drop_key); the
caller then puts this device's whole state into the new vault (a snap) and asks for a new rescue code.
"""
import base64
import functools
import hashlib
import json
import logging
import time

from net import relay

log = logging.getLogger("booster")
from system.i18n import tr

MODES = ("remove",)   # „Neuer Code“ with a seed change is gone (FUNDE A9, lead 08.11.)


def _own(fn):
    """S7: the key change runs alone – no sync/mailbox job meanwhile, a 410 for the address being left is ignored
    (relay.own_change; relay.Busy if a job doesn't end in time)."""
    @functools.wraps(fn)
    def run(*a, **kw):
        with relay.own_change():
            return fn(*a, **kw)
    return run


class UnknownDevice(ValueError):
    """The server lists a device this identity's own (sealed) device list doesn't know – nothing is sent."""
    def __init__(self, devs):
        super().__init__(f"unknown device(s) on the server: {', '.join(devs)}")
        self.devs = list(devs)


def _new_identity(settings):
    """A fresh seed in a settings copy that shares only the server address."""
    import nacl.utils
    st = relay.state(settings)
    return {"relay": {"seed": base64.b64encode(nacl.utils.random(32)).decode(), "url": st.get("url")}}


def device_name(settings):
    """How this device calls itself to its own other devices (Deine Geräte): set there, else the computer's name."""
    import platform
    return str(settings.get("device_name") or platform.node() or "PC")[:60]


@_own
def change(settings, mode, guard_code=None):
    """The key change (blocking: network). Before it nothing has changed; after it the new identity is this device's.
    -> {"old", "new"}; RelayError (403 not allowed, 429 once a day too often, 410 this address was already moved)."""
    from net import pairing
    if mode not in MODES:
        raise ValueError(mode)
    st = relay.state(settings)
    old_seed = st.get("seed")
    if not old_seed:
        raise relay.RelayError(tr("No ID yet – nothing to change."))
    relay.register(settings)
    old = relay.my_code(settings)
    new_st = _new_identity(settings)
    relay.register(new_st)
    new = relay.my_code(new_st)
    new_pk = relay._b64(relay._signing(new_st).verify_key)
    t = int(time.time())
    notes = _notes(settings, st, old, new, new_st, new_pk, t)
    notes_raw = json.dumps(notes, separators=(",", ":"), sort_keys=True)
    fwd = ""   # no envelope for followers: own devices follow only via their signed letter (S6, remove_one)
    # who did it (legal 07.11.: a removed device says which device removed it) – sealed with the OLD vault key: only
    # sealed with the OLD vault key: only the old identity's devices can read it (the server hands it to anyone who
    # asks at the old address – FUNDE A9 – but it only names a device)
    by = pairing.vault_seal(old_seed, {"v": 1, "name": device_name(settings)})
    fh = hashlib.sha256(fwd.encode("ascii")).hexdigest()
    nh = hashlib.sha256(notes_raw.encode("utf-8")).hexdigest()
    bh = hashlib.sha256(by.encode("ascii")).hexdigest()
    msg = f"rekey|{old}|{new}|{fh}|{nh}|{bh}|{t}"
    payload = {"code": old, "new_code": new, "new_sign_pk": new_pk, "t": t, "fwd": fwd, "notes": notes_raw, "by": by,
               "sig": relay._signed(settings, msg), "sig_new": relay._signed(new_st, f"rekey_new|{old}|{new}|{t}")}
    if guard_code:   # a protection code is set: the same message signed with it (sig_main, net/guard.py)
        from net import guard
        payload["sig_main"] = guard.sign(guard_code, msg, salt=guard.salt_of(settings))
    from net import devkeys
    devkeys.attach(settings, payload, msg)   # B5: a registered device signs too (box 403 dev_required otherwise)
    _send(settings, payload, new_st, {"old": old, "new": new, "t": t, "mode": mode,
                                      "friends": {c: notes[c] for c in notes}})
    return {"old": old, "new": new, "mode": mode}


@_own
def remove_one(settings, target, guard_code=None, known=None, plan=None):
    """„Remove one device“ (B5, DEVICE-KEYS §2; box 7fe65d1): this device R moves the identity to a new seed; the chosen
    device and every device it added stay outside; each other remaining device gets the new seed sealed for its own
    box key (it fetches it at the old address via /v1/dev/fwd). Friends get the same notes as with every key change.
    -> {"old", "new", "gone": [dev_id…]}; RelayError/VaultError (403 dev_required / main_required, 409 the device list
    changed – fetch it again and ask the user again)."""
    from net import devkeys
    st = relay.state(settings)
    if not st.get("seed"):
        raise relay.RelayError(tr("No ID yet – nothing to change."))
    me = devkeys.mine()["dev_id"]
    reg = devkeys.listing(settings)
    rows = reg.get("list") or []
    targets = [target] if isinstance(target, str) else list(target)   # several: „take over“ (foreign devices)
    ids = {r["dev_id"] for r in rows}
    gone = []
    for x in targets:
        if x not in ids:
            raise ValueError("not a removable device")
        gone += [g for g in devkeys.chain(rows, x) if g not in gone]
    if me in gone or not gone:
        raise ValueError("not a removable device")
    rv = int(reg.get("reg_version") or 0)
    if plan is not None and (int(plan.get("rv") or 0) != rv or sorted(plan.get("gone") or []) != sorted(gone)):
        # the page showed another plan (review 08.11., M7): devices added meanwhile would go along unasked – stop
        raise relay.RelayError(tr("The device list changed – please look again."), 409, {"plan_changed": True})
    if known is not None:   # only devices this identity itself lists (sealed */devices) get the new seed – a device the
        # server alone shows (compromised server, review 08.11., H1-6) gets nothing: stop and say so
        stranger = [r["dev_id"] for r in rows if r["dev_id"] not in gone and r["dev_id"] != me and r["dev_id"] not in known]
        if stranger:
            raise UnknownDevice(stranger)
    relay.register(settings)
    old = relay.my_code(settings)
    new_st = _new_identity(settings)
    relay.register(new_st)
    new = relay.my_code(new_st)
    new_pk = relay._b64(relay._signing(new_st).verify_key)
    t = int(time.time())
    notes = _notes(settings, st, old, new, new_st, new_pk, t)
    fwd = {r["dev_id"]: devkeys.seal_for(r["box_pk"], devkeys.letter_for(settings, old, new, new_st["relay"]["seed"],
                                                                           r["dev_id"], t))
           for r in rows if r["dev_id"] not in gone and r["dev_id"] != me}
    gone_raw = json.dumps(gone, separators=(",", ":"))
    fwd_raw = json.dumps(fwd, separators=(",", ":"), sort_keys=True)
    notes_raw = json.dumps(notes, separators=(",", ":"), sort_keys=True)
    h = lambda x: hashlib.sha256(x.encode("utf-8")).hexdigest()  # noqa: E731
    msg = f"rekey1|{old}|{new}|{rv}|{h(gone_raw)}|{h(fwd_raw)}|{h(notes_raw)}|{t}"
    payload = {"mode": "remove_one", "code": old, "new_code": new, "t": t, "reg_version": rv, "gone": gone_raw,
               "fwd": fwd_raw, "notes": notes_raw, "sig_old": relay._signed(settings, msg),
               "sig_new": relay._signed(new_st, f"rekey_new|{old}|{new}|{t}")}
    if guard_code:
        from net import guard
        payload["sig_main"] = guard.sign(guard_code, msg, salt=guard.salt_of(settings))
    devkeys.attach(settings, payload, msg)
    _send(settings, payload, new_st, {"old": old, "new": new, "t": t, "mode": "remove_one", "friends": dict(notes)})
    return {"old": old, "new": new, "gone": gone}


def _send(settings, payload, new_st, pending):
    """POST /v1/rekey with the new seed kept BEFORE it (relay.rekey_inflight, review 08.11. M4): if the answer gets lost
    although the server moved, this device must not stay on the old seed – the old address answers 410 and it would
    destroy itself; were it the last device, nobody would have the new seed. A clear „no“ from the server forgets it."""
    st = relay.state(settings)
    st["rekey_inflight"] = dict(pending, seed=new_st["relay"]["seed"],
                                registered=relay.state(new_st).get("registered"))
    try:
        relay._post(settings, "/v1/rekey", payload)
    except Exception as e:  # noqa: BLE001
        if getattr(e, "status", 0):   # the server answered: nothing moved here
            st.pop("rekey_inflight", None)
        elif confirm_inflight(settings):   # no answer – but the address did move: this device follows
            log.info("Key change: the answer got lost, the server had moved – taken over")
            return
        raise
    _adopt(settings)


def _adopt(settings):
    """From here the change counts: this device takes the new identity."""
    st = relay.state(settings)
    inf = st.pop("rekey_inflight")
    st["seed"] = inf["seed"]
    st["registered"] = inf.get("registered")
    st.pop("test_registered", None)
    st["rekey_pending"] = {k: inf[k] for k in ("old", "new", "t", "mode", "friends")}
    if inf["mode"] == "remove_one":
        from net import devkeys
        devkeys.moved(settings, inf["new"])   # the registry moved along (without gone): R stays registered


def confirm_inflight(settings):
    """A key change whose answer never came: did the server move the address? It did if the NEW address lists this
    device (the registry moves along, R stays in it). -> True taken over | False it didn't move (forgotten) |
    None can't tell now (offline – kept, asked again with the next 410)."""
    st = relay.state(settings)
    inf = st.get("rekey_inflight")
    if not inf:
        return False
    if inf.get("old") != relay.my_code(settings):   # left from an older identity
        st.pop("rekey_inflight", None)
        return False
    from net import devkeys
    me = devkeys.mine(create=False)
    try:
        rows = devkeys.listing({"relay": {"seed": inf["seed"], "url": st.get("url")}}).get("list") or []
    except Exception as e:  # noqa: BLE001
        log.info("Key change: asking the new address failed (%s)", e.__class__.__name__)
        return None if not getattr(e, "status", 0) else _forget(st)
    if me and any(r.get("dev_id") == me["dev_id"] for r in rows):
        _adopt(settings)
        return True
    return _forget(st)


def _forget(st):
    st.pop("rekey_inflight", None)
    return False


def _notes(settings, st, old, new, new_st, new_pk, t):
    """The parcels for the friends: the old key vouches for the new address (rekey_friend)."""
    notes = {}
    for code, f in sorted((st.get("friends") or {}).items()):
        if f.get("status") != "ok" or not f.get("sign_pk"):
            continue
        body = {"old": old, "new": new, "new_sign_pk": new_pk, "t": t,
                "sig_old": relay._signed(settings, f"rekey_friend|{old}|{new}|{relay.norm(code)}|{t}")}
        notes[relay.norm(code)] = relay.pack(new_st, code, f["sign_pk"], "rekey", body)
    return notes


def after_change(settings, guard_code=None):
    """The steps AFTER a key change that went through (review 08.11., M11): the friends' notes and, with a protection
    code, the rescue envelope at the new address. The change itself counts either way – a failure here is no error
    of the change: the notes stay pending (sent at the next start), a missing envelope is marked (rescue_missing).
    -> {"rescued": bool, "after_failed": [...]}"""
    failed = []
    try:
        finish(settings)
    except Exception as e:  # noqa: BLE001 – rekey_pending stays: told at the next start
        log.info("Key change: telling the friends failed (%s) – again at the next start", e.__class__.__name__)
        failed.append("friends")
    rescued = False
    if guard_code:
        from net import vault
        try:
            vault.rescue_put(settings, guard_code)
            rescued = True
        except Exception as e:  # noqa: BLE001
            log.info("Key change: the rescue envelope didn't go up (%s)", e.__class__.__name__)
            failed.append("rescue")
    return {"rescued": rescued, "after_failed": failed}


def finish(settings):
    """Step 4: the notes as parcels to every friend (from the new address). What fails stays for the next start –
    the server's note reaches them anyway when they next send to the old address. -> friends told now."""
    st = relay.state(settings)
    pend = st.get("rekey_pending") or {}
    told = 0
    for code in sorted(pend.get("friends") or {}):
        try:
            relay._post(settings, "/v1/send", _send_payload(settings, code, pend["friends"][code]))
        except relay.RelayError as e:
            if e.status not in (403, 404, 410):
                continue   # not reachable now: next time
        told += 1
        pend["friends"].pop(code, None)
    if not pend.get("friends"):
        st.pop("rekey_pending", None)
    return told


def _send_payload(settings, to, data):
    frm, t = relay.my_code(settings), int(time.time())
    digest = hashlib.sha256(data.encode("ascii")).hexdigest()
    return {"from": frm, "to": relay.norm(to), "t": t, "data": data,
            "sig": relay._signed(settings, f"send|{frm}|{relay.norm(to)}|{digest}|{t}")}
