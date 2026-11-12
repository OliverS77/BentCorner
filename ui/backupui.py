"""„Daten online sichern, verschlüsselt“ – the faces (Oliver/lead/legal 06.11.2026); the logic is performance's
(net/sync_ctl.py, collection/syncrescue.py: settings["sync_backup"], settings["sync_asked"], syncrescue.new_code(),
ctrl.sync_rescue_confirm(code, last5), ctrl.sync_rescue_restore(code), ctrl.vault_delete(), ctrl.sync_offer_answer(False),
results in ctrl.sync_status via the sync_state signal).

Rules (lead/legal): the switch only in Full Orbit (Core/Near: off and dimmed); preselected ON in the setup, but nothing
goes up before the protection code is confirmed by TYPING its last 5 characters (no paste); [Back] = no backup, nothing
uploaded; switching off DELETES the online backup and the rescue envelope (asked inline, equal keys); an upload error is
a grey line with [Try again]; „passt nicht“ never says why. One word everywhere: Schutz-Code / protection code (lead 07.11.).
"""
import time

from system.i18n import tr

# legal's wording (Legal\\bentcorner\\2026-11-06-ganzer-orbit-sync.md + messages 06.11.)
SWITCH = "Online backup and sync"   # legal 07.11. (W3): the one switch must name both
SCOPE = ("When the switch is on, your collection, decks, lists, binders, friends and your profile are stored on our "
         "server, end-to-end encrypted – we can't read them. Details under “What is on the server”.")
# legal 07.11.: ONE line in every state (replaces SYNC_WHAT, ON_LINE and the first scope line)
SETUP_LINE = ("+ Back up and sync your collection, decks, lists, binders, alerts, trade offers and friends between your "
              "devices, end-to-end encrypted")
ONLY_FULL = "Online backup is available in Full Orbit."
BACKUP_HINT = "On top, an encrypted backup is kept on our server; your own backup file still makes sense."
ON_LINE = "Your data is also kept end-to-end encrypted on our server – we can't read it."
CARD = ("New in Full Orbit: your collection, decks, lists, binders, alerts, trade offers and friends can now be backed "
        "up end-to-end encrypted on our server and synced between your devices – we can't read them. Nothing is "
        "uploaded until you decide.")
CARD_ON, CARD_OFF = "Turn on backup", "Continue without backup"
CODE_TITLE = "Your protection code"
CODE_WHY = ("With this code you get your backup back if all your devices are gone – up to 183 days after the last sync. "
            "Every device also needs it to remove "
            "other devices, delete the online backup or delete everything. We don't store it and can't send it to you – write it "
            "down or keep it in a password manager. If you lose it, you can request a new one on one of your devices; "
            "it applies after 14 days.")   # legal 07.11. (protection code model)
# the offer (legal A2 + the setup line, Oliver/lead 07.11.: generated is the default, an own code may be chosen)
OFFER_TITLE = "Protection code"
OFFER = ("Set up a protection code? Then no device can remove other devices, delete the online backup or "
         "delete everything without it. Write it down – if you lose it, a replacement takes 14 days.")   # legal 07.11.
OFFER_GEN, OFFER_OWN, OFFER_NONE = "Let Bent°Corner make a code", "Choose your own code", "Without protection code"
WITHOUT_LINE = ("Without a protection code you can only get back to your online backup through this device or your backup "
                "file – with the file only after 14 days.")   # legal 08.11. (the code is required from the second device)
# adding a second device without a code (Oliver 08.11., legal's A2 08.11.): the setup first, never „without code“
ADD_NEEDS_CODE = ("You need a protection code for another device. You'll enter it on the new device in a moment; it then "
                  "applies to all your devices, and only with it can you remove devices or delete everything. Write it "
                  "down – if you lose it, a replacement takes 14 days.")
ADD_SET_UP = "Set up protection code"
OWN_LINE = ("Your own code must be hard to guess – don't use one you already use elsewhere. A generated code is safer.")
OWN_FIELD, OWN_AGAIN, OWN_DIFF = "Your protection code", "Enter the code again", "The two entries don't match."
WEAK = "This code is too easy to guess. Use a longer one or have it generated."
CHECKING = "Checking the code …"
CODE_NEXT_OWN = "Next"
CODE_FIELD = "To confirm: the last 5 characters"
CODE_COPY, CODE_NEXT, CODE_BACK = "Copy", "Code noted – continue", "Back"
CODE_BACK_NOTE = "Back: no backup, nothing is uploaded."
CODE_FAILED = "The backup couldn't be set up – nothing was uploaded."
# performance 08.11. (Gordon's box: guard/set 409 guard_first_only_alone): a first code only while one device is in
FIRST_ALONE = ('A first protection code can only be set while just this one device is linked. Sign out your other '
               'devices there (“Sign out this device”), set up the code here and add them again afterwards – they '
               'then get your data back from the online backup.')   # legal 08.11.
CODE_BUSY = "Setting up the backup …"
SAME_CODE = "Protection code not changed – that is already your code."   # Oliver 12.11.: no error for the same code
DELETE_ASK = ("Delete the online backup? The backup on our server is deleted, your data on this device stays. Your "
              "other devices stop syncing afterwards.")
DELETE, CANCEL = "Delete", "Cancel"
DELETED = "Online backup deleted."
DELETE_FAILED = "No connection – nothing was deleted, sync is still on. Try again in a moment."   # the web's line
GROUP = "Online backup"   # the group's title in Settings → Backup (legal's word „Online-Sicherung“)
NEW_CODE, NEW_CODE_NOTE = "Create a new protection code", "The old code no longer works afterwards."
RESTORE, RESTORE_FIELD = "Restore with protection code", "Protection code"
WRONG, NO_NET = "The code doesn't match.", "No connection – try again later."
AGAIN = "Try again"
TAKEN = "You can't use this code – please choose another one."   # bug 1 (lead 12.11.): never why
OTHER_CODE = "Choose a different code"
SHARE_LINE = ("Anyone who knows your protection code can restore your online backup. Don't share it, and don't use one "
              "you already use elsewhere.")   # legal 12.11., word for word – on both setup pages
HALF = ("Your protection code is set but isn't on our server yet – until then it won't help if all your devices are "
        "gone. Try again.")   # bug 1; wording legal 12.11. (PC = web)


def built():
    """The sync is built in (collection/syncrun.available(): SYNC_TEST, or BC_SYNC=1 from the source) – until the big
    0.9.7 it is off, and then none of these faces shows: the setup as before (8 steps), no card, no settings block
    (lead 06.11.: everything behind ONE switched-off switch)."""
    try:
        from collection import syncrun
    except ImportError:
        return False
    return bool(syncrun.available())


def available(ctrl):
    """The sync is built in and performance's logic is there."""
    return built() and all(hasattr(ctrl, n) for n in ("sync_rescue_confirm", "vault_delete"))


def new_code():
    try:
        from collection import syncrescue
    except ImportError:
        return ""
    return syncrescue.new_code()


def blocks(code):
    """XXXXX-XXXXX-… as it is shown: the blocks with thin spaces around the dashes (easier to copy by hand)."""
    return " – ".join(code.split("-")) if code else "…"


def last5(code):
    return code.replace("-", "")[-5:].upper() if code else ""


def status(ctrl):
    return getattr(ctrl, "sync_status", None) or {}


# ---------- the setup: the switch right under the Orbit slider's columns (ui.orbit(sync=…), lead 06.11.) ----------
def setup_sync(st, level, refresh):
    """st["backup"]: the choice of this setup page – remembered only here until the code is confirmed (performance).
    None without the sync built in (no switch under the slider)."""
    if not built():
        return None
    full = level == "full"
    st.setdefault("backup", True)
    on = full and st["backup"]

    def flip(v):
        st["backup"] = bool(v)
        refresh()
    notes = ([tr(SETUP_LINE)] + ([tr(BACKUP_HINT)] if on else [])) if full else [tr(ONLY_FULL)]
    return {"text": tr(SWITCH), "on": on, "enabled": full, "notes": notes, "fn": flip}


# ---------- the rescue code page (setup after the Orbit choice; existing users after „Turn on backup“) ----------
def rescue_items(ui, ctrl, st, refresh, on_back, on_done, form=None):
    """The protection code page (setup after the Orbit choice with the backup on; Settings → Backup when turning on).
    st: this page's memory (RAM only) – "mode": None (the offer) | "gen" (a generated code) | "own" (the user's own).
    The offer (legal A2, Oliver 07.11.): three equal keys – „Code erzeugen lassen“ first with the focus, „Eigenen Code
    wählen“, „Ohne Schutz-Code“ – and legal's line what having none means."""
    if st.get("change") == "old":   # „Change protection code“: the current one first (performance: need_old)
        return _old_items(ui, st, refresh, on_back, form)
    mode = st.get("mode")
    if mode == "gen":
        return _gen_items(ui, ctrl, st, refresh, on_done)
    if mode == "own":
        return _own_items(ui, ctrl, st, refresh, on_done, form)
    if st.get("without"):   # „Ohne Schutz-Code“: the backup goes on without a code (performance: sync_backup_set)
        st.clear()
        on_done()
        return []

    # „without code“ only while there's a single device (Oliver 08.11.; performance' guard_optional – the registry)
    none_ok = not st.get("change") and not st.get("second") and ctrl.guard_optional()

    def pick(m):
        def f():
            keep = {k: st[k] for k in ("change", "old", "second") if k in st}   # changing / a second device: kept
            st.clear()
            st.update(keep)
            if m == "none":
                st["without"] = True
                if available(ctrl) and hasattr(ctrl, "sync_backup_set"):
                    ctrl.sync_backup_set(True)
            else:
                st["mode"] = m
            refresh()
        return f
    return [ui.label(tr(OFFER_TITLE), px=22, bold=True),
            ui.note(tr(OFFER)),
            ui.row([ui.button(tr(OFFER_GEN), pick("gen")), ui.button(tr(OFFER_OWN), pick("own"))]
                   + ([ui.button(tr(OFFER_NONE), pick("none"))] if none_ok else []) + [ui.stretch()]),
            ui.note(tr(WITHOUT_LINE)) if none_ok else None,
            ui.row([ui.button(tr(CODE_BACK), lambda: (st.clear(), on_back())), ui.stretch()]),
            None if st.get("second") else ui.note(tr(CODE_BACK_NOTE))]   # adding a device: the backup stays on


def _old_items(ui, st, refresh, on_back, form=None):
    """Changing the code: the current one, typed once – kept in this page's memory (RAM) only until the new code went
    up, never in a draft (the field's draft is dropped at once)."""
    typed = st.get("old_typed", "")

    def put(v):
        st["old_typed"] = v

    def nxt():
        old = st.pop("old_typed", "").strip()
        _forget(form, "change_old")
        if not old:
            return
        st.update(change=True, old=old)
        refresh()
    out = [ui.label(f"<b>{tr(CHANGE_CODE)}</b>", rich=True), ui.label(tr(CHANGE_OLD))]   # a sub-heading (lead 07.11.)
    if st.get("old_wrong"):
        out.append(ui.label(tr(GUARD_WRONG)))
    out += [ui.row([ui.edit(typed, put, key="change_old", live=put, secret=True, enter=lambda _t: nxt(), focus=True), ui.button(tr(CODE_NEXT_OWN), nxt,
                                                                                         primary=True)]),
            ui.row([ui.button(tr(CODE_BACK), lambda: (st.clear(), _forget(form, "change_old"), on_back())), ui.stretch()])]
    return out


def _wrong_old(st, refresh, wrong=True):
    """The server said the current code isn't right (wrong) – or that one is set already and it is needed (bug 1,
    Oliver 12.11.: a joined device set up „its own“ code, the server wanted the current one): back to its field, the
    new one is dropped. Never an error line or an endless „Setting up …“ for this."""
    keep = {k: st[k] for k in ("second",) if k in st}
    st.clear()
    st.update(keep, change="old", old_wrong=wrong)
    refresh()


def _gen_items(ui, ctrl, st, refresh, on_done):
    """A generated code: shown once in blocks, confirmed by TYPING its last 5 characters (no paste – that proves it was
    written down); sync_rescue_confirm sets the code, uploads the envelope and turns the backup on (performance)."""
    if not st.get("code"):
        st["code"] = new_code()
    code = st["code"]
    rs = status(ctrl).get("rescue")
    if st.get("sent") and rs == "ok":
        changed = bool(st.get("change"))
        st.clear()
        st["was_change"] = changed
        on_done()
        return []
    if st.get("sent") and rs in ("need_old", "wrong"):   # bug 1: never „Setting up …“ forever
        _wrong_old(st, refresh, wrong=bool(st.get("change") or st.get("old")))
        return []
    ok5 = bool(code) and st.get("typed", "").strip().upper() == last5(code)

    def typed(v):
        st["typed"] = v
        refresh()

    def copy():
        from PySide6 import QtGui
        QtGui.QGuiApplication.clipboard().setText(code)

    def confirm():
        if not ok5 or not available(ctrl):
            return
        st["sent"] = True
        if st.get("old"):   # changing: the current code goes along once
            ctrl.sync_rescue_confirm(code, st["typed"].strip().upper(), old=st["old"])
        else:
            ctrl.sync_rescue_confirm(code, st["typed"].strip().upper())
        refresh()

    def back():   # the code is dropped – nothing was uploaded; back to the choice
        st.clear()
        refresh()
    items = [ui.label(tr(CODE_TITLE), px=22, bold=True),
             ui.label(f"<span style='font-family:monospace; font-size:20px; letter-spacing:2px'>{blocks(code)}</span>",
                      rich=True),
             ui.row([ui.button(tr(CODE_COPY), copy, enabled=bool(code)), ui.stretch()]),
             ui.note(tr(CODE_WHY)),
             ui.note(tr(SHARE_LINE)),
             ui.label(tr(CODE_FIELD)),
             ui.edit(st.get("typed", ""), typed, key="rescue_last5", live=typed, placeholder="•••••", nopaste=True,
                     enter=lambda _t: None if st.get("sent") else confirm(), focus=True)]   # A (Oliver 12.11.): Enter confirms
    if st.get("sent") and "first_alone" in (rs, status(ctrl).get("guard")):   # A2: a first code only while alone
        items.append(ui.label(tr(FIRST_ALONE), color="gray"))
    elif st.get("sent") and rs in ("taken", "taken_half"):   # bug 1: its envelope id is taken – a new code
        def fresh():
            just = st.get("code") if rs == "taken_half" else None
            keep = {k: st[k] for k in ("change", "old", "second") if k in st}
            st.clear()
            st.update(keep, mode="gen")
            if just:
                st.update(change=True, old=just)
                keep_for(st, ("old",), None, (), refresh)
            refresh()
        items.append(ui.row([ui.label(tr(TAKEN), color="gray"), ui.button(tr(OTHER_CODE), fresh), ui.stretch()]))
    elif st.get("sent") and rs == "half":   # bug 1: the code is set, only its envelope is missing
        def again_half():
            st["sent"] = False
            confirm()
        items.append(ui.row([ui.label(tr(HALF), color="gray"), ui.button(tr(AGAIN), again_half), ui.stretch()]))
    elif st.get("sent") and rs not in ("ok", "error", "mismatch"):
        items.append(ui.note(tr(CODE_BUSY)))
    elif st.get("sent") and rs in ("error", "mismatch"):
        def again():
            st["sent"] = False
            confirm()
        items.append(ui.row([ui.label(tr(CODE_FAILED), color="gray"), ui.button(tr(AGAIN), again), ui.stretch()]))
    items += [ui.row([ui.button(tr(CODE_BACK), back), ui.stretch(),
                      ui.button(tr(CODE_NEXT), confirm, primary=True, enabled=ok5 and not st.get("sent"))])]
    return items


STRENGTH = ("too weak", "too weak", "enough", "strong")   # score 0..3 (performance: ok = at least 60 bits)


def strength_bar(score):
    """Four grey segments – as many lit as the score says (+1), never colour (lead: greys only)."""
    lit = max(0, min(3, int(score))) + 1
    seg = "<span style='background-color:{}'>&nbsp;&nbsp;&nbsp;&nbsp;</span>&nbsp;"   # no glyph needed (symbol font)
    return seg.format("#e8e8e8") * lit + seg.format("#3a3a3e") * (4 - lit)


def slot(ui, text, rich=False):
    """A grey line that comes and goes without changing the page's structure (empty = hidden): lines under code
    fields – a new structure rebuilds the fields and takes the focus mid-typing (F1, Oliver's test round 11.11.)."""
    nd = ui.label(text or "", color="gray", rich=rich)
    if isinstance(nd, dict):   # (a test's stand-in UI gives other nodes – an empty label there)
        nd["hidden"] = not text
    return nd


KEEP_S = 120   # a typed code stays in its field (RAM only) at most this long after sending (U2, lead 11.11.)


def keep_for(mem, keys, form=None, fkeys=(), refresh=None, secs=None):
    """The typed code stays in its field while it is checked and after a wrong answer (U2) – in this page's memory
    only, never in a draft or the settings; after secs it goes (and its drafts) unless typed again meanwhile."""
    token = object()
    mem["_keep"] = token

    def drop():
        if mem.get("_keep") is token:
            for k in keys:
                mem.pop(k, None)
            mem.pop("_keep", None)
            _forget(form, *fkeys)
            if refresh is not None:
                try:
                    refresh()
                except RuntimeError:   # the page is gone
                    pass
    try:
        from PySide6 import QtCore
        QtCore.QTimer.singleShot(int((KEEP_S if secs is None else secs) * 1000), drop)
    except Exception:  # noqa: BLE001 – no Qt (tests without an app): dropped on the next success/cancel anyway
        pass
    return drop


def _forget(form, *keys):
    """The form's drafts of these fields go too (a typed code is kept nowhere – ports/lead 07.11.)."""
    if form is not None and hasattr(form, "forget"):
        for k in keys:
            form.forget(k)


def _own_items(ui, ctrl, st, refresh, on_done, form=None):
    """The user's own code (Oliver 07.11.): paste allowed in both fields (password managers – lead); the strength in
    greys while typing (ctrl.guard_strength, no examples anywhere); below the minimum: legal's line, Next stays off.
    Next: the backup on (sync_backup_set) and the code set (guard_set own=True) – sync_status["guard"] reports."""
    gs = status(ctrl).get("guard")
    if st.get("sent") and gs == "ok" and st.get("same_try"):   # 3: it went through – and nothing changed
        for k in ("sent", "same_try", "a", "b", "_keep"):
            st.pop(k, None)
        _forget(form, "own_a", "own_b")
        st["same"] = True
    if st.get("sent") and gs == "ok":
        changed = bool(st.get("change"))
        st.clear()
        _forget(form, "own_a", "own_b")
        st["was_change"] = changed
        on_done()
        return []
    if st.get("sent") and gs in ("need_old", "wrong"):
        # changing: the current code typed was wrong; a first setup (bug 1): a code is set already – its field
        _forget(form, "own_a", "own_b")
        _wrong_old(st, refresh, wrong=bool(st.get("change") or st.get("old")))
        return []
    a, b = st.get("a", ""), st.get("b", "")
    r = ctrl.guard_strength(a) if (a and hasattr(ctrl, "guard_strength")) else {"score": 0, "ok": False}
    same = bool(a) and a == b

    def put(k):
        def f(v):
            st[k] = v
            st.pop("sent", None)
            st.pop("same", None)
            if k == "b":
                st.pop("tried", None)
            refresh()
        return f

    checking = bool(st.get("sent")) and gs in (None, "busy")   # after an answer (wrong, error, half …) Next works again

    def go():
        if not same and b:   # Enter with a second entry that differs: now say so (lead 11.11.)
            st["tried"] = True
            refresh()
            return
        if not (r.get("ok") and same) or checking or not available(ctrl):
            return
        code = a   # U2: both fields stay filled while it is checked (RAM only) – gone on success, Back or after 2 min
        st["same_try"] = bool(st.get("old")) and code == st["old"]   # Oliver 12.11.: the same code again (ports: the
        # server checks the old one as always; right -> „not changed“ instead of done, wrong -> back to the old one)
        keep_for(st, ("a", "b"), form, ("own_a", "own_b"), refresh)
        st["sent"] = True
        if st.get("old"):   # changing: the current code goes along once
            ctrl.guard_set(code, own=True, old=st["old"])
        else:
            if hasattr(ctrl, "sync_backup_set"):
                ctrl.sync_backup_set(True)
            ctrl.guard_set(code, own=True)
        refresh()
    # F1 (Oliver's test round 11.11.): every line under the fields is always there – shown or hidden – so typing never
    # changes the page's structure (that rebuilt the fields and took the focus after the first key)
    score = max(0, min(3, int(r.get("score", 0))))
    items = [ui.label(tr(OFFER_OWN), px=22, bold=True),
             ui.note(tr(OWN_LINE)),
             ui.note(tr(SHARE_LINE)),
             ui.label(tr(OWN_FIELD)),
             ui.edit(a, put("a"), key="own_a", live=put("a"), secret=True, reveal=True, enter=lambda _t: go(),
                     focus=not a and not b),   # bug 2: type at once after „Choose your own code“
             slot(ui, (strength_bar(score) + "&nbsp;&nbsp;" + tr(STRENGTH[score])) if a else "", rich=True),
             slot(ui, tr(WEAK) if a and not r.get("ok") else ""),
             ui.label(tr(OWN_AGAIN)),
             ui.edit(b, put("b"), key="own_b", live=put("b"), secret=True, reveal=True, enter=lambda _t: go()),
             # lead 11.11.: „don't match“ only once the second entry is as long as the first or Enter was pressed
             slot(ui, tr(OWN_DIFF) if b and not same and (len(b) >= len(a) or st.get("tried")) else ""),
             ui.note(tr(CODE_WHY))]
    line = ""
    if st.get("same"):
        line = tr(SAME_CODE)
    elif st.get("sent") and gs in (None, "busy"):
        line = tr(CHECKING)
    elif st.get("sent") and gs == "first_alone":
        line = tr(FIRST_ALONE)
    elif st.get("sent") and gs == "weak":
        line = tr(WEAK)
    elif st.get("sent") and gs == "half":   # bug 1: the code went through, only the envelope not – never „not set up“
        line = tr(HALF)
    elif st.get("sent") and gs in ("taken", "taken_half"):   # bug 1: its envelope id is taken – another code
        line = tr(TAKEN)
    elif st.get("sent") and gs in ("error", "wrong", "wait"):
        line = tr(CODE_FAILED)   # typed again – the code isn't kept
    items.append(slot(ui, line))
    if st.get("sent") and gs == "taken_half":   # the new code IS set: another one is a change with it as the old one
        def other():
            just = st.get("a")
            st.clear()
            _forget(form, "own_a", "own_b")
            st.update(mode="own", change=True, old=just)
            keep_for(st, ("old",), form, (), refresh)   # RAM only, gone on success, Back or after 2 min (U2)
            refresh()
        items.append(ui.row([ui.button(tr(OTHER_CODE), other), ui.stretch()]))
    items.append(ui.row([ui.button(tr(CODE_BACK), lambda: (st.clear(), _forget(form, "own_a", "own_b"), refresh())), ui.stretch(),
                         ui.button(tr(CODE_NEXT_OWN), go, primary=True,
                                   enabled=bool(r.get("ok")) and same and not checking)]))
    return items


# ---------- D (Oliver/lead 12.11.): the 30-day copy of a device that left the sync – back under Settings → Backup ----------
REMOVED_BACK = "Restore data from before removing (until {date})"
REMOVED_ASK = ("Bring back the data this device had before it left the sync? Your current state is saved first. "
               "Bent°Corner restarts afterwards.")
REMOVED_BACK_KEY = "Restore"
REMOVED_FAILED = "The data couldn't be restored – your current state is back."


def removed_items(ui, ctrl, mem, refresh):
    """The newest copy still within its 30 days: one line [Restore data from before removing (until …)] – asked in
    place (no pop-up), then datastore.restore_backup (the current state is saved first) and a restart."""
    from system import datastore
    rows = datastore.removed_copies()
    if not rows:
        return []
    r = rows[0]
    date = time.strftime("%d.%m.%Y", time.localtime(r["until"]))
    if not mem.get("ask"):
        out = [ui.row([ui.button(tr(REMOVED_BACK).format(date=date), lambda: (mem.update(ask=True), refresh())),
                       ui.stretch()])]
        if mem.get("failed"):
            out.append(ui.label(tr(REMOVED_FAILED), color="gray"))
        return out

    def back():
        mem.clear()
        try:
            ok = datastore.restore_backup(r["folder"])
        except (OSError, ValueError, datastore.RestoreError):
            ok = False
        if ok and hasattr(ctrl, "restart_after_restore"):
            ctrl.restart_after_restore()
            return
        mem["failed"] = True
        refresh()
    return [ui.note(tr(REMOVED_ASK)),
            ui.row([ui.button(tr(REMOVED_BACK_KEY), back, primary=True),
                    ui.button(tr(CANCEL), lambda: (mem.clear(), refresh())), ui.stretch()])]


# ---------- A4: the protection code asked for an action (legal 07.11.) – the web's pages/guardfield.js alike ----------
GUARD_NEED = "You need your protection code for this."
GUARD_WRONG = "That protection code isn't right."
GUARD_WAIT = "Too many wrong codes – try again in {n} min."
GUARD_WAIT_SEC = "Too many wrong codes – try again in {n} sec."   # the pause grows from 1 s (legal 07.11.)


def wait_line(wait):
    """The server's pause (1, 2, 4 … s, at most 1 h): seconds under a minute, else whole minutes rounded up."""
    s = max(1, int(wait or 1))
    return tr(GUARD_WAIT_SEC).format(n=s) if s < 60 else tr(GUARD_WAIT).format(n=-(-s // 60))
GUARD_FIELD = "Protection code"
GUARD_KEY = "guard_code"   # the field's key in the form – its draft is dropped after sending


# ---------- „Code verloren?“ – a new protection code requested (legal A4/A5 07.11., the web's pages/guardreq.js) ----------
GUARD_SET = "A protection code is set."   # the status line above „Lost your code?“ (lead 07.11., T2/T3)
# Einfach für Endnutzer (lead/Oliver 07.11., PLAN-EINFACH C/D; legal 07.11.)
CODE_ONLINE_ONLY = ("The protection code protects your online backup and your devices (removing, deleting). It doesn't "
                    "apply to backup files – treat every backup file like a key.")   # legal 07.11. (W2)
CODE_TROUBLE = "Problems with the code?"
ORBIT_SETTINGS = "Change Orbit settings"
RESTORE_NEW = "Restore on a new device"
CHANGE_CODE = "Change protection code"   # legal 07.11. (PLAN-EINFACH D: under „Problems with the code?“)
CHANGE_OLD = "First your current protection code:"   # legal 07.11.
CODE_CHANGED = ("From now on only the new protection code works – also for restoring your online backup. You can throw "
                "away the old one.")   # legal 07.11.: required after a change
LOST = "Lost your code?"
LOST_KEY = "Request a new protection code"
LOST_TAKES = "– takes 14 days."
REQ_TITLE = "New protection code"
REQ_WHY = ("This is your new protection code – write it down or keep it in a password manager; we can't send it to you. "
           "It won't work for the next 14 days: during that time all your devices show the request, and it can be "
           "declined with the old code.")
REQ_SEND = "Request"
REQ_BUSY = "Sending the request …"
REQ_MINE = "Request made. If nobody declines with the old code, your new protection code applies on {date}."
REQ_OTHER = ("One of your devices wants a new protection code – because the old one is lost? If that isn't you, decline "
             "with your protection code and then remove the unknown device with ✕ in the list of your devices. Otherwise "
             "the new code applies from {date}.")   # legal 08.11. (B5: the ✕ instead of „Remove device“)
REQ_DECLINE = "Decline (with protection code)"
REQ_FAILED = "That didn't work – try again later."


def fmt_when(sec):
    """The server's date (seconds) in local time with the time – „8.11., 14:05“ / „8 Nov, 14:05“ (lead: the test
    instance waits 10 minutes; never reckoned here)."""
    import time as _t
    from system import i18n
    try:
        lt = _t.localtime(int(sec))
    except (TypeError, ValueError, OverflowError, OSError):
        return "…"
    if not sec:
        return "…"
    hm = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    if i18n.LANG == "de":
        return f"{lt.tm_mday}.{lt.tm_mon}., {hm}"
    return f"{lt.tm_mday} {_t.strftime('%b', lt)}, {hm}"


def fold(ui, mem, key, title, items, refresh):
    """A folded part (PLAN-EINFACH): the title as a key with › / ‹, the items only while open (this page's memory)."""
    is_open = bool(mem.get(key))

    def flip():
        mem[key] = not is_open
        refresh()
    return [ui.col([ui.row([ui.button(title + (" ‹" if is_open else " ›"), flip), ui.stretch()])]
                   + (list(items) if is_open else []), spacing=6)]


def to_orbit(ctrl):
    """[Change Orbit settings]: General → the Orbit slider (the same place the devices page and the veil use)."""
    ctrl.stream.show_page("settings", back=True)
    ctrl.show_settings("privacy")


def lost_items(ui, on_lost):
    return [ui.row([ui.label(tr(LOST), color="gray", fixed=True), ui.button(tr(LOST_KEY), on_lost),
                    ui.label(tr(LOST_TAKES), color="gray", fixed=True), ui.stretch()])]


def open_request(ctrl):
    """From another page (Your devices – an A4 field there): Settings → Backup with the request page."""
    b = ctrl.shell.backends.get("settings") if getattr(ctrl, "shell", None) else None
    if b is not None:
        bu = b.__dict__.setdefault("backup_ui", {})
        bu["req"] = {}
        bu.pop("guard", None)
    status(ctrl).pop("delete_guard", None)
    ctrl.show_settings("backup")


def _watch_leave(ctrl, st):
    """The new code lives only in this page's memory until it is sent (lead/performance 07.11.): another section or
    another page drops it."""
    if st.get("_watching"):
        return
    st["_watching"] = True

    def drop(*_):
        st.pop("req", None)
        st.pop("code_changed", None)   # the line after a code change: until another section or page
    ls = getattr(ctrl, "settings_listeners", None)
    if ls is not None:
        ls.append(lambda key: key != "backup" and drop())
    sig = getattr(getattr(ctrl, "shell", None), "pageChanged", None)
    if sig is not None:
        try:
            sig.connect(lambda key, *_: key != "settings" and drop())
        except (TypeError, RuntimeError):
            pass


def request_items(ui, ctrl, st, refresh, on_back, on_done):
    """The request page: the new code shown once, the last 5 TYPED (no paste), only then guard_request_confirm sends
    (performance) – the key and its envelope. st: {code, typed, sent} – RAM only; ok -> on_done (the page closes)."""
    if not st.get("code"):
        code = ctrl.guard_request_prepare() if hasattr(ctrl, "guard_request_prepare") else None
        if not code:
            return []
        st["code"] = code
    code, g = st["code"], status(ctrl).get("guard")
    if st.get("sent") and g == "ok":
        st.clear()
        on_done()
        return []
    ok5 = st.get("typed", "").strip().upper() == last5(code)

    def typed(v):
        st["typed"] = v
        refresh()

    def copy():
        from PySide6 import QtGui
        QtGui.QGuiApplication.clipboard().setText(code)

    def send():
        if ok5 and ctrl.guard_request_confirm(code, st["typed"].strip().upper()):
            st["sent"] = True
        refresh()

    def back():   # nothing was sent – the new code is dropped
        st.clear()
        on_back()
    items = [ui.label(tr(REQ_TITLE), px=22, bold=True),
             ui.label(f"<span style='font-family:monospace; font-size:20px; letter-spacing:2px'>{blocks(code)}</span>",
                      rich=True),
             ui.row([ui.button(tr(CODE_COPY), copy), ui.stretch()]),
             ui.note(tr(REQ_WHY)),
             ui.label(tr(CODE_FIELD)),
             ui.edit(st.get("typed", ""), typed, key="request_last5", live=typed, placeholder="•••••", nopaste=True,
                     enter=lambda _t: (st.pop("sent", None), send()) if ok5 and not (st.get("sent") and g == "busy") else None)]
    if st.get("sent") and g == "busy":
        items.append(ui.note(tr(REQ_BUSY)))
    elif st.get("sent") and g == "wait":
        items.append(ui.label(wait_line(status(ctrl).get("guard_wait")), color="gray"))
    elif st.get("sent") and g in ("error", "wrong"):   # nothing changed – the same code may go again
        items.append(ui.label(tr(REQ_FAILED), color="gray"))
    busy = st.get("sent") and g == "busy"
    items += [ui.row([ui.button(tr(CODE_BACK), back, enabled=not busy), ui.stretch(),
                      ui.button(tr(REQ_SEND), lambda: (st.pop("sent", None), send()), primary=True,
                                enabled=ok5 and not busy)])]
    return items


NOTICE_TITLE = "Protection code"


def foreign_request(ctrl):
    """Another device asked for a new protection code (not this one): the dot on „Your devices“ (lead 07.11.)."""
    if not built() or not hasattr(ctrl, "guard_request_info"):
        return False
    try:
        info = ctrl.guard_request_info()
    except Exception:  # noqa: BLE001 – a dot is never worth an error
        return False
    return bool(info) and not (getattr(ctrl, "settings", None) or {}).get("sync_guard_mine")


def request_unseen(ctrl):
    """Another device's request runs: Settings at the top + „Backup“ pulse orange (PLAN-EINFACH D) – until the request is
    answered (declined or in effect), not only until its page was opened (lead 11.11., Oliver's test round: opening
    the page stopped it before he could see it)."""
    return foreign_request(ctrl)


def request_seen(ctrl):
    """Its frame was shown (qsettings._build) – the pulse goes on until the request is answered (lead 11.11.); kept so
    the callers stay as they are."""
    return None


def notice_group(ui, ctrl, mem, refresh, form=None):
    """Another device's request in its own frame (lead 07.11.: it stands out from the sync text) – [] when none."""
    if not foreign_request(ctrl):
        return []
    items = notice_items(ui, ctrl, mem, refresh, form)
    return [ui.group(tr(NOTICE_TITLE), items)] if items else []


def notice_items(ui, ctrl, mem, refresh, form=None, on_lost=None):
    """A request running (guard_request_info): this device's own line (sync_guard_mine) or – on every other device –
    legal's big line with [Decline (with protection code)] (A4 field, guard_decline). mem: the page's RAM dict."""
    info = ctrl.guard_request_info() if hasattr(ctrl, "guard_request_info") else None
    if not info:
        mem.clear()
        return []
    until = info.get("until")
    mine = (getattr(ctrl, "settings", None) or {}).get("sync_guard_mine")
    if mine:
        return [ui.label(tr(REQ_MINE).format(date=fmt_when(until or mine.get("until"))), bold=True)]
    g = status(ctrl).get("guard")
    if mem.get("sent") and g == "ok":
        mem["declined"] = True   # gone at the next exchange – until then not asked again
        mem.pop("sent", None)
    if mem.get("declined"):
        return []
    items = [ui.label(tr(REQ_OTHER).format(date=fmt_when(until)), bold=True, px=16)]

    def go(code):
        mem["sent"] = True
        ctrl.guard_decline(code)
        refresh()

    def cancel():
        mem.clear()
        refresh()
    if mem.get("sent") and g in ("wrong", "wait"):
        items += guard_items(ui, g, status(ctrl).get("guard_wait"), mem.setdefault("code", {}), REQ_DECLINE, go, cancel, form)
    elif mem.get("sent") and g == "busy":
        items.append(ui.note(tr(CHECKING)))
    elif mem.get("ask"):
        items += guard_items(ui, "need", None, mem.setdefault("code", {}), REQ_DECLINE, go, cancel, form)
    else:
        if mem.get("sent") and g == "error":
            items.append(ui.label(status(ctrl).get("text") or tr(REQ_FAILED), color="gray"))
        items.append(ui.row([ui.button(tr(REQ_DECLINE), lambda: (mem.update(ask=True), mem.pop("sent", None), refresh())),
                             ui.stretch()]))
    return items


def guard_items(ui, state, wait, mem, go_label, on_go, on_cancel, form=None, on_lost=None):
    """The code before an action (performance: sync_status delete_guard need | wrong | wait + guard_wait s). The key
    or Enter sends (lead 11.11.); focus loss only keeps the text (a click elsewhere must never delete anything). mem: the
    page's RAM dict – U2 (lead 11.11.): the typed code stays in the field while it is checked and after a wrong code,
    never in a draft or the settings; it goes on Cancel, when the action asks afresh (it went through) or after 2 min.
    The wrong/wait line is always there (shown or hidden): the field is never rebuilt, the focus stays."""
    if mem.get("sent") and state == "need":   # the last try went through – this is a new question: an empty field
        mem.clear()
        if form is not None and hasattr(form, "forget"):
            form.forget(GUARD_KEY)

    def keep(text):
        mem["code"] = text
        mem.pop("sent", None)

    def forget():
        mem.clear()
        if form is not None and hasattr(form, "forget"):
            form.forget(GUARD_KEY)

    def send(_text=None):
        code = (mem.get("code") or "").strip()
        if not code:
            return
        mem["sent"] = True
        keep_for(mem, ("code", "sent"), form, (GUARD_KEY,))
        on_go(code)

    def cancel():
        forget()
        on_cancel()
    line = tr(GUARD_WRONG) if state == "wrong" else wait_line(wait) if state == "wait" else ""
    items = [ui.label(tr(GUARD_NEED)),
             ui.form([(tr(GUARD_FIELD), ui.edit(mem.get("code") or "", keep, key=GUARD_KEY, live=keep, secret=True,
                                                reveal=True, enter=send, focus=True))]),
             slot(ui, line)]
    items.append(ui.row([ui.button(tr(CANCEL), cancel),
                         ui.button(tr(go_label), send, enabled=bool((mem.get("code") or "").strip())), ui.stretch()]))
    if on_lost is not None:   # legal A4: „Lost your code? [Request a new protection code] – takes 14 days.“
        def lost():
            forget()
            on_lost()
        items += lost_items(ui, lost)
    return items


# ---------- Settings → Backup: the same switch, deleting asked inline ----------
def settings_items(ui, ctrl, b, refresh, more=()):
    """The box „Online backup“; more: folded parts at its end (What is on the server, Moving – PLAN-EINFACH C)."""
    if not built():   # without the sync built in: Settings → Backup as before
        return []
    from system import orbit
    s = ctrl.settings
    full = orbit.level(s) == "full"
    on = full and s.get("sync_backup") is True
    st = b.__dict__.setdefault("backup_ui", {})
    ss = status(ctrl)
    if st.get("rescue") is not None:   # turning on / a new code: the rescue page right here
        def done():
            if (st.pop("rescue", None) or {}).get("was_change"):   # legal 07.11.: the old code is void – say so once
                st["code_changed"] = True
                _watch_leave(ctrl, st)
            refresh()
        return [ui.group(tr(GROUP), rescue_items(ui, ctrl, st["rescue"], refresh,
                                                    on_back=done, on_done=done, form=getattr(b, "form", None)))]
    if st.get("req") is not None:   # „Code verloren?“: the request page right here (A5)
        _watch_leave(ctrl, st)

        def req_end():
            st.pop("req", None)
            refresh()
        items = request_items(ui, ctrl, st["req"], refresh, on_back=req_end, on_done=req_end)
        if items:
            return [ui.group(tr(GROUP), items)]
        st.pop("req", None)

    def start_request():
        ss.pop("delete_guard", None)
        st.pop("guard", None)
        st["req"] = {}
        refresh()

    def flip(v):
        if v:
            st["rescue"] = {}
        else:
            st["ask_delete"] = True
        refresh()

    def delete(yes, code=None):
        st.pop("ask_delete", None)
        if yes and available(ctrl):
            ctrl.vault_delete(code) if code else ctrl.vault_delete()
        refresh()

    def guard_cancel():
        ss.pop("delete_guard", None)   # nothing was sent – back to the page as it was
        refresh()
    from ui import qsync   # the test server's access code missing: its line first (T2 07.11.)
    items = qsync.gate_items(ui, ctrl, st.setdefault("gate", {}), refresh, getattr(b, "form", None))
    if card_due(ctrl):   # existing users: legal's card (also right in „What's new?“ after the update)
        items.append(card_items(ui, ctrl, st, refresh))
    items.append(ui.check(tr(SWITCH), on, flip, enabled=full))
    items.append(ui.note(tr(SCOPE)))   # legal 07.11. (Art. 13): what goes up, visible when switching on
    if not full:   # the same layout, the online parts dimmed – and the way to the Orbit (PLAN-EINFACH D)
        items += [ui.note(tr(ONLY_FULL)), ui.label(tr(CODE_ONLINE_ONLY), color="gray"),
                  ui.row([ui.button(tr(ORBIT_SETTINGS), lambda: to_orbit(ctrl)), ui.stretch()])]
    elif on:
        items.append(ui.note(tr(CODE_ONLINE_ONLY)))
    else:
        items.append(ui.note(tr(CODE_ONLINE_ONLY)))
    guard = ss.get("delete_guard")   # a protection code is set: asked before deleting (legal A4) – never an error line
    if guard in ("need", "wrong", "wait") and not ss.get("busy"):
        items += guard_items(ui, guard, ss.get("guard_wait"), st.setdefault("guard", {}), DELETE,
                             lambda code: delete(True, code), guard_cancel, getattr(b, "form", None),
                             on_lost=start_request)
    elif st.get("ask_delete"):
        # DELETE_ASK says it already: the other devices stop syncing – no second line (lead 08.11., step 10)
        items += [ui.label(tr(DELETE_ASK)),
                  ui.row([ui.button(tr(DELETE), lambda: delete(True), danger=True),
                          ui.button(tr(CANCEL), lambda: delete(False)), ui.stretch()])]   # equal, nothing on Enter
    elif ss.get("deleted") is True:
        items.append(ui.note(tr(DELETED)))
    elif ss.get("deleted") is False:   # the server first, then off (lead 07.11.): nothing changed – say so
        items.append(ui.label(tr(DELETE_FAILED), color="gray"))
    # with a protection code set, a new one needs the old one (performance: need_old) – the key waits for that page (A4)
    guarded = getattr(ctrl, "guard_on", lambda: False)()
    framed = []
    if on and guarded and not st.get("ask_delete") and not guard:   # a request running: the lines (A5); else „lost?“
        items.append(ui.label(tr(GUARD_SET)))
        if st.get("code_changed"):
            items.append(ui.label(tr(CODE_CHANGED), bold=True))
        running = hasattr(ctrl, "guard_request_info") and ctrl.guard_request_info()
        if not running:   # one statement per state – „lost?“ folded (PLAN-EINFACH D)
            change = ui.row([ui.button(tr(CHANGE_CODE), lambda: (st.update(rescue={"change": "old"}), refresh())),
                             ui.stretch()])
            items += fold(ui, st.setdefault("folds", {}), "trouble", tr(CODE_TROUBLE),
                          lost_items(ui, start_request) + [change], refresh)
        elif foreign_request(ctrl):   # another device's: its own frame above (lead 07.11.)
            framed = notice_group(ui, ctrl, st.setdefault("notice", {}), refresh, getattr(b, "form", None))
        else:
            items += notice_items(ui, ctrl, st.setdefault("notice", {}), refresh, getattr(b, "form", None))
    # never reached the server (access code missing, not synced yet): it can't know whether a code exists (T2 07.11.)
    unknown = ss.get("gate") == "missing" or ss.get("reached") is False
    if on and not st.get("ask_delete") and not guarded and not guard and not unknown:   # while deleting is asked: only the question
        items += [ui.row([ui.button(tr(NEW_CODE), lambda: (st.update(rescue={}), refresh())), ui.stretch()]),
                  ui.note(tr(NEW_CODE_NOTE))]
    # restoring only where this PC doesn't sync (lead 07.11.: fresh, removed, switched off) – else it gets in the way
    eng = getattr(ctrl, "sync_engine", None)
    syncing = bool(eng is not None and eng.on())
    restore = []
    if full and not st.get("ask_delete") and not guard and not syncing:
        # an online backup here before (deleted, or this device synced once): nothing to restore here – folded
        meta = getattr(eng, "meta", None) or {}
        had = ss.get("deleted") is not None or bool(meta.get("seeded") or meta.get("deleted_off"))
        if on or had:   # set up already: the rare way „a new device without the old one“ – folded (lead 07.11./08.11.)
            restore = fold(ui, st.setdefault("folds", {}), "restore", tr(RESTORE_NEW),
                           [restore_items(ui, ctrl, st, refresh, getattr(b, "form", None))], refresh)
        else:    # never an online backup on this device: the fitting way in, open
            items.append(restore_items(ui, ctrl, st, refresh, getattr(b, "form", None)))
    if (more or restore) and not st.get("ask_delete") and not guard:
        items += [ui.line()] + restore + list(more)
    return framed + [ui.group(tr(GROUP), items)]


def restore_items(ui, ctrl, st, refresh, form=None):
    """„Restore with protection code“: a password field, never pre-filled; the key reads it once and empties the page
    memory and the form's draft at once – the code only in the call (ports/lead 07.11.)."""
    rs = status(ctrl).get("rescue")

    def typed(v):
        st["restore_code"] = v

    def go():
        code = (st.pop("restore_code", "") or "").strip()
        _forget(form, "restore_code")
        if available(ctrl) and code:
            st["restore_sent"] = True
            ctrl.sync_rescue_restore(code)
        refresh()
    line = None
    if st.get("restore_sent"):
        line = {"wrong": WRONG, "error": NO_NET}.get(rs)
    return ui.col([ui.label(tr(RESTORE), bold=True),
                   ui.row([ui.edit("", typed, key="restore_code", live=typed, secret=True,
                                   placeholder=tr(RESTORE_FIELD), enter=lambda _t: go()),
                           ui.button(tr(RESTORE), go)]),
                   ui.label(tr(line), color="gray") if line else None], spacing=6)


# ---------- existing users in Full Orbit: the card right in „What's new?“ after the update (lead 06.11.) ----------
def card_due(ctrl):
    """Full Orbit, not asked yet, the backup not on: the card belongs where it is seen after the update."""
    from system import orbit
    s = ctrl.settings
    return built() and orbit.level(s) == "full" and s.get("sync_asked") is None and s.get("sync_backup") is not True


def news_items(ui, ctrl, d, refresh):
    """The card under the points of „What's new?“. „Turn on backup“: the dialog closes, Settings → Backup opens with
    the rescue code page (nothing goes up before it is confirmed); „Continue without backup“: answered right here."""
    if not card_due(ctrl):
        return []

    def turn_on():
        d.close("backup")
        b = ctrl.shell.backends.get("settings") if getattr(ctrl, "shell", None) else None
        if b is not None:
            b.__dict__.setdefault("backup_ui", {})["rescue"] = {}
        ctrl.stream.show_page("settings", back=True)
        ctrl.show_settings("backup")

    def without():
        answer_without(ctrl)
        refresh()
    return [ui.line(), ui.label(tr(CARD)),
            ui.row([ui.button(tr(CARD_ON), turn_on), ui.button(tr(CARD_OFF), without), ui.stretch()])]


def answer_without(ctrl):
    if hasattr(ctrl, "sync_offer_answer"):
        ctrl.sync_offer_answer(False)
    else:   # until performance's branch is in: the answer only (sync_asked = when) – nothing is uploaded either way
        import time
        ctrl.settings["sync_asked"] = int(time.time())
        ctrl.settings_changed()


# ---------- existing users in Full Orbit: the card in Settings → Backup too (sync_asked missing) ----------
def card_items(ui, ctrl, st, refresh):
    def turn_on():
        st["rescue"] = {}
        refresh()

    def without():
        answer_without(ctrl)
        refresh()
    return ui.col([ui.label(tr(CARD)),
                   ui.row([ui.button(tr(CARD_ON), turn_on), ui.button(tr(CARD_OFF), without), ui.stretch()])],
                  spacing=8)
