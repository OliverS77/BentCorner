"""The job queue of the main window: enqueue, pause/cancel, estimate, the worker that runs one job after the other
(downloads, prices, card database, packs …), what happens when a job is done, progress. APP-SPLIT phase C."""
import logging
import threading
import time

from PySide6 import QtCore, QtGui

import games
from cards import carddb, currency, library, pricehist
from scanner import ocrscan
from scanner.common import BASE
from system.i18n import tr
from ui.scanlook import mix

log = logging.getLogger("booster")   # the same logger as app.py
JOB_TEXT = {}   # label per job kind – filled by app.py after the language is set (the texts are translated there)


class Cancelled(Exception):
    pass


def fmt_duration(sec):
    if sec < 60:
        return f"{max(1, round(sec))} s"
    if sec < 3600:
        return tr(f"{round(sec / 60)} min")
    return f"{sec / 3600:.1f} h"


class JobQueue:
    """Mixin of MainWindow (app.py) – moved there unchanged (docs/APP-SPLIT.md, phase C). self is the MainWindow."""

    def on_progress(self, text, done, total):
        now = time.time()
        if (self.current or {}).get("kind") in ("carddb", "pack"):   # for the first-run setup (onboarding.py)
            self.setup_progress = (text, done, total)
        self.job_progress = (text, done, total)
        if now - getattr(self, "_jobs_emit_t", 0) > 0.25:   # download circle/games bar at most 4× per second
            self._jobs_emit_t = now
            self.jobs_changed()
        if text != self._phase[0]:
            self._phase = (text, now, done)
        elif total and done - self._phase[2] >= 5:
            rate = (now - self._phase[1]) / (done - self._phase[2])
            job = self.current or {}
            is_img = "images" in text.lower() or "bilder" in text.lower()   # cards/library.download_set
            if is_img and job.get("kind") == "download" and not job.get("was_installed"):
                self.img_rate = min(3.0, rate)
            elif "merkmale" in text.lower():
                self.feat_rate = min(1.0, rate)
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        text = tr(text)
        self.progress.setFormat(f"{text}  %v / %m" if total else text)

        if "bilder" in text.lower() and total:
            left = (total - done) * self.img_rate + total * self.feat_rate + 1.5
        elif "merkmale" in text.lower() and total:
            left = (total - done) * self.feat_rate + 1.5
        else:
            left = self.job_estimate(self.current) if self.current else 0
        left += sum(self.job_estimate(j) for j in self.jobs)
        waiting = sum(1 for j in self.jobs if j["kind"] in JOB_TEXT)
        parts = [text]
        if waiting:
            parts.append(tr(f"{waiting} more in the queue"))
        if left >= 3:
            parts.append(tr(f"done in about {fmt_duration(left)} (≈ {time.strftime('%H:%M', time.localtime(now + left))})"))
        self.data_info.setStyleSheet("")
        self.data_info.setText("  ·  ".join(parts))

    def _carddb_pending(self):
        return any(j["kind"] == "carddb" for j in self.jobs + ([self.current] if self.current else []))

    @staticmethod
    def independent_job(j):
        """Job that isn't tied to the open game: data bundle, card database with a fixed target game."""
        return j.get("kind") == "pack" or (j.get("kind") == "carddb" and bool(j.get("for")))

    def jobs_changed(self):
        shell = getattr(self, "shell", None)
        if shell is not None and hasattr(shell, "jobsChanged"):
            shell.jobsChanged.emit()
            shell.gamesChanged.emit()

    def job_fraction(self):
        """Progress (0 … 1) of the running job – card database by its sections, otherwise done/total."""
        cur = self.current or {}
        p = getattr(self, "job_progress", None)
        if not cur or not p:
            return 0.0
        if cur.get("kind") == "carddb":
            from ui import onboarding
            return onboarding.fraction(p)
        return (p[1] / p[2]) if p[2] else 0.0

    def on_job_done(self, job, msg, error):
        self.current = None
        kind = job["kind"]
        if job.get("paused") and job.get("cancelled"):   # paused: waits at the front of the list to be resumed
            self.jobs.insert(0, job)
            self.refresh_sets()
            self.next_job()
            return
        if kind == "prices" and not error and not job.get("cancelled"):
            self.settings[f"price_ok_{job.get('game') or 'mtg'}"] = time.time()
            self.settings_changed()
        pending = getattr(self, "_pending_switch", None)
        if pending is not None:   # game switch was waiting for this job to end (cancel)
            self._pending_switch = None
            self.progress.setVisible(False)
            self.refresh_sets()
            key, then = pending
            self.switch_game(key, then=then)
            return
        pal = QtGui.QGuiApplication.palette()
        msg, error = tr(msg) if msg else msg, tr(error) if error else error
        if error:
            self.last_msg = error
            self.data_info.setStyleSheet("color: #e06c75;")
            self.data_info.setText(error)
        else:
            if msg:
                self.last_msg = msg
            elif kind in ("load", "rebuild") and not self.jobs:
                msg = self.last_msg or (tr(f"{len(self.cards)} cards recognizable.") if self.cards else "")
            if msg:
                self.data_info.setStyleSheet(
                    f"color: {mix(pal.color(QtGui.QPalette.Window), pal.color(QtGui.QPalette.WindowText), 0.6)};")
                self.data_info.setText(msg)
        changed = not job.get("cancelled") and (
            kind in ("download", "remove", "import", "prices")
            or (kind == "update" and not any(j["kind"] == "update" for j in self.jobs)))
        if changed and not any(j["kind"] == "rebuild" for j in self.jobs):
            # make new sets recognisable right away; after price updates only once all are through
            self.jobs.insert(0, {"kind": "rebuild", "code": None, "name": ""})
        self.refresh_sets()
        if job.get("dl_game") and not error and not job.get("cancelled") and not job.get("missing") \
                and not self._game_downloading(job["dl_game"]):
            self._game_downloaded(job["dl_game"])
        if job.get("missing") and job.get("dl_game"):   # asked for in the games bar: say so (else it looks broken off)
            self.stream_toast(msg)
        if kind in ("carddb", "pack"):   # the first-run setup shows the error with "Try again"
            from ui import onboarding
            self.setup_error = error if onboarding.active(self.settings) else ""
            self.setup_error_job = dict(job) if error else None
        if kind == "pack" and not error and not job.get("cancelled") and not job.get("missing"):
            # bundle here: take over its database (Pokémon), reload recognition with the index of all cards
            if job.get("code") == games.current().key:   # newer version: take it over now (otherwise at the next start)
                if games.current().market_fix is not None:
                    type(games.current())._fix = None   # read new marketplace corrections
                from cards import finishes
                finishes.clear_cache()
                carddb._upgrade_checked.discard(carddb.DB_PATH)
                from system import orbit
                if carddb.exists() and games.current().update_prices is not None and orbit.prices_on(self.settings):
                    self.enqueue("prices", "all", label="€", name=tr("Prices (all cards)"))   # corrected mappings
            self.refresh_db_info()
            if carddb.exists() and self.settings.get("first_setup") and not self._carddb_pending():
                self.settings["first_setup"] = False
                self.settings_changed()
            self.update_fingerprints(self.cards)
        if kind == "carddb":
            self.refresh_db_info()
            self.reprice_collection()
            self.update_fingerprints(self.cards)  # index of all cards needs the card database
            if self.settings.get("first_setup") and carddb.exists():
                self.settings["first_setup"] = False
                self.settings_changed()
                self.recognizer.status = tr("All set – hold a card up to the camera.")
                from ui import onboarding
                if not onboarding.active(self.settings):   # setup open: it sends to the Library at the end
                    self.stream.show_page("scan", animate=False)
            ocrscan._names, ocrscan._local = None, None  # reload name directories
            if not error and games.current().key != "mtg" and job.get("for") in (None, games.current().key):
                # the open game's database is new (Lorcana right after switching to it): its sets and the card data
                # come from it – the window still shows the empty state of the switch
                self.catalog_sets = library.cached_sets()
                self.catalog_by_code = {s["code"]: s for s in self.catalog_sets}
                self.refresh_sets()
                self.enqueue("load")
        if kind in ("pricehist", "prices"):
            self.refresh_ph_info()
            if kind == "pricehist" and not error:   # open detail/alert views now show the chart
                from ui import librarycore
                librarycore.PriceData.refresh_all()
                tb = getattr(getattr(self, "shell", None), "backends", {}).get("trade")
                if tb is not None:
                    tb.alarmChanged.emit()
            if kind == "prices":
                self.reprice_collection()
                if not error:
                    self.check_alarms()
                    self.reprice_market_fix()
                if games.current().price_source == "daily":   # the price history has grown as well
                    from ui import librarycore
                    librarycore.PriceData.refresh_all()
            if self.library_win is not None and self.library_win.detail.row is not None:
                self.library_win.detail.fill_text()
        if kind == "images" and self.library_win is not None:
            self.library_win.loader.failed.clear()
        if kind == "load" and not getattr(self, "_after_start_done", False):   # only at program start – after a
            self._after_start_done = True                                       # game switch the jobs come later
            self.after_start()
        self.next_job()

    def enqueue(self, kind, code=None, front=False, **extra):
        key = (kind, code)
        if any((j["kind"], j["code"]) == key for j in self.jobs):
            return
        if self.current and (self.current["kind"], self.current["code"]) == key and kind != "rebuild":
            return
        job = {"kind": kind, "code": code,
               "name": tr("Card database (Scryfall, offline)") if kind == "carddb" else self.set_title(code) if code else ""}
        if kind == "download":
            job["was_installed"] = any(s["code"] == code for s in self.installed)
        job["game"] = games.current().key
        job.update(extra)
        self.jobs.insert(0, job) if front else self.jobs.append(job)
        self.refresh_sets()
        self.next_job()

    def pause_job(self, job, on=True):
        """Pause/resume a download (download circle): a running one is stopped and waits paused at the front of the
        list – bundles and the card database resume later from where they were (.part), sets skip finished images."""
        if on:
            job["paused"] = True
            if job is self.current:
                self.cancel_requested = True
        else:
            job.pop("paused", None)
            job.pop("cancelled", None)
            self.next_job()
        self.refresh_sets()

    def cancel_job(self, job):
        if job is self.current:
            self.cancel_requested = True
            self.data_info.setText(tr(f"Cancelling {(job.get('code') or job.get('name') or '').upper()} …"))
        elif job in self.jobs:
            self.jobs.remove(job)
            self.refresh_sets()

    def job_estimate(self, job):
        """Estimated duration of a job in seconds (rates are learned while downloading)."""
        kind = job["kind"]
        if kind == "download":
            n = self.catalog_by_code.get(job["code"], {}).get("count", 300)
            return 3 + n * (self.img_rate + self.feat_rate)
        if kind == "carddb":
            return 90
        if kind == "pricehist":
            return 60 if job.get("daily") else 180
        if kind == "images":
            return 2 + 0.4 * sum(1 for it in self.collection.items if not (BASE / it["img"]).exists())
        return {"export": 10, "import": 10, "update": 1.8, "load": 1.5, "rebuild": 1.5, "prices": 25}.get(kind, 0.5)

    def next_job(self):
        if self.current:
            return
        if not self.jobs:
            self.progress.setVisible(False)
            if self.quit_when_done:
                QtCore.QTimer.singleShot(0, self.request_quit)
            return
        i = next((i for i, j in enumerate(self.jobs) if not j.get("paused")), None)
        if i is None:   # only paused downloads left
            self.progress.setVisible(False)
            if self.quit_when_done:
                QtCore.QTimer.singleShot(0, self.request_quit)
            return
        job = self.current = self.jobs.pop(i)
        self._job_t0 = time.time()
        self.cancel_requested = False
        self._phase = ("", 0.0, 0)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("")
        self.refresh_sets()
        threading.Thread(target=self._work, args=(job,), daemon=True).start()

    def _job_done(self, *args):
        try:
            self.bridge.job_done.emit(*args)
        except RuntimeError:  # program was closed in the meantime
            pass

    def _work(self, job):
        def progress(text, done, total):
            if self.cancel_requested:
                raise Cancelled()
            try:
                self.bridge.progress.emit(text, done, total)
            except RuntimeError:  # program is closing (e.g. "Quit" in the tray)
                raise Cancelled()
        kind, code = job["kind"], job["code"]
        try:
            if kind in ("download", "update"):
                total, priced = library.download_set(code, progress)
                msg = (tr(f"{code.upper()} loaded: {total} cards, {priced} with price.") if kind == "download"
                       else tr(f"{code.upper()}: prices and card list updated."))
            elif kind == "remove":
                library.remove_set(code)
                msg = f"{code.upper()} entfernt."
            elif kind == "carddb":
                n_cards, n_langs = carddb.download(progress, game=job.get("for"))
                msg = tr(f"Card database ready: {n_cards} cards, {n_langs} language entries.")
            elif kind == "pack":   # data bundle from our own server (packs.py)
                from cards import packs
                try:
                    packs.download(code, progress)
                except packs.PackMissing:   # not on the server yet (a new game until its release): a note, no error –
                    self.packs_missing.add(code)   # and not asked again in this session (packs_check)
                    job["missing"] = True
                    msg = tr(f"{job.get('name') or code}: card data will follow with the next update.")
                else:
                    if code == "mtg":   # attach languages to an existing Magic database
                        from scanner.common import DATA
                        mdb = games.folders("mtg", DATA)["ref"] / "cards.sqlite"
                        if mdb.exists():
                            carddb.import_langs(mdb, progress)
                    msg = tr(f"{job.get('name') or code}: downloaded.")
            elif kind == "prices" and games.current().price_source == "daily":   # their own daily prices
                currency.refresh()
                n_cm, n_tcg = games.current().update_prices(progress)   # TCGplayer: all sets (one file each)
                msg = tr(f"Prices updated: {n_cm} cards (Cardmarket), {n_tcg} (TCGplayer).")
            elif kind == "prices":
                currency.refresh()  # dollar rate for TCGplayer
                prices = pricehist.today_prices(progress, history=bool(self.settings["price_history"]))
                progress(tr("Enter prices …"), 0, 0)
                n = self.apply_prices(prices)
                msg = tr(f"Prices updated: {len(prices)} cards (MTGJSON), {n} of them changed in loaded sets.")
            elif kind == "pricehist":
                currency.refresh()  # dollar rate for TCGplayer
                if job.get("daily"):
                    n, mode = pricehist.daily_update(progress)
                else:
                    n, mode = pricehist.full_import(progress), "voll"
                msg = (tr(f"Price history ready: {n} cards (90 days).") if mode == "voll"
                       else tr(f"Price history: today's prices added for {n} cards."))
            elif kind == "images":
                n = self.download_collection_images(progress)
                msg = tr(f"Collection offline: {n} new images saved.")
            elif kind == "export":
                n = library.export_sets(job["codes"], job["path"], progress)
                msg = tr(f"{len(job['codes'])} sets exported ({n} files): {job['path']}")
            elif kind == "import":
                codes = library.import_sets(job["path"], progress)
                msg = tr(f"Imported: {', '.join((c.upper() for c in codes))}")
            else:  # load / rebuild: rebuild recognition with all sets
                if kind == "load":
                    library.migrate()
                progress(tr("Preparing recognition …"), 0, 0)
                self.bridge.loaded.emit(*self.build_matcher())
                msg = ""
            self._job_done(job, msg, "")
        except Cancelled:
            job["cancelled"] = True
            if kind == "download" and not job.get("was_installed") and not job.get("paused"):
                library.remove_set(code)  # delete half-loaded images again
            self._job_done(job, tr(f"{(code if code and code != 'all' else job.get('name') or kind).upper()} cancelled."), "")
        except Exception as e:
            log.exception("Job failed: %s %s", kind, code)
            self._job_done(job, "", f"{(code or '').upper()} fehlgeschlagen: {e}".strip())
