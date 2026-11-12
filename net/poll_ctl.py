"""Sync without buttons (lead/Oliver 07.11., docs/web/DEVICE-KEYS.md §7): one cheap question to the server per minute
while the app is used (net/poll.py), every 15 min when nobody is at the PC, nothing when it is closed – and only when
the answer says something changed does the vault fetch (sync_now) or the mailbox fetch (relay_poll) follow.

Events go at once: sync_event() (a log ended, a friend added, a ticket made or sent, just paired) and sync_flush() when
the app closes (at most 3 s). The old timers (vault every 3 min, mailbox every 3 min) stay as the way back: they run
until the first answer of /v1/poll, and again if the server doesn't know /v1/poll (404/405 – an older server).
"""
import logging
import random
import threading

from PySide6 import QtCore

log = logging.getLogger("booster")


class PollControl:
    """Mixin of MainWindow (app.py), next to SyncControl and RelayControl. self is the MainWindow."""

    POLL_BURST = 20   # s between questions for a while after an own friend action (was the mailbox's 20 s burst)

    def _poll_wanted(self):
        """Only in Full Orbit, only with the sync behind its switch (syncrun.available: test builds until Gordon's
        /v1/poll is live) and only if the online backup or the mailbox is on – otherwise not one question (lead 07.11.);
        then the old timers keep doing exactly what they did before."""
        from collection import syncrun
        from net import relay
        from system import orbit
        if not syncrun.available() or orbit.level(self.settings) != "full":
            return False
        return (self.sync_on() and self.sync_orbit_ok()) or relay.enabled(self.settings)

    def poll_mode(self):
        """True once /v1/poll answered: the minute question replaces the old 3-minute timers."""
        return bool(getattr(self, "_poll_on", False)) and not getattr(self, "_poll_unsupported", False)

    def poll_setup(self):
        """After sync_setup / relay_setup: (re)start the question, and in poll mode keep the old timers stopped."""
        if getattr(self, "_poll_unsupported", False):
            return
        if getattr(self, "_poll_t", None) is None:
            from net import poll
            self._poll_pace = poll.Pace()
            self._poll_on = False   # (guide run 07.11.: missing on the real window – every answer crashed)
            self._poll_t = QtCore.QTimer(self, singleShot=True, timeout=self._poll_tick)
            self._poll_busy = False
        if not self._poll_wanted():
            self._poll_t.stop()
            return
        if self.poll_mode():
            self._poll_quiet_old()
        if not self._poll_t.isActive() and not self._poll_busy:
            self._poll_t.start(3000)

    def _poll_quiet_old(self):
        for name in ("_sync_t", "_relay_t"):
            t = getattr(self, name, None)
            if t is not None:
                t.stop()

    def _poll_schedule(self, now=None):
        if getattr(self, "_poll_t", None) is None or not self._poll_wanted() or getattr(self, "_poll_unsupported", False):
            return
        import time
        if time.time() < getattr(self, "_poll_burst_until", 0.0) and not self._poll_pace.fails:
            wait = max(self.POLL_BURST, self._poll_pace.hold_until - time.monotonic())
        else:
            wait = self._poll_pace.next(not self.activity.idle(), random.uniform(-1.0, 1.0))
        self._poll_t.start(int(wait * 1000))

    def poll_now(self):
        """Ask at once (an event, the first input after a long pause) – unless a question is on its way already or the
        server asked for a pause (its slow hint, Retry-After): then at the next possible moment."""
        if getattr(self, "_poll_t", None) is None or self._poll_busy or not self._poll_wanted():
            return
        import time
        hold = self._poll_pace.hold_until - time.monotonic()
        self._poll_t.start(int(max(0.0, hold) * 1000))

    def _poll_tick(self):
        if not self._poll_wanted() or self._poll_busy:
            return
        self._poll_busy = True
        s = self.settings
        from net import poll
        self._sync_bg("poll", lambda: poll.ask(s))

    def _poll_done(self, res, err):
        """Called from _sync_done (step "poll")."""
        self._poll_busy = False
        from net.vault import VaultError
        if err is not None:
            status = getattr(err, "status", 0) if isinstance(err, VaultError) else 0
            if status in (404, 405):   # an older server: the old timers go on as before
                log.info("Sync: the server doesn't know /v1/poll – the old timers stay")
                self._poll_unsupported = True
                self._poll_on = False
                self._poll_t.stop()
                self.sync_setup()
                self.relay_setup()
                return
            if status == 410:   # this address moved / was removed: the vault path follows it (moved_away)
                self.sync_now()
            self._poll_pace.failed(getattr(err, "retry_after", 0))
            self._poll_schedule()
            return
        first = not getattr(self, "_poll_on", False)
        self._poll_on = True
        self._poll_pace.ok(res.get("slow") or 0)
        if first:
            log.info("Sync: minute question on (/v1/poll)")
            self._poll_quiet_old()
        self._poll_act(res)
        self._poll_schedule()

    def _poll_act(self, res):
        """What changed -> the real fetches."""
        from net import guard
        guard.learn(self.settings, res.get("guard"))   # the ID's salt (S5 = b)
        e = getattr(self, "sync_engine", None)
        if (e is not None and self.sync_on() and self.sync_orbit_ok() and not res.get("closed")
                and (int(res.get("vault_version") or 0) != int(e.meta.get("version") or 0) or res.get("deleted")
                     or bool(res.get("guard_request")) != bool(e.meta.get("guard_request"))
                     or bool((res.get("guard") or {}).get("set")) != bool(e.meta.get("guard")))):
            self.sync_now()
        from net import relay
        if int(res.get("box_n") or 0) > 0 and relay.enabled(self.settings):
            self.relay_poll()
        if hasattr(self, "_dev_poll"):   # B5: devices in/out, join requests
            self._dev_poll(res)

    def sync_event(self):
        """Something happened the other devices or friends should see now (lead 07.11.): a log ended, a friend
        added, a ticket made or sent, just paired – sync at once and ask the server."""
        if self.sync_on() and self.sync_orbit_ok():
            self.sync_now()
        self.poll_now()

    def sync_poll_burst(self):
        """After an own friend action (request, accept): ask every 20 s for 5 min, so the answer arrives quickly."""
        import time
        self._poll_burst_until = time.time() + 300
        self.poll_now()

    FLUSH_WAIT = 3.0   # s the app waits for its last push when it closes

    def sync_flush(self):
        """The app closes: own unsent changes go out (at most FLUSH_WAIT s, then the app closes anyway – the rest goes
        at the next start). Blocking, only from the quit path."""
        e = getattr(self, "sync_engine", None)
        if e is None or not (self.sync_on() and self.sync_orbit_ok()) or self.sync_status.get("busy") \
                or self.sync_status.get("rekey") == "busy" or not e.pending:
            return False
        done = threading.Event()

        def work():
            try:
                e.push()
            except Exception as ex:  # noqa: BLE001 – closing: never stop the quit
                log.info("Sync: last push on closing failed (%s)", ex.__class__.__name__)
            finally:
                done.set()
        threading.Thread(target=work, daemon=True).start()
        return done.wait(self.FLUSH_WAIT)
