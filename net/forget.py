"""„Bent°Corner löschen“ – the server part (labs/installer/PLAN.md § 5, texts legal 03.11.2026, endpoint Gordon 03.11.2026).

    available(settings) -> bool                        B or A? GET /v1/health says "forget": true (Gordon) – the
                                                       checkbox wording follows it; error/offline = A
    delete_server(settings, notify=True) -> Result     what the checkbox in Settings and the uninstaller do
    forget(settings) -> Result                         B: /v1/forget – ID with key, lists, binders, parcels, blocks
    delete_shared(settings, notify=True) -> Result     A: /v1/board/del for every shared list/binder (until B is live)
    main()                                             `BentCorner.exe --forget-server` for the uninstaller: no window,
                                                       exactly the deletion request(s), exit code = Result.code

Rules (legal): "deleted" only when the server confirmed it; otherwise the app says clearly that NOTHING was deleted,
with the automatic deadlines and the mail route (contacts.MAIL) plus the own ID. A deleted ID is never registered anew
(the usual _post re-registers on {"unknown": true} – not here). The uninstaller sends nothing else: no register, no
messages to friends, no statistics.
"""
import json
import logging
import time
from dataclasses import dataclass

from net import relay

log = logging.getLogger("booster")

DELETED, ALREADY, FAILED, NO_ID, UNAVAILABLE = "deleted", "already", "failed", "no_id", "unavailable"
MAIN_REQUIRED = "main_required"   # a protection code is set: needed (or wrong; detail = retry_after s)
EXIT = {DELETED: 0, ALREADY: 2, FAILED: 3, NO_ID: 4, UNAVAILABLE: 3, "main_required": 3}
CHECK_FULL, CHECK_SHARED = 10, 11   # `--forget-server --check`: version B (/v1/forget) or A (lists and binders only)
# the server's automatic deadlines (Gordon, live code + privacy policy, 03.11.2026) – the texts name exactly these
BOARD_DAYS = relay.BOARD_DAYS   # shared lists and binders: 6 months after they were last shared
KEY_DAYS = 365                  # ID and key: after 365 days without use
PARCEL_DAYS = 14                # parcels: once picked up, at the latest after 14 days


@dataclass
class Result:
    status: str          # DELETED / ALREADY / FAILED / NO_ID / UNAVAILABLE
    detail: str = ""     # for the log (never shown as the only message)
    code: str = ""       # the own ID (pretty) – shown with the failure text for the mail route
    offline: bool = False   # no connection at all (not a refusal): the page deletes locally and remembers (lead 07.11.)

    @property
    def exit_code(self):
        return EXIT[self.status]

    @property
    def ok(self):
        return self.status in (DELETED, ALREADY, NO_ID)


def has_id(settings):
    """Is there anything of ours on the server? (an ID was made and registered at some point)"""
    st = relay.state(settings)
    return bool(st.get("seed")) and bool(st.get("registered") or st.get("posted"))


def _raw_post(settings, path, payload):
    """POST without the re-registering of relay._post -> (status, json dict) or raises OSError-like on no answer."""
    from net import vault
    r = vault.gated("POST", relay.url(settings) + path, 20, json=payload)   # gate cookie only for the test instance
    try:
        d = r.json()
    except ValueError:
        d = {}
    return r.status_code, d if isinstance(d, dict) else {}


def _forget_local_state(settings):
    """After the server confirmed: our ID no longer exists there – drop it here too, keys included (Gordon: otherwise
    the next start registers the same ID again). Friends' entries stay as local data until the PC part is deleted."""
    st = relay.state(settings)
    for k in ("registered", "posted", "on", "seed"):
        st.pop(k, None)


def available(settings):
    """Does the server offer /v1/forget? Only {"forget": true} in GET /v1/health counts (Gordon 03.11.2026);
    a missing field, an error or no network means version A (lists and binders only)."""
    from net import vault
    try:
        r = vault.gated("GET", relay.url(settings) + "/v1/health", 10)
        return r.status_code == 200 and (r.json() or {}).get("forget") is True
    except Exception:  # noqa: BLE001
        return False


def forget(settings, guard_code=None):
    """B: delete everything of ours on the server at once (POST /v1/forget, signed "forget|<CODE>|<t>")."""
    if not has_id(settings):
        return Result(NO_ID)
    code, t = relay.my_code(settings), int(time.time())
    payload = {"code": code, "t": t, "sig": relay._signed(settings, f"forget|{code}|{t}")}
    if guard_code:   # a protection code is set: needed for deleting everything online (Oliver 07.11.)
        from net import guard
        payload["sig_main"] = guard.sign(guard_code, f"forget|{code}|{t}", salt=guard.salt_of(settings))
    from net import devkeys
    devkeys.attach(settings, payload, f"forget|{code}|{t}")
    from net import vault
    try:
        status, d = _raw_post(settings, "/v1/forget", payload)
    except vault.GateMissing:   # the test server's access code not typed in: nothing sent – NOT offline (no wiping)
        return Result(FAILED, "gate", relay.pretty(code))
    except Exception as e:  # noqa: BLE001 – offline, timeout, DNS …
        return Result(FAILED, e.__class__.__name__, relay.pretty(code), offline=True)
    if status == 200 and d.get("deleted"):
        _forget_local_state(settings)
        return Result(DELETED, code=relay.pretty(code))
    if status == 403 and d.get("unknown"):
        _forget_local_state(settings)
        return Result(ALREADY, code=relay.pretty(code))
    if status == 404 and not d.get("error"):
        return Result(UNAVAILABLE, "no /v1/forget yet", relay.pretty(code))
    if status in (403, 429) and d.get("main_required"):
        return Result(MAIN_REQUIRED, str(d.get("retry_after") or ""), relay.pretty(code))
    return Result(FAILED, str(d.get("error") or status), relay.pretty(code))


def delete_shared(settings, notify=True):
    """A (until /v1/forget is live): delete every shared list and binder (/v1/board/del). notify: tell the friends who
    had them (board_gone, like withdrawing) – the uninstaller doesn't (it sends nothing but the deletion)."""
    if not has_id(settings):
        return Result(NO_ID)
    code = relay.my_code(settings)
    posted = relay.state(settings).setdefault("posted", {})
    failed = []
    for key in list(posted):
        game, _, slot = key.partition("/")
        try:
            if notify:
                relay.withdraw(settings, game, slot)
            else:
                t = int(time.time())
                msg = f"board_del|{code}|{game}|{slot}|{t}"
                status, d = _raw_post(settings, "/v1/board/del", relay._dev(settings, {
                    "code": code, "game": game, "slot": slot, "t": t, "sig": relay._signed(settings, msg)}, msg))
                if status != 200 and not d.get("unknown"):
                    raise relay.RelayError(str(d.get("error") or status))
                posted.pop(key, None)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{key}: {e}")
    if failed:
        return Result(FAILED, "; ".join(failed), relay.pretty(code))
    return Result(DELETED, code=relay.pretty(code))


# ---------- deleting everything while offline (lead 07.11.) ----------
def pending_file():
    """Next to settings.json – outside what „Bent°Corner löschen“ deletes (settings.json, data/)."""
    from system import datastore
    return datastore.SETTINGS.with_name("forget-pending.json")


def remember_pending(settings):
    """The server part could not run (offline): only what forget needs later stays – the seed (to sign), the server
    and the address. Nothing else (no collection, friends, board keys, nothing set aside)."""
    import time as _t
    from net import relay
    st = relay.state(settings)
    if not st.get("seed"):
        return None
    data = {"at": _t.time(), "seed": st["seed"], "url": st.get("url") or "", "code": relay.my_code(settings)}
    p = pending_file()
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data), "utf-8")
    tmp.replace(p)
    return p


def pending():
    """-> the mark {at, seed, url, code} while a forget waits, else None."""
    try:
        return json.loads(pending_file().read_text("utf-8"))
    except (OSError, ValueError):
        return None


def finish_pending(guard_code=None):
    """At the start (and again with the protection code): forget for the remembered identity. Deleted (or already
    gone) -> the mark goes too. -> Result (FAILED offline: next start; MAIN_REQUIRED: the code is needed)."""
    d = pending()
    if not d:
        return None
    s = {"relay": {"seed": d["seed"], "url": d.get("url") or None}}
    r = forget(s, guard_code)
    if r.status in (DELETED, ALREADY):
        pending_file().unlink(missing_ok=True)
    log.info("Delete Bent°Corner (pending): server %s %s", r.status, r.detail)
    return r


def delete_server(settings, notify=True, full=None, guard_code=None):
    """What the checkbox does: B if the server has /v1/forget, otherwise A. full: the version the page showed
    (None: ask the server now) – the request never does more than the text promised. guard_code: the protection code
    if one is set (Oliver 07.11.)."""
    if full is None:
        full = available(settings)
    r = forget(settings, guard_code) if full else Result(UNAVAILABLE)
    if r.status == UNAVAILABLE:
        r = delete_shared(settings, notify=notify)
    log.info("Delete Bent°Corner: server %s %s", r.status, r.detail)
    return r


def main():
    """`BentCorner.exe --forget-server` (uninstaller): the server part only, exit code for the uninstaller page."""
    from system import datastore
    try:
        settings = json.loads(datastore.SETTINGS.read_text("utf-8"))
    except (OSError, ValueError):
        raise SystemExit(EXIT[NO_ID])
    import sys
    if "--check" in sys.argv:   # the uninstaller asks which checkbox text applies – deletes nothing (only GET /v1/health)
        raise SystemExit(EXIT[NO_ID] if not has_id(settings) else CHECK_FULL if available(settings) else CHECK_SHARED)
    r = delete_server(settings, notify=False)
    if r.status in (DELETED, ALREADY):
        datastore.SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({"status": r.status, "code": r.code}))
    raise SystemExit(r.exit_code)
