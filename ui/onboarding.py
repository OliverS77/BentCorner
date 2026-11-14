"""First-run setup, part 2 – in the program window, while the card database is already loading in the background.

Part 1 (language, storage location, games) runs before the program in the small window (setupui.py, FirstRun.qml) and
sets settings["onboarding"] = "profile". Leaner setup 0.9.8 (Oliver/Gordon/lead 13.11.): one sentence per step, the
rest behind „▸ More“. It continues here, step by step on ONE page:

    profile     The name friends see (the card back behind „▸ Card back“)
    friends     Bent°Corner Orbit: Core · Near Orbit · Full Orbit (slider; Full = the exchange, with terms of use) –
                a consent; with the online backup the protection code page follows (rescue, not a step of its own)
    finish      Still loading (progress + time left) or "All set" – plus the game (ui/scalper.py)

Out of the setup since 0.9.8 (lead 13.11.): the anonymous numbers (off until switched on under Settings → Friends &
privacy), keeping running in the background / start with Windows (Settings → General), updates (Settings → Updates,
defaults as before), the backup line and the Fortune Card.

While something loads, a small line at the top right says so, with „Play“: the game (ui/scalper.py) takes the page area
(„Back to setup“ above it), the step stays.

The step is stored in the settings – anyone who closes the program in between lands there again on the next start.
"""
import time

from PySide6 import QtCore, QtGui

from system import contacts
from system.i18n import tr

STEPS = ("profile", "friends", "rescue", "finish")
# the rescue code is a page of the Orbit step (only with the online backup on) – it doesn't count as a step of its own.
# The numbers count from the end: „Step n of m“ with m = settings["setup_steps"] (5, or 4 without the storage step)
FROM_END = {"profile": 1, "friends": 0, "rescue": 0}
OLD = ("stats", "background", "wait", "done")   # older setups closed in between: they land on the finish page
LOADING = ("carddb", "pack")   # jobs the setup waits for: card database (Scryfall) and data packs
# Card database (Magic): share of each section in the total duration – for bar and time left
PHASES = (("Scryfall fragen", 0.02), ("Kartendaten: herunterladen", 0.45), ("Kartendaten: einlesen", 0.35),
          ("Sprachen", 0.08), ("Suchindex", 0.10))


def active(settings):
    return settings.get("onboarding") in STEPS + OLD


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
                   "more": False, "backs": False, "play": False}
        self.dlg = None
        self.t0, self.f0, self.job = None, 0.0, None
        self.had_download, self.sig = False, None
        self.timer = QtCore.QTimer(ctrl, interval=1500, timeout=self._tick)
        bridge = getattr(ctrl, "bridge", None)   # the rescue code's upload reports through the sync row's signal
        if bridge is not None and hasattr(bridge, "sync_state"):
            bridge.sync_state.connect(lambda: self.dlg.refresh() if self.dlg is not None and self.step == "rescue" else None)

    # ---------- Flow ----------
    @property
    def step(self):
        s = self.s.get("onboarding") or "finish"
        return "finish" if s in OLD else s

    def go(self, step):
        self.st["more"] = False
        self.s["onboarding"] = step
        self.ctrl.settings_changed()
        if self.dlg is not None:
            self.dlg.refresh()

    def back(self):
        i = STEPS.index(self.step)
        if 0 < i < STEPS.index("finish"):
            self.go("friends" if STEPS[i - 1] == "rescue" else STEPS[i - 1])   # back past the code page: the Orbit step

    def finish(self):
        self.timer.stop()
        self.s.pop("onboarding", None)
        self.s.pop("setup_backup_later", None)   # (only the setup's own state – the lamp decides by itself)
        self.s["profile_asked"] = True
        from net import anonstats
        if not anonstats.asked(self.s):   # not asked in the setup any more (lead 13.11.): off, never a later question
            self.s["stats_share"] = False
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

    def _play(self, on):
        self.st["play"] = bool(on)
        if self.dlg is not None:
            self.dlg.refresh()

    # ---------- Pages ----------
    def build(self, ui, d):
        step = self.step
        total = int(self.s.get("setup_steps") or 5)
        head = [ui.label(tr(f"Step {total - FROM_END[step]} of {total}"), color="gray", fixed=True)
                if step in FROM_END else None, ui.stretch(), self._indicator(ui)]
        playing = self.st["play"] and step != "finish"   # the finish page has the game anyway
        if step != "finish" and not playing and self._loading():
            head.append(ui.button(tr("Play"), lambda: self._play(True)))   # no play triangle: not in the symbol font
        if playing:
            body = [ui.row([ui.button(tr("Back to setup"), lambda: self._play(False), primary=True), ui.stretch()]),
                    self._game(ui, 290, on_go=lambda: self._play(False))]   # „let's go“: back to the step
        else:
            body = getattr(self, "_" + step)(ui)
        return ui.col([ui.row([h for h in head if h is not None])] + body, spacing=12)

    def _game(self, ui, fit, on_go=None):
        """The game sized so the page never scrolls (lead 13.11.: 1280x720 the smallest target) – fit = the px
        the rest of the page and the window need around it (MirrorNode cGame). done/on_go (scanner 13.11.): when the
        download finishes WHILE playing, the game shows its own strip „Done – keep playing or let's go“ – the pages
        keep their structure for that (only values change), so the game is never started anew."""
        from ui import scalper
        node = scalper.node(ui, self.s, self.ctrl.settings_changed, done=not self._loading(), on_go=on_go)
        node["fit"] = fit
        return node

    def _more(self, ui, items):
        """„▸ More“: the rest of a step folded away (one sentence per step, lead 13.11.)."""
        out = [self._fold(ui, "more", tr("More"))]
        return out + (items if self.st["more"] else [])

    def _fold(self, ui, key, text):
        """„▸ text“ / „▾ text“ – small, on the left (not a full-width button)."""
        return ui.row([ui.button(("▾ " if self.st[key] else "▸ ") + text,
                                 lambda: (self.st.update({key: not self.st[key]}), self.dlg.refresh())), ui.stretch()])

    def _with_rescue(self):
        """The online backup is chosen in this setup: the sync built in, Full Orbit (picked or on) and the switch on."""
        from system import orbit
        from ui import backupui
        if not backupui.built():
            return False
        lv = self.st.get("orbit") or orbit.level(self.s)
        return lv == "full" and self.st.get("backup", True) is not False

    def _nav(self, ui, *buttons, back=True):
        row = [ui.button(tr("Back"), self.back)] if back else []
        return ui.row(row + [ui.stretch()] + list(buttons))

    def _profile(self, ui):
        from system import userprofile

        def next_(skip=False):
            userprofile.ensure(self.s, "" if skip else self.st["name"], self.st["back"])
            self.s["profile_asked"] = True
            self.go("friends")
        name = ui.edit(self.st["name"], lambda t: (self.st.update(name=t[:40]), next_()), key="name",
                       live=lambda t: self.st.update(name=t[:40]), placeholder=tr("Your name or nickname"))
        name["focus"] = True
        items = [ui.label(tr("What name should your friends see?"), px=22, bold=True), name,
                 self._fold(ui, "backs", tr("Card back"))]
        if self.st["backs"]:
            items.append(ui.pixel(self.st["back"], lambda b: self.st.update(back=b)))
        return items + [self._nav(ui, ui.button(tr("Later"), lambda: next_(skip=True)),
                                  ui.button(tr("Next"), next_, primary=True), back=False)]

    def _friends(self, ui):
        """Bent°Corner Orbit (Oliver, 2026-10-29) – replaces "Trade with friends? yes/no": one slider, three levels,
        each says exactly what leaves the device. Preselected: Near Orbit (prices on start were the default before) –
        Full Orbit is never preselected (privacy policy §5: off until you turn it on)."""
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
            from ui import backupui   # online backup chosen: the rescue code first – nothing goes up before (legal)
            on = want == "full" and self.st.get("backup", True) and backupui.available(self.ctrl) \
                and self.s.get("sync_backup") is not True
            self.go("rescue" if on else "finish")

        def confirm(on):
            if on:
                orbit.confirm_age(self.s)
                self.dlg.refresh()
        # one sentence (lead 13.11.; the consent texts go via Gordon to legal) – the rest behind „▸ More“
        items = [ui.label(tr("How far should your data travel?"), px=22, bold=True),
                 ui.space(6),
                 ui.orbit(orbit.LEVELS.index(lv), pick,   # back here after Full Orbit was set: what leaving does
                          leave=tr(orbit.LEAVE) if orbit.level(self.s) == "full" else "",
                          # „Daten online sichern, verschlüsselt“ right under the columns (lead 06.11.)
                          sync=__import__("ui.backupui", fromlist=["x"]).setup_sync(self.st, lv, self.dlg.refresh))]
        # the terms (legal 04.11., § 305 (2) BGB): whenever "Next" would turn Full Orbit on – also with the age
        # confirmed earlier (then without the age line); right above the age line when that is asked
        if lv == "full" and (orbit.level(self.s) != "full" or not orbit.age_ok(self.s)):
            items.append(ui.note(tr(orbit.TERMS_LINE).replace("{url}", contacts.SITE + "/nutzung.html")))
        if lv == "full" and not orbit.age_ok(self.s):
            items += [ui.check(tr(orbit.AGE), False, confirm), ui.note(tr(orbit.AGE_NOTE))]
        items += [ui.space(6)] + self._more(ui, [
            ui.label(tr("Orbit is everything around your collection: prices, marketplaces, friends and trading. The rings show how far your data travels.")),
            ui.row([ui.button(tr("Read privacy policy"), lambda: web("datenschutz.html")),
                    ui.button(tr("Terms of use"), lambda: web("nutzung.html")), ui.stretch()])])
        items.append(self._nav(ui, ui.button(tr("Next"), next_, primary=True)))
        return items

    def _rescue(self, ui):
        from ui import backupui

        def back():   # no backup – nothing uploaded; the Orbit page with the switch off
            self.st["backup"] = False
            self.go("friends")
        return backupui.rescue_items(ui, self.ctrl, self.st.setdefault("rescue", {}), self.dlg.refresh,
                                     on_back=back, on_done=lambda: self.go("finish"), form=getattr(self.dlg, "form", None))

    def _finish(self, ui):
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
        else:
            # loading and ready: the SAME structure (scanner 13.11.: a new structure restarts the game) – only texts
            # and „hidden“ change; the game gets done=True as a value and shows its strip if it is being played
            f, left = self._progress() if loading else (1.0, "")
            bar = ui.progress(int(f * 1000), 0, 1000, f"{self._what()} · " + (left or f"{int(f * 100)} %"))
            fold = self._fold(ui, "more", tr("More"))
            note = ui.note(tr("If you close Bent°Corner anyway, the download picks up where it left off next time."))
            go = ui.row([ui.button(tr("Let's go"), self.finish, primary=True), ui.stretch()])
            bar["hidden"] = fold["hidden"] = not loading
            note["hidden"] = not loading or not self.st["more"]
            go["hidden"] = loading
            info = [ui.label(tr("Almost done – the data is still loading.") if loading
                             else tr("All set – hold a card up to the camera."), px=22, bold=True), bar, fold, note, go]
        # fit constant (330): the field never jumps while playing
        return [ui.col(info, spacing=10), self._game(ui, 330, on_go=self.finish)]


def start(ctrl):
    ob = Onboarding(ctrl)
    ctrl.onboarding = ob
    ob.show()
    return ob
