"""Recognizer: recognition in the background – takes the camera's frames, asks the scanner (AI fingerprints, text
recognition, older modes) and books hits into the session; no user interface (moved out of app.py, unchanged)."""
import collections
import logging
import threading
import time

import cv2
import numpy as np

import games
from cards import carddb
from cards import library
from scanner import aiscan
from scanner import fingerprint
from scanner import hybrid
from scanner import langcheck
from scanner import ocrscan
from scanner import scandata
from scanner.common import BASE
from scanner.core import SEARCH_THREADS, zone_rect
from system import i18n
from system.i18n import tr

log = logging.getLogger("booster")

HINT_AFTER = 1.5   # s without a match until a tip (glare, dark, blurry) appears – setting "scan_hints"
UNKNOWN_AFTER = 1.5   # s a sharp card lies there without a hit until the card search opens (Esc = skip)
# "Empty" frames (no edges in the scan zone) – only the mat itself ends a card (Oliver, live 0.9.2: a card lying there
# was counted twice): a dark frame (the camera waking up) or a hand over the card doesn't
DARK_BELOW = 30       # mean brightness (0–255) of the scan zone: darker = the camera isn't seeing yet
MAT_DIFF = 16         # mean difference (0–255) to the learnt mat: more = something lies over it (a hand)
COVER_AS_MAT = 3.0    # s: still "covered" after this long – it is the mat after all (light changed, mat moved)
UNIFORM_STD = 12      # spread of the brightness (0–255): a hand right over the lens is even; an out-of-focus room
                      # behind a card held up (no mat) is not – that counts as empty, as before, and becomes the "mat"
# What the scanner is doing right now, for the line under the scan frame (Recognizer.stage) – the same codes and
# wording as the phone scanner (web/scan/scanner.js), so waiting shows where it's busy. Texts via stage_text().
STAGES = {
    "loading": "Loading card data …",
    "idle": "Card into the frame",
    "searching": "Looking …",
    "loading_refs": "Loading a comparison image …",
    "comparing": "Comparing card images …",
    "reading_line": "Reading the collector line …",
    "asking": "Which print? – please choose",
    "card_search": "Card search open – pick the card or take it away",
    "counted": "Counted – take the card away for the next one",
    "studio": "Card from the studio – the next one counts",
    "paused": "Paused",
    "no_engine": "SCAN° Engine missing – reading the card's text instead",
}


def stage_text(code):
    return tr(STAGES[code]) if code in STAGES else ""
# … in games scanning by the collector line only (no fingerprint index: e.g. Lorcana as shipped): two reads must
# agree and each takes ~0.3–1 s – the bench waits up to 4 s for them, so does the card search
UNKNOWN_AFTER_FOOTER = 4.0


# ---------- Recognition in the background ----------
def how_text(how):
    """Reason of the AI scanner (aiscan, English, parts joined by " · ") for the status line – each part translated."""
    return " · ".join(tr(part) for part in (how or "").split(" · ")) if how else ""


def _iou(a, b):
    """Overlap of two boxes (x, y, w, h): 0 apart … 1 the same."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw, ih = max(0, min(ax + aw, bx + bw) - max(ax, bx)), max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / max(1, aw * ah + bw * bh - inter)


class Recognizer:
    def __init__(self, camera, session, settings):
        self.camera, self.session, self.settings = camera, session, settings
        self.matcher = None
        self.paused = False
        self.hold_until_empty = False   # after the Studio: only count again once the frame has been empty once
        self.sleeping = False                    # nobody sees the scan (other page): compute nothing
        self.status = tr("Loading card data …")
        self.stage = ""   # STAGES code – read by the scan page (ui/qscan.py), only the code is set here
        self.stable_idx = None
        self.running = True
        self.pending = None                      # question open: {"cands", "img", "r", "thumb", "lang"}
        self.lang_ask = None                     # language unclear: {"added", "entry", "names", "img"} (doesn't block)
        self.print_ask = None                    # print unclear, top pick counted: {"added", "cands", "img", "r"}
        self.unknown_offer = None                # card lies there, no hit for UNKNOWN_AFTER: {"name"} -> card search
        self.unknown_gone = False                # that card was counted or taken away: close the search it opened
        self._nohit_since, self._offered = None, False
        self.offer_open = False                  # that search is open (recognition keeps running)
        self._print_lock = threading.Lock()      # stamp and language check correct the same counted card (threads)
        self._stamped = {}                       # added -> stamped print (_stamp_check): the language keeps it
        self.live = aiscan.LiveScanner()         # AI mode: first looks where the last card was
        self.current = None                      # currently recognised card (entry) – for the scan overlay
        self.hit = None                          # (entry, time) of the last counted card
        self.looking = False                     # something card-like in the frame (being read/searched)
        self.fp_index = None                     # AI fingerprints of the loaded sets (set by the main window)
        self.confirmed = collections.Counter()   # sets confirmed in this session (preferred on a tie)
        threading.Thread(target=self._run, daemon=True).start()

    MODE_TEXT = {"leer": tr("no card in frame, idle"), "kurz": tr("quick check"),
                 "gleich": tr("unchanged, no new search"), "voll": tr(f"full search ({SEARCH_THREADS} cores)")}

    def _run(self):
        hist = collections.deque(maxlen=3)
        last_seq, last_matcher = -1, None
        while self.running:
            if getattr(self, "ticket_mode", False) and not self.sleeping:   # read a trade ticket via the camera
                last_seq = self._run_ticket(last_seq)
                continue
            if self.sleeping:  # other page open: neither AI nor text recognition (saves CPU and GPU)
                self.current, self.looking = None, False
                time.sleep(0.1)
                continue
            if self.settings.get("scan_mode") in ("ai", "ai_foil") and self.fp_index is None:
                # the fingerprint index is still loading (first start, game switch) – or there is no SCAN° Engine at all
                # (model missing): then the text recognition below reads the card, never an endless "loading"
                self.stage = "loading" if fingerprint.available() else "no_engine"
            if self.settings.get("scan_mode") in ("ai", "ai_foil") and self.fp_index is not None:
                self.live.allow_foil = self.settings.get("scan_mode") == "ai_foil"
                self.live.langs = self.scan_langs()
                self.live.asia_ok = any(lg in aiscan.ASIA_LANGS for lg in (
                    self.settings.get("card_lang"), getattr(self, "_recent_lang", None)))
                try:
                    last_seq = self._run_ai(last_seq)
                except Exception as e:  # an error must never stop the scanner
                    log.exception("AI scan")
                    self.status = tr(f"Recognition error ({e}) – continuing …")
                    time.sleep(0.2)
                hist.clear()
                matcher = last_matcher = None
                continue
            if self.settings.get("scan_mode") in ("ocr", "ai", "ai_foil"):
                last_seq = self._run_ocr(last_seq)
                hist.clear()
                matcher = last_matcher = None  # don't keep a reference to released image features
                continue
            matcher = self.matcher
            if matcher is not last_matcher:  # new card list: old indices are no longer valid
                hist.clear()
                last_matcher = matcher
            frame, seq = self.camera.latest()
            if matcher is None or frame is None or seq == last_seq or self.paused:
                if self.paused:
                    self.status, self.stable_idx = tr("Recognition paused"), None
                    hist.clear()
                time.sleep(0.03)
                continue
            last_seq = seq
            if hist.maxlen != self.settings["stable"]:
                hist = collections.deque(maxlen=self.settings["stable"])
            matcher.min_inliers = self.settings["min_inliers"]
            fh, fw = frame.shape[:2]
            x, y, w, h = zone_rect(self.settings["zone"], fw, fh)
            t0 = time.time()
            last = hist[-1] if hist else None
            idx, inliers, mode = matcher.match(frame[y:y + h, x:x + w], last)
            dt = time.time() - t0
            hist.append(idx)
            self.current = matcher.cards[idx] if idx is not None else None
            self.looking = mode != "leer"
            if len(hist) == hist.maxlen and len(set(hist)) == 1:
                self.stable_idx = idx
                if not self.paused:
                    if idx is not None:
                        self._mark_hit(matcher.cards[idx])
                        self.session.on_card(matcher.cards[idx])
                    else:
                        self.hit = None
                        self.session.on_empty()
            name = matcher.cards[idx]["name"] if idx is not None else tr("no card")
            self.status = tr(f"{name}   ·   {inliers} matches   ·   {dt * 1000:.0f} ms   ·   {self.MODE_TEXT[mode]}")

    def _run_ticket(self, last_seq):
        """Ticket mode: every ~0.3 s search the camera image for a trade ticket's pixel code."""
        frame, seq = self.camera.latest()
        if frame is None or seq == last_seq or time.time() - getattr(self, "_ticket_t", 0) < 0.3:
            time.sleep(0.03)
            return last_seq
        self._ticket_t = time.time()
        self.status = tr("Looking for a trade ticket …")
        from collection import ticket
        try:
            t = ticket.decode_photo(frame)
        except Exception:  # noqa: BLE001
            log.exception("Reading ticket")
            t = None
        if t is not None:
            self.ticket_mode = False
            cb = getattr(self, "on_ticket", None)
            if cb is not None:
                cb(t)
        return seq

    def _run_ocr(self, last_seq):
        """One pass of the "All cards" scan mode: read text, match candidates by image, count after two identical
        results. If several prints remain equally good, ask (self.pending)."""
        frame, seq = self.camera.latest()
        if frame is None or seq == last_seq or self.paused or self.pending is not None:
            if self.paused:
                self.status = tr("Recognition paused")
                self.current = None
            elif self.pending is not None:
                self.status = tr("Several printings possible – please pick in the window")
            time.sleep(0.03)
            return last_seq
        if not carddb.exists() and not (self.settings.get("scan_mode") in ("ai", "ai_foil") and self.fp_index):
            self.status = (tr("Setting up … loading the card database (once, a minute or two).")
                           if self.settings.get("first_setup") else
                           tr("Scan mode “All cards”: card database missing (Settings → Card data)"))
            time.sleep(0.3)
            return seq
        fh, fw = frame.shape[:2]
        x, y, w, h = zone_rect(self.settings["zone"], fw, fh)
        rect = (x, y, w, h)
        fresh = [f for sq, f in self.camera.recent_frames() if sq > last_seq and f.shape == frame.shape]
        if len(fresh) > 1:  # shaky? take the sharpest of the new frames
            frame = max(fresh, key=lambda f: self._sharpness(f, rect))
        crop = frame[y:y + h, x:x + w]
        small = cv2.cvtColor(cv2.resize(crop, (160, 224), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(small, (3, 3), 0), 50, 150).mean() / 255
        if edges < 0.02:  # empty frame
            self._ocr_hist, self._ocr_thumb, self._ocr_last = [], None, None
            self.current, self.hit, self.looking = None, None, False
            self._card_t0, self._steady_since, self._prev_thumb, self._ai_fails = None, None, None, 0
            self.session.on_empty()
            self.status = tr("no card in frame, idle")
            return seq
        thumb = cv2.resize(small, (32, 44)).astype(np.int16)
        self.looking = True
        now = time.time()
        if getattr(self, "_card_t0", None) is None:
            self._card_t0 = now  # card entered the picture (for the time in the log)
        pt = getattr(self, "_prev_thumb", None)
        if pt is not None and np.abs(thumb - pt).mean() < 6:  # image barely changes: card is lying still
            self._steady_since = getattr(self, "_steady_since", None) or now
        else:
            self._steady_since = None
        self._prev_thumb = thumb
        prev = getattr(self, "_ocr_thumb", None)
        last = getattr(self, "_ocr_last", None)
        known = getattr(self, "_known", None)  # last recognised card (persists across short dropouts)
        if prev is not None and np.abs(thumb - prev).mean() < 5 and last is not None:
            res = self._ocr_last  # unchanged: don't read again
            dt = 0.0
        elif known is not None and hybrid.verify(frame, rect, BASE / known["entry"]["img"]) >= max(
                aiscan.MIN_INLIERS, 0.5 * known.get("strength", 0)):  # only if it still fits almost as well (not
            # just peeking out from behind the next card at the edge)
            # known card only moved/briefly covered: confirmed by image matching, no new text recognition needed
            res = dict(known, how=tr("Image match (known card)"))
            self._ocr_thumb, self._ocr_last = thumb, res
            dt = 0.0
        else:
            t0 = time.time()
            try:
                res = self._recognize(frame, rect)
            except Exception as e:
                log.exception("OCR")
                self.status = tr(f"Text recognition: error ({e})")
                time.sleep(0.5)
                return seq
            dt = time.time() - t0
            if not res.get("retry"):
                self._ocr_thumb, self._ocr_last = thumb, res
        entry, r, how = res["entry"], res["r"], res["how"]
        self.current = entry if res["status"] == "ok" else None
        if res["status"] == "ok" and entry is not None:
            self._known = res
        if res["status"] == "ask":
            key = ("?",) + tuple(c["id"] for c, _ in res["cands"])
        else:
            key = entry["id"] if entry else None
        hist = (getattr(self, "_ocr_hist", []) + [key])[-3:]
        self._ocr_hist = hist
        # count: strong image match immediately, otherwise 2 of the last 3 results equal (single shaky frames
        # in between no longer slow it down)
        agreed = key is not None and (hist.count(key) >= 2 or res.get("strength", 0) >= aiscan.STRONG)
        read = " ".join(x for x in ((r.get("set") or "").upper(), f"#{r['number']}" if r.get("number") else "",
                                     (r.get("lang") or "").upper()) if x)
        if res["status"] == "ask":
            names = " / ".join(f"{c['set_code'].upper()} #{c['number']}" for c, _ in res["cands"][:3])
            if agreed:
                self.pending = {"cands": res["cands"], "img": res["img"], "r": r, "thumb": thumb,
                                "lang": r.get("lang") if r.get("lang") not in (None, "en") else None}
                self.status = tr(f"Several printings possible ({names}) – please pick")
            else:
                self.status = tr(f"unclear: {names} …   ·   {dt * 1000:.0f} ms")
            return seq
        if entry is None:
            if res.get("retry"):
                self.status = f"{res['how']}   ·   {dt * 1000:.0f} ms"
            else:
                self.status = tr(f"not recognized   ·   read: {r.get('name') or '–'} {read}   ·   {dt * 1000:.0f} ms")
            if res.get("note"):
                self.status += f"   ·   {res['note']}"
            return seq
        if agreed:
            lang = r.get("lang") if r.get("lang") not in (None, "en") else None
            before = self.session.current
            self._count(entry, lang, (frame, rect, res) if res.get("ai") else None)
            if self.session.current is not before and getattr(self, "_card_t0", None):
                log.info("Counted: %s %s #%s after %.2f s · %s", entry["name"], entry["set"], entry["number"],
                         time.time() - self._card_t0, how)
        self.status = tr(f"{entry['name']}   ·   {entry['set']} #{entry['number']}   ·   {how}   ·   read: {read or '–'}   ·   {dt * 1000:.0f} ms")
        return seq

    # ---------- AI mode: fast, for stacks in the hand ----------
    # Measured on a test video (39 cards from the hand, penny sleeves, DE/EN): an image match with ≥ 35 points has
    # never been wrong -> count immediately. Same card = same name (prints with the same image would otherwise flip
    # back and forth); it's only counted again after an empty frame or in another language (second card).
    def _run_ai(self, last_seq):
        frame, seq = self.camera.latest()
        if self.pending is not None and frame is not None and seq != last_seq and self._pending_other_card(frame):
            return seq
        if self.pending is not None:
            self.status = tr("Which printing? – please choose in the window")
            self.stage = "asking"
            time.sleep(0.03)
            return last_seq
        if frame is None or seq == last_seq or self.paused:
            if self.paused:
                self.status = tr("Recognition paused")
                self.stage = "paused"
                self.current = None
            time.sleep(0.004)
            return last_seq
        fh, fw = frame.shape[:2]
        x, y, w, h = zone_rect(self.settings["zone"], fw, fh)
        rect = (x, y, w, h)
        fresh = [f for sq, f in self.camera.recent_frames() if sq > last_seq and f.shape == frame.shape]
        if len(fresh) > 1:  # shaky? take the sharpest of the new frames
            frame = max(fresh, key=lambda f: self._sharpness(f, rect))
        crop = frame[y:y + h, x:x + w]
        small = cv2.cvtColor(cv2.resize(crop, (160, 224), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        if cv2.Canny(cv2.GaussianBlur(small, (3, 3), 0), 50, 150).mean() / 255 < 0.02:  # empty frame
            kind = self._empty_kind(small)
            self._last_empty = (kind, time.time())   # for the log: what the frame was before the next count
            if kind != "mat":   # dark (camera waking up) or covered (a hand): the card lying there stays counted
                self.current, self.hit, self.looking = None, None, False
                self.status = tr("camera image dark") if kind == "dark" else tr("card covered")
                self.stage = "idle"
                return seq
            self._ai_reset()
            if self._offered and not self.offer_open:   # gone, its search never opened: the [K] note goes
                self.unknown_gone = True
            self._nohit_since = None
            if not self.offer_open:   # an open search stays (the card is often looked at in the hand) – until another
                self._offered = False   # card is recognized (on_card: unknown_gone) or the search is closed
            self.session.on_empty()
            self.hold_until_empty = False
            self.status = tr("no card in frame, idle")
            self.stage = "idle"
            return seq
        self._cover_since = None   # a card in view: a cover starts anew the next time
        if self.hold_until_empty:   # Studio just closed: the card that was lying there doesn't count
            self.status = tr("Card from the studio – counting starts with the next one")
            self.stage = "studio"
            return seq
        thumb = cv2.resize(small, (32, 44)).astype(np.int16)
        self.looking = True
        now = time.time()
        if getattr(self, "_card_t0", None) is None:
            self._card_t0 = now
        # don't even check blurred frames (card being moved) – otherwise a futile attempt (~0.25 s) blocks
        # exactly the sharp frame after it
        sharp = cv2.Laplacian(small, cv2.CV_32F).var()
        ref = getattr(self, "_sharp_ref", 0.0) * 0.97  # slowly forget
        self._sharp_ref = max(ref, sharp)
        skipped = getattr(self, "_blur_skips", 0)
        if sharp < 0.4 * self._sharp_ref and skipped < 6:
            self._blur_skips = skipped + 1
            return seq
        self._blur_skips = 0
        known = getattr(self, "_ai_known", None)
        anchor = getattr(self, "_ai_thumb", None)
        t0 = time.time()
        if known is not None and anchor is not None and np.abs(thumb - anchor).mean() < 4:
            res, fresh_search = known, False  # unchanged since the last search
        else:
            res, fresh_search = self.live.step(frame, rect, self.fp_index, self.prefer_sets(),
                                               focus=self.focus_sets()), True
            res = aiscan.sure_print(frame, res, self.fp_index)   # print not certain -> ask (never count blindly)
            if res["status"] in ("ok", "ask"):
                # print question (sure_print): read the collector line again next frame; collector line only (footer):
                # its reads run in the background – a kept result would freeze an old read on a card lying still
                if not res.get("pick") and not res.get("footer"):
                    self._ai_known, self._ai_thumb = res, thumb
                self._ai_fail_since = None
            elif getattr(self, "_ai_fail_since", None) is None:
                self._ai_fail_since = now
        dt = time.time() - t0
        if res["status"] == "ok":
            entry = res["entry"]
        elif res["status"] == "ask":
            row = res["cands"][0][0]
            entry = row.get("_entry") or carddb.entry_from_row(row)
        else:
            entry = None
        self.current = entry
        name = entry["name"] if entry else None
        if res["status"] == "none":   # a sharp card lies there, nothing found: hand over to the card search early
            if self._nohit_since is None:
                self._nohit_since = now
            elif (now - self._nohit_since >= (UNKNOWN_AFTER_FOOTER if res.get("footer") else UNKNOWN_AFTER)
                  and not self._offered and self.pending is None):
                self._offered = True
                self.unknown_offer = {"name": res.get("guess") or ""}
                log.info("No hit for %.1f s – card search offered (%s)", now - self._nohit_since, res.get("guess"))
        else:
            self._nohit_since = None
        hist = (getattr(self, "_ai_hist", []) + [name or (res.get("hint") if fresh_search else None)])[-3:]
        self._ai_hist = hist
        agreed = name is not None and (hist.count(name) >= 2 or res.get("strength", 0) >= aiscan.STRONG)
        last_name = getattr(self, "_ai_last_name", None)
        counted = getattr(self, "_ai_counted", {})  # name -> time (last counted)
        force = False
        if agreed and name == last_name and fresh_search and res.get("box") is not None:
            # same card again – or the next one in another language? (check at most every 0.3 s; two
            # clear readings of the other language needed, otherwise a misread would count twice)
            last_lang = getattr(self, "_ai_last_lang", None)
            if last_lang is not None and now - getattr(self, "_ai_lang_t", 0) >= 0.3:
                self._ai_lang_t = now
                lg, info = langcheck.detect(res["img"], entry, frame, res["box"])
                sc = (info.get("scores") or [(lg, 0)])[0][1]
                other = getattr(self, "_ai_other_lang", [])
                other = (other + [lg])[-2:] if lg is not None and lg != last_lang and sc >= 80 else []
                self._ai_other_lang = other
                force = len(other) == 2 and other[0] == other[1]
        recently = name is not None and now - counted.get(name, -99) < 10.0  # just counted (lying next to it)
        if agreed and res["status"] == "ask" and ((name != last_name and not recently) or force):
            # same image in several prints, collector line and set symbol unreadable: keep trying briefly
            # (the next sharp frame usually settles it), then ask instead of guessing
            since = getattr(self, "_ask_since", None)
            if since is None or since[0] != name:
                self._ask_since = since = [name, now, 0]
            since[2] += fresh_search   # reads of this card (sure_print reads the collector line on every one)
            # collector line unreadable on 3 frames in a row: ask after 0.5 s (it either decides on the first sharp
            # frame or not at all) – otherwise (image match / set symbol) the full 0.8 s
            if now - since[1] < (0.5 if res.get("pick") and since[2] >= 3 else 0.8):
                self.status = tr(f"{name} · which printing? (reading the collector line …)")
                self.stage = "reading_line"
                return seq
            self._ask_since = None
            self.pending = {"cands": res["cands"], "img": res["img"], "r": {"name": name}, "thumb": thumb,
                            "lang": None, "ai": True, "force": force, "pick": res.get("pick"),
                            "loupe": res.get("loupe"), "stamp_front": res.get("stamp_front")}
            self.status = tr("Which printing? – please choose in the window")
            self.stage = "asking"
            return seq
        # Protection against miscounts when placing/removing: A, B, A – if the previous card is back shortly after B
        # (without an empty frame in between), B was a mistake (half-covered intermediate frame) – B is removed again.
        prev = getattr(self, "_ai_prev", None)          # (name of the card before the last, entry of the last, time)
        still = agreed and self._lying_still(name, res.get("box"))   # back where it was counted: the same card
        if (agreed and prev is not None and name == prev[0] and name != last_name and now - prev[2] < 3.0
                and res.get("strength", 0) >= aiscan.STRONG and not force and not still):
            if self.session.remove_entry(prev[1]):
                log.info("Miscount undone: %s (%s was still there before)", prev[1].get("name"), name)
                if self.settings.get("scan_data", True):
                    scandata.removed(prev[1].get("added"), prev[1], "auto")
            self._ai_prev = None
            self._ai_last_name = name
            counted[name] = now
            return seq
        if agreed and ((name != last_name and not recently and not still) or force):
            self._ai_other_lang, self._ask_since = [], None
            counted[name] = now
            self._ai_counted = {k: v for k, v in counted.items() if now - v < 20}
            self._ai_last_name, self._ai_last_lang = name, None
            if not (BASE / entry["img"]).exists() and not entry.get("img_normal") and res["status"] == "ask":
                entry["img_normal"] = hybrid.image_url(res["cands"][0][0])
            cur = self._ai_book(entry, force)
            if cur is not None:
                # for the A-B-A check: the card before and the entry just counted
                self._ai_prev = (last_name, cur, now) if last_name and last_name != name else None
                self._ai_boxes = dict(getattr(self, "_ai_boxes", {}), **{name: res.get("box")})
                last = getattr(self, "_last_empty", None)   # why it may count again: what the frame was before
                before = f" · frame was {last[0]} {now - last[1]:.1f} s ago" if last and now - last[1] < 60 else ""
                log.info("Counted: %s %s #%s after %.2f s · %s%s", entry["name"], entry["set"], entry["number"],
                         now - (self._card_t0 or now), res.get("how"), before)
                self._card_t0 = now
                self._remember_crop(cur["added"], entry, res.get("how"))
                if res.get("lang"):  # confirmed via the image in this language: language is already settled
                    self._set_lang_checked(entry, cur["added"], res["lang"])
                else:
                    threading.Thread(target=self._lang_vote, args=(entry, cur["added"]), daemon=True).start()
                if games.current().print_check_after_count and res.get("img") is not None:
                    threading.Thread(target=self._print_check, args=(entry, cur["added"], frame, res),
                                     daemon=True).start()
                if games.current().stamp_check and res.get("img") is not None:
                    threading.Thread(target=self._stamp_check, args=(entry, cur["added"], frame, res),
                                     daemon=True).start()
        elif res["status"] == "none" and getattr(self, "_ai_fail_since", None) is not None \
                and now - self._ai_fail_since > 2.0 and carddb.exists() and not getattr(self, "_ocr_busy", False) \
                and games.current().text_recognition:
            # nothing found for a long time (e.g. card without fingerprint): try text recognition in the background
            self._ai_fail_since = now
            self._ocr_busy = True
            threading.Thread(target=self._ai_text_fallback, args=(frame.copy(), rect), daemon=True).start()
        self.stage = self._stage_of(res, name, recently or (agreed and name == self._ai_last_name))   # incl. just now
        hint = self._scan_hint(crop, small, sharp) if entry is None and self.settings.get("scan_hints") else None
        if entry is not None:
            self.status = (f"{entry['name']}   ·   {entry['set']} #{entry['number']}   ·   {how_text(res.get('how'))}"
                           f"   ·   {dt * 1000:.0f} ms")
        elif hint and now - self._card_t0 > HINT_AFTER:
            self.status = hint
        else:
            self.status = (how_text(res.get("how")) or tr("SCAN° searching …")) + f"   ·   {dt * 1000:.0f} ms"
        return seq

    @staticmethod
    def _stage_of(res, name, counted):
        """STAGES code of an AI frame that neither asks nor waits: counted (the card lying there is in the pack),
        otherwise what the scanner is busy with (its reason, aiscan "how")."""
        if name is not None and counted:
            return "counted"
        how = (res.get("how") or "").lower()
        if "reference images" in how:
            return "loading_refs"
        if "similar print" in how or "image match close" in how:
            return "comparing"
        if res.get("footer") or "collector line" in how:
            return "reading_line"
        return "searching"

    def _scan_hint(self, crop, small, sharp):
        """Tip on why the card isn't recognised (setting "Hints while scanning"): glare, too dark or
        blurry. Decided over the recent frames (majority), so a single shaky frame doesn't
        trigger anything. -> text or None"""
        hsv = cv2.cvtColor(cv2.resize(crop, (160, 224), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
        white = ((hsv[..., 2] >= 252) & (hsv[..., 1] < 20)).astype(np.uint8)
        glare = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)).mean()
        kind = "glare" if glare > 0.075 else "dark" if small.mean() < 60 and sharp < 2000 else             "blur" if sharp < 600 else None
        seen = self.__dict__.setdefault("_hint_seen", collections.deque(maxlen=8))
        seen.append(kind)
        top, n = collections.Counter(seen).most_common(1)[0]
        if top is None or n < 5:
            return None
        return {"glare": tr("Tip: glare on the card – tilt the light or the card a bit"),
                "dark": tr("Tip: too dark – more light on the card"),
                "blur": tr("Tip: blurry – hold the card still or adjust focus")}[top]

    def scan_langs(self):
        """Languages whose card images the AI also compares: default card language, last scanned language
        and the UI language (at most two, excluding English)."""
        out = []
        for lg in (self.settings.get("card_lang"), getattr(self, "_ai_last_lang", None),
                   getattr(self, "_recent_lang", None), i18n.LANG):
            if lg and lg != "en" and lg not in out:
                out.append(lg)
        return out[:2]

    def _auto_foil(self):
        """Automatic foil (from the print) only in "AI, Foil – Beta" – otherwise always normal."""
        return None if self.settings.get("scan_mode") == "ai_foil" else False

    def _ai_book(self, entry, force=False):
        """Count a recognized (or picked) card: mark the hit, fetch its image if it's missing, add it to the session.
        -> the new session entry, or None if it didn't count (e.g. the same card is still lying there)."""
        before = self.session.current
        self._mark_hit(entry)
        if not (BASE / entry["img"]).exists() and entry.get("img_normal"):
            threading.Thread(target=self._fetch_card_image, args=(entry,), daemon=True).start()
        self.session.on_card(entry, None, force=force, foil=self._auto_foil())
        cur = self.session.current
        if cur is not before and cur is not None and self._offered:
            self.unknown_gone = True   # recognized after all: close the card search it opened
        return cur if cur is not before and cur is not None else None

    def counted_by_hand(self, name):
        """The card lying there was picked in the card search (offered for it): don't count it again."""
        now = time.time()
        self._ai_last_name = name
        self._ai_counted = dict(getattr(self, "_ai_counted", {}), **{name: now})

    def _ai_count_chosen(self, entry, force=False, lang=None, how=None):
        """AI mode: print chosen in the question -> count (like a normal match). lang: chosen there as well (the card
        search shows the language keys) – then that language counts and nobody asks about it again."""
        now = time.time()
        self._ai_last_name, self._ai_last_lang = entry["name"], None
        counted = getattr(self, "_ai_counted", {})
        counted[entry["name"]] = now
        self._ai_counted = counted
        cur = self._ai_book(entry, force)
        if cur is not None:
            log.info("Counted (picked): %s %s #%s", entry["name"], entry["set"], entry["number"])
            self._remember_crop(cur["added"], entry, "gewählt")
            if how:   # finish/edition chosen in the question
                self.session.set_card(cur["added"], finish=how.get("finish"), edition=how.get("edition"))
            if lang:
                if (cur.get("lang") or "en") != lang:
                    self.session.set_card(cur["added"], lang=lang)
                return
            threading.Thread(target=self._lang_vote, args=(entry, cur["added"]), daemon=True).start()

    question_dropped = None   # name of a card whose question was dropped (taken away) – scan_ctl tells the user

    def _pending_other_card(self, frame):
        """A question is open (Oliver 2026-10-30): taking the card away does NOT end it – it is often picked up for a
        closer look; the same card laid back keeps it too. Only a NEW, OTHER card recognized surely (image match >=
        COUNT_NEEDS or the unambiguous fingerprint) ends it: that question is dropped (not counted – never blindly),
        the new card is scanned as usual. Checked every 0.3 s in the background, so scanning never blocks.
        -> True if the question was dropped."""
        now = time.time()
        if self.fp_index is None or now < getattr(self, "_pend_next", 0.0):
            return False
        self._pend_next = now + 0.3
        fh, fw = frame.shape[:2]
        x, y, w, h = zone_rect(self.settings["zone"], fw, fh)
        crop = frame[y:y + h, x:x + w]
        if not crop.size:
            return False
        small = cv2.cvtColor(cv2.resize(crop, (160, 224), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        if cv2.Canny(cv2.GaussianBlur(small, (3, 3), 0), 50, 150).mean() / 255 < 0.02:
            return False   # nothing there (taken into the hand): the question stays
        try:
            res = self.live.step(frame, (x, y, w, h), self.fp_index, self.prefer_sets(), focus=self.focus_sets())
        except Exception:  # noqa: BLE001 – a failed look never ends the question
            log.exception("Looking for another card during a question")
            return False
        how = res.get("how") or ""
        sure = res.get("status") == "ok" and (res.get("strength", 0) >= aiscan.COUNT_NEEDS or "unambiguous" in how)
        name = (res.get("entry") or {}).get("name") or ""
        asked = (self.pending.get("r") or {}).get("name") or ""
        if not sure or not name or name == asked:
            return False
        self.resolve(None)
        self.question_dropped = asked
        self._ai_reset()
        log.info("Question dropped – another card is there (%s instead of %s)", name, asked)
        return True

    def _empty_kind(self, small):
        """An empty frame (no edges in the scan zone): "mat" – the card is gone; "dark" – the camera isn't seeing yet
        (waking up); "covered" – something smooth lies over the card (a hand), the card is still there. The mat is
        learnt from the empty frames themselves (slowly, so the light may change); still "covered" after
        COVER_AS_MAT it is taken as the mat."""
        if small.mean() < DARK_BELOW:
            return "dark"
        thumb = cv2.resize(small, (32, 44)).astype(np.int16)
        mat, now = getattr(self, "_mat", None), time.time()
        if mat is None or np.abs(thumb - mat).mean() < MAT_DIFF or thumb.std() >= UNIFORM_STD:
            self._mat = thumb if mat is None else (mat * 7 + thumb) // 8
            self._cover_since = None
            return "mat"
        since = getattr(self, "_cover_since", None)
        if since is None:
            self._cover_since = now
        elif now - since > COVER_AS_MAT:
            self._mat, self._cover_since = thumb, None
            return "mat"
        return "covered"

    def _lying_still(self, name, box):
        """A card counted since the frame was last empty is back where it was counted, while the card counted
        after it lay somewhere else: two cards lie in view and the tracking hopped back – the same card, not a new
        one (in a stack in the hand every card lies at the same place: there it counts as before)."""
        boxes = getattr(self, "_ai_boxes", {})
        was, last = boxes.get(name), boxes.get(getattr(self, "_ai_last_name", None))
        return (box is not None and was is not None and last is not None and name != self._ai_last_name
                and _iou(box, was) >= 0.5 and _iou(last, was) < 0.3)

    def _ai_reset(self):
        self.live._foot_reads = []   # collector line reads of the card that is gone – never for the next one
        self._ai_known = self._ai_thumb = self._ai_last_name = self._ai_last_lang = None
        self._ai_hist, self._card_t0, self._ai_fail_since = [], None, None
        self._ai_counted, self._ai_other_lang = {}, []
        self._ai_prev, self._ai_boxes = None, {}
        self.current, self.hit, self.looking = None, None, False

    def _fetch_card_image(self, entry):
        try:
            library.fetch_image(entry, entry["img_normal"])
        except Exception as e:
            log.info("Image %s: %s", entry["img"], e)

    def _remember_crop(self, added, entry, how=None):
        """For the scan data: keep a crop of the card just counted in memory (only written on a
        correction – see scandata)."""
        if not self.settings.get("scan_data", True):
            return
        try:
            frame, box = self.camera.latest()[0], getattr(self.live, "prior", None)
            if frame is not None and box is not None:
                x, y, w, h = box
                scandata.remember(added, frame[y:y + h, x:x + w].copy(), entry, how)
        except Exception:  # noqa: BLE001
            log.exception("Remembering scan data")

    def _ai_text_fallback(self, frame, rect):
        try:
            # only count if name, set and number match (otherwise text recognition misreads too easily)
            d = ocrscan.scan_frame(frame, rect, detail=True)
            if d["entry"] is not None and d["conf"] >= 0.95 \
                    and d["entry"]["name"] != getattr(self, "_ai_last_name", None):
                self._ai_last_name = d["entry"]["name"]
                lang = d["r"].get("lang") if d["r"].get("lang") not in (None, "en") else None
                self.session.on_card(d["entry"], lang)
                log.info("Counted via OCR (AI found nothing): %s %s #%s", d["entry"]["name"],
                         d["entry"]["set"], d["entry"]["number"])
        except Exception:
            log.exception("OCR (fallback)")
        finally:
            self._ocr_busy = False

    def _lang_vote(self, entry, added):
        """Language of the card just counted: read the name line in the next frames until two readings
        agree (or one is very clear). Unclear -> ask briefly. Runs in the background."""
        votes, t_end = [], time.time() + 1.6
        try:
            names = langcheck.printed_names(entry)
            if len(names) == 1:
                return
            while time.time() < t_end and getattr(self, "_ai_last_name", None) == entry["name"]:
                frame, _ = self.camera.latest()
                box = self.live.prior
                if frame is None or box is None:
                    time.sleep(0.05)
                    continue
                x, y, w, h = box
                lg, info = langcheck.detect(frame[y:y + h, x:x + w], entry, frame, box)
                if lg is not None:
                    votes.append((lg, (info.get("scores") or [(lg, 0)])[0][1]))
                    decided = langcheck.vote(votes)
                    if decided is not None:
                        self._set_lang_checked(entry, added, decided)
                        log.info("Language %s %s: %s (%s)", entry["set"], entry["number"], decided, votes)
                        return
                time.sleep(0.12)
            if len(votes) == 1:  # only one reading, but clear enough
                self._set_lang_checked(entry, added, votes[0][0])
                return
            if entry.get("plang"):   # Asian print, language unclear (e.g. JA or ZH-TW): it keeps its own language
                return
            if self._take_log_lang(entry, added, names, votes):   # unclear: the language this log scans in
                return
            sl = getattr(self, "_session_lang", None)   # unclear: take the language of the last cards of this session
            last = sl[1] if sl and sl[0] == self.session.id else None
            if last is not None and last in names and not any(sc >= 85 and lg != last for lg, sc in votes):
                self._set_lang_checked(entry, added, last)
                log.info("Language %s %s: like the last cards (%s), readings %s", entry["set"], entry["number"],
                         last, votes)
                return
            self.lang_ask = {"added": added, "entry": entry, "names": names,
                             "img": self.live._crop(self.camera.latest()[0], self.live.prior)
                             if self.live.prior is not None and self.camera.latest()[0] is not None else None}
        except Exception:
            log.exception("Language vote")

    def _take_log_lang(self, entry, added, names, votes):
        """The language is unclear: take the one this log scans in (Scan tile → Settings → Language) – only if the
        card exists in it and no reading clearly shows another language (>= 85, the same guard as "like the last
        cards"); a clearly read language always wins before this is asked. -> taken?"""
        want = self.session.scan_lang_for(entry)
        if not want or want not in names or any(sc >= 85 and lg != want for lg, sc in votes):
            return False
        cur = self.session.find(added)
        if cur is None:
            return False
        self._set_lang_checked(entry, added, want)
        log.info("Language %s %s: the log's language (%s), readings %s", entry["set"], entry["number"], want, votes)
        return True

    def _print_check(self, entry, added, frame, res):
        """Pokémon, Yu-Gi-Oh!: the same artwork in several prints – read the collector line in the background and
        correct the counted print if it clearly names another one (scanning doesn't wait for it). Games with their own
        collector line parser (Lorcana: "5/204 • DE • 1") take the language – and a print the line clearly names –
        from it first."""
        try:
            if games.current().footer_parse is not None:
                entry = self._footer_check(entry, added, frame, res) or entry
            group = aiscan.art_group(entry, index=self.fp_index)
            if len(group) < 2:
                return
            box = None if aiscan._is_warped(res.get("box")) else res.get("box")
            pick, why = aiscan.resolve_generic(frame, res["img"], box, entry, group)
            if pick["id"] != entry["id"]:
                self.session.replace_added(added, pick)
                log.info("Print via collector line: %s %s -> %s %s%s", entry["set"], entry["number"], pick["set"],
                         pick["number"], why)
        except Exception:
            log.exception("Print check")

    def _stamp_check(self, entry, added, frame, res):
        """After counting, in the background: is there exactly one stamped special print of the counted one (Magic:
        prerelease promo – same art, same collector line, only the date stamp differs)? Stamp on the card -> that
        print; no stamp read -> the counted one stays (never the other way round)."""
        try:
            g = games.current()
            with carddb.connection() as con:
                twin = g.stamped_twin(con, entry)
            if twin is None:
                return
            box = res.get("box")
            card = langcheck.card_view(res["img"], entry, frame, None if aiscan._is_warped(box) else box)
            if card is None and aiscan._is_warped(box):   # already the straightened card
                card = res["img"]
            if card is None or not g.has_stamp(card):
                return
            pick = carddb.entry_from_row(twin)
            pick["img_normal"] = hybrid.image_url(twin)
            with self._print_lock:   # the language check (_set_lang_checked) may have changed the card meanwhile
                pos = self.session.find(added)
                cur = self.session.packs[pos[0]]["cards"][pos[1]] if pos is not None else None
                if cur is None or (str(cur["set"]).lower(), str(cur["number"])) != \
                        (str(entry["set"]).lower(), str(entry["number"])):
                    return   # removed, or already another print (e.g. the language's): leave it
                lang = cur.get("lang")
                self._stamped[added] = pick
                while len(self._stamped) > 50:
                    self._stamped.pop(next(iter(self._stamped)))
                self.session.replace_added(added, pick)
                if lang:
                    self.session.set_card(added, lang=lang)
            log.info("Print via stamp: %s %s -> %s %s", entry["set"], entry["number"], pick["set"], pick["number"])
        except Exception:
            log.exception("Stamp check")

    def _footer_check(self, entry, added, frame, res):
        """Collector line of the counted card (footer_parse of the game): another language -> set it, another print that
        exists -> replace the counted one. -> the print now counted, or None if nothing changed."""
        box = res.get("box")
        card = langcheck.card_view(res["img"], entry, frame, None if aiscan._is_warped(box) else box)
        if card is None and aiscan._is_warped(box):   # already the straightened card
            card = res["img"]
        got = aiscan.LiveScanner.read_footer(card) if card is not None else None
        if got is None:
            return None
        changed = None
        if (got["set"], got["number"]) != (str(entry["set"]).lower(), str(entry["number"]).lower()):
            row = hybrid.row_by_print(got["set"], got["number"])
            if row is not None:
                changed = carddb.entry_from_row(row)
                changed["img_normal"] = hybrid.image_url(row)
                self.session.replace_added(added, changed)
                log.info("Print via collector line: %s %s -> %s %s", entry["set"], entry["number"], changed["set"],
                         changed["number"])
        if got.get("lang"):   # printed on the card: settled – the name-band guess (_lang_vote) may not overwrite it
            footer = self.__dict__.setdefault("_lang_by_footer", {})
            footer[added] = got["lang"]
            while len(footer) > 50:
                footer.pop(next(iter(footer)))
        counted = res.get("lang") or self.settings.get("card_lang") or "en"
        if got.get("lang") and got["lang"] != counted:
            self._set_lang_checked(changed or entry, added, got["lang"])
            log.info("Language via collector line: %s", got["lang"])
        return changed

    def _set_lang_checked(self, entry, added, lang):
        """Set the language – if the chosen print doesn't exist in it (e.g. special print only in English), switch to a
        print of the same card that exists in that language."""
        printed = getattr(self, "_lang_by_footer", {}).get(added)
        if printed is not None and lang != printed:   # the collector line already settled it (_footer_check)
            return
        self._ai_last_lang = lang
        self._session_lang = (self.session.id, lang)   # persists across empty frames (per session)
        if lang != "en":
            self._recent_lang = lang  # the AI then also compares with images in this language
        with self._print_lock:   # _stamp_check corrects the same card in its own thread
            # the stamp settled the print (prerelease promo): only the language changes, never back to the normal print
            row = None if added in self._stamped else langcheck.print_in_lang(entry, lang)
            if row is not None:
                fixed = carddb.entry_from_row(row)
                fixed["img_normal"] = hybrid.image_url(row)
                self.session.replace_added(added, fixed)
                log.info("Print for %s: %s %s -> %s %s", lang, entry["set"], entry["number"], fixed["set"],
                         fixed["number"])
            self.session.set_card(added, lang=lang)

    @staticmethod
    def _sharpness(frame, rect):
        x, y, w, h = rect
        g = cv2.cvtColor(cv2.resize(frame[y:y + h, x:x + w], (256, int(256 * h / max(1, w))),
                                    interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(g, cv2.CV_32F).var()

    def prefer_sets(self):
        """Sets preferred on a tie: those of the session and the ones already confirmed here."""
        codes = {st["code"].lower() for st in (self.session.info.get("sets") or []) if st.get("code")}
        return codes | set(self.confirmed)

    def focus_sets(self):
        """Filtered scan ("Only these sets" in the log tile): opening boosters or scanning cards with sets chosen ->
        their codes – the fingerprint ranks among their prints first (aiscan.FOCUS_EPS: only when the card is from
        there, the full search runs along as the check), their data and reference features wait in RAM
        (scan_ctl.preload_filtered_sets); otherwise none."""
        from scanner.core import kind_of
        if kind_of(self.session.info) not in ("packs", "cards"):
            return ()
        return tuple(sorted({st["code"].lower() for st in (self.session.info.get("sets") or []) if st.get("code")}))

    def _recognize(self, frame, rect):
        """AI fingerprint (scan mode "ai"), otherwise/as fallback text recognition + image comparison.
        -> {"status": "ok"|"ask"|"none", "entry", "r", "how", "cands", "img"}"""
        empty_r = {"name": "", "number": None, "set": None, "lang": None}
        if self.settings.get("scan_mode") in ("ai", "ai_foil"):
            if self.fp_index is None:  # fingerprints are still being computed (or no SCAN° Engine): text recognition
                note = tr("SCAN° fingerprints are still being computed") if fingerprint.available() else                     tr("SCAN° Engine missing – reading the card's text instead")
                return dict(self._recognize_text(frame, rect), note=note)
            res = aiscan.recognize(frame, rect, self.fp_index, self.prefer_sets())
            if res["status"] != "none":
                self._ai_fails = 0
                res.update(r=empty_r, ai=True)
                return res
            self._ai_fails = getattr(self, "_ai_fails", 0) + 1
            steady = self._steady_since is not None and time.time() - self._steady_since >= 0.3
            if not carddb.exists() or not games.current().text_recognition:
                return dict(res, r=empty_r, how=tr("no matching card in the downloaded sets"), retry=True)
            if not steady or self._ai_fails < 2:
                # card is still moving (blurred): just try the next frame, no text recognition
                return dict(res, r=empty_r, how=tr("SCAN° searching …"), retry=True)
        return self._recognize_text(frame, rect)

    def _recognize_text(self, frame, rect):
        """Text recognition + image comparison."""
        d = ocrscan.scan_frame(frame, rect, detail=True)
        out = {"status": "ok" if d["entry"] else "none", "entry": d["entry"], "r": d["r"], "how": d["how"],
               "cands": [], "img": d["img"]}
        if d["conf"] >= 0.95:  # name, set and number match
            return out
        if d["row"] is not None and ocrscan.unique_result(d["conf"], d["how"]):
            # text pins down exactly one print: check only this image instead of ten candidates
            inl = hybrid.confirm(d["img"], d["row"])
            if inl >= hybrid.MIN_INLIERS:
                out["how"] = d["how"] + tr(f" · image confirmed ({inl})")
                out["entry"]["img_normal"] = hybrid.image_url(d["row"])
                return out
        prefer = self.prefer_sets()
        cands = ocrscan.candidates(d["r"], first=d["row"], prefer_sets=prefer)
        res = hybrid.decide([d["img"], d["region"]], cands, d["r"], prefer) if cands else None
        if res and res["status"] == "ok":
            entry = carddb.entry_from_row(res["row"])
            entry["img_normal"] = hybrid.image_url(res["row"])
            out.update(entry=entry, status="ok", how=tr(f"image match ({res['inliers']} points, {res['loaded']} images)"))
        elif res and res["status"] == "ask":
            out.update(status="ask", cands=res["cands"])
        elif d["entry"] is not None and d["conf"] < 0.8:
            # no image matches (e.g. offline): with several prints don't guess, ask instead
            same = [c for c in cands if c["name"] == d["row"]["name"]][:hybrid.ASK_MAX]
            if len(same) > 1:
                out.update(status="ask", cands=[(c, 0) for c in same])
        return out

    def _mark_hit(self, entry):
        if self.hit is None or self.hit[0]["id"] != entry["id"]:
            self.hit = (entry, time.time())

    def _check_lang(self, entry, frame, rect, res=None):
        """AI mode: determine the language of the card just counted (artwork is the same in all languages). The card
        is straightened exactly via image matching, its name line read and compared with the printed names in
        all languages. Unclear -> ask (doesn't block). Runs in the background."""
        try:
            time.sleep(0.15)  # priority for recognising the next card
            cur = self.session.current
            if cur is None or cur["id"] != entry["id"]:
                return
            if res is not None and res.get("box") is not None:
                lang, info = langcheck.detect(res["img"], entry, frame, res["box"])
                log.info("Language %s %s: %s · %s", entry["set"], entry["number"], lang, info)
                if lang is not None:
                    if (cur.get("lang") or "en") != lang:
                        self.session.set_card(cur["added"], lang=lang)
                else:
                    names = langcheck.printed_names(entry)
                    if len(names) > 1 and not self._take_log_lang(entry, cur["added"], names,
                                                                  info.get("scores") or []):
                        self.lang_ask = {"added": cur["added"], "entry": entry, "names": names, "img": res["img"]}
            if self.session.current is None or self.session.current["id"] != entry["id"]:
                return
            d = ocrscan.scan_frame(frame, rect, detail=True)
            row, lang = d["row"], d["r"].get("lang")
            cur = self.session.current
            if (row is not None and d["conf"] >= 0.95 and row["set_code"] != entry["set"].lower()
                    and ocrscan._front(row["name"]) == ocrscan._front(entry["name"])
                    and cur is not None and cur["id"] == entry["id"]):
                # same artwork, different set (reprint, Special Guest): the footer clearly says something else
                fixed = carddb.entry_from_row(row)
                self.session.replace(fixed, lang=lang if lang and lang != "en" else None)
                log.info("Set corrected via footer: %s %s -> %s %s", entry["set"], entry["number"],
                         fixed["set"], fixed["number"])
                return
            same = row is not None and row["set_code"] == entry["set"].lower() and row["number"] == entry["number"]
            if res is not None or not lang or lang == "en" or not (same or d["r"].get("set") == entry["set"].lower()):
                return  # (AI mode: language comes from the name line, see above)
            if cur is not None and cur["id"] == entry["id"] and cur.get("lang") != lang:
                self.session.set_card(cur["added"], lang=lang)
                log.info("Language detected afterwards: %s %s -> %s", entry["set"], entry["number"], lang)
        except Exception:
            log.exception("Language check")

    def _count(self, entry, lang, shot=None, how=None):
        self._mark_hit(entry)
        if not (BASE / entry["img"]).exists() and entry.get("img_normal"):
            try:  # fetch image for overlay/statistics (set not downloaded)
                library.fetch_image(entry, entry["img_normal"])
            except Exception as e:
                log.info("Image %s: %s", entry["img"], e)
        before = self.session.current
        self.session.on_card(entry, lang)
        cur = self.session.current
        if how and cur is not None and cur is not before:   # finish/edition chosen in the question
            self.session.set_card(cur["added"], finish=how.get("finish"), edition=how.get("edition"))
        if shot is not None and self.session.current is not before and not lang:
            threading.Thread(target=self._check_lang, args=(entry, *shot), daemon=True).start()

    def resolve(self, row):
        """Answer from the question window (main thread): row of the card database or None (skip)."""
        p, self.pending = self.pending, None
        if p is None:
            return
        if row is None:
            self._ocr_last = {"status": "none", "entry": None, "r": p["r"], "how": tr("skipped"), "cands": [],
                              "img": None}
            self._ocr_thumb, self._ocr_hist = p["thumb"], []
            return
        entry = row.get("_entry") or carddb.entry_from_row(row)
        if not row.get("_entry"):
            entry["img_normal"] = hybrid.image_url(row)
        self.confirmed[row["set_code"]] += 1
        if p.get("ai"):  # AI mode: count the chosen print (in the language set in the card search – no question after)
            self._ai_count_chosen(entry, p.get("force", False), lang=p.get("chosen_lang"), how=p.get("chosen_how"))
            return
        self._ocr_last = {"status": "ok", "entry": entry, "r": p["r"], "how": tr("confirmed"), "cands": [],
                          "img": None}
        self._known = self._ocr_last
        self._ocr_thumb, self._ocr_hist = p["thumb"], [entry["id"], entry["id"]]
        self.current = entry
        threading.Thread(target=self._count, args=(entry, p.get("chosen_lang") or p["lang"]),
                         kwargs={"how": p.get("chosen_how")}, daemon=True).start()
