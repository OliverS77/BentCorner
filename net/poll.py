"""The one cheap question per minute (docs/web/DEVICE-KEYS.md §7, Gordon 07.11.): /v1/poll {code, t, sig} ->
{vault_version, box_n, now, guard, guard_request[, deleted, every, closed]} (box 7c3bbb7). Only when something changed
does the real work follow – the vault fetch (vault_version differs from the one this device last saw) or the mailbox
fetch (box_n > 0: parcels waiting).

    ask(settings)            -> {"vault_version", "box_n", "guard", "guard_request", "slow", "closed", "deleted"};
                                VaultError like net/vault.py
    Pace().next(active, rnd) -> seconds until the next question

One kept-open connection (requests.Session) for all questions: without it every question costs a TLS handshake
(~5 KB instead of ~1 KB). The test instance's gate cookie goes along exactly as in vault.gated (only there).
"""
import threading
import time

from net import relay, vault
from system.i18n import tr

EVERY = 60            # s: app open and used in the last 30 min
IDLE_EVERY = 15 * 60  # s: nobody at the PC for 30 min (activity.idle)
JITTER = 10           # s: ± per question, so the devices don't all meet at the full minute
MAX_BACKOFF = 15 * 60

_session = [None]
_lock = threading.Lock()


def _http():
    with _lock:
        if _session[0] is None:
            import requests
            from net import netpolite
            s = requests.Session()
            s.headers.update({"User-Agent": netpolite.UA, netpolite.CHECK_HEADER[0]: netpolite.CHECK_HEADER[1]})
            _session[0] = s
        return _session[0]


def ask(settings):
    """The question itself (blocking: network). 404/405 = the server doesn't know /v1/poll yet (VaultError 404)."""
    from net import boxbase
    boxbase.check(vault._base(settings) + "/v1/poll")   # never outside Full Orbit (lead/legal 14.11.)
    code, t = vault._me(settings)
    url = vault._base(settings) + "/v1/poll"
    payload = {"code": code, "t": t, "sig": relay._signed(settings, f"poll|{code}|{t}")}
    kw = {"json": payload, "timeout": 20, "allow_redirects": False}
    if vault._gated(url):
        if not vault._gate[0]:
            raise vault.VaultError(401, tr("The access code for the test server is missing."))
        kw["cookies"] = {vault.GATE_COOKIE: vault._gate[0]}
    try:
        r = _http().post(url, **kw)
    except Exception as e:  # noqa: BLE001   (only the class name: the message could carry the request)
        raise vault.VaultError(0, tr(f"Server unreachable ({e.__class__.__name__})")) from None
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code != 200:
        err = vault.VaultError(r.status_code, d.get("error") or tr(f"Error {r.status_code}"), d)
        err.retry_after = _seconds(r.headers.get("Retry-After"))
        raise err
    # every: the server's emergency switch „slow“ (VAULT_SLOW_S) – ask no more often than that; closed: writing to
    # the vault is closed (vault-zu) – no sync started from here; deleted: the vault was deleted on another device
    return {"vault_version": int(d.get("vault_version") or 0), "box_n": int(d.get("box_n") or 0),
            "guard": d.get("guard") or None, "guard_request": d.get("guard_request") or None,
            "slow": _seconds(d.get("every")), "closed": bool(d.get("closed")), "deleted": d.get("deleted"),
            # B5 (box 84c2b58): the device registry – a new reg_version or a join request fetches the list
            "reg_version": d.get("reg_version"), "devices": d.get("devices"),
            "dev_request": d.get("dev_request") if isinstance(d.get("dev_request"), list) else []}


def _seconds(v):
    try:
        return max(0, int(float(v or 0)))
    except (TypeError, ValueError):
        return 0


class Pace:
    """When to ask next: 60 s active, 15 min idle, ± JITTER. After errors twice as long each time (up to 15 min);
    a server's slow hint or Retry-After holds at least that long. Never „right away again“."""

    def __init__(self):
        self.fails = 0
        self.hold_until = 0.0   # monotonic: no question before (slow hint, Retry-After)

    def ok(self, slow=0, now=None):
        self.fails = 0
        now = time.monotonic() if now is None else now
        self.hold_until = now + slow if slow else 0.0

    def failed(self, retry_after=0, now=None):
        self.fails += 1
        now = time.monotonic() if now is None else now
        if retry_after:
            self.hold_until = max(self.hold_until, now + retry_after)

    def next(self, active, rnd=0.0, now=None):
        """rnd in [-1, 1] (random.uniform) -> seconds."""
        now = time.monotonic() if now is None else now
        base = EVERY if active else IDLE_EVERY
        if self.fails:
            base = max(base, min(MAX_BACKOFF, EVERY * 2 ** (self.fails - 1)))
        wait = max(base + JITTER * rnd, EVERY - JITTER)
        return max(wait, self.hold_until - now)
