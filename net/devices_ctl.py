"""Own devices one by one (B5, docs/web/DEVICE-KEYS.md; Oliver 07.11.: „Gerät entfernen geht einfach von einem Gerät aus.
Mit Code: Code eingeben; ohne: delete > yes/no.“). The logic for library's page (✕ in the device list), the web alike.

    sync_remove_plan(dev)        -> {"name", "n", "with": [{"dev", "name", "n"}], "guard": bool} | None
    sync_remove(dev, guard=None) sync_status["remove"] = busy | ok | error (+ text) | conflict (409, list changed);
                                 a protection code: delete_guard need / wrong / wait (+ guard_wait), like deleting
    sync_join_request_info()     -> None | [{"dev", "since", "until"}] – a device asks to join (from a backup, 14 days)
    sync_join_request_answer(dev, allow, guard=None)   decline always; allow with the code if one is set
    sync_status["join_wait"]     {"until"} on the device that asked itself

Registration runs by itself: after a sync this device puts its keys into the server's registry – as the first device,
with the invitation from the pairing payload, or (a backup without code, devices there) as a join request.
"""
import logging
import time

from system.i18n import tr

log = logging.getLogger("booster")


class DevicesControl:
    """Mixin of MainWindow (app.py), next to SyncControl. self is the MainWindow."""

    # ---------- registration ----------
    def _dev_ensure(self, force=False):
        """After a good sync run: this device in the registry (once; a join request is asked only once).
        force: the server refused a sync write because this device isn't registered (403 dev_required) – register NOW,
        before any good run (ports 08.11.: otherwise a restored/unregistered device never asks to join)."""
        from collection import syncrun
        from net import devkeys
        e = getattr(self, "sync_engine", None)
        if (not syncrun.available() or e is None or not e.on() or (not e.meta.get("seeded") and not force)
                or getattr(self, "_dev_busy", False)):
            return
        bad = devkeys.unreadable()   # M3: never new keys over it – but never silent either (lead 08.11.)
        if bad != bool(self.sync_status.get("devkey_unreadable")):
            log.warning("Sync: %s %s", devkeys.FILE, "can't be read – no registration until it can" if bad else "readable again")
            self.sync_status["devkey_unreadable"] = bad
            self._sync_changed()
        if bad:
            return
        if devkeys.registered(self.settings):
            if getattr(self, "_dev_reg", None) is None:   # the device list for the page (✕) – once, then the poll
                self._dev_refresh()
            return
        k = devkeys.mine(create=False)
        from net import relay
        if k is not None and devkeys._load(False).get("pending") == relay.my_code(self.settings):
            return   # asked already – the poll's reg_version tells when it was let in
        if time.time() < getattr(self, "_dev_cooldown", 0):   # declined: not before the server's date (A3)
            return
        self._dev_busy = True
        s, invite = self.settings, getattr(self, "_join_invite", None)
        self._dev_add_plain = not invite and not getattr(self, "_rescue_guard", None)
        guard, self._rescue_guard, self._rescue_typed = getattr(self, "_rescue_guard", None), None, None   # once

        def work():
            from net.vault import VaultError
            if guard and not invite:   # just restored with the protection code: join at once (M10)
                try:
                    return devkeys.register(s, None, guard)
                except VaultError as ex:
                    if ex.status not in (403, 429):
                        raise
                    log.info("Sync: joining with the protection code didn't work (%s) – asking instead", ex.status)
            try:
                return devkeys.register(s, invite)
            except VaultError as ex:
                if invite and ex.status == 403:   # the invitation expired (15 min) or was used: ask instead
                    return devkeys.register(s, None)
                raise
        self._sync_bg("dev_add", work)

    def _dev_refresh(self):
        """The registry (on a new reg_version from the poll): device list ids and join requests for the page."""
        from net import devkeys
        if getattr(self, "_dev_listing", False):
            return
        self._dev_listing = True
        s = self.settings
        self._sync_bg("dev_list", lambda: devkeys.listing(s))

    def _dev_done(self, step, res, err):
        from net import devkeys
        st = self.sync_status
        if step == "dev_add":
            self._dev_busy = False
            data = getattr(err, "data", None) or {}
            if err is not None and getattr(err, "status", 0) == 429 and data.get("cooldown_until"):
                # box 01e8440 (A3): a device declined this one – no new request for 7 days; the date comes from the
                # server. The page says when it may ask again; no new try before then
                st["join_wait"] = {"declined": True, "cooldown_until": int(data["cooldown_until"])}
                self._dev_cooldown = int(data["cooldown_until"])
                self._sync_changed()
                return
            if (err is not None and getattr(self, "_dev_add_plain", False)
                    and (getattr(err, "data", None) or {}).get("main_required")):
                # A2 (box 8597915): the ID has a protection code – no join request without it; another device is
                # signed in (the owner's, or a copy of the backup): the page offers „take over with the code“
                st.setdefault("foreign_device", {"dev": None, "since": int(time.time())})
                log.info("Sync: device registration – the ID has a protection code: asking for it")
                self._sync_changed()
                return
            if err is not None:
                log.info("Sync: device registration – %s", err)
                return
            self._join_invite = None
            if isinstance(res, dict) and res.get("pending"):
                st["join_wait"] = {"until": res.get("until")}
                if getattr(self, "_dev_add_plain", False):
                    # neither an invitation (pairing) nor the protection code (restore): another device already has
                    # this ID – the owner's other device, or a copy of the backup file (legal/lead 08.11.)
                    st.setdefault("foreign_device", {"dev": None, "since": int(time.time())})
            else:
                st.pop("join_wait", None)
                st.pop("foreign_device", None)
                e = getattr(self, "sync_engine", None)
                if e is not None:
                    e.catch_up()   # the device list learns this device's registry id
            self._sync_changed()
            return
        if step == "dev_list":
            self._dev_listing = False
            if err is not None:
                return
            self._dev_reg = res or {}
            mine = (devkeys.mine(create=False) or {}).get("dev_id")
            rows = {r["dev_id"] for r in (res or {}).get("list") or []}
            k = devkeys._load(False) or {}
            if mine in rows and not devkeys.registered(self.settings):   # let in (allowed, or 14 days passed)
                from net import relay
                devkeys._update(code=relay.my_code(self.settings), pending="")
                st.pop("join_wait", None)
            elif k.get("pending") and mine not in {r.get("dev_id") for r in (res or {}).get("dev_request") or []} \
                    and mine not in rows:   # declined: the request is gone – the user may ask again
                devkeys._update(pending="")
                st["join_wait"] = {"declined": True}
            st["dev_request"] = [dict(r, dev=r["dev_id"]) for r in (res or {}).get("dev_request") or []
                                 if r.get("dev_id") != mine]
            self._sync_changed()
            return
        if step == "dev_decide":
            from net.vault import VaultError
            if isinstance(err, VaultError) and (err.data or {}).get("main_required"):
                st.update(delete_guard="wait" if err.status == 429 else "wrong",
                          guard_wait=int((err.data or {}).get("retry_after") or 0))
            elif err is not None:
                st.update(text=problem_text(err))
            self._sync_changed()
            self._dev_refresh()
            return
        if step == "remove_one":
            return self._remove_done(res, err)
        if step == "add_code":
            return self._add_code_done(res, err)

    def _dev_poll(self, res):
        """From the minute question: the registry changed (devices in/out, a request) -> fetch the list."""
        rv = res.get("reg_version")
        reqs = res.get("dev_request") or []
        if rv != getattr(self, "_dev_rv", None) or reqs != getattr(self, "_dev_reqs", None):
            self._dev_rv, self._dev_reqs = rv, reqs
            self._dev_refresh()

    # ---------- removing one device ----------
    def _rid_of(self, dev):
        """The registry id of a device in the list (*/devices rid), or the id itself."""
        for d in self.sync_devices():
            if d.get("dev") == dev or d.get("rid") == dev:
                return d.get("rid")
        return None

    def sync_remove_plan(self, dev):
        """What removing `dev` (a */devices id) means – the page shows it BEFORE anything happens: its name, the devices
        it added itself („Mit entfernt: …“, removed with it) and whether the protection code is needed."""
        from net import devkeys
        rid = self._rid_of(dev)
        rows = (getattr(self, "_dev_reg", None) or {}).get("list") or []
        if not rid or rid not in {r["dev_id"] for r in rows}:
            self._dev_refresh()   # an older list (guide run 07.11.): fetch it – the page asks again on its next draw
            if getattr(self, "_rm_wait", 0) < time.time() - 60:   # a just-added device (box run 12.11.): its entry
                self._rm_wait = time.time()                           # and the server's list may lag – check a while
                if not rid and hasattr(self, "sync_now"):
                    self.sync_now(manual=True)
            return None
        by_rid = {d.get("rid"): d for d in self.sync_devices() if d.get("rid")}
        me = by_rid.get(rid) or {}
        others = []
        chain = devkeys.chain(rows, rid)
        # M7 (review 08.11.): exactly this plan is what gets sent – a list that changed meanwhile -> 409, ask again
        self._remove_plans = dict(getattr(self, "_remove_plans", None) or {})
        self._remove_plans[rid] = {"rv": int((self._dev_reg or {}).get("reg_version") or 0), "gone": sorted(chain)}
        for r in chain[1:]:
            d = by_rid.get(r) or {}
            others.append({"dev": d.get("dev"), "name": d.get("name"), "n": int(d.get("n") or 0)})
        return {"name": me.get("name"), "n": int(me.get("n") or 0), "with": others, "guard": bool(self.guard_on())}

    def sync_remove_checking(self):
        """True for a short while after a ✕ found no plan: the device list is being fetched (the page says so, not
        „This device isn't in the list any more“ – desk-geraete3 box run 12.11.)."""
        return bool(getattr(self, "_dev_listing", False) or time.time() - getattr(self, "_rm_wait", 0) < 20)

    def sync_remove(self, dev, guard=None):
        """Remove one device (and those it added): a new key for this identity, the others follow by themselves."""
        from collection import syncrun
        from net import rekey
        st = self.sync_status
        if not syncrun.available() or st.get("remove") == "busy" or st.get("rekey") == "busy":
            return
        rid = self._rid_of(dev)
        if not rid:
            st.update(remove="error", text=tr("This device isn't in the list any more."))
            self._sync_changed()
            return
        st.pop("delete_guard", None)
        if self.guard_on() and not guard:
            st.update(delete_guard="need")
            self._sync_changed()
            return
        st.update(remove="busy", rekey="busy", text="")
        self._rekey_n = getattr(self, "_rekey_n", 0) + 1   # a fetch still running answers for the old address
        self._sync_changed()
        s = self.settings
        known = {d.get("rid") for d in self.sync_devices() if d.get("rid")}   # the identity's own (sealed) list
        plan = (getattr(self, "_remove_plans", None) or {}).get(rid)

        def work():
            res = rekey.remove_one(s, rid, guard, known, plan)
            # the code moved along with the identity; the envelope holds the old seed: up anew (M11: after the change)
            return dict(res, **rekey.after_change(s, guard))
        self._sync_bg("remove_one", work)

    def _remove_done(self, res, err):
        st = self.sync_status
        from net.relay import RelayError
        from net.vault import VaultError
        data = getattr(err, "data", None) or {}
        if isinstance(err, (RelayError, VaultError)) and data.get("main_required"):
            st.update(remove="", rekey="", delete_guard="wait" if err.status == 429 else "wrong",
                      guard_wait=int(data.get("retry_after") or 0))
            self._sync_changed()
            return
        if isinstance(err, (RelayError, VaultError)) and err.status in (409, 410):
            # 410: another device removed one at the same moment and moved the address first (review 08.11.)
            st.update(remove="conflict", rekey="", text="")
            self._sync_changed()
            self._dev_refresh()
            return
        from net.rekey import UnknownDevice
        if isinstance(err, UnknownDevice):   # the server lists a device this identity doesn't know: nothing sent
            st.update(remove="error", rekey="", text=tr("A device on the server isn't in your own device list – "
                                                        "nothing was changed. Try again in a minute."))
            log.info("Sync: remove one – %s", err)
            self._sync_changed()
            self._dev_refresh()
            return
        if err is not None:
            st.update(remove="error", rekey="", text=problem_text(err))
            log.info("Sync: remove one – %s", err)
            self._sync_changed()
            return
        e = getattr(self, "sync_engine", None)
        if e is not None:
            e.drop_devices(res.get("gone"))
        self._rekey_done(dict(res, mode="remove_one"), None)   # the new vault from here, sharing anew, sync
        st.update(remove="ok")
        self._sync_changed()
        self._dev_refresh()

    # ---------- join requests (a backup without code while devices are registered: 14 days) ----------
    # ---------- „another device is signed in with your ID“ (legal/lead 08.11.) ----------
    def sync_add_with_code(self, guard):
        """[Add with protection code] (lead 09.11.): this device joins with the code – nobody is removed; a device that
        isn't yours goes afterwards with ✕ in the list. A wrong code changes nothing.
        sync_status["add_code"]: busy | ok | wrong | wait (+ guard_wait) | error (+ text)."""
        from collection import syncrun
        st = self.sync_status
        if not syncrun.available() or not guard or st.get("add_code") == "busy" or st.get("rekey") == "busy":
            return
        st.update(add_code="busy", text="")
        self._sync_changed()
        s = self.settings
        self._sync_bg("add_code", lambda: add_with_code(s, guard))

    def _add_code_done(self, res, err):
        from net.relay import RelayError
        from net.vault import VaultError
        st = self.sync_status
        data = getattr(err, "data", None) or {}
        if isinstance(err, (RelayError, VaultError)) and data.get("main_required"):
            st.update(add_code="wait" if err.status == 429 else "wrong", guard_wait=int(data.get("retry_after") or 0))
            self._sync_changed()
            return
        if err is not None:
            st.update(add_code="error", text=problem_text(err))
            log.info("Sync: take over – %s", err)
            self._sync_changed()
            self._dev_refresh()
            return
        st.pop("foreign_device", None)
        st.pop("join_wait", None)
        st["add_code"] = "ok"
        if res.get("gone"):
            e = getattr(self, "sync_engine", None)
            if e is not None:
                e.drop_devices(res["gone"])
            self._rekey_done(dict(res, mode="remove_one"), None)
        self._sync_changed()
        self._dev_refresh()

    def identity_new(self):
        """[Create new ID]: a new identity on this device – only this device's own data stays (legal 08.11. (1)):
        the old ID's friends, their keys, what was shared, the device registration and the sync with the old ID go.
        sync_status["identity_new"] = "ok" (local only, nothing sent)."""
        import base64
        import nacl.utils
        from net import devkeys
        rel = self.settings.setdefault("relay", {})
        rel["seed"] = base64.b64encode(nacl.utils.random(32)).decode()
        for k in OLD_ID_BITS:
            rel.pop(k, None)
        devkeys.device_bits_off(self.settings)
        devkeys.forget()
        _drop_friend_files()
        e = getattr(self, "sync_engine", None)
        if e is not None:
            e.switch_off()
        self.settings["sync_backup"] = False
        self.settings_changed()
        st = self.sync_status
        for k in ("foreign_device", "join_wait", "add_code"):
            st.pop(k, None)
        st.update(identity_new="ok", ok=None, text="")
        self._dev_reg = None
        self.sync_setup()
        self._sync_changed()

    def sync_join_request_info(self):
        return list(self.sync_status.get("dev_request") or []) or None

    def sync_join_request_answer(self, dev, allow, guard=None):
        from net import devkeys
        st = self.sync_status
        st.pop("delete_guard", None)
        if allow and self.guard_on() and not guard:
            st.update(delete_guard="need")
            self._sync_changed()
            return
        s = self.settings
        self._sync_bg("dev_decide", lambda: devkeys.decide(s, dev, bool(allow), guard if allow else None))


# what belongs to the OLD identity in relay.*: friends and their keys, what was shared, key changes under way
OLD_ID_BITS = ("friends", "posted", "audience", "audience_v", "rekey_pending", "rekey_inflight", "test_registered",
               "registered", "dev_request", "join_wait", "removed", "removed_by", "identity_gone", "blocked",
               "guard_salt")


def _drop_friend_files():
    """The friends' shared lists kept per game (<game>/friends/*.json) – they came under the old ID."""
    import games
    for key, *_ in games.GAMES:
        d = games.mine(key) / "friends"
        if d.is_dir():
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                except OSError:
                    log.info("Sync: new ID – a friend file stays (%s)", f.name)


def add_with_code(settings, guard, known=None):
    """The network part of sync_add_with_code (blocking): ONLY dev/add with the code (lead 09.11., A2) – this device joins,
    nobody is removed. A freshly restored device has no device list yet, and the sealed list can be written by anyone
    with the seed (legal 09.11.) – so it decides nothing here. A foreign device goes afterwards with ✕ in the list
    (the code needed, H1-6). known: unused (kept for older callers). -> {"gone": []}"""
    from net import devkeys, relay, vault
    if not devkeys.registered(settings):
        try:
            got = devkeys.register(settings, None, guard)
        except (vault.VaultError, relay.RelayError) as e:
            data = e.data or {}
            if e.status == 429 and data.get("retry_after"):   # Gordon 08.11.: too many wrong codes – the wait line
                raise vault.VaultError(429, str(e), dict(data, main_required=True)) from None
            if e.status == 403 or (e.status == 429 and data.get("cooldown_until")):
                # 403 {guard_wrong, main_required}: the code is wrong – nothing happened (older box: a decline's A3 wait)
                raise vault.VaultError(403, str(e), dict(data, main_required=True)) from None
            raise
        if got != "ok":   # older box (01e8440): a wrong code became an ordinary join request (pending)
            raise vault.VaultError(403, "wrong protection code", {"main_required": True})
    return {"gone": []}


def problem_text(err):
    from net.sync_ctl import problem_text as pt
    return pt(err)
