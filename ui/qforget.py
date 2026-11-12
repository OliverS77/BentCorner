"""Settings → "Delete Bent°Corner" (the last page; labs/installer/PLAN.md § 5.1, texts legal 03.11.2026 § 8 word for
word). Everything inline, no pop-up:

    1. "Export your collection first?" [Go to export]
    2. the server checkbox (preselected; only with an own ID, else the line "There is nothing of yours …") – version
       A or B as net/forget.available() says (asked once in the background; offline = A)
    3. the local checkbox (never preselected) with the latest backup – kept, or inside the data folder [Save elsewhere],
       or none [Create a backup now]
    4. [Delete Bent°Corner] (red): the server first (in the background), its result as a line under the button
       ("Deleted." only when the server confirmed it); then this PC – the portable line and [Quit now]: only that key
       ends the program so the `--wipe-local` process can delete (open databases can't be deleted on Windows)
       Failed: red "NOT deleted" with the deadlines, the mail and the own ID [Copy] – [Try again] [Continue without
       deleting server data]

The steps live in Forget (no UI – tests drive it with a runner that calls at once); page(ui, ctrl) draws them.
"""
import os
import pathlib
import sys
import time

from system.i18n import tr

RED = "#ff5252"   # the desktop's warning red (paused, camera off) – only the button and the NOT line

# legal 03.11.2026 (PLAN.md § 8) – word for word; {…} are filled in after tr()
EXPORT = "Export your collection first?"
EXPORT_GO = "Go to export"
A_CHECK = "Delete my shared lists and binders on the Bent°Corner server"
A_SMALL = ("Your ID (the address your friends find you by) and key remain until they haven't been used for 365 days. Parcels are deleted once picked up, at "
           "the latest after 14 days.")
B_CHECK = ("Delete my data on the Bent°Corner server – your ID (the address your friends find you by) and key, shared lists and binders, parcels and blocks. "
           "Immediately.")
B_SMALL = ("Exceptions: reports are kept for 180 days, and the server's backups still contain the data, encrypted, for "
           "up to 4 weeks (see privacy policy).")
BOTH = "Your friends will no longer see your shared lists and binders."
NO_ID = "There is nothing of yours on the Bent°Corner server."
LOCAL_CHECK = "Delete my collection and settings on this PC"
BACKUP_KEPT = "Your latest backup: {file}, {date} (will be kept)"
BACKUP_GOES = "Your latest backup: {file}, {date} – it is inside the data folder and will be deleted too."
BACKUP_ELSEWHERE = "Save elsewhere"
BACKUP_NONE = "No backup yet –"
BACKUP_MAKE = "Create a backup now"
BUTTON = "Delete Bent°Corner"
DONE = "Deleted."
ALREADY = "Was already deleted."
FAILED = ("Your data on the server is NOT deleted. Without use, the server deletes it automatically: shared lists and "
          "binders 6 months after they were last shared, your ID and key after 365 days, parcels once picked up, at "
          "the latest after 14 days. To have it deleted right away, email {mail}.")
FAILED_ID = "Your ID: {id} (please include it in the email)"
COPY = "Copy"
RETRY = "Try again"
SKIP = "Continue without deleting server data"
SKIP_LOCAL = ("After this, Bent°Corner can no longer delete the server data – the key exists only on this PC – note down "
              "your ID (above); then it works by email.")
PORTABLE = ("Deleted: {data}. Kept: the program folder {program} – delete it yourself (drag it to the Recycle Bin).")
QUIT = "Quit now"   # under the portable line: only this ends the program and starts the deleting (lead 03.11.)

# 0.9.7 (lead/legal 07.11., A7 – behind the sync switch): two equal keys instead of the checkboxes, nothing preselected
ONLY_HERE = "Delete only this device"
ALL_ONLINE = "Delete everything, online too"
ONLY_HERE_WHY = ("Deletes your collection and settings on this PC. Your other devices, your online backup and your friends "
                 "stay.")
ALL_ONLINE_WHY = ("First deletes your data on our server – online backup, mailbox, shared lists and binders and your ID – the address your friends find you by – "
                  "and then the data on this PC. Your other devices stop syncing; what's on them stays there. You'll need "
                  "to add friends again afterwards.")
LOST_DEVICE = "Device lost or no longer yours? Use “Remove device” on one of your other devices."
OFFLINE = ("No connection: your collection and settings on this PC are deleted; Bent°Corner only keeps the key f" "or deleting on the server until that has worked. We'll delete your data on our server as soon as Ben" "t°Corner is online again – until then Bent°Corner doesn't set anything new up here. If you uninstall" " Bent°Corner before that, your data on the server is deleted automatically after the periods in the " "privacy policy.")   # legal 07.11.: the key stays – said
LAST_DEVICE = ("If this is your last device, your online backup stays on our server for up to 183 days and is then d" "eleted – without a protection code you can't get to it in that time. If you don't want that, choose " "“Delete everything, online too”.")   # legal: always (we can't know it's the last)
NEEDS_NET = "“Delete everything, online too” needs a connection."   # with a protection code: no offline route (the code is never kept)
PENDING = "Your data on our server isn't deleted yet – that happens as soon as there's a connection."


def program_folder():
    """The folder the program runs from (portable: the user deletes it himself)."""
    if getattr(sys, "frozen", False):
        return str(pathlib.Path(sys.executable).resolve().parent)
    return str(pathlib.Path(__file__).resolve().parents[1])


class Forget:
    """The steps of the page. run(fn, done, on_error): fn in the background, done(result) back in the main thread –
    done(on_error) when fn raises."""

    def __init__(self, settings, *, run, changed, quit_after=None):
        self.settings, self.run, self.changed = settings, run, changed
        self.quit_after = quit_after          # (plan) -> None: start the deleting after exit and end the program
                                              # (only with [Quit now])
        self.server, self.local = True, False  # legal: the server one preselected, the local one never
        self.full = None                       # None = still asking the server (A or B)
        self.state = "idle"     # idle · server · failed · need_code · server_pending · server_done · local_done
        self.result = None
        self.guard_code = None                 # the protection code, typed for this one deletion (never stored)
        self.skipped = False
        self.plan = None
        self.choice = None                     # 0.9.7: "here" | "all" – nothing preselected (lead/legal 07.11.)
        self.typed = False                     # a code went with the last call: main_required = wrong, else needed
        self.guarded = lambda: False           # a protection code is set (the page sets ctrl.guard_on): no offline route

    def choose(self, kind):
        """The two keys: only this device (nothing sent) or everything, online too (the server first, then here)."""
        if self.state not in ("idle", "needs_net") or kind not in ("here", "all"):
            return
        self.state = "idle"   # after „needs a connection“ the other choice is still open
        self.choice = kind
        self.server, self.local = kind == "all", True
        self.changed()

    def code_state(self):
        """need_code -> the A4 field's state: wait (429, detail = seconds), wrong (a code was typed) or need."""
        r = self.result
        if r is not None and str(getattr(r, "detail", "") or "").isdigit():
            return "wait", int(r.detail)
        return ("wrong" if self.typed else "need"), None

    def cancel_code(self):
        if self.state == "need_code":
            self.state, self.typed = "idle", False
            self.changed()

    # ---------- what the page shows ----------
    def has_id(self):
        from net import forget
        return forget.has_id(self.settings)

    def ask_version(self):
        """Once per opening: A or B (offline = A). The checkbox text waits for it."""
        if self.full is not None or not self.has_id():
            return
        from net import forget
        self.full = None
        self.run(lambda: forget.available(self.settings), self._version, False)   # an error = A

    def _version(self, full):
        self.full = bool(full)
        self.changed()

    def can_start(self):
        server = self.server and self.has_id() and self.full is not None
        return self.state == "idle" and (server or self.local)

    # ---------- the button ----------
    def start(self):
        if not self.can_start():
            return
        if self.server and self.has_id():
            self._server()
        else:
            self._local()

    def _server(self):
        from net import forget
        self.state, self.result = "server", None
        self.changed()
        full = self.full
        kw = {"full": full}
        if self.guard_code:   # only when typed in (a protection code is set) – otherwise the call as always
            kw["guard_code"] = self.guard_code
        self.run(lambda: forget.delete_server(self.settings, **kw), self._server_done,
                 forget.Result(forget.FAILED, "error"))   # an error = NOT deleted

    def with_code(self, code):
        """A protection code is set (the server said main_required): the deletion again with it."""
        if self.state == "need_code":
            self.guard_code, self.typed = code, True
            self._server()

    def _server_done(self, r):
        from net import forget
        self.result = r
        self.guard_code = None
        if r is not None and r.status == forget.MAIN_REQUIRED:
            self.state = "need_code"   # the page asks for the protection code (429: detail = seconds to wait)
            self.changed()
            return
        from collection import syncrun
        offline = r is not None and r.status == forget.FAILED and getattr(r, "offline", False)
        if offline and self.local and syncrun.available() and self.guarded():
            # legal 07.11.: with a protection code the later deletion would need the code, which is never kept – so
            # „everything, online too“ needs a connection; nothing was deleted
            self.state = "needs_net"
            self.changed()
            return
        if (offline and self.local
                and syncrun.available()):   # 0.9.7 rule, behind the switch – off: as before (failed, try again)
            # no connection (lead 07.11.): this PC's data goes now; only the seed and a mark stay, the next start
            # online deletes on the server first – until then nothing new
            if forget.remember_pending(self.settings):
                self.state = "server_pending"
                self.changed()
                self._local()
                return
        if r is None or not r.ok:
            self.state = "failed"
            self.changed()
            return
        self.state = "server_done"
        self.changed()
        if self.local:
            self._local()

    def retry(self):
        if self.state in ("failed", "needs_net"):
            self._server()

    def skip(self):
        """Continue without deleting server data: then this PC (if chosen), else nothing more."""
        if self.state != "failed":
            return
        self.skipped = True
        if self.local:
            self._local()
        else:
            self.state = "idle"
            self.changed()

    def _local(self):
        from system import wipe
        self.plan = wipe.plan(self.settings)
        self.pending = self.state == "server_pending"   # the server part still waits (shown with the result)
        self.state = "local_done"
        self.changed()

    def finish(self):
        """[Quit now]: the deleting starts once the program has ended."""
        if self.state == "local_done" and self.plan is not None and self.quit_after:
            self.state = "quitting"
            self.changed()
            self.quit_after(self.plan)

    # ---------- texts of the result ----------
    def server_line(self):
        from net import forget
        if self.state in ("server_done", "local_done") and self.result is not None and not self.skipped:
            return tr(ALREADY) if self.result.status == forget.ALREADY else tr(DONE) if self.result.status == forget.DELETED else ""
        return ""

    def my_id(self):
        code = getattr(self.result, "code", "") or ""
        if not code:
            from net import relay
            try:
                code = relay.pretty(relay.my_code(self.settings))
            except Exception:  # noqa: BLE001
                code = ""
        return code


def backup_line(p):
    """The backup under the local checkbox: (text, kind) – kind "kept" / "goes" / "none"."""
    if not p.backup:
        return tr(BACKUP_NONE), "none"
    name = pathlib.Path(p.backup).name
    date = time.strftime("%d.%m.%Y", time.localtime(p.backup_time)) if p.backup_time else ""
    return tr(BACKUP_GOES if p.backup_goes else BACKUP_KEPT).format(file=name, date=date), "goes" if p.backup_goes else "kept"


# ---------- the page ----------
def _runner(ctrl):
    """fn in a thread, done(result) in the main thread (a queued signal, like the settings' counts)."""
    from PySide6 import QtCore

    class _Back(QtCore.QObject):
        done = QtCore.Signal(object, object)
    back = getattr(ctrl, "_forget_back", None)
    if back is None:
        back = ctrl._forget_back = _Back()
        back.done.connect(lambda cb, value: cb(value))

    def run(fn, done, on_error=None):
        import threading

        def work():
            try:
                value = fn()
            except Exception:  # noqa: BLE001 – a failure is a result too ("NOT deleted", version A)
                import logging
                logging.getLogger("booster").exception("Delete Bent°Corner")
                value = on_error
            back.done.emit(done, value)
        threading.Thread(target=work, name="delete-bentcorner", daemon=True).start()
    return run


def _quit_after(ctrl, form):
    def go(plan):
        from system import wipe
        ctrl.wiping = True               # no backup on exit: the collection is to go (app.request_quit)
        wipe.start_after_exit(plan)
        ctrl.force_quit = True
        ctrl.request_quit()
    return go


def state_of(ctrl, form):
    st = getattr(ctrl, "_forget", None)
    if st is None:
        st = ctrl._forget = Forget(ctrl.settings, run=_runner(ctrl), changed=form.soon, quit_after=_quit_after(ctrl, form))
    st.changed = form.soon
    st.guarded = lambda: bool(getattr(ctrl, "guard_on", lambda: False)())
    return st


def page(ui, b):
    ctrl = b.ctrl
    st = state_of(ctrl, b.form)
    st.ask_version()
    busy = st.state != "idle"
    items = [ui.row([ui.label(tr(EXPORT), fixed=True), ui.button(tr(EXPORT_GO), lambda: ctrl.show_import("coll_export")), ui.stretch()])]

    from collection import syncrun
    if syncrun.available():   # 0.9.7: the choice (lead/legal 07.11., A7)
        return _choice_page(ui, b, ctrl, st, items)

    # the server
    if not st.has_id():
        items.append(ui.note(tr(NO_ID)))
    elif st.full is None:
        items.append(ui.note("…"))       # asking the server which version (A or B) – the text follows
    else:
        def server(on):
            st.server = on
            b.form.soon()
        items += [ui.check(tr(B_CHECK if st.full else A_CHECK), st.server, server, enabled=not busy),
                  ui.note(tr(B_SMALL if st.full else A_SMALL)), ui.note(tr(BOTH))]

    # this PC
    from system import wipe
    p = wipe.plan(ctrl.settings)

    def local(on):
        st.local = on
        b.form.soon()
    text, kind = backup_line(p)
    ip = ctrl.import_page

    def make():
        ip.make_backup()
        b.form.soon()

    def elsewhere():
        from ui import qdialogs
        folder = qdialogs.get_dir(tr("Where should the backup go?"), "")
        if folder:
            import shutil
            try:
                dest = shutil.copy2(p.backup, folder)
                wipe.remember_backup(ctrl.settings, dest)   # now it is the latest backup – outside, so it stays
                ctrl.settings_changed()
                ip.bk_msg = tr("✓ Backed up: ") + str(dest)
            except OSError as e:
                ip.bk_msg = tr(f"Couldn't back up: {e}")
        b.form.soon()
    backup = [ui.label(text, color="gray", fixed=True)]
    if kind == "none":
        backup.append(ui.button(tr(BACKUP_MAKE), make, enabled=not busy))
    elif kind == "goes":
        backup.append(ui.button(tr(BACKUP_ELSEWHERE), elsewhere, enabled=not busy))
    items += [ui.check(tr(LOCAL_CHECK), st.local, local, enabled=not busy),
              ui.row(backup + [ui.stretch()])]
    if ip.bk_msg and kind != "kept":
        items.append(ui.note(ip.bk_msg))

    # the button and, right under it, what happened
    items.append(ui.row([ui.button(tr(BUTTON), st.start, enabled=st.can_start(), alert=RED), ui.stretch()]))
    if st.state == "server":
        items.append(ui.note("…"))
    line = st.server_line()
    if line:
        items.append(ui.label(line))
    if st.state == "failed":
        from system import contacts
        from PySide6 import QtGui
        code = st.my_id()
        items += [ui.label(tr(FAILED).format(mail=contacts.MAIL), color=RED)]
        if code:
            items.append(ui.row([ui.label(tr(FAILED_ID).format(id=code), fixed=True),
                                 ui.button(tr(COPY), lambda: QtGui.QGuiApplication.clipboard().setText(code)),
                                 ui.stretch()]))
        items.append(ui.row([ui.button(tr(RETRY), st.retry), ui.button(tr(SKIP), st.skip), ui.stretch()]))
        if st.local:
            items.append(ui.note(tr(SKIP_LOCAL)))
    if st.state in ("local_done", "quitting") and st.plan is not None:
        items += [ui.label(tr(PORTABLE).format(data=st.plan.folder, program=program_folder())),
                  ui.row([ui.button(tr(QUIT), st.finish, enabled=st.state == "local_done"), ui.stretch()])]
    return ui.col(items, spacing=10)


def _backup_items(ui, b, ctrl, st, busy):
    """The latest backup under the choice (legal 03.11.): kept / goes too [Save elsewhere] / none [Create a backup now]."""
    from system import wipe
    p = wipe.plan(ctrl.settings)
    text, kind = backup_line(p)
    ip = ctrl.import_page

    def make():
        ip.make_backup()
        b.form.soon()

    def elsewhere():
        from ui import qdialogs
        folder = qdialogs.get_dir(tr("Where should the backup go?"), "")
        if folder:
            import shutil
            try:
                dest = shutil.copy2(p.backup, folder)
                wipe.remember_backup(ctrl.settings, dest)
                ctrl.settings_changed()
                ip.bk_msg = tr("✓ Backed up: ") + str(dest)
            except OSError as e:
                ip.bk_msg = tr(f"Couldn't back up: {e}")
        b.form.soon()
    row = [ui.label(text, color="gray", fixed=True)]
    if kind == "none":
        row.append(ui.button(tr(BACKUP_MAKE), make, enabled=not busy))
    elif kind == "goes":
        row.append(ui.button(tr(BACKUP_ELSEWHERE), elsewhere, enabled=not busy))
    out = [ui.row(row + [ui.stretch()])]
    if ip.bk_msg and kind != "kept":
        out.append(ui.note(ip.bk_msg))
    return out


def _choice_page(ui, b, ctrl, st, items):
    """0.9.7: [Delete only this device] [Delete everything, online too] – equal, nothing preselected; legal's 03.11.
    sentences under the chosen one; with a protection code the A4 field (performance' need_code / with_code)."""
    from net import forget
    busy = st.state not in ("idle", "needs_net")
    has_id = st.has_id()
    if forget.pending():   # deleted here offline, the server part waits (performance' mark)
        items.insert(0, ui.label(tr(PENDING), bold=True))
    # selection = brightness: the chosen one normal, the other dimmed (nothing chosen yet: both normal)
    keys = [ui.button(tr(ONLY_HERE), lambda: st.choose("here"), active=st.choice == "here",
                      dim=st.choice == "all", enabled=not busy)]
    if has_id:   # never online: nothing there to delete
        keys.append(ui.button(tr(ALL_ONLINE), lambda: st.choose("all"), active=st.choice == "all",
                              dim=st.choice == "here", enabled=not busy and st.full is not None))
    items += [ui.row(keys + [ui.stretch()]), ui.note(tr(LOST_DEVICE))]
    if not has_id:
        items.append(ui.note(tr(NO_ID)))
    if st.choice == "here":
        items += [ui.note(tr(ONLY_HERE_WHY)), ui.note(tr(LAST_DEVICE))]
    elif st.choice == "all":
        items += [ui.note(tr(ALL_ONLINE_WHY)), ui.note(tr(B_SMALL if st.full else A_SMALL)), ui.note(tr(BOTH))]
    if st.choice:
        items += _backup_items(ui, b, ctrl, st, busy)
    if st.state == "need_code":   # legal A4: the field, never an error line; „lost?“ under it
        from ui import backupui
        state, wait = st.code_state()
        items += backupui.guard_items(ui, state, wait, b.__dict__.setdefault("forget_code", {}), BUTTON,
                                      st.with_code, st.cancel_code, getattr(b, "form", None),
                                      on_lost=lambda: (st.cancel_code(), backupui.open_request(ctrl)))
    else:
        items.append(ui.row([ui.button(tr(BUTTON), st.start, enabled=bool(st.choice) and st.can_start(), alert=RED),
                             ui.stretch()]))
    if st.state == "server":
        items.append(ui.note("…"))
    line = st.server_line()
    if line:
        items.append(ui.label(line))
    if st.state == "needs_net":   # a protection code is set and no connection: nothing deleted (legal 07.11.)
        items += [ui.label(tr(NEEDS_NET), color="gray"), ui.row([ui.button(tr(RETRY), st.retry), ui.stretch()])]
    if st.state == "failed":
        from system import contacts
        from PySide6 import QtGui
        code = st.my_id()
        items += [ui.label(tr(FAILED).format(mail=contacts.MAIL), color=RED)]
        if code:
            items.append(ui.row([ui.label(tr(FAILED_ID).format(id=code), fixed=True),
                                 ui.button(tr(COPY), lambda: QtGui.QGuiApplication.clipboard().setText(code)),
                                 ui.stretch()]))
        items.append(ui.row([ui.button(tr(RETRY), st.retry), ui.button(tr(SKIP), st.skip), ui.stretch()]))
        items.append(ui.note(tr(SKIP_LOCAL)))
    if st.state in ("local_done", "quitting") and st.plan is not None:
        if getattr(st, "pending", False):   # no connection: here now, the server later (lead 07.11.)
            items.append(ui.label(tr(OFFLINE), bold=True))
        items += [ui.label(tr(PORTABLE).format(data=st.plan.folder, program=program_folder())),
                  ui.row([ui.button(tr(QUIT), st.finish, enabled=st.state == "local_done"), ui.stretch()])]
    return ui.col(items, spacing=10)
