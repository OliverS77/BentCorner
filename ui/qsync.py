"""Settings → Your devices (test build only, collection/syncrun.available()): sync on/off, the sync row, coupling a
device – this PC shows the code, the phone enters it (lead 03.11.: entering on the desktop comes with rekey).
Texts with legal weight are legal's (03.11.2026); the logic is net/sync_ctl.py."""
import time

from system import contacts
from system.i18n import tr
from ui import textsafe


# legal's wording 07.11.2026 (the sync test's text went: the library is synced now, and with the coupling choice what you
# have isn't always kept – it may be set aside); the web says the same with "this device"
SYNC_WHAT = ("Your collection, decks, lists, binders, alerts, trade offers, friends and your profile are encrypted on this PC "
             "and synced through our server with your other devices. Only your devices can read them, we can't. If both "
             "devices already have data, you decide what counts before anything is synced. You can turn sync off at any "
             "time. All the details: Privacy policy, section 5a.")


# the device switch OFF (lead/legal 07.11., the web's wording word for word – „PC“ for „Handy“): only THIS device leaves
# the sync; the online backup is deleted only by „Back up data online“ OFF – except when this is the only device:
# with a protection code (or unclear) it asks, without a code it says so first (performance: sync_switch_plan)
LEAVE = ('This device leaves the sync. Your data on this device is deleted – a backup stays here for 30 days; '
         'your other devices and the online backup keep everything.')
ONLY_ASK = ("You're not coupled with any other device. Keep the online backup (e.g. for a new device with your "
            "protection code) or delete it?")
ONLY_183 = "Without sync it stays for 183 days, then we delete it."
ONLY_NOCODE = ("You're not coupled with any other device and have no protection code – the online backup will be "
               "deleted.")
KEEP_OFF, DEL_BACKUP, OFF_DELETE = "Keep and turn off", "Delete online backup", "Turn off and delete"
OFF_DELETED = "Online backup deleted. Sync is off on this PC – your data here stays."
OFF_FAILED = "No connection – nothing was deleted, sync is still on. Try again in a moment."


# A1 the pairing warning (legal 07.11. + the online backup, lead) – the phone shows it word for word
A1 = ("Only couple with your own devices. The new device sees your whole online backup and your friends, can share in "
      "your name and – without a protection code – remove your other devices, delete the online backup or delete "
      "everything.")


# coupling and syncing only in Full Orbit (Oliver/lead 07.11.; legal's wording, the web's dv_orbit_need / dv_orbit_go)
ORBIT_NEED = "Coupling is only available in Full Orbit – sync and the online backup are part of it."
ORBIT_GO = "Switch to Full Orbit"
# coupled, outside Full Orbit (lead; legal 07.11.: the 183 days must be visible – the backup isn't synced meanwhile)
ORBIT_PAUSED = ("Sync is paused until you're back in Full Orbit. Your online backup stays; if none of your devices "
                "accesses it for 183 days, it is deleted.")

# B5 (Oliver 07.11.): the box „Remove device“ (sign out all others) is gone – the ✕ in each row; A10 dropped
RM_KEY = "Remove device"
A3 = ("Picked up, but not by you? Remove that device right away with ✕ in the list above and contact "
      "{mail}.")   # legal 07.11. (B5: the ✕ in its row instead of the box „Remove device“)


# legal 07.11. (word for word with the web's dv_empty_ask): no "vault", the list as in the sync text
EMPTY_ASK = ("The online backup is empty. Back it up again from this device? Your collection, decks, lists, binders, price "
             "alerts, trade offers, friends and your profile then go into the online backup, encrypted, and your other "
             "devices get this state.")


def _ago(when):
    if not when:
        return tr("Not synced yet")
    m = int((time.time() - when) // 60)
    return tr("Last synced just now") if m < 1 else tr(f"Last synced {m} min ago")


# Einfach für Endnutzer (lead/Oliver 07.11., PLAN-EINFACH B): the list of devices on top, one „Add a device“, no
# sync switch and no „Sync now“ (the one switch is „Online backup and sync“ under Backup; a coupled device always syncs)
# – legal 07.11.: texts 1–12 approved
LIST_TITLE = "Your devices"
ME_LINE = "{name} – this device"
ADDED_LINE = "{name} – added on {date}"
PC_N = "PC {n}"
PHONE_N = "Phone {n}"


def default_name(kind, n):
    """B (Oliver/lead 12.11., the web alike): a device without its own name is „<type> <n>“ with the shared, unique
    number (DEVICE-KEYS §5) – „PC 2“, „Handy 1“ – never „Gerät n“ (kind unknown counts as PC, like the web)."""
    n = n or "?"
    return tr(PHONE_N).format(n=n) if str(kind or "").lower() == "phone" else tr(PC_N).format(n=n)
NO_OTHERS = "No other devices"
RENAME, SAVE = "Rename", "Save"
SIGN_OUT = "Sign out this device"
RM_CHECKING = "Checking the device list …"   # box run 12.11.: right after adding, the list lags a moment
SIGN_OUT_ASK = ('Sign out this device? It no longer syncs, and your data on this device is deleted – a backup stays '
                'here for 30 days. Your other devices and the online backup keep everything.')
SIGNING_OUT = "Signing out …"
ADD_TITLE = "Add a device"
ADD_HOW = ("Show a code on one device and enter it on the other – on the PC or in the Bent°Corner web app. Any device "
           "can do both.")
SHOW_CODE, ENTER_CODE = "Show a code", "Enter a code"
NEED_BACKUP = "Your devices sync through the online backup – turn on “Online backup and sync” under Backup."
TO_BACKUP = "Go to Backup"
OS_NAMES = {"windows": "Windows", "linux": "Linux", "mac": "macOS", "web": "Web app"}
# B5 – removing one device (Oliver 07.11.: ✕ on hover; with a protection code the field, without it „Remove? [Yes] [No]“;
# performance' sync_remove_plan / sync_remove) – legal 07.11. (plan-einfach.md: A8 and the B5 lines)
RM_ASK1 = ('Remove {name}? It no longer syncs afterwards; your other devices automatically get a new key. Your '
           "friends get a message to accept, your online backup stays. Once it's online again, Bent°Corner "
           'deletes your data there; a backup of it stays on the device for another 30 days. If it never goes '
           "online again, everything stays there – we can't delete it.")
RM_WITH = "Removed with it: {names}"   # legal A8 „Mit entfernt: …“ – only when it added devices itself, before the question
RM_YES, RM_NO = "Yes", "No"
RM_BUSY1 = "Removing {name} …"
RM_DONE1 = "{name} is removed. Your other devices get the new key automatically."   # legal: they fetch it on their next run
RM_CONFLICT = "The list of devices has just changed – look again and try once more."
RM_X = "Remove {name}"   # the ✕'s tooltip
# the join request (a device restored from a backup file without a code, 14 days – performance' sync_join_request_*);
# legal: the G2-like warning – allowing gives full access
REQ_JOIN = ("A device wants to join your devices (from a backup file). If you allow it, it gets access to your online "
            "backup and your friends – as if it were you. Without an answer it joins on {date}. If you don't recognise "
            "it, decline.")
REQ_JOIN_TITLE = "New device"
REQ_DECLINE, REQ_ALLOW = "Decline", "Allow now"
JOIN_WAIT = ("This device wants to join your devices. It joins on {date} if none of your devices declines – or allow it "
             "right away on one of your other devices.")
JOIN_DECLINED = "One of your devices declined. This device doesn't sync; your data here stays."
JOIN_DECLINED_UNTIL = ("One of your devices declined. This device doesn't sync; your data here stays. You can ask again "
                       "from {date}.")   # legal 08.11. (A3: 7 days, the date from the server)
NAME_THIS = "Name of this device"   # legal 07.11. – asked on the NEW device when adding (Oliver 07.11.)


def name_items(ui, b, refresh):
    """The name, given on the joining device right after its code was accepted (performance' join_n, sync_join_name):
    prefilled „Device N“ (empty with the placeholder when the number isn't known), [Save] once – then the list."""
    ctrl = b.ctrl
    st = getattr(ctrl, "sync_status", None) or {}
    mem = b.__dict__.setdefault("devices_name", {})
    if st.get("join") not in ("busy", "ok", "choice"):
        mem.clear()   # the join is over: the next one (the same PC again) asks again
        return []
    if mem.get("done") or not hasattr(ctrl, "sync_join_name"):
        return []
    n = int(st.get("join_n") or 0)
    if not mem.get("edited"):   # the proposal follows join_n (it comes after the first drawing) until the user types
        from system import nicknames   # Oliver/lead 12.11.: the proposal is this device's nickname
        nick = ctrl.sync_my_nick() if hasattr(ctrl, "sync_my_nick") else None
        mem["typed"] = nicknames.render(nick, nicknames.lang()) if nick else (default_name("pc", n) if n else "")
    typed = mem["typed"]

    def keep(v):
        mem["typed"] = v
        mem["edited"] = True

    def save():
        ctrl.sync_join_name(mem.get("typed", ""))
        mem.clear()
        mem["done"] = True
        refresh()
    return [ui.label(f"<b>{tr(NAME_THIS)}</b>", rich=True),
            ui.row([ui.edit(typed, keep, key="devname_join", live=keep, placeholder=tr("Device"), enter=lambda _t: save()),
                    ui.button(tr(SAVE), save, primary=True), ui.stretch()])]


def _day(ms):
    return time.strftime("%d.%m.%Y", time.localtime(int(ms) / 1000))


def device_name(d):
    """The name in the list: the device's own, else its nickname (Oliver/lead 12.11.: „Großer Mutiger Fuchs“ – its own
    or the fallback from its id), else „PC N“ / „Handy N“ – shown only as plain text (textsafe, review low)."""
    from system import nicknames
    return textsafe.name(d.get("name") or nicknames.name_of(d) or default_name(d.get("kind"), d.get("n")))


def _devices(ctrl):
    try:
        return list(ctrl.sync_devices() if hasattr(ctrl, "sync_devices") else ctrl.sync_engine.devices())
    except Exception:  # noqa: BLE001 – the list is never worth an error
        return []


def list_items(ui, b, refresh, on):
    """The devices: „<name> – this device“ / „<name> – added on <date>“, platform · version in grey, [Rename]; this
    device's row with [Sign out this device] while it syncs."""
    import html
    ctrl = b.ctrl
    mem = b.__dict__.setdefault("devices_list", {})   # "edit": the device being renamed, "typed"
    devs = _devices(ctrl)
    if not devs:   # not coupled yet: only this device, from the settings
        nick = ctrl.sync_my_nick() if hasattr(ctrl, "sync_my_nick") else None   # its nickname already (lead 12.11.)
        devs = [{"dev": "", "name": (getattr(ctrl, "settings", None) or {}).get("device_name"), "n": 1, "me": True,
                 "nick": nick}]
    out = []
    for d in devs:
        name = html.escape(device_name(d))
        line = (tr(ME_LINE).format(name=f"<b>{name}</b>") if d.get("me") else
                tr(ADDED_LINE).format(name=f"<b>{name}</b>", date=_day(d["added"])) if d.get("added") else f"<b>{name}</b>")
        sub = " · ".join(x for x in (tr(OS_NAMES.get(d.get("os") or "", d.get("os") or "")), d.get("ver") or "") if x)
        key = d.get("dev") or "me"
        if mem.get("edit") == key:
            typed = mem.setdefault("typed", d.get("name") or "")

            def keep(v):
                mem["typed"] = v

            def save(dd=d):
                ctrl.device_rename(mem.get("typed", ""), dev=None if dd.get("me") else dd.get("dev"))
                mem.clear()
                refresh()

            def stop():
                mem.clear()
                refresh()
            out.append(ui.row([ui.edit(typed, keep, key=f"devname_{key}", live=keep,
                                       placeholder=device_name(dict(d, name=None)),
                                       enter=lambda _t, s=save: s()),
                               ui.button(tr(SAVE), save, primary=True), ui.button(tr("Cancel"), stop), ui.stretch()]))
            continue

        def edit(k=key):
            mem.clear()
            mem["edit"] = k
            refresh()
        keys = [ui.button(tr(RENAME), edit)]
        rm = b.__dict__.get("devices_rm") or {}
        # the ✕ in every other device's row – also while its question is open, so all keys stay aligned (lead 07.11.)
        if not d.get("me") and on and hasattr(ctrl, "sync_remove_plan"):
            def ask_rm(dd=d):
                plan = ctrl.sync_remove_plan(dd.get("dev"))
                b.__dict__["devices_rm"] = {"dev": dd.get("dev"), "plan": plan, "name": device_name(dd)}
                if (b.__dict__.get("devices_off") or {}).get("ask"):   # one question at a time
                    b.__dict__.pop("devices_off", None)
                ctrl.sync_status.pop("remove", None)
                ctrl.sync_status.pop("delete_guard", None)
                refresh()
            # U4 (lead 11.11.): always visible – hover-only it was missed, and the wide „Sign out“ key sat where the ✕
            # of the other rows is (Oliver's test round: a sign-out where he meant a removal)
            keys.append(ui.button("✕", ask_rm, tip=tr(RM_X).format(name=device_name(d))))
        if d.get("me") and on:   # U4: this device's ✕ = „Sign out this device“, asked right under its row
            def sign_out():
                plan = ctrl.sync_leave_plan() if hasattr(ctrl, "sync_leave_plan") else "leave"
                b.__dict__["devices_off"] = {"ask": plan}
                b.__dict__.pop("devices_rm", None)   # one question at a time
                refresh()
            keys.append(ui.button("✕", sign_out, tip=tr(SIGN_OUT)))
        # U3 (lead 11.11.): [Rename] [✕] in every row – the same keys, so „Rename“ is always at the same place
        out.append(ui.row([ui.label(line + (f"<br><span style='color:gray'>{html.escape(sub)}</span>" if sub else ""),
                                    rich=True), ui.stretch()] + keys))
        if rm.get("dev") and rm.get("dev") == d.get("dev"):
            out += _remove_items(ui, b, refresh)
        if d.get("me"):
            out += _leave_items(ui, b, refresh)
    if len(devs) <= 1:
        out.append(ui.note(tr(NO_OTHERS)))
    return out


def _leave_items(ui, b, refresh):
    """„Sign out this device“ asked as a line (no pop-up), then how it went (performance: sync_leave_plan/sync_leave)."""
    ctrl, st = b.ctrl, b.ctrl.sync_status
    off = b.__dict__.setdefault("devices_off", {})   # "ask": the plan asked; "sent"

    def go(delete=None, code=None):
        def f():
            off.clear()
            off["sent"] = True
            if code:
                ctrl.sync_leave(delete=delete, guard=code)
            else:
                ctrl.sync_leave(delete=delete)
            refresh()
        return f

    def cancel():
        off.clear()
        st.pop("switch_off", None)
        refresh()
    ask = off.get("ask")
    if ask == "leave":
        return [ui.label(tr(SIGN_OUT_ASK)),
                ui.row([ui.button(tr(SIGN_OUT), go()), ui.button(tr("Cancel"), cancel), ui.stretch()])]
    if ask == "ask":   # the last device, with a protection code (or unclear): keep or delete – equal keys
        return [ui.note(tr(ONLY_ASK)), ui.note(tr(ONLY_183)),
                ui.row([ui.button(tr(KEEP_OFF), go(False)), ui.button(tr(DEL_BACKUP), go(True)), ui.stretch()]),
                ui.row([ui.button(tr("Cancel"), cancel), ui.stretch()])]
    if ask == "delete":   # the last device, no protection code: it says so before anything happens
        return [ui.note(tr(ONLY_NOCODE)),
                ui.row([ui.button(tr(OFF_DELETE), go(True)), ui.button(tr("Cancel"), cancel), ui.stretch()])]
    if not off.get("sent"):
        return []
    if st.get("delete_guard") in ("need", "wrong", "wait") and not st.get("busy"):
        from ui import backupui   # a protection code is set: asked before deleting (legal A4) – never an error line

        def guard_cancel():
            st.pop("delete_guard", None)
            off.clear()
            refresh()
        return backupui.guard_items(ui, st["delete_guard"], st.get("guard_wait"),
                                    b.__dict__.setdefault("devices_guard", {}), DEL_BACKUP,
                                    lambda code: go(True, code)(), guard_cancel, getattr(b, "form", None))
    if st.get("busy"):
        return [ui.label(tr(SIGNING_OUT))]
    if st.get("left"):
        from ui import joinui   # signed out: no code left in any field, „Add a device“ closed (lead 08.11.)
        b.__dict__.pop("devices_add", None)
        joinui._ui_state(b).pop("code", None)
        return [ui.note(tr(LEAVE))]
    if st.get("deleted") is not None:
        return [ui.label(tr(OFF_DELETED) if st.get("deleted") else tr(OFF_FAILED))]
    return []


def _add_items(ui, b, refresh, orbit_ok, backup_on):
    """One „Add a device“ (PLAN-EINFACH B): [Show a code] [Enter a code] – the same on every device. Outside Full Orbit
    or without the online backup: the same place, dimmed keys and the way there."""
    ctrl = b.ctrl
    mem = b.__dict__.setdefault("devices_add", {})   # "mode": "show" | "enter"
    dim = ui.row([ui.button(tr(SHOW_CODE), lambda: None, enabled=False),
                  ui.button(tr(ENTER_CODE), lambda: None, enabled=False), ui.stretch()])
    if not orbit_ok:
        def to_orbit():
            ctrl.stream.show_page("settings", back=True)
            ctrl.show_settings("privacy")   # the Orbit slider (the veil's "Change level" goes there too)
        from ui import backupui   # the same key as on Backup (lead 07.11.: one wording)
        return [ui.note(tr(ORBIT_NEED)), dim, ui.row([ui.button(tr(backupui.ORBIT_SETTINGS), to_orbit), ui.stretch()])]
    # without the online backup only [Show a code] waits for it – [Enter a code] always works: joining switches the sync
    # on and takes the other device's backup (ports/lead 07.11.: a fresh device never sets up its own first)
    from ui import joinui
    mode = mem.get("mode")
    if not backup_on and mode in ("show", "setup"):
        mode = mem["mode"] = None
    if mode == "setup":   # [Set up protection code] under the list (no code yet): the offer in place of the two keys
        return _setup_items(ui, b, refresh, mem)
    fetched = bool((getattr(ctrl, "pair", None) or {}).get("fetched"))
    if mode == "show" and fetched:   # picked up (lead 07.11.): the box back to its two keys – the list above shows the device
        mode = mem["mode"] = None
    sst = getattr(ctrl, "sync_status", None) or {}
    if mode == "enter" and (sst.get("join") in ("ok", "choice") or sst.get("left")):
        # joined (or signed out): closed – no code left in its field (lead 08.11.)
        mode = mem["mode"] = None
        joinui._ui_state(b).pop("code", None)

    def pick(m):
        def f():
            if mem.get("mode") == "enter" and m != "enter":
                joinui._cam_off(ctrl)
            mem["mode"] = None if mem.get("mode") == m else m   # a second click folds it again
            if mem["mode"] == "enter":   # signed out earlier, joining again: the „leaves the sync“ line is over –
                sst.pop("left", None)    # otherwise it closes the field at once (performance' guide run 09.11.)
            pr = getattr(ctrl, "pair", None) or {}
            if mem["mode"] == "show" and (pr.get("fetched") or not (pr.get("code") and ctrl.pair_left()))                     and not pr.get("busy"):
                ctrl.pair_show()   # „Show a code“ shows one at once – the first time too (performance' guide run)
            refresh()
        return f
    # lead 11.11. (Oliver's step 2, too much text): while this device joins (Enter a code, no backup of its own yet) the
    # dimmed [Show a code] and the „turn on the backup“ hint stay away – they belong to the other way round
    joining = mode == "enter" and not backup_on
    keys = [ui.button(tr(ENTER_CODE), pick("enter"), active=True, enabled=hasattr(ctrl, "sync_join_code"))] if joining         else [ui.button(tr(SHOW_CODE), pick("show"), active=mode == "show", enabled=backup_on),
              ui.button(tr(ENTER_CODE), pick("enter"), active=mode == "enter", enabled=hasattr(ctrl, "sync_join_code"))]
    out = [ui.note(tr(ADD_HOW)), ui.row(keys + [ui.stretch()])]
    if not backup_on and not joining:
        out += [ui.note(tr(NEED_BACKUP)),
                ui.row([ui.button(tr(TO_BACKUP), lambda: ctrl.show_settings("backup")), ui.stretch()])]
    if mode == "show":
        out += _couple(ui, ctrl)
    elif mode == "enter":
        out += joinui.join_items(ui, b, refresh)
    return out


def _setup_items(ui, b, refresh, mem):
    """[Set up protection code] from the line under the list (Oliver 13.11.: a code is voluntary, also with several
    devices): the known offer – generate / own, never „without code“ here – then back to the two keys."""
    from ui import backupui
    ctrl = b.ctrl

    def close():
        mem.clear()
        refresh()
    st = mem.setdefault("rescue", {"second": True})
    return backupui.rescue_items(ui, ctrl, st, refresh, on_back=close, on_done=close, form=getattr(b, "form", None))


def no_code_items(ui, b, refresh, on):
    """legal 13.11. (1f): with other devices and no protection code – a quiet line under the list, [Set up protection
    code]. No pop-up, no must."""
    ctrl = b.ctrl
    if not on or getattr(ctrl, "guard_on", lambda: True)() or not getattr(ctrl, "sync_has_others", lambda: False)():
        return []
    from ui import backupui
    mem = b.__dict__.setdefault("devices_add", {})

    def setup():
        mem.clear()
        mem["mode"] = "setup"
        refresh()
    return [ui.note(tr(backupui.NO_CODE_HINT)),
            ui.row([ui.button(tr(backupui.ADD_SET_UP), setup, enabled=mem.get("mode") != "setup"), ui.stretch()])]


# ---------- „A protection code was set up on {device}.“ (Oliver 13.11. via Gordon; performance' guard_set_by) ----------
CODE_SET = "A protection code was set up on {device}."   # legal 13.11. (EN + DE)


def code_set_unseen(ctrl):
    """Another device set the FIRST protection code and this device hasn't shown it yet: Settings at the top +
    „Your devices“ pulse quietly, as with a join request (no new effect)."""
    return bool((getattr(ctrl, "sync_status", None) or {}).get("guard_set_by"))


def code_set_items(ui, b):
    """The line once, above the list. Drawn = remembered for this run of the app (b's memory), then performance'
    code_set_seen(key) notes it for good (qsettings._build) – after a restart it's gone."""
    by = (getattr(b.ctrl, "sync_status", None) or {}).get("guard_set_by")
    if isinstance(by, dict):
        name = str(by.get("name") or "") or tr("Device {n}").format(n=by.get("n") or "?")   # performance: name empty
        b.__dict__["code_set_line"] = (tr(CODE_SET).replace("{device}", textsafe.name(name)), by.get("key"))
    line = b.__dict__.get("code_set_line")
    return [ui.label(line[0], bold=True)] if line else []


def code_set_seen(ctrl, b):
    """„Your devices“ drawn with the line: performance stores sync_code_seen and clears guard_set_by."""
    line = b.__dict__.get("code_set_line")
    if line and code_set_unseen(ctrl) and hasattr(ctrl, "code_set_seen"):
        ctrl.code_set_seen(line[1])
        if hasattr(ctrl, "autobackup_badge"):
            ctrl.autobackup_badge()


def page(ui, b):
    ctrl = b.ctrl
    eng = getattr(ctrl, "sync_engine", None)
    if eng is None:
        return ui.col([ui.note(tr("Not available in this version."))])
    st = ctrl.sync_status
    on = eng.on()
    orbit_ok = getattr(ctrl, "sync_orbit_ok", lambda: True)()   # performance: pairing and syncing only in Full Orbit
    backup_on = (getattr(ctrl, "settings", None) or {}).get("sync_backup") is True
    refresh = b.form.refresh

    gate = gate_items(ui, ctrl, b.__dict__.setdefault("devices_gate", {}), refresh, getattr(b, "form", None))
    items = gate + join_wait_items(ui, ctrl) + name_items(ui, b, refresh) + code_set_items(ui, b) \
        + list_items(ui, b, refresh, on) + no_code_items(ui, b, refresh, on)
    if (getattr(ctrl, "pair", None) or {}).get("fetched"):   # legal A3 after a pickup (B5: the ✕ in the list above)
        items.append(ui.note(tr(A3).format(mail=contacts.MAIL)))
    if on and st.get("emptied") and not eng.meta.get("empty_not_now"):
        # SYNC-PLAN §6: never silently – the user decides; both answers equal (legal 06.11.)
        items += [ui.note(tr(EMPTY_ASK)),
                  ui.row([ui.button(tr("Back it up again"), ctrl.sync_restore),
                          ui.button(tr("Not now"), ctrl.sync_not_now), ui.stretch()])]
    elif on and st.get("emptied"):   # "Not now": only the quiet line stays (no asking at every run)
        items.append(ui.row([ui.label(tr("The online backup is empty.")), ui.stretch(),
                             ui.button(tr("Back it up again"), ctrl.sync_restore)]))
    elif on and not orbit_ok:   # coupled, but not in Full Orbit: paused – nothing sent or deleted, the coupling stays
        items.append(ui.note(tr(ORBIT_PAUSED)))
    elif on and not gate and (st.get("busy") or st.get("text")):   # no „Sync now“ – the clock runs by itself
        items.append(ui.label(tr("Syncing …") if st.get("busy") else st["text"], color="gray"))
    elif not on and eng.meta.get("deleted_off"):   # deleted on another device (legal 06.11.)
        from net import sync_ctl
        items.append(ui.note(sync_ctl.DELETED_TEXT()))
    from ui import joinui   # both devices have data / set aside (lead 07.11., legal's wording)
    notice = joinui.status_items(ui, b, refresh) + joinui.notice_items(ui, b, refresh)   # signed out, removed identity, set aside
    framed = []
    if on:   # a new protection code requested (legal A5): big on every device, [Decline] here too – its own frame
        from ui import backupui
        framed = backupui.notice_group(ui, ctrl, b.__dict__.setdefault("devices_notice", {}), refresh,
                                       getattr(b, "form", None))
    from ui import expiryui   # the online backup's expiry (legal 07.11.): its own frame at the top while it applies
    foreign = foreign_group(ui, b, refresh)
    if st.get("foreign_device"):   # not signed in yet (another device has this ID): only that frame – no list, no
        return ui.col(gate + foreign, spacing=12)   # „Add a device“, no sign-out until it's resolved (lead 08.11.)
    framed = expiryui.items(ui, ctrl) + foreign + join_request_group(ui, b, refresh) + framed
    groups = framed + [ui.group(tr(LIST_TITLE), notice + items)]
    choice = joinui.choice_items(ui, ctrl, refresh, b.__dict__.setdefault("devices_choice", {}))
    if choice:   # both devices have data: the comparison in place of „Add a device“
        groups.append(ui.group(tr("Both devices have data"), choice))
    else:
        groups.append(ui.group(tr(ADD_TITLE), _add_items(ui, b, refresh, orbit_ok, backup_on or on)))
    aside = joinui.aside_items(ui, b, refresh)
    if aside:
        groups.append(ui.group(tr("Set aside"), aside))
    return ui.col(groups, spacing=12)


def gate_missing(ctrl):
    """Test builds only: the test server's access code isn't typed in (performance: sync_status["gate"])."""
    return (getattr(ctrl, "sync_status", None) or {}).get("gate") == "missing"


def gate_items(ui, ctrl, mem, refresh, form=None):
    """The access code missing (T2 07.11.: Test-PC 2 after a restart never reached the server, yet said „Coupled ✓“):
    the line and a password field right here – no dialog. Read once, the page memory and the form's draft emptied at
    once; the code only in the call. mem: the page's RAM dict."""
    if not gate_missing(ctrl) or not hasattr(ctrl, "sync_gate"):
        return []
    st = getattr(ctrl, "sync_status", None) or {}

    def typed(v):
        mem["code"] = v

    def go():
        code = (mem.pop("code", "") or "").strip()
        if form is not None and hasattr(form, "forget"):
            form.forget("gate_code")
        if code:
            mem["sent"] = True
            ctrl.sync_gate(code)
        refresh()
    out = [ui.label(tr("The test server needs its access code."), bold=True),
           ui.row([ui.edit("", typed, key="gate_code", live=typed, secret=True, enter=lambda _t: go()), ui.button(tr("Enter access code"), go,
                                                                                          primary=True)])]
    if st.get("busy") and mem.get("sent"):
        out.append(ui.note(tr("Syncing …")))
    elif mem.get("sent") and st.get("text"):
        out.append(ui.label(st["text"], color="gray"))
    return out


TYPE_THERE = "Type this code on your other device under “Enter a code”."   # the web's line (ports 11.11.)


def _couple(ui, ctrl):
    p = getattr(ctrl, "pair", None) or {}
    out = [ui.note(tr("Show a code here and enter it on your phone in the Bent°Corner web app – then both stay in "
                      "sync."))]
    if p.get("fetched"):   # picked up: the box goes back to its keys (_add_items); A3 stands under the list
        return out
    left = ctrl.pair_left()
    if p.get("busy"):   # it syncs first (T2 07.11.), then the code – the joining device then sees this one's data
        out.append(ui.label(tr("This device syncs first – then the code comes …")))
    elif p.get("code") and left:
        img = f"image://cards/{p['img']}" + ("" if p.get("shown") else "_blur")
        if p.get("turn"):   # the sphere (PAIRING §2: the main way – the phone's camera reads it while it turns)
            from ui import sphere
            ball = (ui.frames(p["img"] + "_s", p["turn"], 300, 300, sphere.FPS) if p.get("shown")
                    else ui.image(f"image://cards/{p['img']}_sblur", 300, 300))
            out += [ui.row([ball, ui.stretch()]),
                    ui.note(tr("Point your phone's camera at the turning sphere – or type the code below."))]
        else:   # lead/ports 11.11.: no sphere (SPHERE off) – the web's sentence in its place
            out.append(ui.note(tr(TYPE_THERE)))
        out += [ui.row([ui.image(img, 280, 60), ui.stretch()]),
                ui.row([ui.button(tr("Hide") if p.get("shown") else tr("Show"), ctrl.pair_toggle),
                        ui.button(tr("Copy"), ctrl.pair_copy),
                        ui.label(tr(f"Valid for {left // 60}:{left % 60:02d}")), ui.stretch()]),
                ui.note(tr("Enter this code only on your own devices – don't show or send it to anyone. It works for "
                           "10 minutes and only once.")),
                ui.label(tr(A1), bold=True)]   # legal A1: bold, in the content
    else:
        if p.get("error"):
            out.append(ui.label(p["error"]))
        elif p.get("until"):
            out.append(ui.label(tr("The code has expired – make a new one.")))
        out.append(ui.row([ui.button(tr("Show a code for a new device"), ctrl.pair_show), ui.stretch()]))
    return out


def _remove_items(ui, b, refresh):
    """Under the device's row (B5, no pop-up): legal's A8 with „Removed with it: …“ when it added devices itself; with a
    protection code its field (A4), without „[Yes] [No]“ (Oliver); then busy / done / the list changed / an error."""
    ctrl, st = b.ctrl, b.ctrl.sync_status
    rm = b.__dict__.get("devices_rm") or {}
    plan = rm.get("plan")
    if plan is None and not rm.get("sent") and rm.get("dev") and hasattr(ctrl, "sync_remove_plan"):
        # the list was older when ✕ was pressed (its refresh is under way): ask again on every draw – before, the
        # empty answer stayed and ✕ said „not in the list any more“ for a device just added (box run 12.11.)
        plan = rm["plan"] = ctrl.sync_remove_plan(rm["dev"])
    name = textsafe.name(rm.get("name") or "")

    def close():
        b.__dict__.pop("devices_rm", None)
        st.pop("delete_guard", None)
        refresh()

    def go(code=None):
        if code:
            ctrl.sync_remove(rm["dev"], guard=code)
        else:
            ctrl.sync_remove(rm["dev"])
        rm["sent"] = True
        refresh()
    state = st.get("remove")
    if rm.get("sent") and state == "busy":
        return [ui.label(tr(RM_BUSY1).format(name=name))]
    if rm.get("sent") and state == "ok":
        return [ui.row([ui.label(tr(RM_DONE1).format(name=name)), ui.stretch(), ui.button(tr("OK"), close)])]
    if rm.get("sent") and state == "conflict":
        return [ui.row([ui.label(tr(RM_CONFLICT)), ui.stretch(), ui.button(tr("OK"), close)])]
    if rm.get("sent") and state == "error":
        return [ui.row([ui.label(st.get("text") or tr("That didn't work – try again later.")), ui.stretch(),
                        ui.button(tr("OK"), close)])]
    if not plan:   # not in the registry (yet): nothing to remove
        if getattr(ctrl, "sync_remove_checking", lambda: False)():   # just added: the lists are being fetched
            return [ui.row([ui.label(tr(RM_CHECKING)), ui.stretch(), ui.button(tr("Cancel"), close)])]
        return [ui.row([ui.label(tr("This device isn't in the list any more.")), ui.stretch(), ui.button(tr("OK"), close)])]
    others = [device_name(w) for w in plan.get("with") or []]   # legal: before the question
    out = [ui.label(f"<b>{tr(RM_WITH).format(names=', '.join(others))}</b>", rich=True)] if others else []
    out.append(ui.label(tr(RM_ASK1).format(name=name)))
    guard = st.get("delete_guard")
    if plan.get("guard") or guard in ("need", "wrong", "wait"):
        from ui import backupui   # legal A4: the field, never an error line; the code stays in the call only
        state = guard if guard in ("wrong", "wait") else "need"
        out += backupui.guard_items(ui, state, st.get("guard_wait"), b.__dict__.setdefault("devices_rm_code", {}),
                                    RM_KEY, go, close, getattr(b, "form", None),
                                    on_lost=lambda: (close(), backupui.open_request(ctrl)))
        return out
    out.append(ui.row([ui.button(tr(RM_YES), lambda: go()), ui.button(tr(RM_NO), close), ui.stretch()]))   # equal
    return out


# another device is signed in with this ID that isn't in the list (legal 08.11., via performance; lead go): its own
# frame at the top; with a protection code the way to take it over (B5 removal), always the way to a new ID
FOREIGN_HEAD = ("Another device is already signed in with your ID that you don't see here. If it's yours (e.g. an old "
                "phone or another browser), allow this device there.")
FOREIGN_NOCODE = ("If you don't recognise it, someone may have a copy of your backup file. Then create a new ID: your data "
                  "here stays, but your friends have to add you again. Tell them to remove your old ID – the other device "
                  "can keep using it.")
# with a protection code (lead 09.11., ports' find): the code ADDS this device only (dev/add) – nobody is removed; foreign
# devices go afterwards with ✕ in the list (legal 09.11.)
FOREIGN_HEAD_CODE = ("Your ID is already used on other devices. If they're yours, sign this device in with your protection "
                     "code.")
FOREIGN_CODE = ("With your protection code you sign this device in; your other devices stay. Then check the list of your "
                "devices: if you don't recognise one, remove it with ✕ – your ID, your friends and your online backup stay "
                "with you.")
FOREIGN_OR_NEW = "Or create a new ID; then your friends have to add you again."
NEW_ID, TAKE_OVER = "Create new ID", "Sign in with protection code"   # legal 09.11.
NEW_ID_ASK = "Really create a new ID?"   # legal 08.11. (the second step as a line – friends have to add you again)
TAKE_BUSY = "Signing this device in …"   # legal 09.11.
TAKE_DONE = "This device is signed in. Check the list of your devices – if you don't recognise one, remove it with ✕."   # legal 09.11.


def foreign_group(ui, b, refresh):
    """„Another device with your ID“ (performance' sync_status["foreign_device"], desk-thief): legal's text without or
    with a protection code. [Take over with protection code] → legal's sentence stays, the A4 code field, then
    ctrl.sync_add_with_code(code) (sync_status["add_code"] busy | ok | wrong | wait | error – only dev/add, nobody is
    removed, lead 09.11.); [Create new ID] asks once
    more as a line, then ctrl.identity_new() (local, at once)."""
    ctrl = b.ctrl
    st = getattr(ctrl, "sync_status", None) or {}
    mem = b.__dict__.setdefault("devices_foreign", {})   # "ask_new" | "take" (+ "sent")
    to = st.get("add_code")
    if mem.get("sent") and to == "ok":   # done: the frame goes with the next sync, the line says it once
        return [ui.group(tr("Your ID"), [ui.row([ui.label(tr(TAKE_DONE)), ui.stretch(),
                                                ui.button(tr("OK"), lambda: (mem.clear(), st.pop("add_code", None),
                                                                            refresh()))])])]
    fd = st.get("foreign_device")
    if not fd:
        return []
    guarded = bool(getattr(ctrl, "guard_on", lambda: False)())
    can_take = guarded and hasattr(ctrl, "sync_add_with_code")

    def new_id():
        mem.clear()
        ctrl.identity_new()
        refresh()

    def back():
        mem.clear()
        st.pop("add_code", None)
        refresh()

    def take(code):
        mem["sent"] = True
        ctrl.sync_add_with_code(code)
        refresh()
    out = [ui.label(tr(FOREIGN_HEAD_CODE if can_take else FOREIGN_HEAD), bold=True)]
    out.append(ui.note(tr(FOREIGN_CODE if can_take else FOREIGN_NOCODE)))
    if mem.get("take"):   # legal's sentence above is the question; the code field, never an error line (A4)
        if mem.get("sent") and to == "busy":
            out.append(ui.label(tr(TAKE_BUSY)))
        elif mem.get("sent") and to == "error":
            out += [ui.label(st.get("text") or tr("That didn't work – try again later.")),
                    ui.row([ui.button(tr("Back"), back), ui.stretch()])]
        else:
            from ui import backupui
            state = to if mem.get("sent") and to in ("wrong", "wait") else "need"
            out += backupui.guard_items(ui, state, st.get("guard_wait"), b.__dict__.setdefault("devices_take_code", {}),
                                        TAKE_OVER, take, back, getattr(b, "form", None),
                                        on_lost=lambda: (back(), backupui.open_request(ctrl)))
        return [ui.group(tr("Your ID"), out)]
    if mem.get("ask_new"):
        out.append(ui.row([ui.label(tr(NEW_ID_ASK), fixed=True), ui.button(tr("Yes"), new_id),
                           ui.button(tr("Back"), back), ui.stretch()]))
        return [ui.group(tr("Your ID"), out)]
    ask = lambda: (mem.update(ask_new=True), refresh())   # noqa: E731
    if can_take:
        out += [ui.row([ui.button(tr(TAKE_OVER), lambda: (mem.update(take=True), refresh())), ui.stretch()]),
                ui.row([ui.label(tr(FOREIGN_OR_NEW)), ui.button(tr(NEW_ID), ask), ui.stretch()])]
    else:
        out.append(ui.row([ui.button(tr(NEW_ID), ask), ui.stretch()]))
    return [ui.group(tr("Your ID"), out)]


def join_request_group(ui, b, refresh):
    """Another device restored from a backup file wants in (B5, 14 days): its own frame at the top of „Your devices“,
    open like the code request – [Decline] [Allow now]; allowing needs the protection code if one is set."""
    ctrl = b.ctrl
    reqs = ctrl.sync_join_request_info() if hasattr(ctrl, "sync_join_request_info") else None
    if not reqs:
        return []
    st = ctrl.sync_status
    mem = b.__dict__.setdefault("devices_req", {})   # "allow": the request asked for its code
    out = []
    for r in reqs:
        dev = r.get("dev") or r.get("dev_id")
        out.append(ui.label(tr(REQ_JOIN).format(date=_day(int(r.get("until") or 0) * 1000 if int(r.get("until") or 0) < 10**11
                                                         else r.get("until"))), bold=True))
        if mem.get("allow") == dev and (st.get("delete_guard") in ("need", "wrong", "wait")):
            from ui import backupui

            def cancel():
                mem.clear()
                st.pop("delete_guard", None)
                refresh()
            out += backupui.guard_items(ui, st["delete_guard"], st.get("guard_wait"), b.__dict__.setdefault("devices_req_code", {}),
                                        REQ_ALLOW, lambda code, d=dev: ctrl.sync_join_request_answer(d, True, guard=code),
                                        cancel, getattr(b, "form", None))
            continue

        def answer(allow, d=dev):
            def f():
                mem.clear()
                if allow:
                    mem["allow"] = d
                ctrl.sync_join_request_answer(d, allow)
                refresh()
            return f
        out.append(ui.row([ui.button(tr(REQ_DECLINE), answer(False)), ui.button(tr(REQ_ALLOW), answer(True)), ui.stretch()]))
    return [ui.group(tr(REQ_JOIN_TITLE), out)]


DEVKEY_UNREADABLE = ("This device's key file can't be read right now – perhaps a virus scanner or OneDrive is "
                     "holding it. Nothing was changed; Bent°Corner tries again by itself.")


def join_wait_items(ui, ctrl):
    """On the device that asked to join: when it joins, or that it was declined. Also: this device's key file can't
    be read (M3, lead 08.11.) – it is never replaced, but the page says so."""
    st = getattr(ctrl, "sync_status", None) or {}
    out = [ui.label(tr(DEVKEY_UNREADABLE), bold=True)] if st.get("devkey_unreadable") else []
    w = st.get("join_wait")
    if not w:
        return out
    return out + _join_wait_line(ui, w)


def _join_wait_line(ui, w):
    if w.get("declined"):
        until = int(w.get("cooldown_until") or 0)   # A3 (Gordon, legal 08.11.): the server's date, never counted here
        if until:
            return [ui.label(tr(JOIN_DECLINED_UNTIL).format(date=_day(until * 1000 if until < 10**11 else until)), bold=True)]
        return [ui.label(tr(JOIN_DECLINED), bold=True)]
    until = int(w.get("until") or 0)
    return [ui.label(tr(JOIN_WAIT).format(date=_day(until * 1000 if until < 10**11 else until)), bold=True)]


def join_request_unseen(ctrl):
    """A join request not seen on this device yet: Settings at the top + „Your devices“ pulse (lead 07.11.)."""
    reqs = ctrl.sync_join_request_info() if hasattr(ctrl, "sync_join_request_info") else None
    if not reqs:
        return False
    seen = (getattr(ctrl, "settings", None) or {}).get("join_req_seen") or []
    return any(f"{r.get('dev') or r.get('dev_id')}:{r.get('until')}" not in seen for r in reqs)


def join_request_seen(ctrl):
    """„Your devices“ opened: the pulse stops for these requests."""
    if not join_request_unseen(ctrl):
        return
    ctrl.settings["join_req_seen"] = [f"{r.get('dev') or r.get('dev_id')}:{r.get('until')}"
                                      for r in ctrl.sync_join_request_info() or []]
    if hasattr(ctrl, "settings_changed"):
        ctrl.settings_changed()
    if hasattr(ctrl, "autobackup_badge"):
        ctrl.autobackup_badge()


