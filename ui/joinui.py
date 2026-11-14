"""Settings → Your devices: coupling when BOTH devices already have data (three equal keys) and the state set aside
(lead 07.11.2026, docs/KOPPEL-TEXTE.md – legal's wording 06./07.11., 1:1). Only with the sync built in
(collection/syncrun.available()); the logic is performance's (net/sync_ctl.py):
    ctrl.sync_join_choice      None | {"other": "phone"|"pc"|…, "here": counts, "there": counts}   nothing sent before
    ctrl.sync_join_answer(k)   "merge" | "theirs" (keep the other device's state) | "mine" (keep this PC's) | "" (cancel)
    sync_status["join"]        "busy" | "ok" | "error" (+ "join_text") | "again" (another device took over first)
    ctrl.aside_list()          [{"id", "when", "what": counts, "why": "theirs"|"takeover"|"offline"}]
    ctrl.aside_restore(id) / aside_delete(id) / aside_open(id) (the folder, local) / aside_seen(id)
    sync_status["aside"]       id of the newest one set aside without asking (takeover/offline) until seen
No window, no key chosen beforehand, none of them primary (nothing on Enter), Cancel of its own."""
import time

from system.i18n import tr

KINDS = ("merge", "theirs", "mine")


def built():
    try:
        from collection import syncrun
        return bool(syncrun.available())
    except ImportError:
        return False


def _ui_state(b):
    return b.__dict__.setdefault("join_ui", {})


# ---------- counts ("2 decks, 3 lists and 120 cards") ----------
_ONE = {"decks": "1 deck", "lists": "1 list", "binders": "1 binder", "friends": "1 friend", "cards": "1 card"}


def what(counts):
    parts = []
    for k, one in _ONE.items():
        n = int((counts or {}).get(k) or 0)
        if n:
            parts.append(tr(one) if n == 1 else tr(f"{n} {k}"))
    if not parts:
        return tr("nothing that syncs")
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + tr(" and ") + parts[-1]


# ---------- the device words: German needs the article, so whole sentences per device ----------
def _texts(other):
    if other == "phone":
        return (tr("Keep the phone's state"),
                tr("This device takes over the state of the phone. What is here now is set aside on this device – "
                   "you can restore or delete it."),
                tr("The phone takes over the state of this device. What is there now is set aside there – you can "
                   "restore or delete it there."))
    if other == "pc":
        return (tr("Keep the PC's state"),
                tr("This device takes over the state of the PC. What is here now is set aside on this device – "
                   "you can restore or delete it."),
                tr("The PC takes over the state of this device. What is there now is set aside there – you can "
                   "restore or delete it there."))
    return (tr("Keep the other device's state"),
            tr("This device takes over the state of the other device. What is here now is set aside on this device – "
               "you can restore or delete it."),
            tr("The other device takes over the state of this device. What is there now is set aside there – you "
               "can restore or delete it there."))


def _took_over(other):
    if other == "phone":
        return tr("The phone took over with its state. What was here is set aside on this device only – you can "
                  "restore or delete it.")
    if other == "pc":
        return tr("The PC took over with its state. What was here is set aside on this device only – you can restore "
                  "or delete it.")
    return tr("Another device took over with its state. What was here is set aside on this device only – you can "
              "restore or delete it.")


OFFLINE = ("This device was not synced for over 90 days and has now taken over the current state. Its earlier state "
           "is set aside on this device only and is not uploaded.")
VIEW = ("This is the earlier state of this device. It may include entries you have since deleted on another device. "
        "It stays on this device only and is not synced. You can delete it if you no longer need it.")
WHERE = ("States set aside stay only on this PC and don't go to our server. You can delete each one in its line, "
         "or everything with “Delete Bent°Corner”.")   # legal 07.11.: no key names but the real one for everything


# ---------- the choice ----------
CONFIRM = "Do it this way?"   # PLAN-EINFACH B: the second step as a line, no pop-up (legal 07.11.)
THIS_ONE = "{name} (this one)"   # the table's column head for this device
KEEP_NAMED = "Keep the state of {name}"   # „Stand von Gerät 1 behalten“


def other_name(c):
    """The other device by its name (Gordon/lead 07.11.: always names – someone may have two PCs): its own name, else
    „Device N“; not known yet (performance' other_name/other_n): None."""
    if c.get("other_name"):
        return c["other_name"]
    if c.get("other_nick"):   # Oliver/lead 12.11.: its nickname
        from system import nicknames
        name = nicknames.render(c["other_nick"], nicknames.lang())
        if name:
            return name
    if c.get("other_n"):
        from ui import qsync
        return qsync.default_name(c.get("other"), c["other_n"])
    return None
ROWS = (("cards", "Cards"), ("decks", "Decks"), ("lists", "Lists"), ("binders", "Binders"), ("friends", "Friends"))


def _my_name(ctrl):
    """This device's name as in the list (performance: name None = „Device N“). Joining, it isn't in the list yet:
    its own name, else „Device {join_n}“; None when not even the number is known (performance 07.11. guide run)."""
    from ui import qsync
    try:
        me = next((d for d in (ctrl.sync_devices() if hasattr(ctrl, "sync_devices") else []) if d.get("me")), None)
    except Exception:  # noqa: BLE001
        me = None
    if me is None:
        n = int(((getattr(ctrl, "sync_status", None) or {}).get("join_n")) or 0)
        name = (getattr(ctrl, "settings", None) or {}).get("device_name")
        nick = ctrl.sync_my_nick() if hasattr(ctrl, "sync_my_nick") else None   # Oliver/lead 12.11.
        if not name and not n and not nick:
            return None
        me = {"name": name, "n": n, "kind": "pc", "nick": nick}
    return qsync.device_name(me)


def compare_table(ui, ctrl, c):
    """Both devices next to each other (lead 07.11., Oliver: „Inhalt beider Geräte nebeneinander“): one row per kind,
    the device names as column heads; „–“ for none."""
    here, there = c.get("here") or {}, c.get("there") or {}
    other = other_name(c) or tr("Other device")
    mine = _my_name(ctrl)
    head = tr(THIS_ONE).format(name=mine) if mine else tr("This device")
    cells = [ui.label(""), ui.label(f"<b>{head}</b>", rich=True),
             ui.label(f"<b>{other}</b>", rich=True)]
    shown = [(k, t) for k, t in ROWS if int(here.get(k) or 0) or int(there.get(k) or 0)] or list(ROWS[:1])

    def n(d, k):
        v = int(d.get(k) or 0)
        return str(v) if v else "–"
    for k, t in shown:
        cells += [ui.label(tr(t)), ui.label(n(here, k)), ui.label(n(there, k))]
    return ui.row([ui.col([ui.grid(cells, 3)], w=2), ui.stretch()])


def choice_items(ui, ctrl, refresh, mem=None):
    """The group's rows while ctrl.sync_join_choice is set; [] otherwise. Both sides next to each other, then four equal
    keys [Merge] [Keep <other>] [Keep this device's] [Cancel]; with mem (the page's memory, PLAN-EINFACH B) a choice
    first asks once more as a line – what it does + [Yes] [Back] – before anything happens."""
    if not built():
        return []
    c = getattr(ctrl, "sync_join_choice", None)
    if not c or not hasattr(ctrl, "sync_join_answer"):
        return []
    st = getattr(ctrl, "sync_status", {}) or {}
    state = st.get("join")
    name = other_name(c)
    keep_there, line_there, line_mine = _texts(c.get("other") if name else "")   # no name yet: „the other device“
    if name:
        keep_there = tr(KEEP_NAMED).format(name=name)
    out = [compare_table(ui, ctrl, c)]   # lead 07.11.: the table and the keys first – no detour tip
    if state == "again":
        out.append(ui.label(tr("Another device chose first – please choose again.")))
        if mem is not None:
            mem.pop("pick", None)
    busy = state == "busy"
    kinds = (("merge", tr("Merge"), tr("Logs, decks, lists, binders, alerts, trade offers and friends from both devices "
                                      "are merged. Afterwards both have the same state.")),
             ("theirs", keep_there, line_there),
             ("mine", tr(KEEP_NAMED).format(name=_my_name(ctrl)) if _my_name(ctrl) else tr("Keep this device's state"),
              line_mine))

    def answer(kind):
        if mem is not None:
            mem.pop("pick", None)
        ctrl.sync_join_answer(kind)
        refresh()

    def pick(kind):
        def f():
            if mem is None or not kind:   # Cancel never asks
                answer(kind)
            else:
                mem["pick"] = kind
                refresh()
        return f
    chosen = (mem or {}).get("pick")
    if chosen and not busy:
        text, line = next((t, ln) for k, t, ln in kinds if k == chosen)
        out += [ui.label(f"<b>{text}</b>", rich=True), ui.note(line),
                ui.note(tr("Anything set aside stays on that device only and doesn't go to our server.")),
                ui.row([ui.label(tr(CONFIRM), fixed=True), ui.button(tr("Yes"), lambda: answer(chosen)),
                        ui.button(tr("Back"), lambda: (mem.pop("pick", None), refresh())), ui.stretch()])]
        return out
    out.append(ui.row([ui.button(text, pick(kind), enabled=not busy) for kind, text, _l in kinds]
                      + [ui.button(tr("Cancel"), pick(""), enabled=not busy), ui.stretch()]))
    if mem is None:   # without the second step: what each key does right below (as before)
        out += [ui.note(line) for _k, _t, line in kinds]
        out.append(ui.note(tr("Anything set aside stays on that device only and doesn't go to our server.")))
    if busy:
        out.append(ui.label(tr("Coupling … (a few seconds)")))
    elif state == "error":
        out.append(ui.label(st.get("join_text") or tr("Coupling didn't work – try again.")))
    return out


# ---------- set aside ----------
# [Bring back], second click (legal/lead 07.11.: what really comes back – friends and open trades don't)
BACK_ASK = ("Click again to bring it back: sync turns off on this PC, and your collection, decks, lists, binders, trade "
            "offers, price and list alerts and your profile go back to the state set aside. Your friends and open trades "
            "stay as they are now. Bent°Corner sets the current state aside first.")

# open trades of a state set aside (legal 07.11.; performance' aside_tickets / aside_ticket_delete): look and delete only
TICKETS_LINE = ("You can only view and delete open trades from this saved state. What still applies is shown under "
                "Trades.")
TICKET_ROW = "Trade with {partner}, {date}: {what}"
TICKET_GIVE = "you give {cards}"
TICKET_TAKE = "you get {cards}"
TICKET_PAY = "you pay {amount}"
TICKET_PAID = "{partner} pays {amount}"   # lead 07.11.: money from the partner – „bekommst“ never twice
TICKET_ASK = "Click again to delete this trade from the state set aside – the current one under Trades stays."


def _count(rows):
    return sum(int(r[4] or 1) if isinstance(r, (list, tuple)) and len(r) > 4 else 1 for r in rows or [])


def _cards(n):
    return tr("1 card") if n == 1 else tr("{n} cards").format(n=n)


def ticket_line(tk):
    """One open trade in words: partner, date, what goes each way, the agreed amount (the user's, no market value)."""
    from ui.scanlook import money
    from ui import textsafe
    partner = textsafe.name(tk.get("partner")) or "–"   # display only: the stored name stays as it came
    give, take = _count(tk.get("give")), _count(tk.get("get"))
    cards = ", ".join(x for x in (give and tr(TICKET_GIVE).format(cards=_cards(give)),
                                  take and tr(TICKET_TAKE).format(cards=_cards(take))) if x)   # zero parts left out
    m = int(tk.get("money") or 0)
    pay = (tr(TICKET_PAY).format(amount=money(m / 100)) if m > 0 else
           tr(TICKET_PAID).format(partner=partner, amount=money(-m / 100)) if m < 0 else "")
    return tr(TICKET_ROW).format(partner=partner, date=_when(tk.get("t")), what=" · ".join(x for x in (cards, pay) if x))


def _ticket_items(ui, ctrl, st, sid, refresh):
    try:
        by_game = ctrl.aside_tickets(sid) if hasattr(ctrl, "aside_tickets") else {}
    except Exception:  # noqa: BLE001 – a broken state must not take the page down
        by_game = {}
    tickets = sorted(((g, tk) for g, ts in (by_game or {}).items() for tk in ts or []), key=lambda x: x[1].get("t") or 0)
    if not tickets:
        return []
    out = [ui.note(tr(TICKETS_LINE))]
    for g, tk in tickets:
        key = ("tdrop", sid, g, tk.get("id"))

        def ask(key=key):
            st["ask"] = None if st.get("ask") == key else key
            refresh()

        def drop(g=g, tid=tk.get("id")):
            st["ask"] = None
            if ctrl.aside_ticket_delete(sid, g, tid):
                st["done"] = tr("Trade deleted from the state set aside.")
            refresh()
        if st.get("ask") == key:   # two clicks, no pop-up (like deleting a state)
            out += [ui.label(ticket_line(tk)), ui.note(tr(TICKET_ASK)),
                    ui.row([ui.button(tr("Delete"), drop), ui.button(tr("Cancel"), ask), ui.stretch()])]
        else:   # the key in the trade's own row – clear which one it deletes
            out.append(ui.row([ui.label(ticket_line(tk), fixed=True), ui.button(tr("Delete"), ask), ui.stretch()]))
    return out


def _when(t):
    return time.strftime("%d.%m.%Y", time.localtime(t)) if t else "–"


def _entries(ctrl):
    try:
        return list(ctrl.aside_list() or []) if hasattr(ctrl, "aside_list") else []
    except Exception:  # noqa: BLE001 – a broken folder must not take the page down
        return []


def notice_items(ui, b, refresh):
    """The line at the top of „Your devices“ after a state was set aside without asking (offline / takeover)."""
    ctrl = b.ctrl
    if not built():
        return []
    aid = (getattr(ctrl, "sync_status", {}) or {}).get("aside")
    e = next((e for e in _entries(ctrl) if e.get("id") == aid), None) if aid else None
    if not e:
        return []
    text = tr(OFFLINE) if e.get("why") == "offline" else _took_over(e.get("other"))

    def view():
        _ui_state(b)["view"] = e["id"]
        if hasattr(ctrl, "aside_seen"):
            ctrl.aside_seen(e["id"])
        if hasattr(ctrl, "aside_open"):
            ctrl.aside_open(e["id"])
        refresh()

    def close():
        if hasattr(ctrl, "aside_seen"):
            ctrl.aside_seen(e["id"])
        refresh()
    return [ui.note(text), ui.row([ui.button(tr("View"), view), ui.button(tr("Close"), close), ui.stretch()])]


def aside_items(ui, b, refresh):
    """„Set aside“: one line per state set aside on this PC with [View] [Bring back] [Delete what's set aside];
    bringing back and deleting ask once inline (click again), equal keys."""
    ctrl = b.ctrl
    if not built():
        return []
    entries = _entries(ctrl)
    if not entries:
        return []
    st = _ui_state(b)
    out = []
    for e in entries:
        i = e.get("id")

        def ask(what, i=i):
            def f():
                st["ask"] = None if st.get("ask") == (what, i) else (what, i)
                refresh()
            return f

        def do(what, i=i):
            def f():
                st["ask"] = None
                if what == "back":
                    ctrl.aside_restore(i)
                    st["done"] = tr("Brought back.")
                else:
                    ctrl.aside_delete(i)
                    st["done"] = tr("What was set aside is deleted.")
                refresh()
            return f

        def view(i=i):
            st["view"] = None if st.get("view") == i else i
            if st["view"] and hasattr(ctrl, "aside_open"):
                ctrl.aside_open(i)
            refresh()
        out.append(ui.label(tr("From {when}: {what}").format(when=_when(e.get("when")), what=what(e.get("what")))))
        if st.get("view") == i:
            out.append(ui.note(tr(VIEW)))
            out += _ticket_items(ui, ctrl, st, i, refresh)
        a = st.get("ask")
        if a == ("back", i):
            out += [ui.note(tr(BACK_ASK)),
                    ui.row([ui.button(tr("Bring back"), do("back")), ui.button(tr("Cancel"), ask("back")),
                            ui.stretch()])]
        elif a == ("drop", i):
            out += [ui.note(tr("Click again to delete what's set aside on this PC – it can't be brought back "
                               "afterwards.")),
                    ui.row([ui.button(tr("Delete"), do("drop")), ui.button(tr("Cancel"), ask("drop")),
                            ui.stretch()])]
        else:
            out.append(ui.row([ui.button(tr("View"), view), ui.button(tr("Bring back"), ask("back")),
                               ui.button(tr("Delete"), ask("drop")), ui.stretch()]))
    if st.get("done"):
        out.append(ui.label(st.pop("done")))
    out.append(ui.note(tr(WHERE)))
    return out


# ---------- this device was signed out / a backup of a removed identity (PAIRING §3, legal 07.11.2026; logic: performance) ----------
#   sync_status["removed"]                     410 without forwarding: another device chose „Remove device“ –
#                                              True or {"by": "<that device's name>"} (legal A6: say WHO)
#   settings["relay"]["identity_gone"] = t     a restored backup came from a removed identity; ctrl.identity_gone_seen()
REMOVED = ('This device was removed. Your data on this device has therefore been deleted; a backup of it stays '
           "here for 30 days (Settings → Backup). Wasn't that you? Then a device that isn't yours has taken over"
           ' your ID: restore the backup and save your collection as a file, then start over (“Delete '
           'Bent°Corner”) and tell your friends to decline the “moved” message from you.')   # legal A6 (protection code model); on the PC only „Delete Bent°Corner“ (lead)
WIPED_WHERE = "You can bring the data back under Settings → Backup for 30 days."   # D (lead 12.11.)
GONE = ("This backup comes from a removed identity. Your data has been restored; sync starts with a new identity.")


def _removed(ctrl):
    """Signed out by another device: the live answer (sync_status) or the kept mark (settings relay.removed {by, at} –
    performance: it survives a restart). -> {"by": …} / True / None"""
    live = (getattr(ctrl, "sync_status", {}) or {}).get("removed")
    kept = ((getattr(ctrl, "settings", {}) or {}).get("relay") or {}).get("removed")
    return live or kept or None


def really_coupled(ctrl):
    """„Coupled ✓“ only while this device is really paired and syncing (lead 07.11.): sync on, not signed out, not
    switched off by a deletion on another device, the test server reached, another device in the list. Paused
    outside Full Orbit still counts (the pairing stays)."""
    eng = getattr(ctrl, "sync_engine", None)
    if eng is None or not eng.on() or _removed(ctrl):
        return False
    if (getattr(ctrl, "sync_status", None) or {}).get("gate") == "missing":   # never reached the test server (T2 07.11.)
        return False
    devs = getattr(eng, "devices", None)
    if callable(devs) and not any(not d.get("me") for d in devs()):   # alone after „Remove device“ (performance 07.11.)
        return False
    return not (getattr(eng, "meta", {}) or {}).get("deleted_off")


def status_items(ui, b, refresh):
    """The lines at the very top of „Your devices“: signed out (with [Couple again] – the sphere reading starts) and
    the restored backup of a removed identity (until [OK])."""
    ctrl = b.ctrl
    if not built():
        return []
    out = []
    removed = _removed(ctrl)
    settings = getattr(ctrl, "settings", {}) or {}
    if removed:
        def seen():
            settings.pop("sync_wiped", None)
            if hasattr(ctrl, "identity_gone_seen"):
                ctrl.identity_gone_seen()
            refresh()
        # D (Oliver/lead 12.11.): removed = emptied (a 30-day copy) – no „Add again“: it is added like a new device
        out += [ui.note(tr(REMOVED)), ui.row([ui.button(tr("OK"), seen), ui.stretch()])]
    elif isinstance(settings.get("sync_wiped"), dict):   # signed itself out: emptied after the copy (D)
        from ui import qsync

        def ok():
            settings.pop("sync_wiped", None)
            if hasattr(ctrl, "settings_changed"):
                ctrl.settings_changed()
            refresh()
        out += [ui.note(tr(qsync.LEAVE) + " " + tr(WIPED_WHERE)), ui.row([ui.button(tr("OK"), ok), ui.stretch()])]
    # a restored backup of a removed identity – only when this device wasn't simply signed out (that line says it all)
    if not removed and ((getattr(ctrl, "settings", {}) or {}).get("relay") or {}).get("identity_gone"):
        def seen():
            if hasattr(ctrl, "identity_gone_seen"):
                ctrl.identity_gone_seen()
            refresh()
        out += [ui.note(tr(GONE)), ui.row([ui.button(tr("OK"), seen), ui.stretch()])]
    return out


# ---------- this PC joins the phone (Paket 2c, lead/performance 07.11.): the phone shows code + sphere, the PC reads ----------
#   ctrl.sync_join_code(code)             typed; sync_status["join"]: busy | ok | wrong (never why – legal) | error | choice
#   ctrl.sync_join_camera(on, device)     the webcam reads the sphere (only in memory – performance, tested before the
#   ctrl.sync_join_cameras()              camera line goes live); sync_status["join_cam"]: looking | found | no_camera |
#   "image://cards/sync_cam"              stopped; the preview. Found -> the same as a typed code.
JOIN_HOW = ("On your phone: profile symbol at the top right → Devices → “Show a code for a new device”. Hold the turning "
            "sphere up to the webcam – or type the code below it.")
JOIN_HOW_CODE = "On your other device: Your devices → “Show a code”. Type that code here."   # SPHERE off (11.11.)
JOIN_SAFE = ("Only enter a code your own phone is showing right now – never one someone sends you. This PC then gets access "
             "to your whole online backup and your friends, and its data is synced with the phone.")
CAM_LOCAL = "The camera image is only read on this PC – nothing is stored or sent."


def _cam_off(ctrl):
    if hasattr(ctrl, "sync_join_camera"):
        try:
            ctrl.sync_join_camera(False)
        except Exception:  # noqa: BLE001 – stopping must never take the page down
            pass


def _watch_page(ctrl, st):
    """Leaving „Your devices“ for another settings page: the camera goes off (performance stops it after 3 min anyway)."""
    if st.get("watching") or not hasattr(ctrl, "settings_listeners"):
        return
    st["watching"] = True

    def changed(key):
        if key != "devices" and st.get("cam"):
            st["cam"] = False
            _cam_off(ctrl)
    ctrl.settings_listeners.append(changed)


# the protection code on the joining device (Oliver 08.11., legal 08.11.)
JOIN_CODE = ("Enter the protection code of your other devices. If this device had its own before, it no longer applies "
             "afterwards.")
JOIN_FROM = "From now on, the protection code of {device} applies to all devices."   # C (lead 12.11.)
JOIN_FROM_OTHER = "From now on, the protection code of your other device applies to all devices."
JOIN_CODE_REQ = "If a request for a new code is running, that's still the old one until the set date."
JOIN_CODE_CANCEL = "If you cancel here, you need a new code from your other device."


def _join_guard_items(ui, b, refresh):
    """The A4 field after the accepted pairing code (performance: join "need_guard", ctrl.sync_join_guard(code), then
    the known guard states). The pairing parcel waits in memory only – cancelling needs a new code."""
    from ui import backupui
    ctrl = b.ctrl
    st = getattr(ctrl, "sync_status", None) or {}
    g = st.get("guard")
    state = g if g in ("wrong", "wait") else "need"

    def cancel():
        ctrl.sync_join_drop()   # the parcel leaves memory; join/guard/guard_wait/join_request are gone
        _ui_state(b).clear()
        b.__dict__.pop("join_guard_code", None)   # nothing typed stays behind
        refresh()
    out = [ui.label(tr(JOIN_CODE), bold=True)]
    if st.get("join_had_own"):   # C: this device had its own code – whose applies now
        out.append(ui.note(tr(JOIN_FROM).format(device=st["join_from"]) if st.get("join_from") else tr(JOIN_FROM_OTHER)))
    if st.get("join_request"):   # a request for a new code runs on the other devices
        out.append(ui.note(tr(JOIN_CODE_REQ)))
    out += backupui.guard_items(ui, state, st.get("guard_wait"), b.__dict__.setdefault("join_guard_code", {}),
                                "Add device", ctrl.sync_join_guard, cancel, getattr(b, "form", None))[1:]   # own line above
    out.append(ui.note(tr(JOIN_CODE_CANCEL)))
    return out


def join_items(ui, b, refresh):
    """„Couple with your phone“: read the phone's sphere with the webcam or type its code. [] without the sync."""
    ctrl = b.ctrl
    if not built() or not hasattr(ctrl, "sync_join_code"):
        return []
    st = _ui_state(b)
    _watch_page(ctrl, st)
    sstat = getattr(ctrl, "sync_status", {}) or {}
    state, cam = sstat.get("join"), sstat.get("join_cam")
    busy = state == "busy"
    if state == "need_guard":   # Oliver 08.11.: the protection code on the NEW device, after the pairing code
        return _join_guard_items(ui, b, refresh)
    from net import sync_ctl
    sphere = sync_ctl.sphere_on(getattr(ctrl, "settings", None))   # lead/ports 11.11.: behind its switch, off by default
    out = [ui.note(tr(JOIN_HOW if sphere else JOIN_HOW_CODE))]
    if state == "ok" and really_coupled(ctrl):
        return out[:0] + [ui.label(f"<b>{tr('Coupled ✓')}</b>", rich=True)]

    def camera(on):
        def f():
            st["cam"] = on
            st["err"] = ""
            if on:
                ctrl.sync_join_camera(True, st.get("device"))
            else:
                _cam_off(ctrl)
            refresh()
        return f

    def pick_cam(v):
        st["device"] = v
        if st.get("cam"):
            ctrl.sync_join_camera(True, v)
        refresh()

    cams = []
    try:
        cams = list(ctrl.sync_join_cameras() or []) if hasattr(ctrl, "sync_join_cameras") else []
    except Exception:  # noqa: BLE001
        cams = []
    reading = st.get("cam") and cam in (None, "looking", "found")
    # Cancel is never the first key (lead 07.11.): while reading it sits under the preview
    row = [] if reading or not sphere else [ui.button(tr("Read the sphere"), camera(True), enabled=not busy)]
    if len(cams) > 1 and sphere:
        row.append(ui.combo([(i, n) for i, n in cams], st.get("device", cams[0][0]), pick_cam, enabled=not busy))
    if row:
        out.append(ui.row(row + [ui.stretch()]))
    if reading:
        out += [ui.row([ui.live("sync_cam", 320, 240), ui.stretch()]),
                ui.note(tr("Hold the whole sphere in the picture – it takes about one turn.")),
                ui.note(tr(CAM_LOCAL)),
                ui.row([ui.button(tr("Cancel"), camera(False), enabled=not busy), ui.stretch()])]
    elif st.get("cam") and cam == "no_camera":
        out.append(ui.label(tr("No camera found – type the code instead.")))
    elif st.get("cam") and cam == "stopped":
        out.append(ui.label(tr("The camera is off – read the sphere again or type the code.")))

    def go(text=None):
        code = "".join(ch for ch in str(text if text is not None else st.get("code", "")).upper() if ch.isalnum())
        if len(code) != 10:
            st["err"] = tr("The code has 10 letters and digits.")
            refresh()
            return
        st["err"] = ""
        st.pop("code", None)   # read once – the field and its draft empty again (lead 08.11., desk-codefields)
        form = getattr(b, "form", None)
        if form is not None and hasattr(form, "forget"):
            form.forget("join_code")
        ctrl.sync_join_code(code)
        refresh()
    out.append(ui.form([(tr("Code"), ui.edit(st.get("code", ""), go, live=lambda t: st.update(code=t), key="join_code",
                                                placeholder="XXXXX XXXXX", enabled=not busy, focus=True))]))
    out.append(ui.row([ui.button(tr("Next"), lambda: go(None), enabled=not busy), ui.stretch()]))
    if busy:
        out.append(ui.label(tr("Coupling … (a few seconds)")))
    elif st.get("err"):
        out.append(ui.label(st["err"]))
    elif st.get("cam") and cam in ("looking", "found"):
        pass   # reading the sphere again: the last typed code's answer no longer applies (performance' pictures)
    elif state == "wrong":
        out.append(ui.label(tr("The code doesn't fit or has expired – show a new one on your phone.")))
    elif state == "error":
        out.append(ui.label(sstat.get("join_text") or sstat.get("text") or tr("No connection – try again in a moment.")))
        if getattr(ctrl, "_join_payload", None) is not None and hasattr(ctrl, "sync_join_retry"):
            # performance 13.11.: the ID's state couldn't be asked (offline / an older server) – the same identity again
            out.append(ui.row([ui.button(tr("Try again"), ctrl.sync_join_retry, primary=True), ui.stretch()]))
    out.append(ui.note(tr(JOIN_SAFE)))
    return out
