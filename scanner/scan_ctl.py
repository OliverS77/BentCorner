"""Scanning for the main window: cameras (choice, phone, driver controls) and the scan actions with the tick that
fetches the frame and refreshes the display, plus the memory and prefetch upkeep tied to it. APP-SPLIT phase D."""
import collections
import logging
import sys
import threading
import time

import cv2
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from cards import carddb
from cards import imgcache
from collection import sessions
from scanner import camctl
from scanner import camera
from scanner import fingerprint
from scanner import hybrid
from scanner import scandata
from scanner.camera import Camera
from scanner.common import BASE
from system.i18n import tr
from ui import qdialogs
from ui import scanui

log = logging.getLogger("booster")   # the same logger as app.py


def rest_image(frame):
    """The camera goes to rest: its last picture, small and strongly blurred (RGB) – or None without one."""
    if frame is None:
        return None
    h, w = frame.shape[:2]
    k = 480.0 / max(1, w)
    small = cv2.resize(frame, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(small, (0, 0), 9)


def print_has_languages(entry):
    """Is there a language to choose for this very print? False when the card data knows its languages and there is
    only one (Mystery Booster 2: English only) – then the language question doesn't come. Unknown: True (ask)."""
    try:
        known = carddb.languages(str(entry["set"]).lower(), str(entry["number"])) if carddb.exists() else []
    except Exception:  # noqa: BLE001
        return True
    return not known or len(known) > 1


class ScanControl:
    """Mixin of MainWindow (app.py) – moved there unchanged (docs/APP-SPLIT.md, phase D). self is the MainWindow."""

    # --- Camera ---
    def fill_cameras(self):
        names = camera.camera_names()
        log.info("Cameras: %s", names)
        self._known_cams = set(names)
        self.cam_combo.clear()
        for i, n in enumerate(names):
            self.cam_combo.addItem(n, i)
        phone = [self.PHONE_NAME] if self.PHONE_CAMERA else []
        if phone:
            self.cam_combo.addItem(self.PHONE_NAME, Camera.PHONE)   # phone on Wi-Fi/cable as camera
        want = self.settings["camera"]
        if want in self.PHONE_OLD:
            want = self.PHONE_NAME
        all_names = names + phone
        if not names and want not in phone:
            self.camera.message = tr("No camera found. Plug in a webcam – or use your phone with a webcam app: Windows then sees it like a normal camera. Then press ↻.")
            return
        idx = all_names.index(want) if want in all_names else 0
        self.cam_combo.setCurrentIndex(idx)
        self.camera_selected()

    def camera_selected(self, *_):
        if self.cam_combo.count() == 0 or getattr(getattr(self, "tray", None), "hidden", False):
            return
        if getattr(self, "tray", None) is None and "--tray" in sys.argv and self.settings.get("tray_mode", True):
            return  # started with Windows: straight into the tray – camera only when opened
        self.settings["camera"] = self.cam_combo.currentText()
        self.settings_changed()
        self.frame_rgb = None
        self._cam_ctl = None
        if not self.camera_watched():
            # nobody is looking (e.g. start in the Library): open the camera only with the scan page – saves
            # opening at start (some drivers briefly flash a window) and the retries
            self.camera.sleep()
            self._cam_asleep = True
            return
        w, h = map(int, self.settings["resolution"].split("x"))
        if self.cam_combo.currentData() == Camera.PHONE:
            self.phone_start()
        self.camera.start(self.cam_combo.currentData(), w, h)
        # apply saved image controls as soon as the camera runs (webcams forget them when unplugged)
        QtCore.QTimer.singleShot(2500, self.apply_cam_controls)

    # Phone as camera (phonecam.py: QR code, Wi-Fi, USB tethering) – in the backlog: on some Wi-Fi networks the phone
    # doesn't get through, and fruitless trial and error is too much to ask. Until then: phone webcam app (hint above).
    PHONE_CAMERA = False
    PHONE_NAME = "Handy (WLAN oder Kabel)"
    PHONE_OLD = ("Handy im WLAN",)   # former names in the settings

    def phone_start(self):
        """Start the phone server (Wi-Fi only) -> URL for the phone or ""."""
        from scanner import common
        from scanner import phonecam
        if not self.settings.get("phone_token"):
            self.settings["phone_token"] = phonecam.new_token()
            self.settings_changed()

        def status():   # show the phone what was last recognised
            try:
                cards = [c for p in self.session.packs for c in p["cards"]]
                return cards[-1]["name"] if cards else ""
            except Exception:  # noqa: BLE001
                return ""
        if getattr(self, "_usb_watch", None) is None:   # phone via cable as webcam: detect a new camera
            self._usb_watch = QtCore.QTimer(self)
            self._usb_watch.timeout.connect(self.phone_usb_check)
            self._usb_watch.start(3000)
        url = phonecam.start(common.DATA, self.settings["phone_token"], status)
        if url:
            self._phone_qr_images(url)
        return url

    def _phone_qr_images(self, url):
        from scanner import phonecam
        from ui import quickimages
        qr = phonecam.qr_image(url, 8)
        quickimages.keep("phoneqr", qr)
        quickimages.keep("phoneqr_blur", phonecam.blurred(qr))

    def phone_usb_check(self):
        """As long as the phone is selected and sends no image: detect the phone via cable – "USB tethering" (new
        network on the PC: switch the QR code to the cable address) or webcam mode (Pixel & co.: new camera, switch to
        it right away). Also keeps the scan view fresh (cable hint after 20 s)."""
        from scanner import phonecam
        if self.cam_combo.currentData() != Camera.PHONE or not self.camera_watched():
            return
        st = getattr(self, "stream", None)
        if st is not None:
            st.view.update()
        if time.time() - phonecam.latest()[2] < 5:
            return   # the phone is delivering – do nothing
        ips = set(phonecam.lan_ips())   # cheap; "ipconfig" only when a network changed on the PC
        if ips != getattr(self, "_phone_ips", None) and phonecam.url():
            self._phone_ips = ips
            want = (phonecam.usb_ips() or [phonecam.lan_ip()])[0]
            if want != phonecam.host():
                self._phone_qr_images(phonecam.set_host(want))
                if st is not None:
                    st.view._qr_first = 0.0   # new address: the cable hint counts anew
        names = camera.camera_names()
        new = [n for n in names if n not in getattr(self, "_known_cams", set())]
        self._known_cams = set(names)
        if new:
            log.info("Camera: new device %s – switching (phone via USB?)", new[0])
            self.settings["camera"] = new[0]
            self.fill_cameras()

    def use_phone(self):
        """"Phone as camera" (Settings): set the camera to the phone."""
        i = self.cam_combo.findData(Camera.PHONE)
        if i >= 0:
            self.cam_combo.setCurrentIndex(i)
            self.camera_selected()

    def cam_controls(self):
        """Controls of the selected camera (opened once) or None."""
        idx = self.cam_combo.currentData()
        if idx is None:
            return None
        if getattr(self, "_cam_ctl", None) is None or self._cam_ctl[0] != idx:
            old = getattr(self, "_cam_ctl", None)
            if old is not None and old[1] is not None:
                old[1].close()   # its COM objects stay in camctl's keep – never garbage in another thread
            self._cam_ctl = (idx, camctl.open_controls(idx))
        return self._cam_ctl[1]

    def apply_cam_controls(self):
        saved = self.settings.get("cam_controls", {}).get(self.cam_combo.currentText())
        if saved:
            ctl = self.cam_controls()
            if ctl is not None:
                ctl.apply(saved)
                log.info("Camera controls set: %s", saved)

    def open_cam_controls(self):
        ctl = self.cam_controls()
        if ctl is None:
            qdialogs.info(tr("Image controls"), tr("This camera has no adjustable controls (e.g. virtual cameras like OBS). Tip: try “Driver dialog …”."))
            return
        name = self.cam_combo.currentText()

        def save(values):
            self.settings.setdefault("cam_controls", {})[name] = values
            self.settings_changed()
        self._cam_dlg = scanui.camera_controls(ctl, name, save)

    # --- Pack actions ---
    def selected_row(self):
        return self.pack_sel if self.pack_sel is not None and self.pack_sel < len(self.snap["pack"]) else None

    def new_pack(self):
        self.session.new_pack()
        self.pack_sel = None

    def scan_removed(self, old, sure="ja"):
        """Counted too many: into the scan data as a mistake (only if we still have the crop). sure: "ja"
        (button), "auto" (noticed by the scanner), "vielleicht" (deleted shortly after the scan)."""
        if old and self.settings.get("scan_data", True) and scandata.removed(old.get("added"), old, sure):
            log.info("Scan data: %s counted too often (%s)", old.get("name"), sure)

    def removed_soon(self, entry):
        """✕/U: deleted shortly after the scan -> maybe a mistake (only noted, to be evaluated with care)."""
        if entry and time.time() - float(entry.get("added") or 0) < 15:
            self.scan_removed(entry, "vielleicht")

    def scan_correction(self, old, new):
        """Card in the pack corrected: if we still have the crop, store it as a scan datum."""
        if old and self.settings.get("scan_data", True) and scandata.correction(old.get("added"), old, new):
            log.info("Scan data: %s -> %s", old.get("name"), new.get("name"))
            box = getattr(self, "scandata_info", None)
            if box is not None:
                self.refresh_scandata()

    def remove_card(self):
        row, pack = self.selected_row(), self.snap.get("pack") or []
        i = row if row is not None else len(pack) - 1
        if 0 <= i < len(pack):
            self.removed_soon(pack[i])
        self.session.undo(row)
        self.pack_sel = None

    def toggle_foil(self):
        self.session.toggle_foil(self.selected_row())

    def toggle_cond(self):
        """Key Z: move the condition of the selected (otherwise the last scanned) card one grade on."""
        self.session.toggle_cond(self.selected_row())

    def plus_card(self):
        """Key +: count the selected (otherwise the last scanned) card once more."""
        self.session.duplicate(self.selected_row())

    def toggle_out(self):
        """Key G: mark the selected (otherwise the last scanned) card as "giving away" – only in a trade scan."""
        from scanner import core
        if not core.is_trade(self.session.info):
            self.stream_toast(tr("“I give this” exists in trade logs (New log → Scan a trade)."))
            return
        on = self.session.toggle_out(self.selected_row())
        if on is not None:
            self.stream_toast(tr("I give this – booked when the log ends") if on else tr("I get this"))

    def toggle_pause(self):
        self.set_paused(not self.recognizer.paused)

    def toggle_camera_user(self):
        """Bar in the scan window: camera off (stays off, even on the scan page) or back on."""
        self._cam_user_off = not getattr(self, "_cam_user_off", False)
        if self._cam_user_off:
            self.set_paused(True)
            if self.camera.running:
                self.camera.sleep()
            self.frame_rgb = None
            self._cam_asleep = True
            log.info("Camera: off by hand")
        else:
            self._cam_asleep = False
            self.set_paused(False)
            self.camera_selected()
            log.info("Camera: on by hand")

    @property
    def camera_user_off(self):
        return bool(getattr(self, "_cam_user_off", False))

    def toggle_hit_mode(self):
        ov = self.overlay
        ov.hit_mode = "session" if ov.hit_mode == "all" else "all"
        if ov.hit_mode == "all":
            self.update_all_time_hit()

    def update_all_time_hit(self):
        """Most expensive card of all saved sessions (incl. the running one)."""
        hits = [s["stats"]["biggest_hit"] for s in sessions.load_all()
                if s["stats"].get("biggest_hit") and sessions.counts_in_stats(s)]
        cur = self.snap["stats"]["biggest_hit"]
        if cur:
            hits.append(cur)
        self.overlay.all_time_hit = max(hits, key=lambda h: h["price"] or 0) if hits else None

    def set_paused(self, paused):
        self.recognizer.paused = paused
        if paused:
            self.session.on_empty()

    def edit_card(self):
        """Edit the selected (otherwise last) card in the stream window."""
        row = self.selected_row()
        n = len(self.snap["pack"])
        if n:
            self.stream.open_edit(row if row is not None else n - 1)

    def add_card(self):
        """K / "Search card": a question waiting (the card search was busy) opens; for the card lying there without a
        hit (the note in the status line) the search with its most likely name – the card picked there isn't counted a
        second time; otherwise the plain search."""
        if not self.open_question(self.question_wait) and not self.open_offered_search():
            self.stream.open_add()

    question_wait = None   # "print" / "lang": the scanner asks, but the card search is busy – the status line offers it

    def question_check(self):
        """The scanner asks (which print – before counting; which language – after): the card search opens with the
        question right away (Oliver 2026-10-30: one way, no window of its own). Busy with something else (editing, an
        own search): it waits, the status line says so (key K), and opens as soon as the search is free."""
        rec, panel = self.recognizer, self.stream.card_panel
        if getattr(rec, "question_dropped", None) is not None:   # the card was taken away during its question: not counted – say so
            name, rec.question_dropped = rec.question_dropped, None
            if panel.question is not None and panel.question["kind"] == "print":
                self.stream.close_card_panel()
            self.question_wait = None
            self.stream_toast(tr(f"{name}: not counted – another card came during the question") if name else
                              tr("Not counted – another card came during the question"))
        q = panel.question
        if q is not None and panel.isHidden():   # asked but the window isn't there (must not happen): open it again
            panel.question = None
            q = None
        if q is not None:
            if q["kind"] == "lang" and (rec.lang_ask is not None or rec.pending is not None
                                        or (rec.current or {}).get("id") not in (None, q["entry"].get("id"))):
                self.stream.close_card_panel()   # the next card is there: the suggestion stays (skip)
            return
        kind = "print" if rec.pending is not None else "lang" if rec.lang_ask is not None else None
        if kind is None:
            self.question_wait = None
        elif not panel.isHidden():
            self.question_wait = kind
        elif self.question_wait != kind or getattr(self, "_question_try", None) != id(rec.pending or rec.lang_ask):
            self._question_try = id(rec.pending or rec.lang_ask)   # one try per question (a failure: [K] stays)
            self.open_question(kind)

    def open_question(self, kind):
        """Open the scanner's question in the card search. -> False if there is none or the search is busy. The rule:
        "which version?" in the status line means the search is open – or the [K] note stands; never the text alone
        (Oliver 2026-10-30: an error while opening left only the text) – a failure leaves the [K] note."""
        rec, panel = self.recognizer, self.stream.card_panel
        if kind is None or not panel.isHidden() or panel.question is not None:
            return False
        try:
            return self._open_question(kind)
        except Exception:  # noqa: BLE001
            log.exception("Opening the scanner's question")
            panel.question = None
            self.question_wait = kind
            return False

    def _open_question(self, kind):
        rec, panel = self.recognizer, self.stream.card_panel
        self.question_wait = None
        if kind == "print" and rec.pending is not None:
            p = rec.pending
            info = scanui.print_question(p)

            def done(card, lang, how):
                if card is not None and rec.pending is not None:
                    rec.pending["chosen_lang"] = lang or "en"   # seen and set in the search: no language question after
                    rec.pending["chosen_how"] = how             # finish/edition chosen there (Reverse Holo …)
                rec.resolve(None if card is None else panel.question_row(card))
            self._question_window()
            panel.open_question("print", done, rows=info["rows"], star=info["star"], name=info["name"],
                                cam=info["cam"], loupe=info["loupe"], note=info["note"], lang=p.get("lang"))
            self.stream.flip_in_card_panel()
            return True
        if kind == "lang" and rec.lang_ask is not None:
            ask, rec.lang_ask = rec.lang_ask, None
            if not print_has_languages(ask["entry"]):   # this print exists in one language only: nothing to ask
                return False
            cam = scanui._bgr_url(ask["img"], f"la_cam_{id(ask)}")[0] if ask.get("img") is not None else ""

            def done(card, lang, how):
                if lang:
                    self.session.set_card(ask["added"], lang=lang)
                    self._session_lang = (self.session.id, lang)   # the next unclear cards: this language
                if card is not None and how:   # finish/edition changed in the window: taken along (0.9.6 users)
                    self.session.set_card(ask["added"], finish=how.get("finish"), edition=how.get("edition"))
            self._question_window()
            guess = ask.get("guess") or ask["entry"].get("lang")
            panel.open_question("lang", done, entry=ask["entry"], cam=cam, lang=guess)
            self.stream.flip_in_card_panel()
            return True
        return False

    def _question_window(self):
        """The card search as the only window (one window at a time), for a question – not editing a card."""
        st = self.stream
        st.bring_up()
        st.only(st.card_panel)
        st.edit_index = st.edit_pack = None

    search_offer = None   # {"name"}: a card lies there without a hit – the status line offers the search (key K)

    def unknown_card_check(self):
        """A card lies there without a hit (Recognizer.unknown_offer): no window opens by itself any more – the status
        line says "Search is taking long – search? [K]" (qscan.scanStage "offer"). Counted after all or taken away: the
        note goes without a trace, and a search opened through it closes again (never a search the user opened)."""
        rec, panel = self.recognizer, self.stream.card_panel
        if getattr(self, "_auto_search", False) and panel.isHidden():
            self._auto_search = False   # closed (Esc, a card picked): a search opened later is the user's own
        if rec.unknown_gone:
            rec.unknown_gone = False
            self.search_offer = None
            if getattr(self, "_auto_search", False) and not panel.isHidden() and self.stream.edit_index is None:
                self.stream.close_card_panel()
            self._auto_search = False
        offer, rec.unknown_offer = rec.unknown_offer, None
        if offer is not None:
            self.search_offer = offer
        rec.offer_open = bool(getattr(self, "_auto_search", False))

    def open_offered_search(self):
        """Open the card search offered in the status line, with the most likely name. -> False if none is offered."""
        offer, panel = self.search_offer, self.stream.card_panel
        if offer is None or not panel.isHidden() or self.recognizer.pending is not None:
            return False
        self.search_offer = None
        self.stream.open_add()
        if offer.get("name"):
            panel.set_search(offer["name"])
        self._auto_search = True   # added_by_hand: the card picked there is the one lying there – counted once
        self.recognizer.offer_open = True
        return True

    def added_by_hand(self, card):
        """A card from the card search went into the pack: if the search was opened for the card lying there, the
        scanner must not count it a second time."""
        if getattr(self, "_auto_search", False):
            self._auto_search = False
            self.recognizer.counted_by_hand(card.get("name"))

    def thumb(self, card, size):
        """Small card image (cached) or None if the image is missing."""
        key = (card["img"], size.width(), size.height())
        if key not in self._thumbs:
            pm = QtGui.QPixmap(str(BASE / card["img"]))
            self._thumbs[key] = None if pm.isNull() else pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            while len(self._thumbs) > 300:
                self._thumbs.popitem(last=False)
        return self._thumbs[key]

    # --- Tick: fetch the frame, refresh the display ---
    def tick(self):
        frame, seq = self.camera.latest()
        note = getattr(self.camera, "dialog_error", "")
        if note:   # the driver dialog didn't open (camera thread): a quiet note, once
            self.camera.dialog_error = ""
            shell = getattr(self, "shell", None)
            if shell is not None:
                shell.show_toast(note)
        new_frame = False
        if frame is None:
            new_frame = self.frame_rgb is not None
            self.frame_rgb = None
        elif seq != self.frame_seq:
            self.frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.frame_seq = seq
            new_frame = True

        if self.session.rev != self.last_rev:
            self.snap = self.session.snapshot()
            self.last_rev = self.snap["rev"]
            self.refresh_table()
            self.load_info_fields(reload_panel=False)
            if self.session.rev != self.saved_rev:
                self._session_timer.start()  # save in batches
            if self.page_shown("stats", "sessions"):
                self._stats_timer.start()
            self.fetch_lang_images()
        self.scan_sound_check()
        self.overlay.update(self.snap, time.monotonic())
        self.overlay.suppress = self.stream.stats_panel.isVisible()
        self.overlay.paused = self.recognizer.paused
        if self.stream.card_panel.isVisible():
            self.stream.card_panel.place()

        self.question_check()
        self.unknown_card_check()
        status = self.recognizer.status + (f"   ⚠ {self.camera.warning}" if self.camera.warning else "")
        self.status.setText(status)
        self.tracker.visible = self.preview_watched
        if new_frame or self.preview.hover_q:
            self.preview.update()
        self.camera_sleep_check()
        if self.session.autostarted and self.session.autostarted != getattr(self, "_autostart_seen", 0.0):
            self._autostart_seen = self.session.autostarted
            self.save_session()
            if hasattr(self, "refresh_stats"):
                self.refresh_stats()
            self.stream_toast(tr("Log started (scanning cards). Other kind: Log → End log → New log …"))
        if self.stream.isVisible() and self.stream.page == "scan" and not self.stream.isMinimized():
            now = time.monotonic()  # new camera frame or transition: immediately, otherwise at most 30 frames/s
            if new_frame or self.overlay.busy(now) or now - getattr(self, "_view_t", 0.0) >= 0.029:
                self._view_t = now
                self.stream.view.update()

    def scan_sound_check(self):
        """Sound for the last automatically counted card (scansound.py): only the highest matching one. If the price
        comes later (e.g. Pokémon from the index), wait at most 1.5 s – otherwise a hit sounds like a normal card."""
        auto = self.session.last_auto
        if auto is not None and auto is not getattr(self, "_sound_seen", None):
            self._sound_seen = auto
            self._sound_due = (auto, time.monotonic())
        due = getattr(self, "_sound_due", None)
        if due is None or (due[0].get("price") is None and time.monotonic() - due[1] < 1.5):
            return
        self._sound_due = None
        if self.settings.get("scan_sounds", True):
            from scanner import scansound
            scansound.play(scansound.kind_for(due[0].get("price"), self.settings.get("hit")))

    CAM_SLEEP_AFTER = 60.0  # s on another page until the camera turns off (a quick look: stays on) – Oliver's c2

    def camera_watched(self):
        """Does anyone see the camera image? (scan page in the visible window or preview in the settings)"""
        st = getattr(self, "stream", None)
        ob = getattr(self, "onboarding", None)   # the first-run setup lies above everything (the game runs there too)
        covered = ob is not None and ob.dlg is not None and not ob.dlg.done
        return bool((st is not None and st.isVisible() and not st.isMinimized() and st.page == "scan" and not covered)
                    or getattr(self, "preview_watched", False))

    AI_IDLE = 60.0        # s without a fingerprint (no scan – on any page) until the AI network releases its memory
    # (GPU and RAM); the next card in the frame reloads it by itself in the scan thread (< 1 s)
    TRIM_AFTER = 90.0     # s minimised until Bent°Corner clears caches and Windows takes back memory

    def warm_ai(self):
        """Load the AI network in the background (choose the GPU, ~1–2 s) so the first card doesn't wait – in its own
        AI process (aiworker) with all batch sizes and text recognition: the UI doesn't stall meanwhile."""
        if fingerprint.loaded() or getattr(self, "_ai_warming", False) or not fingerprint.available():
            return
        self._ai_warming = True

        def work():
            try:
                t = time.time()
                fingerprint.warm(ocr=True)
                log.info("AI runs on: %s (ready in %.1f s)", fingerprint.backend, time.time() - t)
            except Exception:  # noqa: BLE001
                log.exception("Loading AI")
            finally:
                self._ai_warming = False
        threading.Thread(target=work, daemon=True).start()

    def memory_check(self, watched, now):
        """Save memory when nobody is scanning: unload the AI network after AI_IDLE without a fingerprint (also on the
        scan page; entering the scan page preloads it, otherwise the next card in the frame); minimised after TRIM_AFTER
        clear the image cache, tear down pages and let Windows take back the rest."""
        studio = getattr(self, "studio", None)
        scanning = watched and not self.recognizer.paused and not (studio is not None and studio.on)
        if scanning and not getattr(self, "_was_scanning", False):   # just switched to the scan page: preload
            self.warm_ai()
        self._was_scanning = scanning
        if fingerprint.loaded() and not getattr(self, "_ai_warming", False) and fingerprint.idle_for(now) > self.AI_IDLE:
            if fingerprint.release():
                log.info("AI: unloaded (no scan for %.0f s)", fingerprint.idle_for(now))
        st = getattr(self, "stream", None)
        minimized = st is not None and (st.isMinimized() or not st.isVisible())
        if not minimized:
            self._min_since, self._trimmed = None, False
            return
        if getattr(self, "_min_since", None) is None:
            self._min_since = now
        if not getattr(self, "_trimmed", False) and now - self._min_since > self.TRIM_AFTER:
            self._trimmed = True
            self.trim_memory()

    def trim_memory(self):
        import gc
        fingerprint.release()
        for lv in (self.library_win, getattr(getattr(self, "library_win", None), "detail", None)):
            loader = getattr(lv, "loader", None)
            if loader is not None:
                loader.cache.clear()
        shell = getattr(self, "shell", None)
        if shell is not None:
            shell.trimPages.emit()   # tear down Qt Quick pages (except scan) – short loading screen when brought back
            QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)   # release right away
            shell.engine.collectGarbage()
            shell.engine.trimComponentCache()
        win = getattr(shell, "window", None)
        if win is not None:
            try:
                win.releaseResources()   # Qt Quick: release graphics caches
            except Exception:  # noqa: BLE001
                pass
        gc.collect()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
            except Exception:  # noqa: BLE001
                pass
        log.info("Minimized: caches cleared")

    frame_rest = None   # the camera rests: its last picture, small and blurred (qscan shows it, fades out when live)

    def camera_sleep_check(self):
        """Nobody sees the camera image (other page, window minimised/hidden): pause recognition immediately,
        camera off after CAM_SLEEP_AFTER. Back on the scan page (or preview in the settings) both turn
        on again. Saves CPU, GPU (AI) and USB bandwidth."""
        watched = self.camera_watched()
        self.recognizer.sleeping = not watched
        now = time.monotonic()
        if now - getattr(self, "_mem_t", 0.0) > 2.0:   # every 2 s is enough
            self._mem_t = now
            self.memory_check(watched, now)
        if watched:
            self._unwatched_since = None
            if getattr(self, "_cam_user_off", False):   # switched off by hand: don't wake up by itself
                return
            if getattr(self, "_cam_asleep", False):
                self._cam_asleep = False
                log.info("Camera: back on (scan page)")
                self.camera_selected()
            return
        if getattr(self, "_unwatched_since", None) is None:
            self._unwatched_since = now
        if not getattr(self, "_cam_asleep", False) and self.camera.running and \
                now - self._unwatched_since > self.CAM_SLEEP_AFTER:
            self._cam_asleep = True
            log.info("Camera: sleeping (no scan page for %.0f s)", now - self._unwatched_since)
            self.frame_rest = rest_image(self.frame_rgb)   # the last picture, blurred, stays until the camera is back
            self.camera.sleep()
            self.frame_rgb = None

    def prewarm_search(self):
        """A few seconds after start (idle): run the card search once in the background, so the first search in the
        scan window doesn't wait for the database to come off the disk (set codes, name index, full-text index)."""
        def work():
            try:
                t = time.time()
                if not carddb.exists():
                    return
                from ui import searchbox  # noqa: F401 – imported on the first search otherwise
                carddb.set_codes()
                carddb.names_by_printed("zz")
                carddb.search("zz", limit=1)
                log.info("Search prepared in %.2f s", time.time() - t)
            except Exception:  # noqa: BLE001 – only a head start, the search itself works without it
                log.exception("Preparing search")
        threading.Thread(target=work, daemon=True, name="prewarm-search").start()

    def prefetch_tick(self):
        self.prefetch_session_images()
        self.prefetch_recent_sets()
        self.preload_filtered_sets()

    def preload_filtered_sets(self):
        """Filtered scan, sets chosen: their fingerprint rows and card data into RAM right away (index.preload_sets),
        the features of their reference images on disk next (hybrid.preload_features), missing images politely
        (hybrid.prefetch_sets, netpolite) and their features after that. Once per set choice, in the background."""
        index = self.recognizer.fp_index
        codes = self.recognizer.focus_sets()
        if index is None or not codes or codes == getattr(self, "_filtered_ready", None):
            return
        self._filtered_ready = codes
        stop = lambda: self._filtered_ready != codes   # noqa: E731 – the choice changed: the next one takes over

        def step(name, done=0, total=0):   # the scan tile shows it (scantiles._sets_load)
            if not stop():
                self.filtered_load = {"step": name, "done": done, "total": total}

        def work():
            try:
                t0 = time.monotonic()
                step("memory")
                entries = index.preload_sets(codes)
                paths = [BASE / e["img"] for e in entries if e.get("img")]
                have = [p for p in paths if p.exists()]
                n = hybrid.preload_features(have, stop, lambda i, k: step("features", i, k))
                log.info("Filtered scan (%s): %d prints, %d reference features in RAM (%.1f s)",
                         ", ".join(codes), len(entries), n, time.monotonic() - t0)
                if not stop() and not imgcache.offline() and \
                        hybrid.prefetch_sets(list(codes), stop=stop, progress=lambda i, k: step("images", i, k)):
                    hybrid.preload_features([p for p in paths if p.exists()], stop,
                                            lambda i, k: step("features", i, k))
            except Exception:
                log.exception("Filtered scan: preloading")
            finally:
                if not stop():
                    self.filtered_load = None
        threading.Thread(target=work, daemon=True, name="filtered-scan").start()

    PREFETCH_FROM = 3     # preload from the third scanned card on
    PREFETCH_LOOK = 12    # this many recently scanned cards count for the set mix
    PREFETCH_SETS = 3     # at most this many sets at once

    def prefetch_recent_sets(self):
        """Preload comparison images of the sets currently being scanned from – then the next print of the
        same sets doesn't wait for the download. From the third card: a booster (two of the first three from one set)
        stands out right away; with a mixed collection every set counts that appeared at least twice among the
        last cards. If the mix changes, loading swings over (sets that drop out are cancelled).
        Throttled via netpolite (hybrid.prefetch_sets), finished sets are remembered."""
        if self.settings.get("scan_mode") == "sets":   # "Loaded sets": images are already there
            return
        with self.session.lock:
            recent = [c.get("set") for pk in self.session.packs[-4:] for c in pk["cards"]][-self.PREFETCH_LOOK:]
        if len(recent) < self.PREFETCH_FROM:
            return
        done = self.__dict__.setdefault("_sets_loaded", set())
        counts = collections.Counter(str(c).lower() for c in recent if c)
        active = [c for c, n in counts.most_common() if n >= 2 and c not in done][:self.PREFETCH_SETS]
        self._sets_wanted = active
        if not active or getattr(self, "_sets_loading", False):
            return
        self._sets_loading = True

        def work():
            try:
                while True:
                    todo = [c for c in self._sets_wanted if c not in done]
                    if not todo or imgcache.offline():
                        break
                    code = todo[0]
                    n = hybrid.prefetch_sets([code], stop=lambda: code not in self._sets_wanted)
                    if code in self._sets_wanted and not imgcache.offline():
                        done.add(code)
                        log.info("Reference images preloaded (%s): %s", code, n)
                    else:
                        break   # the mix has changed: decide anew at the next tick
            except Exception:
                log.exception("Preloading reference images")
            finally:
                self._sets_loading = False
        threading.Thread(target=work, daemon=True).start()

    def prefetch_session_images(self):
        """Scan mode "All cards": preload images of the session sets in the background (once per set selection)."""
        if self.settings.get("scan_mode") != "ocr":
            return
        codes = sorted({st["code"].lower() for st in (self.session.info.get("sets") or []) if st.get("code")})
        if not codes or codes == getattr(self, "_prefetched", None):
            return
        self._prefetched = codes

        def work():
            try:
                n = hybrid.prefetch_sets(codes, stop=lambda: self._prefetched != codes)
                log.info("Images preloaded (%s): %s", ", ".join(codes), n)
            except Exception:
                log.exception("Preloading images")
        threading.Thread(target=work, daemon=True).start()

    def trim_image_cache(self):
        """Limit the card image cache to the configured size (in the background)."""
        items = list(self.collection.items)
        codes = [st["code"] for st in (self.installed or [])]
        # plus the sets whose comparison images the scanner is preloading or has preloaded (prefetch_recent_sets)
        codes += list(getattr(self, "_sets_wanted", ())) + list(getattr(self, "_sets_loaded", ()))
        limit = int(self.settings.get("image_cache_mb", 1000))

        def work():
            try:
                freed, secs = scanui.trim_cache(items, codes, limit)
                if freed:
                    log.info("Image cache: %.0f MB freed (%.1f s)", freed / 1024 / 1024, secs)
            except Exception:
                log.exception("Image cache")
        threading.Thread(target=work, daemon=True).start()
