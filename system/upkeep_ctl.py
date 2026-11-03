"""Updates, messages from the team, voluntary usage numbers and the automatic backup for the main window (updater.py,
teamnews.py, anonstats.py, autobackup.py do the work). APP-SPLIT phase C."""
import logging
import threading
import time

from PySide6 import QtCore

import games
from system import datahome
from system.i18n import tr
from ui import qdialogs

log = logging.getLogger("booster")   # the same logger as app.py


class UpkeepControl:
    """Mixin of MainWindow (app.py) – moved there unchanged (docs/APP-SPLIT.md, phase C). self is the MainWindow."""

    # ---------- Updates (updater.py) ----------
    def updater_setup(self):
        from collection import collectibles
        from net import updater
        updater.cleanup_old()
        if not getattr(self, "_collectibles_done", False):   # back up tickets & co. (data/collectibles)
            self._collectibles_done = True
            QtCore.QTimer.singleShot(15000, collectibles.startup)
        if getattr(self, "updater", None) is not None:
            return
        from net import teamnews
        self.updater = updater.Updater(on_change=lambda: self.bridge.update_changed.emit(),
                                       news=lambda: teamnews.enabled(self.settings))
        self.bridge.update_changed.connect(self._update_changed)
        self._upd_t = QtCore.QTimer(self, interval=updater.CHECK_EVERY * 1000, timeout=self.update_check)
        self.updater_apply()
        if self.settings.get("updates", True):
            QtCore.QTimer.singleShot(30000, self.update_check)
        QtCore.QTimer.singleShot(45000, self.anonstats_tick)

    def updater_apply(self):
        """Switch "Check for updates" changed: regular checking on/off."""
        t = getattr(self, "_upd_t", None)
        if t is None:
            return
        if self.settings.get("updates", True):
            t.start()
        else:
            t.stop()

    def update_check(self):
        """Check; download only with "Download updates automatically" – otherwise just notify. Never in a test start
        (otherwise a test would replace the real exe)."""
        import version
        # never while developing, in a test start or in work-in-progress builds (0.8.21.3 – only on the dev's PC; they
        # are newer than everything on the server anyway and shouldn't count as an "active installation")
        if self.settings.get("updates", True) and not datahome.TEST and datahome.FROZEN and version.is_release():
            self.updater.check(auto_download=bool(self.settings.get("update_download")))

    # ---------- Emergency switch per game (games/offswitch.py) ----------
    def games_off_check(self, manifest):
        """A game switched off (or on again) in the update manifest: gone from the game picker, an open one is left
        for Magic, and everyone gets the notice once – also those who never had the game open. Data stays."""
        from games import offswitch
        went_off, back = offswitch.apply(manifest.get("games_off"))
        if not went_off and not back:
            return
        shell = getattr(self, "shell", None)
        if shell is not None:
            shell.gamesChanged.emit()
        for key in back:
            self.stream_toast(tr(f"{games.name_of(key)} is available again."))
        if not went_off:
            return
        text = "\n\n".join(offswitch.reason(k) for k in went_off)
        if games.current().key in went_off:
            text += "\n\n" + tr(f"Bent°Corner switches to {games.name_of(games.DEFAULT)} now.")
            self._leave_off_game()
        names = ", ".join(games.name_of(k) for k in went_off)
        qdialogs.ask(tr(f"No longer available: {names}"), text, wait=False)

    def _leave_off_game(self):
        """The open game was switched off: to Magic – if jobs are still running, again in half a minute."""
        from games import offswitch
        if offswitch.is_off(games.current().key) and not self.switch_game(games.DEFAULT):
            QtCore.QTimer.singleShot(30000, self._leave_off_game)

    # ---------- Inbox from the team (teamnews.py) ----------
    def team_inbox_changed(self, toast=False):
        from net import teamnews
        n = teamnews.unread(self.settings)
        if toast and n:
            self.stream_toast(tr(f"Message from the Bent°Corner team – see profile ({n} new)"))
        self.autobackup_badge()

    # ---------- Voluntary anonymous numbers (anonstats.py) ----------
    def anonstats_tick(self):
        """Ask once (yes/no equally weighted); afterwards send at most once a week – only with consent."""
        from net import anonstats
        anonstats.bind(self.settings)
        if not anonstats.asked(self.settings):
            from ui import onboarding
            if onboarding.active(self.settings):   # the first-run setup is asking right now
                QtCore.QTimer.singleShot(60000, self.anonstats_tick)
                return
            shell = getattr(self, "shell", None)
            if shell is not None and getattr(shell, "sheets", None) is not None and shell.sheets.covering:
                QtCore.QTimer.singleShot(60000, self.anonstats_tick)   # another dialog is open right now: later
                return
            self.anonstats_ask()
            return
        if anonstats.due(self.settings):
            s = self.settings

            def work():
                try:
                    if anonstats.send(s):
                        self.bridge.update_changed.emit()
                except Exception:  # noqa: BLE001 – offline: again next week
                    pass
            threading.Thread(target=work, daemon=True).start()
        if not getattr(self, "_stats_t", None):
            self._stats_t = QtCore.QTimer(self, interval=6 * 3600 * 1000, timeout=self.anonstats_tick)
            self._stats_t.start()

    def anonstats_ask(self):
        from net import anonstats
        sample = anonstats.describe(anonstats.payload(self.settings))
        answer = qdialogs.ask(
            tr("Help with anonymous numbers?"),
            tr("Once a week Bent°Corner could send a small packet without any identifier – no ID, no name, no cards. Oliver only sees totals from it: which games are collected and how often tickets are used. Voluntary, changeable any time under Settings → Friends & privacy.") +
            "\n\n" + tr("This would be sent:") + "\n" + sample,
            [("no", tr("No, thanks"), ""), ("yes", tr("Yes, gladly"), "")])
        if answer not in ("yes", "no"):   # "← Back": not decided yet – ask again at the next start
            return
        self.settings["stats_share"] = answer == "yes"
        self.settings_changed()
        if answer == "yes":
            QtCore.QTimer.singleShot(5000, self.anonstats_tick)

    def _update_changed(self):
        u = self.updater
        if u.manifest and u.state in ("none", "available", "ready", "downloading"):
            from net import teamnews
            if teamnews.take_news(self.settings, u.manifest.get("news"), games.current().key):
                self.settings_changed()
                self.team_inbox_changed(toast=True)
            self.games_off_check(u.manifest)
        shell = getattr(self, "shell", None)
        if shell is not None:   # update in the download circle at the top: progress, then checkmark + "Install"
            shell.jobsChanged.emit()
            self.autobackup_badge()   # lamp on Settings: update ready or backup missing
            if u.state == "ready" and not getattr(self, "_upd_told_ready", False):
                self._upd_told_ready = True
                self.stream_toast(tr(f"Update {u.latest} is downloaded – install it with the download button at the top."))
        if u.state == "available" and not self.settings.get("update_download") \
                and getattr(self, "_upd_told", None) != u.latest:   # don't download automatically: just notify
            self._upd_told = u.latest
            self.tray.notify(tr("Update available"),
                             tr(f"Bent°Corner {u.latest} is out – download it under Settings → Updates."))
        pb = getattr(getattr(self, "shell", None), "backends", {}).get("settings")
        if pb is not None and hasattr(pb, "refresh"):
            try:
                pb.refresh()
            except Exception:  # noqa: BLE001
                pass

    def update_install(self):
        from ui.busy import busy
        try:
            with busy(self, tr("Installing update …")):
                self.save_session()
                self.save_collection()
                self.save_settings()
                self.updater.install()
        except Exception as e:  # noqa: BLE001
            log.exception("Installing update")
            self.stream_toast(tr(f"Update not installed: {e}"))
            return
        log.info("Update installed – restarting")
        self.restart()

    # ---------- Automatic backup (autobackup.py) ----------
    def autobackup_setup(self):
        if getattr(self, "_ab_t", None) is None:
            # every minute ("after each change" waits 2 minutes of quiet); the mark on Settings only every 5th time
            self._ab_n = 0
            self._ab_t = QtCore.QTimer(self, interval=60 * 1000, timeout=self.autobackup_check)
            self._ab_t.start()
            self.bridge.backup_done.connect(self._autobackup_done)
        QtCore.QTimer.singleShot(20000, self.autobackup_check)
        self.autobackup_badge()

    def autobackup_check(self, force=False):
        """Due (or force)? Then back up quietly in the background – save the current state first."""
        from system import autobackup
        from system import undo
        if getattr(self, "_ab_busy", False):
            return False
        if not force and not autobackup.due(self.settings, undo.LAST_WRITE[0]):
            self._ab_n = getattr(self, "_ab_n", 0) + 1
            if self._ab_n % 5 == 0:
                self.autobackup_badge(only_changed=True)   # every 5 minutes: anything new not backed up? -> mark
            return False
        if not force and self.autobackup_hold():
            return False   # camera/scan or the game running: the next minute again
        self._ab_busy = True
        try:
            self.save_collection()
            self.save_session()
        except Exception:  # noqa: BLE001
            log.exception("Saving before backup")
        s = self.settings

        def work():
            autobackup.background_thread()   # low CPU/disk priority – a scan or the UI never feels it
            try:
                res = autobackup.run(s, force=force, only_changed=not force)   # by hand: always a fresh one
            except Exception:  # noqa: BLE001
                log.exception("Automatic backup")
                res = []
            try:
                self.bridge.backup_done.emit(res)
            except RuntimeError:
                pass
        self._ab_thread = threading.Thread(target=work, daemon=True)
        self._ab_thread.start()
        return True

    def autobackup_hold(self):
        """Not now: the camera runs (scanning) or the game (Scalper Invaders) is open – the backup waits for quiet."""
        cam = getattr(self, "camera", None)
        if cam is not None and getattr(cam, "running", False):
            return True
        stream = getattr(self, "stream", None)
        return getattr(stream, "page", "") == "settings" and getattr(self, "settings_page", "") == "game"

    def autobackup_on_exit(self):
        """Closing: one last backup if the content changed since the last one – invisibly, at most EXIT_LIMIT
        seconds (a slow cloud folder, a stick pulled out: caught up at the next start). A backup already running
        is waited for instead."""
        from system import autobackup
        c = autobackup.cfg(self.settings)
        if not c["on"] or not c["targets"]:
            return
        t = getattr(self, "_ab_thread", None)
        if t is None or not t.is_alive():
            s = self.settings

            def work():
                autobackup.background_thread()
                try:
                    autobackup.run(s, force=True, only_changed=True)
                except Exception:  # noqa: BLE001
                    log.exception("Backup on exit")
            t = threading.Thread(target=work, daemon=True)
            t.start()
        t.join(autobackup.EXIT_LIMIT)
        if not t.is_alive():
            self.save_settings()   # time and checksum of the backup

    def _autobackup_done(self, res):
        self._ab_busy = False
        for path, ok, text in res:
            log.info("Backup %s: %s (%s)", "ok" if ok else "not possible", path, text)
            if ok:
                self.settings["last_backup"] = time.time()
        self.settings_changed()
        self.autobackup_badge()
        ip = getattr(self, "import_page", None)
        if ip is not None and hasattr(ip, "_changed"):
            ip._changed()

    def autobackup_badge(self, only_changed=False):
        """Exclamation mark (Import/Export, later Profile) as long as the data isn't backed up anywhere else – and the
        pages that show it anew. only_changed (the 5-minute check): nothing at all unless a mark or the backup notice
        changed – otherwise the profile with all its binder tiles was rebuilt every 5 minutes (a stutter in an open
        binder)."""
        from system import autobackup
        from net import teamnews
        u = getattr(self, "updater", None)
        state = (teamnews.unread(self.settings) > 0, autobackup.attention(self.settings),
                 bool(u is not None and u.state in ("ready", "available")), autobackup.lamp(self.settings))
        if only_changed and state == getattr(self, "_badge_state", None):
            return
        self._badge_state = state
        st = getattr(self, "stream", None)
        if st is not None and hasattr(st, "set_badge"):
            # Profile: unread team message (requests are shown by the friends icon next to it)
            st.set_badge("profile", state[0])
            # Settings: backup missing (until at least one is set up) or update ready
            warn = bool(state[3])   # the lamp follows lamp(); the notice text (state[1]) may stay without it
            # (the backup lamp only lights up in the settings: button at the top + "Backup" tab)
            st.set_badge("settings", warn or state[2])
            st.set_badge("import", False)
            ib = getattr(getattr(self, "shell", None), "backends", {}).get("import")
            if ib is not None:
                ib.changed.emit()
            sp = getattr(getattr(self, "shell", None), "backends", {}).get("settings")
            if sp is not None:
                sp.changed.emit()
        pb = getattr(getattr(self, "shell", None), "backends", {}).get("profile")
        if pb is not None:
            pb.refresh()
