"""Where EVERY /v1 request of this app goes – the one place that decides it (Oliver/Gordon/lead 13.11.2026: the DEV
version must never talk to the live box). relay.url and vault._base both ask here.

- From the source with the sync switched on and BC_SYNC_BASE set: exactly that box (a local box.py for the tests and
  box checks, or the test instance for the test copies) – as before.
- A Ship build (build.ps1 -Ship): the live box, contacts.SERVER – never an address stored in older settings.
- Every other build – the DEV version (a work build without the ship flag) and the source without BC_SYNC_BASE: the
  gated test instance <SERVER>/testapp/box. Without its access code (typed in by hand, memory only, vault.set_gate)
  vault.gated refuses before anything is sent – the online parts are then simply off ("access code missing").
/dl (updates, data packs, index, emergency switch) and the prices are not /v1 and stay live (read only).
"""
from system import contacts


def base(settings=None):
    from collection import syncrun
    from net import vault
    test = syncrun.test_base()
    if test:
        return test
    if syncrun.SYNC_TEST:   # a sync test build is never live – not even if someone builds it with -Ship (lead 13.11.)
        return contacts.SERVER.rstrip("/") + vault.GATE_PATH
    if syncrun.ship_build():
        return contacts.SERVER.rstrip("/")
    return contacts.SERVER.rstrip("/") + vault.GATE_PATH


def live(settings=None):
    """True only where /v1 goes to the live box (a Ship build without a test base)."""
    return base(settings) == contacts.SERVER.rstrip("/")


# ---------- the /v1 lock outside Full Orbit (lead/legal 14.11.2026, 0.9.9) ----------
# Outside Full Orbit no /v1 request leaves this app – except the user's own explicit catch-up deletions: signing this
# device out of an ID (dev/leave) and deleting everything online (forget). legal's conditions: only these two; each
# goes out once (no re-registering, no repeat in the same start), with ID + signature and no collection data; nothing
# asked afterwards. /dl, prices and exchange rates are not /v1 and stay. Every sender of /v1 asks here first:
# vault.gated (relay, vault, devkeys, guard, pairing, rekey, forget), poll.ask and anonstats.
CATCHUP = frozenset({"/v1/dev/leave", "/v1/forget"})


class Blocked(Exception):
    """A /v1 request outside Full Orbit that is not one of the two catch-ups – nothing was sent."""


BLOCKED_STATUS = 451   # how relay/vault errors carry it: not sent on purpose (never "offline", never a retry)
BLOCKED_TEXT = "This needs Full Orbit – nothing was sent."


def v1_path(url):
    """"/v1/…" of a request URL (behind the test instance's prefix too), or None for anything else (/dl, prices).
    It does not look at the host (lead 14.11.): fine because only our own senders of the box call check()/allowed() –
    a foreign API with /v1/ in its path (exchange rates) never goes through them."""
    from urllib.parse import urlsplit
    path = urlsplit(str(url)).path
    i = path.find("/v1/")
    return path[i:] if i >= 0 else None


def full(settings=None):
    """Full Orbit? From the settings given, else the app's bound settings (orbit.bind at start). Unbound: a Ship build
    stays locked (fail closed); the source and tools are open (tests, box checks)."""
    from system import orbit
    s = settings if settings is not None else orbit._bound
    if s is None:
        from collection import syncrun
        return not syncrun.ship_build()
    return orbit.level(s) == "full"


def allowed(url, settings=None):
    p = v1_path(url)
    return p is None or p in CATCHUP or full(settings)


def check(url, settings=None):
    """Raises Blocked BEFORE anything is sent if this /v1 request may not go out now."""
    if not allowed(url, settings):
        raise Blocked(v1_path(url))
