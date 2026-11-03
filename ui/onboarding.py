"""First-run setup, part 2 – in the program window, while the card database is already loading in the background.

Part 1 (language, storage location, games) runs before the program in the small window (setupui.py, FirstRun.qml) and
sets settings["onboarding"] = "profile". It continues here, step by step on ONE page:

    profile     Who is scanning here? (name + card back)
    friends     Bent°Corner Orbit: Core · Near Orbit · Full Orbit (slider; Full = the exchange, with terms of use)
    stats       Help make Bent°Corner better (anonymous numbers, yes/no equally weighted)
    background  Keep running in the background, start with Windows, check for updates / download automatically
    finish      Still loading (progress + time left) or "All set" – plus the Fortune Card and Scalper Invaders,
                playable even when nothing is loading any more

On every page a small line at the top right shows whether something is still loading in the background (card
database, data packs).

The step is stored in the settings – anyone who closes the program in between lands there again on the next start.
Everything here can be changed later in Settings (same switches: see qsetpages.py – if something asked here is
changed there, adjust it here too and vice versa).
"""
import time

from PySide6 import QtCore, QtGui

from system import contacts
from system.i18n import tr

STEPS = ("profile", "friends", "stats", "background", "finish")
LOADING = ("carddb", "pack")   # jobs the setup waits for: card database (Scryfall) and data packs
# Card database (Magic): share of each section in the total duration – for bar and time left
PHASES = (("Scryfall fragen", 0.02), ("Kartendaten: herunterladen", 0.45), ("Kartendaten: einlesen", 0.35),
          ("Sprachen", 0.08), ("Suchindex", 0.10))


def active(settings):
    return settings.get("onboarding") in STEPS + ("wait", "done")   # wait/done: older states = finish


def fraction(text):
    """Progress (0 … 1) from the card database's text and numbers."""
    if not text:
        return 0.0
    t, done, total = text
    before = 0.0
    for key, w in PHASES:
        if key in t:
            return before + (w * min(1.0, done / total) if total else 0.0)
        before += w
    return 0.0


class Onboarding:
    def __init__(self, ctrl):
        self.ctrl, self.s = ctrl, ctrl.settings
        from system import userprofile
        prof = userprofile.get(self.s) or {}
        self.st = {"name": prof.get("name") or "", "back": prof.get("back") or userprofile.DEFAULT_BACK,
                   "details": False, "tray": False, "autostart": False, "updates": True, "update_download": False}
        self.dlg = None
        self.t0, self.f0, self.job = None, 0.0, None
        self.had_download, self.sig = False, None
        self.timer = QtCore.QTimer(ctrl, interval=1500, timeout=self._tick)

    # ---------- Flow ----------
    @property
    def step(self):
        s = self.s.get("onboarding") or "finish"
        return "finish" if s in ("wait", "done") else s

    def go(self, step):
        self.s["onboarding"] = step
        self.ctrl.settings_changed()
        if self.dlg is not None:
            self.dlg.refresh()

    def back(self):
        i = STEPS.index(self.step)
        if 0 < i < STEPS.index("finish"):
            self.go(STEPS[i - 1])

    def finish(self):
        self.timer.stop()
        self.s.pop("onboarding", None)
        self.s.pop("setup_backup_later", None)   # (only the setup's own state – the lamp decides by itself)
        self.s["profile_asked"] = True
        self.ctrl.settings_changed()
        if self.dlg is not None:
            self.dlg.close(True)
        self.ctrl.recognizer.status = tr("All set – hold a card up to the camera.")
        if self.s.pop("setup_then", None) == "backup":   # "Set up ›" at the backup note: there, its first block pulses
            self.ctrl.stream.show_page("settings", tab="backup")
        else:
            self.ctrl.stream.show_page("library")   # after setup: into the (still empty) library

    def show(self):
        from ui import qdialogs
        self.dlg = qdialogs.show(tr("Setup"), self.build, wait=False, wide=900, on_back=self.back)
        self.timer.start()

    # ---------- Background downloads (card database, data packs) ----------
    def _jobs(self):
        c = self.ctrl
        return [j for j in ([c.current] if c.current else []) + list(c.jobs) if j.get("kind") in LOADING]

    def _loading(self):
        busy = bool(self._jobs())
        self.had_download = self.had_download or busy
        return busy

    def _tick(self):
        """Update the display – only if something really changed (otherwise the rebuild disturbed painting)."""
        f, left = self._progress()
        sig = (self.step, self._loading(), int(f * 100), left, bool(getattr(self.ctrl, "setup_error", "")))
        if sig != self.sig and self.dlg is not None:
            self.sig = sig
            self.dlg.refresh()

    def _progress(self):
        """-> (fraction 0 … 1, time-left text) of the running download."""
        cur = self.ctrl.current or {}
        p = getattr(self.ctrl, "setup_progress", None)
        if cur.get("kind") == "pack":
            f = (p[1] / p[2]) if p and p[2] else 0.0
        else:
            f = fraction(p)
        if cur is not self.job:   # different job: measure the time left anew
            self.job, self.t0, self.f0 = cur, None, 0.0
        now = time.time()
        if self.t0 is None and f > 0:
            self.t0, self.f0 = now, f
        left = ""
        if self.t0 is not None and f - self.f0 > 0.02:
            secs = (now - self.t0) * (1 - f) / (f - self.f0)
            left = tr(f"about {max(1, round(secs / 60))} min left") if secs >= 60 else tr("almost done")
        return f, left

    def _what(self):
        """What is loading right now, in words."""
        cur = self.ctrl.current or {}
        if cur.get("kind") == "pack":
            return cur.get("name") or tr("Data pack")
        return tr("Card data")

    def _indicator(self, ui):
        """Small line at the top right of every page: is something loading in the background?"""
        if getattr(self.ctrl, "setup_error", ""):
            return ui.label("⚠ " + tr("Download interrupted – continue on the last page"), color="gray", fixed=True)
        if self._loading():
            f, _left = self._progress()
            return ui.label("⟳ " + tr("In the background:") + f" {self._what()} · {int(f * 100)} %", color="gray", fixed=True)
        if self.had_download:
            return ui.label("✓ " + tr("Everything downloaded"), color="gray", fixed=True)
        return None

    # ---------- Pages ----------
    def build(self, ui, d):
        step = self.step
        n = STEPS.index(step) + 4
        head = ui.row([ui.label(tr(f"Step {n} of 8"), color="gray", fixed=True), ui.stretch(), self._indicator(ui)])
        body = getattr(self, "_" + step)(ui)
        return ui.col([head] + body, spacing=12)

    def _nav(self, ui, *buttons, back=True):
        row = [ui.button(tr("Back"), self.back)] if back else []
        return ui.row(row + [ui.stretch()] + list(buttons))

    def _profile(self, ui):
        from system import userprofile

        def next_(skip=False):
            userprofile.ensure(self.s, "" if skip else self.st["name"], self.st["back"])
            self.s["profile_asked"] = True
            self.go("friends")
        return userprofile.profile_items(ui, self.st) + [
            self._nav(ui, ui.button(tr("Later"), lambda: next_(skip=True)),
                      ui.button(tr("Next"), next_, primary=True), back=False)]

    def _friends(self, ui):
        """Bent°Corner Orbit (Oliver, 2026-10-29) – replaces "Trade with friends? yes/no": one slider, three levels,
        each says exactly what leaves the device. Preselected: Near Orbit (prices on start were the default before) –
        Full Orbit is never preselected (privacy policy §5: off until you turn it on)."""
        from net import relay
        from system import orbit

        def web(page):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(contacts.SITE + "/" + page))

        lv = self.st.setdefault("orbit", orbit.level(self.s))   # the slider only moves – the level applies with "Next"

        def pick(i):
            self.st["orbit"] = orbit.LEVELS[i]
            self.dlg.refresh()

        def next_():   # Full Orbit only with the age line on (legal 03.11.) – otherwise Near Orbit
            want = self.st["orbit"]
            if want == "full" and not orbit.age_ok(self.s):
                want = "near"
            orbit.set_level(self.ctrl, want)
            self.go("stats")

        def confirm(on):
            if on:
                orbit.confirm_age(self.s)
                self.dlg.refresh()
        items = [ui.label(tr("Do you want to use Bent°Corner Orbit?"), px=22, bold=True),
                 ui.label(tr("Orbit is everything around your collection: prices, marketplaces, friends and trading. The rings show how far your data travels.")),
                 ui.space(6),
                 ui.orbit(orbit.LEVELS.index(lv), pick,   # back here after Full Orbit was set: what leaving does
                          leave=tr(orbit.LEAVE) if orbit.level(self.s) == "full" else "")]
        if lv == "full" and not orbit.age_ok(self.s):
            items += [ui.check(tr(orbit.AGE), False, confirm), ui.note(tr(orbit.AGE_NOTE))]
        items += [ui.space(6),
                  ui.row([ui.button(tr("Read privacy policy"), lambda: web("datenschutz.html")),
                          ui.button(tr("Terms of use"), lambda: web("nutzung.html")), ui.stretch()])]
        if relay.enabled(self.s):
            items.append(ui.label(tr(f"Your ID: <b>{relay.pretty(relay.my_code(self.s))}</b> – give it to friends who want to add you. You add friends in your profile."),
                                  rich=True))
        items.append(self._nav(ui, ui.button(tr("Next"), next_, primary=True)))
        return items

    def _stats(self, ui):
        from net import anonstats

        def answer(yes):
            self.s["stats_share"] = bool(yes)
            self.go("background")
        items = [ui.label(tr("Help make Bent°Corner better"), px=22, bold=True),
                 ui.label(tr("Once a week Bent°Corner sends a few numbers: which games and which parts of the app you use – not what you do with them. No cards, no name, no ID. That shows me what is really used, so I can plan updates for exactly that. So you help decide what gets better next.")),
                 ui.note(tr("Completely voluntary, change it any time under Settings → Friends & privacy.")),
                 ui.button(("▾ " if self.st["details"] else "▸ ") + tr("Show what gets sent"),
                           lambda: (self.st.update(details=not self.st["details"]), self.dlg.refresh()))]
        if self.st["details"]:
            items.append(ui.label(anonstats.describe(anonstats.payload(self.s)).replace("\n", "<br>"), rich=True,
                                  color="gray"))
        items.append(self._nav(ui, ui.button(tr("No, thanks"), lambda: answer(False)),
                               ui.button(tr("Yes, I'll help"), lambda: answer(True))))
        return items

    def _background(self, ui):
        from ui import tray
        st = self.st

        def setv(k, v):
            st[k] = bool(v)
            if k == "tray" and not v:
                st["autostart"] = False
            if k == "updates" and not v:
                st["update_download"] = False
            self.dlg.refresh()

        def next_():
            self.s["tray_mode"] = st["tray"]
            self.ctrl.tray.apply()
            if tray.autostart_possible():
                tray.set_autostart(st["tray"] and st["autostart"])
            self.s["updates"], self.s["update_download"] = st["updates"], st["update_download"]
            self.ctrl.updater_apply()
            self.go("finish")
        bg = [ui.check(tr("Keep running in the background (daily prices, price alerts)"), st["tray"],
                       lambda v: setv("tray", v))]
        if tray.autostart_possible():   # not possible (test start, without .exe): don't show the row at all
            bg.append(ui.check(tr("Start with Windows (hidden in the system tray)"), st["autostart"],
                               lambda v: setv("autostart", v), enabled=st["tray"]))
        return [ui.label(tr("Should Bent°Corner keep running in the background?"), px=22, bold=True),
                ui.label(tr("Then you get price alerts and update notices even when the window is closed. Bent°Corner sits as a small icon at the bottom right next to the clock."))] + bg + [
                ui.note(tr("Change it any time under Settings → General.")),
                ui.line(),
                ui.check(tr("Check for updates and let me know"), st["updates"], lambda v: setv("updates", v)),
                ui.check(tr("Download updates automatically"), st["update_download"],
                         lambda v: setv("update_download", v), enabled=st["updates"],
                         tip=tr("Off: Bent°Corner only tells you, and downloads when you click – handy when nothing should slow your connection (e.g. while gaming online).")),
                ui.note(tr("Change it any time under Settings → Updates.")),
                self._nav(ui, ui.button(tr("Next"), next_, primary=True))]

    def _finish(self, ui):
        from ui import scalper
        err = getattr(self.ctrl, "setup_error", "")
        loading = self._loading()
        if err:
            def retry():
                job = getattr(self.ctrl, "setup_error_job", None) or {"kind": "carddb", "code": "db"}
                self.ctrl.setup_error = ""
                self.ctrl.enqueue(job["kind"], job.get("code"), front=True,
                                  **{k: v for k, v in job.items() if k in ("name", "label")})
                self.dlg.refresh()
            info = [ui.label(tr("A download got stuck."), px=22, bold=True),
                    ui.label(err, color="gray"),
                    ui.note(tr("Usually the connection just dropped for a moment. What's already downloaded is kept.")),
                    ui.row([ui.button(tr("Try again"), retry, primary=True), ui.stretch()])]
        elif loading:
            f, left = self._progress()
            info = [ui.label(tr("Almost there!"), px=22, bold=True),
                    ui.label(tr("The data is still downloading – Bent°Corner needs to stay open for that. Pass the time with Scalper Invaders. You can keep playing once everything is done, too.")),
                    ui.progress(int(f * 1000), 0, 1000, f"{self._what()} · " + (left or f"{int(f * 100)} %")),
                    ui.note(tr("If you close Bent°Corner anyway, the download picks up where it left off next time."))]
        else:
            info = [ui.label(tr("All set! 🎉"), px=22, bold=True),
                    ui.label(tr("Hold a card up to the camera – Bent°Corner recognizes it and adds it to your collection. Or play another round: you'll find the game later under Settings → Game, too.")),
                    ui.row([ui.button(tr("Let's go"), self.finish, primary=True), ui.stretch()])]
        # backups (Oliver, 29.10.): no step of its own – one quiet line. Two ways (review .101): "Set up now" (Settings →
        # Backup, pulsing) or "Later" – then the lamp on Settings simply stays on until a target is set up
        # (or "I'm aware of the risks" there)
        after = self.s.get("setup_then") == "backup"
        later = self.s.get("setup_backup_later") is True

        def not_now():
            self.s["setup_backup_later"] = True
            self.s.pop("setup_then", None)
            self.dlg.refresh()

        def backup():
            self.s.pop("setup_backup_later", None)
            if loading or err:   # still downloading: Settings → Backup opens right after the setup
                self.s["setup_then"] = "backup"
                self.dlg.refresh()
            else:
                self.s["setup_then"] = "backup"
                self.finish()
        info += [ui.space(4),
                 ui.note(tr("Bent°Corner supports local backups – automatically, too, into a cloud folder (OneDrive, Google Drive …) or onto a USB stick.")),
                 ui.row([ui.button(tr("Opens after the setup ✓") if after else tr("Set up now ›"), backup,
                                   primary=not (after or later)),
                         ui.button(tr("Later ✓") if later else tr("Later"), not_now,
                                   tip=tr("The lamp on Settings stays on until a backup is set up")),
                         ui.stretch()])]
        return [ui.row([ui.col(info, spacing=10), ui.fortune()], spacing=18),
                scalper.node(ui, self.s, self.ctrl.settings_changed)]


def start(ctrl):
    ob = Onboarding(ctrl)
    ctrl.onboarding = ob
    ob.show()
    return ob
