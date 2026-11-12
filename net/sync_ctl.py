"""The sync for the main window (collection/syncrun.py does the work): pace, background thread, writing back on the
main thread, the status for the sync row. Only when syncrun.available() (test build) and switched on.

Pace (SERVER-REGELN §6, SYNC-PLAN §3): at start, 20 s after an own change (collected), otherwise every 3 min while the
window is visible, every 15 min after 30 min without input, never while the window is hidden (tray, minimized), and
"Sync now".
"""
import logging
import threading
import time

from PySide6 import QtCore

from system.i18n import tr

log = logging.getLogger("booster")


def DELETED_TEXT():   # legal 06.11. (Art. 17) – also shown after a restart while the sync stays off
    return tr("The online backup was deleted on another device. Syncing is therefore off here – your data on this "
              "device stays.")


OWN_CHANGE = ("remove_one", "rekey")
UNDO_KEYS = ("sync_backup", "sync_asked", "sync_paired", "profile", "sync_rescue_ok")   # U5: put back on [Cancel]   # S7: these take relay.own_change themselves (net/rekey.py)


def problem_text(e):
    """An error of a run -> the sync row's text (nothing is lost in any of these cases)."""
    from collection import syncops
    from net.vault import VaultError
    from collection import syncrun
    if isinstance(e, syncrun.VaultDeleted):
        return DELETED_TEXT()
    if isinstance(e, syncrun.VaultEmptied):
        return tr("The online backup is empty.")
    from net import relay
    if isinstance(e, relay.Busy):   # S7: the key change waits for no job longer than a minute – nothing changed
        return tr("Your devices are syncing right now – nothing was changed. Try again in a minute.")
    if isinstance(e, syncops.PackError) and e.newer:
        return tr("A newer Bent°Corner wrote here – please update")
    if isinstance(e, VaultError):
        if e.status == 0:
            return tr("Offline – syncs again later")
        if e.status == 429:
            return tr("Enough syncing for today – continues tomorrow")
        if e.status == 503:
            return tr("Sync paused on the server – continues later")
        if e.status == 409:
            return tr("Another device is writing – tries again shortly")
        from collection import syncrun
        from net import vault
        if e.status in (401, 403) and syncrun.test_base():   # the sync test server's gate (vault.set_gate)
            return (tr("The access code for the test server is missing.") if vault.gate_needed()
                    else tr("The test server didn't accept the access code."))
    return tr("Sync did not work – tries again later")


class SyncControl:
    """Mixin of MainWindow (app.py). self is the MainWindow."""

    SYNC_EVERY = 180
    SYNC_IDLE_EVERY = 15 * 60
    SYNC_AFTER_EDIT = 20

    def sync_setup(self):
        from collection import syncrun
        if not syncrun.available():
            return
        if getattr(self, "sync_engine", None) is None:
            from system import datahome
            self.sync_engine = syncrun.Engine(datahome.HOME, self.settings,
                                              docs=syncrun.Docs(self.settings, save_settings=self.save_settings))
            self.sync_status = {"ok": None, "text": "", "when": None, "busy": False}
            syncrun.ENGINE = self.sync_engine
            syncrun.ON_RECORD = lambda: self.bridge.sync_soon.emit()   # a save may come from any thread
            self._sync_t = QtCore.QTimer(self, interval=self.SYNC_EVERY * 1000, timeout=self._sync_tick)
            self._sync_edit_t = QtCore.QTimer(self, singleShot=True, interval=self.SYNC_AFTER_EDIT * 1000,
                                              timeout=self._sync_tick)
            self.bridge.sync_done.connect(self._sync_done)
            self.bridge.sync_soon.connect(self._sync_soon)
        self.sync_status["paused"] = "orbit" if self.sync_engine.on() and not self.sync_orbit_ok() else ""
        # the 5-month warning (legal 07.11.): at every start and orbit change, locally – also while paused
        removed = (self.settings.get("relay") or {}).get("removed")
        warn = None if removed else syncrun.expiry(self.sync_engine.meta, int(time.time() * 1000))
        if warn:
            self.sync_status["expiry"] = warn
        else:
            self.sync_status.pop("expiry", None)
        self._gate_state()
        if self.sync_engine.on() and self.sync_orbit_ok():
            self._sync_t.start()
            QtCore.QTimer.singleShot(5000, self.sync_now)
        else:
            self._sync_t.stop()
            self._sync_edit_t.stop()
        getattr(self, "poll_setup", lambda: None)()   # in poll mode the minute question takes over from _sync_t

    def sync_on(self):
        return getattr(self, "sync_engine", None) is not None and self.sync_engine.on()

    def sync_orbit_ok(self):
        """Pairing and syncing only in Full Orbit (Oliver/lead 07.11.: Core/Near promise less network). Outside it the
        sync pauses – the pairing stays, nothing is sent or deleted – and goes on when Full Orbit is back."""
        from system import orbit
        return orbit.level(self.settings) == "full"

    def sync_switch_plan(self):
        """What „Mit meinen Geräten abgleichen“ OFF means here (lead/legal 07.11., the web alike):
        "leave"  other devices: only this one leaves the sync – vault, backup and friends stay
        "delete" the only device and no protection code: off AND the vault deleted (nobody else could use it)
        "ask"    the only device with a protection code, or unclear (never synced, the list unknown): the page asks
                 „keep or delete the online backup?“ (sync_leave(delete=…))"""
        e = getattr(self, "sync_engine", None)
        if self.sync_has_others():
            return "leave"
        if e is None or not e.meta.get("seeded") or not e.devices():
            return "ask"
        return "ask" if e.meta.get("guard") else "delete"

    # ---------- one switch „Online-Sicherung und Abgleich“ + „Dieses Gerät abmelden“ (lead/Oliver 07.11.) ----------
    # A paired device always syncs (pairing switches on – pair_show, join, rescue). The only switch is the online
    # backup with the sync (sync_backup_set: on, or off = delete it for all); one device leaves by signing itself out
    # (sync_leave).

    def sync_leave_plan(self):
        """„Dieses Gerät abmelden“: "leave" with other devices (only this one goes, they keep syncing); as the only
        device it is the same question as switching the backup off ("ask" | "delete")."""
        return "leave" if self.sync_has_others() else self.sync_switch_plan()

    def sync_leave(self, delete=None, guard=None):
        """This device signs itself out: it stops syncing, its data stays here; the others go on. As the last device
        see sync_leave_plan. sync_status["left"] = True afterwards (the page shows its line)."""
        if getattr(self, "sync_engine", None) is None:
            return
        plan = self.sync_leave_plan()
        if plan != "leave":
            if delete is None:
                self.sync_status["switch_off"] = plan
                self._sync_changed()
                return
            if delete:
                self.vault_delete(guard)
                return
        self.sync_status.pop("switch_off", None)
        e = self.sync_engine
        if self.sync_status.get("busy"):   # a sync run is on: leave after it, never side by side (review 08.11.)
            self.sync_status["text"] = tr("Your devices are syncing right now – nothing was changed. Try again in a minute.")
            self._sync_changed()
            return
        self._wipe_copy = None
        if plan == "leave":   # D (Oliver/lead 12.11.): others remain – this device empties itself, a 30-day copy FIRST
            from system import datastore
            self._wipe_copy = datastore.remove_copy()
            if self._wipe_copy is None:   # no copy: nothing is changed, nothing deleted
                self.sync_status.update(wipe="failed", text=tr(WIPE_FAILED))
                self._sync_changed()
                return
        if plan == "leave" and e.on() and e.meta.get("seeded"):
            # out of the device list in the vault first (the others stop listing it), then off – offline: off anyway,
            # the entry then only ages (seen); B5 takes it out of the server's registry
            self.sync_status.update(busy=True)
            self._sync_changed()

            def work():
                e.drop_self()
                e.push()
                from net import devkeys
                return {"registry": devkeys.leave(s)}   # B5: out of the server's registry too (own key only)
            s = self.settings
            self._sync_bg("leave", work)
            return
        self._leave_done(None, None)

    def _leave_done(self, res, err):
        if err is not None:
            log.info("Sync: leaving – the device list could not be told (%s)", err.__class__.__name__)
        if (res or {}).get("registry") or err is not None:
            # offline too (review 08.11.): signing out deletes seed AND device key here (legal 07.11. a) – the entry on
            # the server stays until another device removes it (✕), it can't act without these keys
            # legal 07.11. (condition a): signing out deletes this device's seed AND device key – the collection
            # stays, the device gets a new identity of its own. NOT marked identity_gone: that is the hint for a
            # restored backup of a removed identity – here it showed „Diese Sicherung stammt von einer entfernten
            # Kennung …“ after signing out (guide run 08.11.)
            import base64
            import nacl.utils
            from net import devkeys
            rel = self.settings.setdefault("relay", {})
            rel["seed"] = base64.b64encode(nacl.utils.random(32)).decode()
            for k in ("registered", "test_registered", "identity_gone", "removed", "removed_by"):
                rel.pop(k, None)
            devkeys.forget()
        self.sync_engine.switch_off()
        self.settings["sync_backup"] = False
        self.settings_changed()
        # an earlier join is over too (guide run 09.11.: join "ok" from adding this device stayed – „Enter a code“ then
        # closed its field at once and the device couldn't be added again)
        for k in ("join", "join_n", "guard", "guard_wait", "join_request", "join_had_own", "join_from"):
            self.sync_status.pop(k, None)
        self.sync_status.update(ok=None, text="", left=True, busy=False)
        self.sync_setup()
        self._sync_changed()
        if getattr(self, "_wipe_copy", None) is not None:   # D: the copy is there – now this device empties itself
            self._empty_device(self._wipe_copy)

    def _empty_device(self, copy=None, mark=None):
        """D (Oliver/lead 12.11.): this device left a group that goes on (signed out, or removed by another device):
        its data goes – only after the 30-day copy (datastore.remove_copy) was written; without it nothing is deleted
        (sync_status["wipe"] = "failed", the page says so). Then the program restarts without saving (the state in
        memory must not write anything back). mark: kept in the settings for the page after the restart."""
        from net import devkeys
        from system import datastore
        self._wipe_copy = None
        dest = copy or datastore.remove_copy()
        if dest is None:
            self.sync_status.update(wipe="failed", text=tr(WIPE_FAILED))
            self._sync_changed()
            return False
        try:
            if getattr(self, "sync_engine", None) is not None:
                self.sync_engine.switch_off()
            datastore.wipe_personal(self.settings)
            devkeys.drop_device_state(datastore.SETTINGS.parent)   # the sync's own state held the data too
        except OSError as e:
            log.warning("Sync: emptying this device – %s", e)
        self.settings["sync_wiped"] = {"at": time.time(), "copy": dest.name, **(mark or {})}
        self.settings.update(sync_backup=False)
        getattr(self, "save_settings", lambda: None)()
        restart = getattr(self, "restart_after_restore", None)
        if restart is not None:
            restart()
        return True

    def _sync_visible(self):
        w = getattr(getattr(self, "shell", None), "window", None)
        if w is None or not w.isVisible():
            return False
        from PySide6 import QtGui
        return w.visibility() not in (QtGui.QWindow.Hidden, QtGui.QWindow.Minimized)   # QQuickWindow: no isMinimized

    def _sync_soon(self):
        if self.sync_on():
            self._sync_edit_t.start()   # restarts: changes in a row go together

    def _sync_tick(self):
        slow = self.activity.idle()
        want = (self.SYNC_IDLE_EVERY if slow else self.SYNC_EVERY) * 1000
        if self._sync_t.interval() != want:
            self._sync_t.setInterval(want)
        if self._sync_visible():
            self.sync_now()

    def sync_now(self, manual=False):
        if (not self.sync_on() or self.sync_status["busy"] or not self.sync_orbit_ok()
                or self.sync_status.get("rekey") == "busy"   # never while the address changes (T2 07.11.)
                or (getattr(self, "pair", None) or {}).get("busy")):   # nor while a code's own sync runs (review 08.11.)
            return
        if self.sync_status.get("join_wait") or self.sync_status.get("foreign_device"):
            from net import devkeys   # this device's join request waits (or was declined): no sync until it's in
            if not devkeys.registered(self.settings):   # (ports 08.11.: the server would refuse every write)
                return
        self.sync_status["busy"] = True
        self._sync_changed()
        gen = getattr(self, "_rekey_n", 0)
        engine = self.sync_engine

        def fetch():
            try:
                return engine.fetch()
            except Exception as e:  # noqa: BLE001 – started before this device's own key change? (see _sync_done)
                e.sync_rekey_n = gen
                raise
        self._sync_bg("fetch", fetch)

    def _sync_bg(self, step, fn):
        from net import relay

        def work():
            try:
                if step in OWN_CHANGE:
                    res, err = fn(), None
                else:
                    with relay.job():
                        res, err = fn(), None
            except Exception as e:  # noqa: BLE001
                res, err = None, e
                from net.vault import VaultError
                if not isinstance(e, VaultError):
                    log.exception("Sync: %s", step)
            try:
                self.bridge.sync_done.emit(step, res, err)
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _gate_state(self):
        """Test builds only (live there is no gate): sync_status["gate"] = "missing" while the test server's access code
        isn't typed in – the page then shows the error line with the field, never „Coupled ✓“ (T2 07.11.: Test-PC 2
        after a restart). sync_status["reached"]: this device ever got an answer from the vault (meta vault_seen)."""
        from net import vault
        e = getattr(self, "sync_engine", None)
        self.sync_status["reached"] = bool(e is not None and (getattr(e, "meta", None) or {}).get("vault_seen"))
        if vault.gate_needed():
            self.sync_status["gate"] = "missing"
        else:
            self.sync_status.pop("gate", None)

    def _sync_done(self, step, res, err):
        st = self.sync_status
        self._gate_state()
        if step in ("dev_add", "dev_list", "dev_decide", "remove_one", "add_code"):   # B5 (net/devices_ctl.py)
            return self._dev_done(step, res, err)
        if step == "leave":   # „Dieses Gerät abmelden“: out of the device list, then off
            return self._leave_done(res, err)
        if step == "poll":   # the minute question (net/poll_ctl.py)
            return self._poll_done(res, err)
        if step.startswith("pair_"):
            return self._pair_done(step, res, err)
        if step == "gate":   # the test server's access code exchanged for its token (vault.set_gate)
            st.update(busy=False, ok=None if err is None else False, text="" if err is None else str(err))
            self._sync_changed()
            if err is None and self.sync_on():
                self.sync_now(manual=True)
            return
        if step == "vault_delete":
            from net.vault import VaultError
            if isinstance(err, VaultError) and (err.data or {}).get("main_required"):   # the code is needed / wrong
                st.update(busy=False, deleted=False, text="",
                          delete_guard=("need" if not getattr(self, "_delete_typed", False)
                                        else "wait" if err.status == 429 else "wrong"),
                          guard_wait=int((err.data or {}).get("retry_after") or 0))
                self._delete_typed = False
                self._sync_changed()
                return
            self._delete_typed = False
            st.update(busy=False, ok=None if err is None else False,
                      text=tr("Online backup deleted") if err is None else problem_text(err), deleted=err is None)
            if err is None:   # deleted on the server: now off here too
                self.sync_engine.switch_off()
                self.sync_setup()
                self.settings.update(sync_backup=False, sync_rescue_ok=False)
                self.settings_changed()
            self._sync_changed()
            return
        if step in ("rescue_put", "rescue_restore"):
            return self._rescue_done(step, res, err)
        if step == "rekey":
            return self._rekey_done(res, err)
        if step == "join_take":
            return self._join_take_done(res, err)
        if step == "join_guard":
            return self._join_guard_done(res, err)
        if step == "join_info":
            return self._join_info_done(res, err)
        if step in ("cam_preview", "cam_found", "cam_end"):
            return self._cam_done(step, res)
        if step == "forget_pending":
            return self._forget_pending_done(res, err)
        if step == "join_leave":
            return self._join_leave_done(res, err)
        if step == "guard":
            return self._guard_done(err)
        if step == "guard_request":
            return self._guard_request_done(res, err)
        if step == "forget":
            st["forget"] = getattr(res, "status", "failed") if err is None else "failed"
            self._sync_changed()
            return
        from collection import syncrun
        from net.vault import VaultError
        if err is not None and step == "fetch" and (st.get("rekey") == "busy"
                                                    or getattr(err, "sync_rekey_n", 0) != getattr(self, "_rekey_n", 0)):
            # an answer about the OLD address (deleted / 410 gone): this device itself just moved to a new one („Remove
            # device“, T2 07.11.: PC 1 switched itself off) – nothing happened to it; the next run asks the new address
            log.info("Sync: fetch – answer for the old address after a key change, ignored")
            st.update(busy=False)
            self._sync_changed()
            return
        st["emptied"] = isinstance(err, syncrun.VaultEmptied)   # the settings page asks (SYNC-PLAN §6)
        if isinstance(err, syncrun.VaultDeleted):   # deleted on another device on purpose: off, never "back it up?"
            self.sync_engine.deleted_elsewhere()
            self.sync_setup()
            # the backup is gone too – Settings → Backup shows it off (Teil-A run 07.11.: it still said „on“ and offered
            # „request a new protection code“); turning it on again is the user's own step
            self.settings.update(sync_backup=False, sync_rescue_ok=False)
            self.settings_changed()
        data410 = (err.data or {}) if isinstance(err, VaultError) and err.status == 410 else {}
        if data410.get("per_device") and not data410.get("gone") and not data410.get("fwd"):
            # B5: this device's own envelope couldn't be fetched (offline, 429, 5xx – review 08.11., M5): nothing is
            # decided yet – not „removed“, the sync stays on and asks again with the next run
            st.update(busy=False, ok=False, text=problem_text(VaultError(0, "dev/fwd")))
            log.info("Sync: %s – own envelope not fetched yet, tries again", step)
            self._sync_changed()
            QtCore.QTimer.singleShot(60_000, self.sync_now)
            return
        if isinstance(err, VaultError) and err.status == 410 and not (err.data or {}).get("fwd"):
            # this device was removed („Gerät entfernen“ elsewhere) or its identity deleted: relay.moved_away gave it
            # a new identity of its own – the sync stops; the collection stays here (PAIRING §3: pair again)
            self.sync_engine.switch_off()
            self.sync_setup()
            rel = self.settings.setdefault("relay", {})
            # a final state, not an error: kept in the settings (the page shows it after a restart too); it is a
            # LIVE removal – not „a backup of a removed identity“ (identity_gone keeps the new one quiet only)
            rel["removed"] = {"by": str(rel.get("removed_by") or ""), "at": time.time()}
            st["removed"] = {"by": rel["removed"]["by"]}
            st.update(busy=False, ok=None, text="")
            self.settings_changed()
            self._sync_changed()
            if rel.pop("removed_here", None):   # D: removed from a group that goes on – empty (copy first)
                self._empty_device(mark={"removed": True})
            return
        if isinstance(err, VaultError) and err.status == 410 and (err.data or {}).get("fwd"):
            # followed the identity to its new address („Neuer Code“, or B5: another device removed one – this one
            # got its own envelope): the new vault starts from its first version – no „emptied?“ question
            with self.sync_engine.lock:
                self.sync_engine.meta.update(version=0)
                self.sync_engine._save()
            st.update(busy=False, ok=None, text="")
            self._sync_changed()
            QtCore.QTimer.singleShot(1500, self.sync_now)
            return
        if err is not None and (getattr(err, "data", None) or {}).get("dev_required"):
            # the ID has a device list and this device isn't in it (a restored backup, an old install): ask to join
            # first – the sync waits for the answer (join_wait), no error line (ports 08.11.)
            from net import devkeys
            if not devkeys.registered(self.settings):
                log.info("Sync: %s – this device isn't registered yet: asking to join first", step)
                st.update(busy=False, ok=None, text="")
                self._sync_changed()
                self._dev_ensure(force=True)
                return
        if err is not None:
            st.update(busy=False, ok=False, text=problem_text(err))
            log.info("Sync: %s – %s", step, err)
            self._sync_changed()
            return
        if step == "fetch":
            meta = self.sync_engine.meta
            if meta.get("join_hold"):   # both devices have data: the three buttons first (nothing written or sent)
                st.update(busy=False, ok=None, text="", join="choice")
                self._sync_changed()
                return
            try:
                self._sync_flush()
                written = self.sync_engine.write_back()   # main thread: no edit can come in between
            except Exception as e:  # noqa: BLE001
                log.exception("Sync: writing back")
                st.update(busy=False, ok=False, text=problem_text(e))
                self._sync_changed()
                return
            if (meta.get("aside_last") and meta.get("aside_last") != meta.get("aside_seen")
                    and meta.get("aside_last_why") in ("takeover", "offline")):
                st["aside"] = meta["aside_last"]   # set aside without asking (takeover / offline) – the page says so
            self._sync_refresh(written)
            self._sync_bg("push", self.sync_engine.push)
            return
        meta = self.sync_engine.meta if getattr(self, "sync_engine", None) is not None else {}
        if meta.pop("join_again", None):   # another device chose „keep mine“ first: show the choice again
            st["join"] = "again"
        elif st.get("join") == "busy":
            st["join"] = "ok"
        st.update(busy=False, ok=True, text="", when=time.time())
        self._sync_changed()
        getattr(self, "_dev_ensure", lambda: None)()   # B5: this device in the server's device registry

    # ---------- „Gerät entfernen“ / „Neuer Code“ (net/rekey.py, PAIRING.md §3) ----------
    def sync_rekey(self, mode, guard=None):
        """mode "remove" (no other device follows – a lost or foreign one keeps nothing) or "new" (own devices
        follow). In the background; sync_status["rekey"] busy -> ok | error (+ text)."""
        from collection import syncrun
        from net import rekey
        if not syncrun.available() or mode not in rekey.MODES or self.sync_status.get("rekey") == "busy":
            return
        self.sync_status.update(rekey="busy", text="")
        self._rekey_n = getattr(self, "_rekey_n", 0) + 1   # a fetch still running answers for the old address
        self._sync_changed()
        s = self.settings
        def work():
            res = rekey.change(s, mode, guard)
            # the server carries the code to the new address (Gordon 07.11.) – the envelope holds the old seed, so it
            # goes up anew (sig_main with the same code); M11: a failure after the change is no error of the change
            return dict(res or {}, mode=mode, **rekey.after_change(s, guard))   # only yes/no – the code stays here
        self._sync_bg("rekey", work)

    def _rekey_done(self, res, err):
        st = self.sync_status
        from net.relay import RelayError
        if isinstance(err, RelayError) and (err.data or {}).get("main_required"):
            st.update(rekey="", guard="wait" if err.status == 429 else "wrong",
                      guard_wait=int((err.data or {}).get("retry_after") or 0))
            self._sync_changed()
            return
        if err is not None:
            st.update(rekey="error", text=problem_text(err))
            log.info("Sync: rekey – %s", err)
            self._sync_changed()
            return
        # the old vault and rescue envelope went with the old address: this device fills the new vault (a snap); with a
        # protection code the new envelope is already up (work() above) – without, a new code is offered again
        self.settings["sync_rescue_ok"] = bool((res or {}).get("rescued"))
        if "rescue" in ((res or {}).get("after_failed") or ()):   # M11: the code is up, its envelope not – ask again
            self.settings["sync_rescue_missing"] = True
            if getattr(self, "sync_engine", None) is not None:
                self.sync_engine.meta["guard"] = True
        self.settings_changed()
        e = getattr(self, "sync_engine", None)
        if e is not None and e.on():
            with e.lock:
                e.meta.update(version=0)
                e._save()
            if (res or {}).get("mode") == "remove":
                e.drop_other_devices()   # the others must pair again – they leave the list
            e.restore_vault()
        # the code shown earlier went to the old address: no „Coupled ✓“ from it any more (T2 07.11.)
        if getattr(self, "_pair_t", None) is not None:
            self._pair_t.stop()
        self.pair = {"busy": False, "code": "", "until": 0, "fetched": False, "shown": False, "error": ""}
        try:
            self.relay_rekey()
        except Exception:  # noqa: BLE001 – shared again at the next change
            log.exception("Sync: sharing anew after rekey")
        st.update(rekey="ok", text="")
        self._sync_changed()
        self.sync_now(manual=True)

    def friend_move_answer(self, old, accept):
        """legal 07.11.: a friend's move is shown, the user answers. Accept: the entry moves to the new address and
        my shared lists go there; decline: nothing moves."""
        from net import relay
        now = relay.move_answer(self.settings, old, bool(accept))
        self.settings_changed()
        if accept and now != relay.norm(old):
            try:
                self.relay_rekey()
            except Exception:  # noqa: BLE001
                log.exception("Sharing with a moved friend")
        return now

    # ---------- this PC joins (the code from the phone; PAIRING §2) ----------
    def sync_join_code(self, code):
        """The code shown on the other device, typed in here. In the background; sync_status["join"]:
        busy -> ok | wrong (never why – legal) | choice (both have data: the three buttons) | error."""
        from collection import syncrun
        from net import pairing, vault
        if not syncrun.available():
            return
        if not self.sync_orbit_ok():   # joining only in Full Orbit – nothing sent (sync_status["join"] = "orbit")
            self.sync_status.update(join="orbit")
            self._sync_changed()
            return
        try:
            pairing.norm_code(code)
        except pairing.PairError:
            self.sync_status.update(join="wrong")
            self._sync_changed()
            return
        # bug 4 (Oliver 12.11.): after a removal the new identity sends nothing „until you decide“ – typing a code IS
        # that decision (before: „Code eingeben“ ran into that wall and nothing happened)
        rel = self.settings.setdefault("relay", {})
        for k in ("identity_gone", "removed", "removed_by"):
            rel.pop(k, None)
        self.sync_status.pop("removed", None)
        self.settings.pop("sync_wiped", None)
        self.sync_status.update(join="busy", text="")
        self._sync_changed()
        s = self.settings
        self._sync_bg("join_take", lambda: vault.pair_take(s, code))

    def _join_take_done(self, res, err):
        """The identity arrived (the server deleted it on fetching). A2 (Oliver 08.11.): before this PC becomes that ID
        it registers with the protection code – sync_status["join"] = "need_guard", the page asks for it,
        sync_join_guard(code). The payload stays in memory only until then (closing the app = a new pairing code)."""
        from net import pairing
        from net.vault import VaultError
        st = self.sync_status
        if err is not None:
            wrong = isinstance(err, pairing.PairError) or (isinstance(err, VaultError) and err.status == 404)
            st.update(join="wrong" if wrong else "error", text="" if wrong else problem_text(err))
            self._sync_changed()
            return
        self._join_payload = res
        st.update(join="need_guard", text="")
        # C (lead 12.11.): had this device its own protection code, its pairing step says whose applies from now on
        from ui import qsync
        ex = ((res or {}).get("extra") or {}) if isinstance(res, dict) else {}
        st["join_had_own"] = bool(self.guard_on() or self.settings.get("sync_rescue_ok"))
        from system import nicknames
        st["join_from"] = str(ex.get("dev_name") or "") or (nicknames.render(ex.get("dev_nick"), nicknames.lang())
                                                            or "")
        for k in ("guard", "guard_wait", "join_request"):
            st.pop(k, None)
        self._sync_changed()
        # the ID's state from the server (signed with the arrived seed, nothing written): its salt if the payload had
        # none (an older showing device), and whether „code lost“ runs there (library: legal's extra line)
        tmp = {"relay": {"seed": res["seed"], "url": (self.settings.get("relay") or {}).get("url")}}

        def info():
            from net import poll
            return poll.ask(tmp)
        self._sync_bg("join_info", info)

    def _join_info_done(self, res, err):
        payload = getattr(self, "_join_payload", None)
        if err is not None or payload is None or not isinstance(res, dict):
            return   # offline: the code still works with the payload's salt
        extra = payload.setdefault("extra", {})
        salt = (res.get("guard") or {}).get("salt")
        if salt and not extra.get("guard_salt"):
            extra["guard_salt"] = salt
        self.sync_status["join_request"] = bool(res.get("guard_request"))
        self._sync_changed()

    def sync_join_drop(self):
        """[Cancel] on the joining device: the arrived identity goes from memory – nothing of it was used; a new try
        needs a new code from the other device (the server deleted this one when it was fetched)."""
        self._join_payload = None
        for k in ("join", "guard", "guard_wait", "join_request"):
            self.sync_status.pop(k, None)
        self._sync_changed()

    def sync_join_guard(self, code):
        """The protection code typed on the joining device: register with it (dev/add + the invitation + sig_main) as
        the ID that arrived – only if the server takes it does this PC become that ID. -> sync_status["join"] busy, then
        _join_apply; a wrong code: guard "wrong" (join stays "need_guard"), too many: guard "wait" (+ guard_wait)."""
        from collection import syncrun
        res = getattr(self, "_join_payload", None)
        if res is None or not code or not syncrun.available() or self.sync_status.get("join") == "busy":
            return
        st = self.sync_status
        st.update(join="busy", text="")
        for k in ("guard", "guard_wait"):
            st.pop(k, None)
        self._sync_changed()
        try:   # where this device's key is registered now – a cancel at the table points it back there (U5)
            from net import devkeys
            self._join_dk = (devkeys._load(False) or {}).get("code") or ""
        except Exception:  # noqa: BLE001
            self._join_dk = ""
        extra = res.get("extra") or {}
        tmp = {"relay": {"seed": res["seed"], "url": (self.settings.get("relay") or {}).get("url")}}
        if extra.get("guard_salt"):
            tmp["relay"]["guard_salt"] = str(extra["guard_salt"])
        invite = extra.get("invite") or None

        def work():
            from net import devkeys
            return {"reg": devkeys.register(tmp, invite, code), "salt": tmp["relay"].get("guard_salt")}
        self._sync_bg("join_guard", work)

    def _join_guard_done(self, res, err):
        from net.relay import RelayError
        from net.vault import VaultError
        st = self.sync_status
        data = getattr(err, "data", None) or {}
        if isinstance(err, (VaultError, RelayError)) and (data.get("main_required") or data.get("guard_wrong")):
            st.update(join="need_guard", guard="wait" if err.status == 429 else "wrong",
                      guard_wait=int(data.get("retry_after") or 0))
            self._sync_changed()
            return
        if err is not None or not isinstance(res, dict) or res.get("reg") != "ok":
            # a join request (an old server without the A2 rule) or an error: this PC stays what it was
            st.update(join="error", text=problem_text(err) if err is not None else "")
            self._sync_changed()
            return
        payload, self._join_payload = self._join_payload, None
        self._join_apply(payload, res.get("salt"))

    def _join_apply(self, res, salt=None):
        """Registered with the code: this PC is now the same identity (its friends come along), then the first sync –
        with data on both sides the three buttons (Engine._join_question)."""
        st = self.sync_status
        import copy
        e = getattr(self, "sync_engine", None)
        # U5 (lead/ports 11.11.): until the user answers at the comparison table, everything this device was stays here
        # in memory – [Cancel] puts it back and signs the device out of the joined ID (dev/leave)
        self._join_undo = {"relay": copy.deepcopy(self.settings.get("relay")),
                           "keys": {k: copy.deepcopy(self.settings[k]) for k in UNDO_KEYS if k in self.settings},
                           "meta": copy.deepcopy(e.meta) if e is not None else None,
                           "dk": getattr(self, "_join_dk", ""), "seed": res["seed"]}
        rel = self.settings.setdefault("relay", {})
        rel["seed"] = res["seed"]
        for k in ("registered", "test_registered", "identity_gone", "removed_by"):
            rel.pop(k, None)
        if salt:
            rel["guard_salt"] = salt
        friends = rel.setdefault("friends", {})
        for c, f in ((res.get("extra") or {}).get("friends") or {}).items():
            friends.setdefault(c, f)
        try:   # this device's number: its name field shows „Device N“ (0: the other side is older – field empty)
            st["join_n"] = max(2, int((res.get("extra") or {}).get("next_n") or 0))   # never the shower's 1 (ports 12.11.)
        except (TypeError, ValueError):
            st["join_n"] = 0
        name = (res.get("extra") or {}).get("name")
        if name and not (self.settings.get("profile") or {}).get("name"):
            self.settings.setdefault("profile", {})["name"] = name
        self.settings["sync_paired"] = True
        st.pop("left", None)   # signed out earlier, now back: no „leaves the sync“ line any more (guide run 08.11.)
        # joined = this PC is in the online backup too (Teil-A run 07.11.: else Settings → Backup showed it off, with
        # the „turn on backup“ card, and without „code lost?“ / deleting)
        self.settings.update(sync_backup=True, sync_asked=self.settings.get("sync_asked") or time.time())
        self.settings_changed()
        self.sync_setup()
        e = getattr(self, "sync_engine", None)
        if e is not None:
            e.switch_on()
            with e.lock:
                other = str((res.get("extra") or {}).get("device") or "phone")   # old web: no field = the phone
                e.meta["join_other"] = other if other in ("pc", "phone") else "phone"
                e.meta["join_other_dev"] = str((res.get("extra") or {}).get("dev") or "") or None
                e.meta["join_n"] = int(st.get("join_n") or 0)   # its number from the pairing (next_n)
                e.meta.pop("my_n", None)
                e.meta.pop("my_added", None)
                e._save()
            self.sync_setup()
        # B5 + A2: already registered (sync_join_guard) – with the invitation and the protection code
        self._join_invite = None
        st.update(join="busy")
        self._sync_changed()
        self.sync_now(manual=True)

    # ---------- the sphere read with the webcam (net/sync_cam.py; library's page) ----------
    def sync_my_nick(self):
        """This device's nickname (Oliver/lead 12.11.): the one in its list entry, else drawn now – against the joined
        account's list – and kept (meta my_nick) for its first entry. None without the sync."""
        from system import nicknames
        e = getattr(self, "sync_engine", None)
        if e is None:
            return None
        me = e.meta.get("dev")
        have = e.state.value("*/devices", me) if me else None
        if isinstance(have, dict) and nicknames.valid(have.get("nick")):
            return list(have["nick"])
        if not nicknames.valid(e.meta.get("my_nick")):
            view = e.state.view("*/devices")
            view = view if isinstance(view, dict) else {}
            taken = [x.get("nick") for k, x in view.items() if k != me and x.get("nick")] + \
                [x.get("name") for k, x in view.items() if k != me and x.get("name")]
            e.meta["my_nick"] = nicknames.pick(taken)
        return list(e.meta["my_nick"])

    def sync_join_name(self, name):
        """The name typed on the joining device (lead/Oliver 07.11.: given when adding, prefilled „Device N“).
        Unchanged prefill or empty -> the default (name null: shows „Device N“ with the number the list settles on);
        else it goes into */devices – at the first entry, or as a rename if the entry is there already."""
        name = " ".join(str(name or "").split())[:60]
        n = int(self.sync_status.get("join_n") or 0)
        from system import nicknames
        nick = self.sync_my_nick()
        prefill = {nicknames.render(nick, "en"), nicknames.render(nick, "de")} if nick else set()
        if name and (name in prefill or (n and name == tr(f"Device {n}"))):   # the unchanged prefill: the nickname
            name = ""
        e = getattr(self, "sync_engine", None)
        me = e.meta.get("dev") if e is not None else None
        if e is not None and me and e.state.value("*/devices", me) is not None:
            if e.rename_device(me, name):
                self.settings_changed()
                self.sync_now(manual=True)
            return
        if name:
            self.settings["device_name"] = name
        else:
            self.settings.pop("device_name", None)
        self.settings_changed()

    def sync_join_cameras(self):
        """-> [(index, name)] – the same cameras as for scanning."""
        from scanner import camera
        return list(enumerate(camera.camera_names()))

    def sync_join_camera(self, on, device=None):
        """Read the phone's sphere with the webcam (on) or stop (off – library calls it when the page is left).
        sync_status["join_cam"] = looking | found | no_camera | stopped; the preview is image://cards/sync_cam,
        sync_status["join_cam_frame"] counts its frames (memory only). A code read goes on like sync_join_code."""
        from collection import syncrun
        cam = getattr(self, "_sphere_cam", None)
        if cam is not None:
            self._sphere_cam = None
            cam.stop()
        if on and syncrun.available() and not self.sync_orbit_ok():   # no camera outside Full Orbit
            self.sync_status.update(join="orbit")
            on = False
        if not on or not syncrun.available():
            from ui import quickimages
            quickimages.drop("sync_cam")
            if self.sync_status.get("join_cam") == "looking":
                self.sync_status["join_cam"] = ""
            self._sync_changed()
            return
        from net import sync_cam
        idx = device if device is not None else self._scan_camera_index()
        emit = self.bridge.sync_done.emit   # the camera thread hands everything to the main thread
        self._sphere_cam = sync_cam.SphereCam(idx, lambda g: emit("cam_preview", g, None),
                                              lambda code: emit("cam_found", code, None),
                                              lambda why: emit("cam_end", why, None))
        self.sync_status.update(join_cam="looking", join_cam_frame=0)
        self._sync_changed()
        self._sphere_cam.start()

    def _scan_camera_index(self):
        """The camera chosen for scanning: the settings keep its NAME (scan_ctl.fill_cameras) – its index in the
        list, else the first one."""
        from scanner import camera
        want = self.settings.get("camera")
        try:
            names = list(camera.camera_names())
        except Exception:  # noqa: BLE001
            names = []
        return names.index(want) if want in names else 0

    def _cam_done(self, step, res):
        st = self.sync_status
        if step == "cam_preview":
            from PySide6 import QtGui
            from ui import quickimages
            h, w = res.shape
            img = QtGui.QImage(res.data, w, h, w, QtGui.QImage.Format_Grayscale8).copy()   # a copy in memory only
            quickimages.keep("sync_cam", img)
            st["join_cam_frame"] = int(st.get("join_cam_frame") or 0) + 1
        elif step == "cam_found":
            st["join_cam"] = "found"
            self.sync_join_code(res)
        elif step == "cam_end":
            self._sphere_cam = None
            if res in ("stopped", "no_camera"):
                st["join_cam"] = res
            from ui import quickimages
            quickimages.drop("sync_cam")
        self._sync_changed()

    # ---------- U5: cancelled at the comparison table (lead/ports 11.11.; the web's syncpair.js leaveJoined) ----------
    def _join_cancel(self, undo):
        """This device is as before (its old ID, its data, its sync state); the joined ID's registry loses it again
        (dev/leave) – offline: the mark sync_leave_pending {seed, at} and a new try at the next start (T5)."""
        e = self.sync_engine
        rel = undo.get("relay")
        if rel is None:
            self.settings.pop("relay", None)
        else:
            self.settings["relay"] = rel
        for k in UNDO_KEYS:
            if k in undo["keys"]:
                self.settings[k] = undo["keys"][k]
            else:
                self.settings.pop(k, None)
        if undo.get("meta") is not None:
            with e.lock:
                e.meta.clear()
                e.meta.update(undo["meta"])
                if e.meta.get("on"):   # its own ID again: fetched and merged afresh (nothing was written meanwhile)
                    e.meta.update(seeded=False, version=0)
                e._save()
                e._suffix()
        try:
            from net import devkeys
            devkeys._update(code=undo.get("dk") or "")
        except Exception:  # noqa: BLE001
            log.info("Sync: cancel – the device key's address not put back")
        self.settings["sync_leave_pending"] = {"seed": undo["seed"], "at": int(time.time() * 1000)}
        self.settings_changed()
        for k in ("join", "join_n", "guard", "guard_wait", "join_request", "join_had_own", "join_from"):
            self.sync_status.pop(k, None)
        self.sync_setup()
        self._sync_changed()
        self.leave_pending_check()

    def leave_pending_check(self):
        """At the start (and right after a cancel): sign out of the ID left at the table (T5)."""
        from collection import syncrun
        mark = self.settings.get("sync_leave_pending")
        if not syncrun.available() or not isinstance(mark, dict) or not mark.get("seed"):
            return
        url = (self.settings.get("relay") or {}).get("url")
        from net import devkeys
        self._sync_bg("join_leave", lambda: devkeys.leave_seed(mark["seed"], url))

    def _join_leave_done(self, res, err):
        from net.vault import VaultError
        gone = err is None or (isinstance(err, VaultError) and err.status in (403, 404, 410))
        if gone:   # out (or not there any more): the mark and the seed it held go
            self.settings.pop("sync_leave_pending", None)
            self.settings_changed()
        else:
            log.info("Sync: leaving the joined ID failed (%s) – again at the next start", err.__class__.__name__)

    # ---------- „delete everything online“ that waited for a connection (lead 07.11.) ----------
    def forget_pending_check(self, guard=None):
        """At the start (and with the protection code): the remembered forget runs first. sync_status["forget"] =
        busy | deleted | main_required | failed (offline: next start)."""
        from collection import syncrun
        from net import forget
        if not syncrun.available() or not forget.pending():
            return
        self.sync_status = getattr(self, "sync_status", None) or {"ok": None, "text": "", "when": None,
                                                                   "busy": False}
        self.sync_status["forget"] = "busy"
        self._sync_changed()
        self._sync_bg("forget_pending", lambda: forget.finish_pending(guard))

    def _forget_pending_done(self, res, err):
        st = self.sync_status
        st["forget"] = "failed" if err is not None or res is None else (
            "deleted" if res.ok else res.status if res.status == "main_required" else "failed")
        self._sync_changed()

    # ---------- the device list (lead 07.11.) ----------
    def sync_devices(self):
        """-> [{"dev", "name" (None: show „Device {n}“), "n", "kind": "pc"|"phone", "os", "ver", "added", "seen" (day
        ms), "me"}] – this device first (docs/web/DEVICE-KEYS.md §5)."""
        e = getattr(self, "sync_engine", None)
        if e is None:
            return []
        if not e.on():   # signed out / off: the others aren't „your devices“ here any more (guide run 08.11.)
            return [d for d in e.devices() if d.get("me")]
        return e.devices()

    def device_rename(self, name, dev=None):
        """Rename a device in the list – this one (dev None) or any other own device (lead 07.11.); empty = back to
        „Device N“. Before the first sync (no list yet) only this device's name in the settings."""
        e = getattr(self, "sync_engine", None)
        me = e.meta.get("dev") if e is not None else None
        if e is None or not me or e.state.value("*/devices", dev or me) is None:
            if dev is None or dev == me:
                name = " ".join(str(name or "").split())[:60]
                if name:
                    self.settings["device_name"] = name
                else:
                    self.settings.pop("device_name", None)
                self.settings_changed()
            return
        if e.rename_device(dev or me, name):
            self.settings_changed()
            self.sync_now(manual=True)

    def sync_has_others(self):
        """Are there other own devices? (the delete page asks then – lead/ports 07.11.: in doubt, ask) The device list,
        or this device joined / one of its codes was fetched."""
        return len(self.sync_devices()) > 1 or bool(self.settings.get("sync_paired"))

    def identity_gone_seen(self):
        """The hint „this backup comes from a removed identity“ / „signed out by …“ was read (library's page)."""
        (self.settings.get("relay") or {}).pop("identity_gone", None)
        (self.settings.get("relay") or {}).pop("removed", None)
        self.sync_status.pop("removed", None)
        self.settings_changed()
        self._sync_changed()

    # ---------- joining with data on both sides (three buttons) and set-aside states (library's ui/joinui.py) ----------
    @property
    def sync_join_choice(self):
        """None, or {"other": "phone"|"pc"|"", "other_name": name or None (= „Device {other_n}“), "other_n": its
        number (0 unknown: „Other device“), "here": counts, "there": counts} while the user has to choose."""
        e = getattr(self, "sync_engine", None)
        hold = (e.meta.get("join_hold") or None) if e is not None else None
        if not hold:
            return None
        other = e.state.value("*/devices", e.meta.get("join_other_dev")) if e.meta.get("join_other_dev") else None
        other = other or {}
        from system import nicknames
        oid = e.meta.get("join_other_dev")
        nick = other.get("nick") if nicknames.valid(other.get("nick")) else (nicknames.fallback(oid) if oid else None)
        return dict(hold, other_name=other.get("name") or None, other_n=int(other.get("n") or 0), other_nick=nick)

    def sync_join_answer(self, kind):
        """"merge" | "theirs" | "mine" | "" (cancel) – the next run does it (Engine.join_answer)."""
        if getattr(self, "sync_engine", None) is None:
            return
        self.sync_engine.join_answer(kind)
        undo, self._join_undo = getattr(self, "_join_undo", None), None
        if not kind and undo:   # U5: cancelled at the table – back to what this device was, out of the joined ID
            return self._join_cancel(undo)
        self.sync_status["join"] = "busy" if kind else ""
        self.sync_setup()
        self._sync_changed()
        if kind:
            self.sync_now(manual=True)

    def aside_list(self):
        from collection import syncaside, syncrun
        return syncaside.list_all() if syncrun.available() else []

    def aside_seen(self, sid):
        e = getattr(self, "sync_engine", None)
        if e is not None:
            with e.lock:
                e.meta["aside_seen"] = sid
                e._save()
        if self.sync_status.get("aside") == sid:
            self.sync_status.pop("aside", None)
        self._sync_changed()

    def aside_open(self, sid):
        from collection import syncaside
        try:
            syncaside.open_folder(sid)
        except (KeyError, OSError):
            log.info("Set aside: %s not there", sid)
        self.aside_seen(sid)

    def aside_delete(self, sid):
        from collection import syncaside
        try:
            syncaside.delete(sid)
        except (KeyError, OSError):
            log.info("Set aside: %s not deleted", sid)
        self.aside_seen(sid)

    def aside_tickets(self, sid):
        """Open trades of a set-aside state, to look at only (legal 07.11.: never brought back) -> {game: [{"id",
        "partner" (the friend's name), "give", "get" (cards / amount), "t"}]}."""
        from collection import syncaside, syncrun
        if not syncrun.available():
            return {}
        try:
            return syncaside.tickets(sid)
        except (KeyError, OSError):
            return {}

    def aside_ticket_delete(self, sid, game, ticket_id):
        """Delete one open trade from a set-aside state (the user's word) -> True if it was there."""
        from collection import syncaside, syncrun
        if not syncrun.available():
            return False
        try:
            return syncaside.ticket_delete(sid, game, ticket_id)
        except (KeyError, OSError):
            return False

    def aside_restore(self, sid):
        """Bring a set-aside state back (two taps in the page): the sync goes off first (legal: restoring leaves it
        off), the current state is set aside itself, then the window re-reads everything."""
        import games
        from collection import syncaside, syncrun
        if not syncrun.available():
            return
        self._sync_flush()
        e = getattr(self, "sync_engine", None)
        if e is not None:
            e.switch_off()
            self.sync_setup()
        keys = e.docs.games() if e is not None else [games.current_key()]
        try:
            syncaside.restore(sid, {g: games.mine(g) for g in keys}, self.settings)
        except (KeyError, OSError) as err:
            log.exception("Set aside: restoring %s", sid)
            self.sync_status.update(text=problem_text(err))
            self._sync_changed()
            return
        self.settings_changed()
        from system import undo
        undo.clear("sync")
        cur = games.current_key()
        self._sync_refresh([(cur, syncrun.LOGS)] + [(cur, f) for f in syncrun.FILES])
        self.aside_seen(sid)

    def sync_gate(self, code):
        """The access code for the sync test server, typed in on Your devices: exchanged in the background (network),
        the result in the sync row."""
        from net import vault
        self.sync_status.update(busy=True, text="")
        self._sync_changed()
        self._sync_bg("gate", lambda: vault.set_gate(code))

    def sync_restore(self):
        """"Back it up again from this device" (the vault was empty): the next run sends the whole state as a snap."""
        if not self.sync_on():
            return
        self.sync_engine.meta.pop("empty_not_now", None)
        self.sync_engine.restore_vault()
        self.sync_status.update(emptied=False, text="")
        self.sync_now(manual=True)

    def sync_not_now(self):
        """"Not now": no more asking at every run (legal 06.11.: that would be a nudge) – only the quiet status line
        with [Back it up again] stays. Still nothing is sent until the user chooses that."""
        if getattr(self, "sync_engine", None) is not None:
            with self.sync_engine.lock:
                self.sync_engine.meta["empty_not_now"] = True
                self.sync_engine._save()
        self._sync_changed()

    def _sync_flush(self):
        """Before writing back: a collection change still waiting for its save goes to the file now – the sync reads
        the files, and the window re-reads them afterwards (nothing in memory may be lost)."""
        t = getattr(self, "_coll_timer", None)
        if t is not None and t.isActive():
            t.stop()
            self.save_collection()

    def _sync_refresh(self, written):
        """Re-read what the sync wrote – the same as after undo (decks, binders, lists, the library window)."""
        import games
        from collection import syncrun
        if not written:
            return
        cur = games.current_key()
        paths = []
        for g, f in written:
            if g != cur:
                continue
            if f == syncrun.LOGS:   # the collection: its file, the bookings, the logs
                from system import undo
                undo.clear("sync")   # Ctrl+Z must not take back what came from another device
                paths += [games.mine(g, "collection.json"), games.mine(g, "bookings.json"),
                          games.mine(g, "sessions", "_.json")]
            else:
                paths.append(games.mine(g, f))
        if any(f == "profile" for _g, f in written):
            self.settings_changed()
        if paths:
            try:
                self.after_undo(paths)
            except Exception:  # noqa: BLE001 – shows up at the next reload
                log.exception("Sync: refresh after writing back")

    # ---------- coupling: this PC shows the code, the other device enters it (PAIRING §2) ----------
    PAIR_POLL = 3   # s between two "fetched?" questions – only while the code is valid and the page is open

    def pair_show(self):
        """A new code (replaces an older one on the server): offer in the background, then poll."""
        if not self.sync_on() or getattr(self, "pair", {}).get("busy"):
            return
        if not self.sync_orbit_ok():   # pairing only in Full Orbit – nothing offered
            self.pair = {"busy": False, "code": "", "until": 0, "fetched": False, "shown": False, "error": "",
                         "orbit": True}
            self._sync_changed()
            return
        self._pair_drop_images()
        if not self.guard_on():   # A2 (Oliver 08.11.): a new device joins with the protection code – set it first
            self.pair = {"busy": False, "code": "", "until": 0, "fetched": False, "shown": False, "error": "",
                         "need_guard": True}
            self._sync_changed()
            return
        if self.sync_status.get("busy"):   # a sync run is on: never two runs side by side (review 08.11.)
            self.pair = {"busy": False, "code": "", "until": 0, "fetched": False, "shown": False,
                         "error": tr("Your devices are syncing right now – nothing was changed. Try again in a minute.")}
            self._sync_changed()
            return
        if not self.sync_engine.meta.get("seeded"):
            # never synced yet (e.g. the test server's access code was missing): nothing to hand over to a new device
            self.pair = {"busy": False, "code": "", "until": 0, "fetched": False, "shown": False,
                         "error": tr("Sync once first – then show a code for a new device.")}
            self._sync_changed()
            return
        self.pair = {"busy": True, "code": "", "until": 0, "fetched": False, "shown": False, "error": ""}
        self._sync_changed()
        s, engine = self.settings, self.sync_engine

        def work():   # first in sync (Oliver/lead T2 07.11., the web the same): the joining device then sees this
            try:      # device's data in the vault and asks „merge / keep“ – a failure: an error, no code
                engine.fetch()
                engine.push()
            except Exception as e:  # noqa: BLE001
                e.presync = True
                raise
            from net import devkeys
            return _offer(s, next_number(engine.devices(), engine.meta.get("my_n")), engine.meta.get("dev"), devkeys.invite(s),
                          dev_nick=engine.meta.get("my_nick"),
                          sphere=sphere_on(s))
        self._sync_bg("pair_offer", work)

    def pair_toggle(self):
        p = getattr(self, "pair", None)
        if p:
            p["shown"] = not p["shown"]
            self._sync_changed()

    def pair_copy(self):
        p = getattr(self, "pair", None)
        if p and p.get("code"):
            from PySide6 import QtGui
            QtGui.QGuiApplication.clipboard().setText(p["code"])
            p["copied"] = True

    def pair_left(self):
        p = getattr(self, "pair", None)
        return max(0, int(p["until"] - time.time())) if p and p.get("until") else 0

    def _pair_images(self, code, turn=()):
        """The code as a picture, sharp and smeared (blurred until "Show" – nobody reads along over your shoulder),
        and the turning sphere (ui/sphere.py: one turn, frames <img>_s0 … – also only a smear until "Show")."""
        from PySide6 import QtCore as C, QtGui
        from ui import quickimages
        self._pair_drop_images()
        from ui import look
        # like the app's input fields (lead 06.11.): a little darker than the surface, a thin line, light text
        img = QtGui.QImage(560, 120, QtGui.QImage.Format_ARGB32_Premultiplied)
        img.fill(C.Qt.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(QtGui.QColor(look.color("line")), 2))
        p.setBrush(QtGui.QColor(look.color("surface")).darker(115))
        p.drawRoundedRect(C.QRectF(1, 1, img.width() - 2, img.height() - 2), 14, 14)
        f = QtGui.QFont()
        f.setFamilies(["Cascadia Mono", "Consolas", "Courier New"])   # monospace: 5/S, 2/Z, 8/B, U/V clearly apart
        f.setStyleHint(QtGui.QFont.Monospace)
        f.setPixelSize(64)
        p.setFont(f)
        p.setPen(QtGui.QColor(look.color("text")))
        p.drawText(img.rect(), C.Qt.AlignCenter, code)
        p.end()
        self._pair_gen = getattr(self, "_pair_gen", 0) + 1   # a new name per code: QML caches images by URL
        self.pair["img"] = f"paircode{self._pair_gen}"
        quickimages.keep(self.pair["img"], img)
        tiny = img.scaled(14, 3, C.Qt.IgnoreAspectRatio, C.Qt.SmoothTransformation)   # nothing readable left
        quickimages.keep(self.pair["img"] + "_blur", tiny.scaled(img.width(), img.height(), C.Qt.IgnoreAspectRatio,
                                                                 C.Qt.SmoothTransformation))
        if turn:   # smeared like the code (6 × 6 and back up), then cut to the circle like the sharp frames
            import cv2
            h, w = turn[0].shape
            smear = cv2.resize(cv2.resize(turn[0], (6, 6), interpolation=cv2.INTER_AREA), (w, h),
                               interpolation=cv2.INTER_CUBIC)
            quickimages.keep(self.pair["img"] + "_sblur", _sphere_image(smear))
        for i, f in enumerate(turn):
            quickimages.keep(f"{self.pair['img']}_s{i}", _sphere_image(f))
        self.pair["turn"] = len(turn)

    def _pair_drop_images(self):
        """The previous code's pictures out of memory (a new code, or this one used up)."""
        p = getattr(self, "pair", None) or {}
        img = p.get("img")
        if not img:
            return
        from ui import quickimages
        for key in [img, img + "_blur", img + "_sblur"] + [f"{img}_s{i}" for i in range(p.get("turn") or 0)]:
            quickimages.drop(key)

    def _pair_poll(self):
        p = getattr(self, "pair", None)
        if not p or p.get("fetched") or p.get("polling") or not self.pair_left():
            if p and not self.pair_left() and getattr(self, "_pair_t", None):
                self._pair_t.stop()
            return
        if getattr(self, "settings_page", "") != "devices" or not self._sync_visible():
            return
        p["polling"] = True
        s, pid = self.settings, p["pid"]
        from net import vault
        self._sync_bg("pair_state", lambda: vault.pair_fetched(s, pid))

    def _pair_done(self, step, res, err):
        p = getattr(self, "pair", None)
        if p is None:
            return
        if step == "pair_offer":
            p["busy"] = False
            if err is not None and getattr(err, "presync", False):   # the web's words (ports, dv_show_nosync)
                p["error"] = tr("Couldn't sync this device first – no code yet. Try again once you're online.")
            elif err is not None:
                p["error"] = problem_text(err)
            else:
                code, pid, until, turn = res
                from net import pairing
                pretty = pairing.norm_code(code)
                p.update(code=f"{pretty[:5]}-{pretty[5:]}", pid=pid, until=until)
                self._pair_images(p["code"], turn)
                if getattr(self, "_pair_t", None) is None:
                    self._pair_t = QtCore.QTimer(self, interval=self.PAIR_POLL * 1000, timeout=self._pair_poll)
                self._pair_t.start()
        else:   # pair_state
            p["polling"] = False
            if err is None and res:
                p["fetched"] = True
                self.settings["sync_paired"] = True   # another device has this identity now (delete page asks)
                self.settings_changed()
                self._pair_t.stop()
                self._pair_forget_code()
                QtCore.QTimer.singleShot(2000, self.sync_now)   # the new device's seed arrives soon
            elif err is not None and getattr(err, "status", 0) == 404:
                p["until"] = 0   # expired or replaced
                self._pair_t.stop()
        self._sync_changed()

    def _pair_forget_code(self):
        """Fetched: the code is used up – out of the clipboard if it is still there, and off the page."""
        p = self.pair
        try:
            from PySide6 import QtGui
            cb = QtGui.QGuiApplication.clipboard()
            if cb.text().strip().upper() == p["code"].upper():
                cb.clear()
        except Exception:  # noqa: BLE001
            log.exception("Sync: clearing the clipboard")
        self._pair_drop_images()
        p.update(code="", shown=False, img="", turn=0)

    # ---------- online backup: the switch, the rescue code (library's pages call these – only behind available()) ----------
    def sync_backup_set(self, on, guard=None):
        """„Daten online sichern, verschlüsselt“: on only through sync_rescue_confirm (the code must be confirmed
        first); off = delete the online backup (Oliver 06.11.: switching off deletes vault + envelope)."""
        from collection import syncrun
        if not syncrun.available():
            return
        if not on:
            self.vault_delete(guard)
            return
        # on without a code (Oliver 07.11.: the protection/rescue code is an offer, not a condition); the user's own
        # step – a removed device's new identity may speak again
        (self.settings.get("relay") or {}).pop("identity_gone", None)
        self.settings["sync_backup"] = True
        self.settings_changed()
        self.sync_setup()
        if getattr(self, "sync_engine", None) is not None and not self.sync_engine.on():
            self.sync_engine.switch_on()
            self.sync_setup()
        self.sync_now(manual=True)

    def sync_rescue_confirm(self, code, last5, old=None):
        """The user noted the code and typed its last 5 characters: seal + upload the envelope, then switch on.
        sync_status["rescue"]: "mismatch" (nothing uploaded) | "need_old" (a code is set: a new one needs the old one,
        old= in plain text – nothing uploaded) | "busy" | "ok" | "error" (+ text); bridge.sync_state."""
        from collection import syncrescue, syncrun
        if not syncrun.available():
            return
        st = self.sync_status
        if not syncrescue.last5_ok(code, last5):
            st.update(rescue="mismatch", text=tr("The last 5 characters don't match the protection code."))
            self._sync_changed()
            return
        e = getattr(self, "sync_engine", None)
        first = not (e is not None and e.meta.get("guard"))
        missing = bool(self.settings.get("sync_rescue_missing"))
        if not first and not old and not missing:   # code and envelope must stay one code: a change needs the old code
            st.update(rescue="need_old", text="")
            self._sync_changed()
            return
        st.update(rescue="busy", busy=True, text="")
        self._sync_changed()
        s = self.settings
        log.info("Sync: generated protection code – first %s, change %s, envelope missing %s", first, bool(old), missing)
        # the code is set but its envelope never went up (sync_rescue_missing, like the web): only the envelope, signed
        # with the typed code (sig_main) – the server takes it only if it is THE code, else 403 -> need_old
        self._sync_bg("rescue_put", lambda: _guard_and_envelope(s, code, old, set_guard=(first or bool(old))))

    # ---------- the protection code (net/guard.py; library's names) ----------
    def guard_on(self):
        e = getattr(self, "sync_engine", None)
        return bool(e is not None and e.meta.get("guard"))

    def guard_optional(self):
        """„Without a protection code“ only while the ID has a single device (Oliver 08.11., A2): the server's registry
        has at most one entry; before its first answer the own device list decides."""
        rows = (getattr(self, "_dev_reg", None) or {}).get("list")
        if rows is not None:
            return len(rows) <= 1
        return not self.sync_has_others()

    def guard_strength(self, text):
        """-> {"score" 0..3, "ok", "bits"} of a code the user chose (collection/codestrength; only on the device)."""
        from collection import codestrength
        r = codestrength.strength(text)
        return {"score": r["score"], "ok": r["ok"], "bits": r["bits"]}

    def guard_set(self, code, own=False, old=None):
        """A (new) protection code – the same as the rescue code: guard + envelope (a change needs the old code).
        own: the user chose it – below the minimum strength it is refused, always (lead/legal 07.11.). A code is set
        already and old (plain text) is missing: sync_status["guard"] = "need_old", nothing is sent."""
        from collection import syncrun
        from net import guard, vault
        if not syncrun.available():
            return
        if own and not self.guard_strength(code)["ok"]:
            self.sync_status.update(guard="weak")
            self._sync_changed()
            return
        missing = bool(self.settings.get("sync_rescue_missing"))
        if self.guard_on() and not old and not missing:
            self.sync_status.update(guard="need_old")
            self._sync_changed()
            return
        s = self.settings
        set_guard = not self.guard_on() or bool(old)
        log.info("Sync: protection code – own %s, change %s, set %s, envelope missing %s", bool(own), bool(old),
                 set_guard, missing)   # bug 1 (lead 12.11.): the path only – never a code
        self.sync_status.update(guard="busy")
        self._sync_changed()
        self._sync_bg("guard", lambda: _guard_and_envelope(s, code, old, set_guard) and None)

    def guard_request_prepare(self):
        """„Code lost“, step 1 (library/ports 07.11., like the web): -> a new code, only shown – nothing is sent and
        nothing kept here (the page holds it in memory until step 2)."""
        from collection import syncrun
        from net import pairing
        if not syncrun.available():
            return None
        return pairing.new_rescue_code()

    def guard_request_confirm(self, code, last5):
        """Step 2: the user noted the code and typed its last 5 characters -> True: the request goes out in the
        background (the new key AND the new code's envelope, guard.request; the server holds it back until it takes
        effect); False: the 5 don't match – nothing sent. sync_status["guard"]: busy -> ok (+ "request_until", the
        SERVER's date – never computed here) | wait | error; settings["sync_guard_mine"] = {"until"}: this device asked
        (it shows its own line, not the big notice for the others)."""
        from collection import syncrescue, syncrun
        from net import guard
        if not syncrun.available() or not syncrescue.last5_ok(code, last5):
            return False
        s = self.settings
        self.sync_status.update(guard="busy")
        self.sync_status.pop("request_until", None)
        self._sync_changed()
        self._sync_bg("guard_request", lambda: guard.request(s, code))
        return True

    def _guard_request_done(self, res, err):
        if err is None:
            until = (res or {}).get("until")
            self.settings["sync_guard_mine"] = {"until": until}
            self.sync_status["request_until"] = until
        self._guard_done(err)

    def guard_request_info(self):
        """-> {"since", "until"} while a request to replace the code runs (every device shows it big), else None. No
        request any more (declined, taken effect, dropped by „Gerät entfernen“): this device's own mark goes too – but only
        once the server reported the request here (or its date passed). F5 (Oliver's test round 11.11.): right after
        sending, the page asked before the next sync brought the request – the mark went at once and this device then
        showed its OWN request as „one of your devices wants a new code“."""
        e = getattr(self, "sync_engine", None)
        info = (e.meta.get("guard_request") or None) if e is not None else None
        mine = self.settings.get("sync_guard_mine")
        if not isinstance(mine, dict) or e is None or not e.meta.get("seeded"):
            return info
        if info is not None and not mine.get("seen"):
            mine["seen"] = True   # the server has it: from now on its end also ends the mark
            self.settings_changed()
        elif info is None and (mine.get("seen") or time.time() > float(mine.get("until") or 0)):
            self.settings.pop("sync_guard_mine", None)
            self.settings_changed()
        return info

    def guard_decline(self, code):
        from collection import syncrun
        from net import guard
        if not syncrun.available():
            return
        s = self.settings
        self.sync_status.update(guard="busy")
        self._sync_changed()
        self._sync_bg("guard", lambda: guard.decline(s, code) and None)

    def _rescue_missing(self, err):
        """settings["sync_rescue_missing"] (the web's name, ports 07.11.): the protection code went up, its envelope
        not (T2: guard without rescue) – the next try with the same code needs no „previous code“. Gone on success."""
        if err is None:
            if self.settings.pop("sync_rescue_missing", None):
                self.settings_changed()
        elif getattr(err, "rescue_missing", False):
            self.settings["sync_rescue_missing"] = True
            self.settings["sync_rescue_ok"] = False
            if getattr(self, "sync_engine", None) is not None:
                self.sync_engine.meta["guard"] = True   # the server has it: a new code needs the old one
            self.settings_changed()

    def _guard_done(self, err):
        """sync_status["guard"]: ok | wrong (403 main_required: missing or wrong code) | wait (429, + guard_wait s – a
        right code still goes through) | half (the code is set, its envelope not) | error."""
        from net.vault import VaultError
        st = self.sync_status
        log.info("Sync: protection code answer – %s", _why(err))
        self._rescue_missing(err)
        if err is None:
            st.update(guard="ok", text="")
            self.settings["sync_rescue_ok"] = True   # a protection code exists now (library's page shows it)
            self.settings_changed()
            self.sync_now(manual=True)
        elif isinstance(err, VaultError) and (err.data or {}).get("guard_first_only_alone"):
            # Gordon 8597915: a first code only while at most one device is registered (A2) – the page says so
            st.update(guard="first_alone", text="")
        elif isinstance(err, VaultError) and (err.data or {}).get("main_required"):
            st.update(guard="wait" if err.status == 429 else "wrong",
                      guard_wait=int((err.data or {}).get("retry_after") or 0))
        elif getattr(err, "taken", False):   # bug 1: this code can't be used (its envelope id is taken)
            st.update(guard="taken_half" if getattr(err, "rescue_missing", False) else "taken", text="")
        elif getattr(err, "rescue_missing", False):   # bug 1: the code IS set – only its envelope didn't go up
            st.update(guard="half", text="")
        else:
            st.update(guard="error", text=problem_text(err))
        self._sync_changed()

    def sync_rescue_restore(self, code):
        """Restore with the rescue code (no old device): the identity from the envelope, then a fresh first sync.
        sync_status["rescue"]: "busy" | "ok" | "wrong" (never says why – legal) | "error"."""
        from collection import syncrun
        if not syncrun.available():
            return
        self.sync_status.update(rescue="busy", busy=True, text="")
        self._sync_changed()
        s = self.settings
        from net import vault
        self._rescue_typed = code   # only in memory: the device registration right after uses it once (M10)
        self._sync_bg("rescue_restore", lambda: vault.rescue_fetch(s, code))

    def sync_offer_answer(self, yes):
        """Existing Full-Orbit users (legal's card): „Ohne Sicherung weiter“ = False – asked once, nothing uploaded.
        „Sicherung einschalten“ goes through the rescue code page -> sync_rescue_confirm."""
        from collection import syncrun
        if not syncrun.available():
            return
        self.settings["sync_asked"] = time.time()
        if not yes:
            self.settings["sync_backup"] = False
        self.settings_changed()

    def _rescue_done(self, step, res, err):
        from net import pairing
        from net.vault import VaultError
        st = self.sync_status
        st["busy"] = False
        log.info("Sync: %s answer – %s", step, _why(err))
        if step == "rescue_put":
            self._rescue_missing(err)
            if isinstance(err, VaultError) and (err.data or {}).get("main_required"):   # not THE code: the old one
                st.update(rescue="need_old", text="")
                self._sync_changed()
                return
            if isinstance(err, VaultError) and (err.data or {}).get("guard_first_only_alone"):
                # box 8597915: a FIRST code only while the ID has a single device – the page says what to do (library)
                st.update(rescue="first_alone", text="")
                self._sync_changed()
                return
        if step == "rescue_restore" and err is not None:
            self._rescue_typed = None
        if err is None:
            if step == "rescue_restore":   # this device takes the identity from the envelope
                # the code that opened it is the protection code (one code, lead 07.11.): the registration joins at
                # once with it instead of a 14-day request a stolen device could decline (review 08.11., M10)
                self._rescue_guard = getattr(self, "_rescue_typed", None)
                self.settings.setdefault("relay", {})["seed"] = res
                self.settings["relay"].pop("test_registered", None)
                self.settings["relay"].pop("registered", None)
            self.settings.update(sync_backup=True, sync_rescue_ok=True, sync_asked=time.time())
            self.settings_changed()
            st.update(rescue="ok", text="")
            if getattr(self, "sync_engine", None) is not None:
                if step == "rescue_restore" or not self.sync_engine.on():
                    self.sync_engine.switch_on()
                self.sync_setup()
                self.sync_now(manual=True)
        elif step == "rescue_put" and getattr(err, "taken", False):   # bug 1: this code can't be used
            st.update(rescue="taken_half" if getattr(err, "rescue_missing", False) else "taken", text="")
        elif step == "rescue_put" and getattr(err, "rescue_missing", False):   # bug 1: set, only the envelope missing
            st.update(rescue="half", text="")
        elif step == "rescue_restore" and (isinstance(err, pairing.PairError)
                                           or (isinstance(err, VaultError) and err.status == 404)):
            st.update(rescue="wrong", text=tr("This protection code doesn't fit."))
        else:
            st.update(rescue="error", text=problem_text(err))
            log.info("Sync: %s – %s", step, err)
        self._sync_changed()

    def vault_delete(self, guard=None):
        """„Online-Sicherung löschen“ (legal 03.11.): empty the vault AND the rescue envelope, then stop syncing;
        this PC's data stays. Server FIRST (lead/ports 07.11., the web alike): without a connection nothing changes –
        sync and switch stay on, only a line. sync_status["deleted"] says how it went.
        A protection code set (lead 07.11.): only with it (guard, plain text, typed for this one action) – without,
        nothing is sent and sync_status["delete_guard"] = "need" (also when the server wants one this PC didn't know
        of yet); with a typed code the server's answers: "wrong" (403 main_required) | "wait" (429, + guard_wait s). Not an error: the page asks for the code, sync and switch stay on."""
        from collection import syncrun
        if getattr(self, "sync_engine", None) is None or not syncrun.available():
            return
        self.sync_status.pop("delete_guard", None)
        if self.guard_on() and not guard:
            self.sync_status.update(delete_guard="need", busy=False)
            self._sync_changed()
            return
        self.sync_status.update(busy=True, text="")
        self._sync_changed()
        s = self.settings
        from net import vault
        self._delete_typed = bool(guard)   # a 403 then means: the code was wrong (else: needed)
        self._sync_bg("vault_delete", lambda: vault.clear(s, guard))

    def _sync_changed(self):
        """The sync row in the settings listens to this (bridge.sync_state)."""
        try:
            self.bridge.sync_state.emit()
        except RuntimeError:
            pass


def _why(err):
    """For the log only: ok, or the kind of error with the server's status and its flags – never a code or a key."""
    if err is None:
        return "ok"
    flags = sorted(k for k, v in (getattr(err, "data", None) or {}).items() if v is True)
    return f"{err.__class__.__name__} {getattr(err, 'status', '')} {flags} rescue_missing={getattr(err, 'rescue_missing', False)}"


WIPE_FAILED = ("The safety copy of your data couldn't be created – so nothing was deleted. Check the free storage "
               "space and try again.")   # legal 12.11.


def _taken(e):
    """409 on rescue/put: the envelope's id (derived from the code alone, so it can be restored without a device)
    belongs to another address – this code can't be used (bug 1, Oliver 12.11.; never said why: legal)."""
    from net import vault
    return isinstance(e, vault.VaultError) and e.status == 409


def _registered_first(settings, fn):
    """fn(); the box says this device isn't in the registry yet (403 dev_required – a fresh device registers after its
    first good sync run; setting the code right after switching on raced it, desk-geraete3 box run 12.11.): register
    now (as the first device, devkeys.register) and once more."""
    from net import devkeys, vault
    try:
        return fn()
    except vault.VaultError as e:
        if not (e.data or {}).get("dev_required"):
            raise
        # the sync's own registration may have finished meanwhile (box run 12.11.) – then simply once more
        if not devkeys.registered(settings) and devkeys.register(settings) != "ok":   # a join request: nothing more
            raise
        log.info("Sync: device registered first – the protection code once more")
        return fn()


def _put_twice(settings, code, keys, wait):
    from net import vault
    try:
        return _registered_first(settings, lambda: vault.rescue_put(settings, code, keys=keys))
    except vault.VaultError as e:
        if (e.data or {}).get("main_required") or _taken(e):   # nothing to retry
            raise
        time.sleep(wait)
    except Exception:  # noqa: BLE001 – no connection: once more
        time.sleep(wait)
    return vault.rescue_put(settings, code, keys=keys)


def _guard_and_envelope(settings, code, old, set_guard, wait=1.0):
    """The protection code (if set_guard) and the envelope it opens – one code (lead 07.11.). The envelope is tried twice
    (ports' web the same). A FIRST code (lead 12.11., bug 1): the envelope first, then the code – a 409 (its id taken)
    sets nothing (err.taken). A change (old): the code first (the envelope needs its signature), then the envelope –
    failing there the error carries rescue_missing (+ taken on a 409): the new code IS set."""
    from net import guard, pairing
    # one run per stage for the code and its envelope (library 07.11.: 12–14 s busy); the ID's salt (S5 = b)
    keys = pairing.code_keys(code, guard.setup_salt(settings))
    if set_guard and not old:
        try:
            res = _put_twice(settings, code, keys, wait)
        except Exception as e:
            e.taken = _taken(e)
            raise
        _registered_first(settings, lambda: guard.set_code(settings, code, old, keys=keys))
        return res
    if set_guard:
        _registered_first(settings, lambda: guard.set_code(settings, code, old, keys=keys))
    try:
        return _put_twice(settings, code, keys, wait)
    except Exception as e:
        from net import vault
        if not (isinstance(e, vault.VaultError) and (e.data or {}).get("main_required")):
            e.rescue_missing = True
        e.taken = _taken(e)
        raise


def next_number(devices, mine=None):
    """The number the next device will get (DEVICE-KEYS §5: the largest + 1). The showing device counts too, even
    before its own entry is in the list (ports 12.11.: else the phone got „1“ like the PC) – so never below 2."""
    return max([int(d.get("n") or 0) for d in devices] + [int(mine or 0), 1]) + 1


SPHERE = False   # lead/ports 11.11.: the sphere (show and read) behind a switch like PHONE_CAMERA – off; the code stays


def sphere_on(_settings=None):
    """The sphere only with the switch on (a constant in the code, like the web's buildflags.js SPHERE – no setting)."""
    return SPHERE


def _offer(settings, next_n=None, dev=None, invite=None, sphere=False, dev_nick=None):
    """In the background: a new code on the server, and – with the switch on – the sphere carrying it (one turn, ~2 s
    of drawing)."""
    from net import pairing, vault
    code, pid, until = vault.pair_offer(settings, next_n, dev, invite, dev_nick)
    if not sphere:
        return code, pid, until, ()
    from ui import sphere as sph
    return code, pid, until, sph.frames(pairing.picture_bytes(code))


def _sphere_image(a):
    """A sphere frame with only the sphere opaque (its outline included, soft edge): around it the card shows through
    (lead 06.11.: no square behind the sphere)."""
    import numpy as np
    from PySide6 import QtGui
    from ui import sphere
    h, w = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx + 0.5 - w / 2, yy + 0.5 - h / 2)
    r = sphere.outline_radius(w)
    alpha = (np.clip(r - d + 1.0, 0.0, 1.0) * 255).astype(np.uint8)
    rgba = np.dstack([a, a, a, alpha])
    return QtGui.QImage(rgba.tobytes(), w, h, 4 * w, QtGui.QImage.Format_RGBA8888).copy()
