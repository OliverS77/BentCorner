"""Scan studio: contribute cards to the database Bent°Corner is building (missing cards, e.g. Japanese
Pokémon, better images, alt arts by artists). Saves NOTHING to the collection.

Layout (ScanPage.qml): "Studio" button in the bottom bar – the scan overlay slides out, the studio panels slide in
left and right, the camera image stays in the middle (with the detected card outline).
    left    camera (device, resolution, focus & exposure), indicator lights "card found · sharp · no glare ·
            light · size", capture (by hand or automatically as soon as everything fits), short instructions
    right   the current card: large image (or empty card mask), further shots, game, name, set, number,
            language, rarity, purpose (alt art: artist required) – "Into the box" at the bottom
    box     button left of the right column (carton + count): expands upwards – "In the box" (rows with
            thumbnail, click = edit on the right; the current card stays parked at the top), attribution, message
            to Bent°Corner, consent, "Upload all"; "Sent" = status per card, grouped by submission

While the studio is open, recognition pauses (nothing is counted). Shots: from the latest camera frames the
sharpest with a detected card, straightened (studiocap.py), corners rounded, as PNG. Files (scanner, phone photo)
are cropped the same way, metadata (EXIF, GPS) is dropped in the process.

Storage: box under data/studio/kiste/<cid>/ (card.json, images, thumbnail – survives restarts), sent cards each
under data/studio/<pid>/ (meta.json with "bundle", images, state.json). Uploads go in chunks to the
mailbox (server/box: /v1/studio/…), signed with the installation's key (relay.py). "Sent" fetches status and
reply note from the server.
"""
import base64
import hashlib
import json
import logging
import pathlib
import shutil
import threading
import time
import uuid

import cv2
import numpy as np
from PySide6 import QtCore, QtGui

from system import contacts
from ui import qform
from ui import quickimages
from scanner import studiocap
from scanner.common import DATA
from system.i18n import tr

log = logging.getLogger("booster")

DIR = DATA / "studio"
BOX = DIR / "kiste"
PART = 1024 * 1024
KINDS = (("front", "Next: front"), ("back", "Next: back"), ("light", "Next: foil / other light"),
         ("extra", "Next: extra"))
SHOT_NAMES = {"front": "Front side", "back": "Back side", "light": "Foil light", "extra": "Extra"}
PURPOSES = (("missing", "Missing from the database"), ("better", "Better image"), ("altart", "Alt-art"))
STATUS = {"wartet": "waiting to upload", "laedt": "uploading …", "neu": "received",
          "geprueft": "checked", "weitergegeben": "passed on – thank you!", "abgelehnt": "not taken",
          "angefragt": "asking the artist", "whitelist": "approved (scannable)", "blacklist": "artist said no",
          "fehler": "upload failed"}
RESOLUTIONS = (("std", "Same as scanning"), ("max", "Highest (up to 4K)"))
FIELDS = ("game", "name", "set", "number", "lang", "rarity", "purpose", "artist", "link", "own_art", "bulk_folder")
TIPS = ("Take the card out of its sleeve – sleeves reflect.",
        "A matte, plain background that stands out from the card's border (grey almost always works); the card lies flat.",
        "Two lamps from left and right at an angle (about 45°), no direct sunlight.",
        "Camera straight from above, the card fills a good half of the image.",
        "Foil/holo: a second capture with the light turned (“foil / other light”).",
        "Even better: a scanner (600 dpi) or a sharp phone photo – just use “Load file”.")


def _now_id():
    return time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8]


def _qimage(bgr_or_bgra, max_h=None):
    img = bgr_or_bgra
    if max_h and img.shape[0] > max_h:
        img = cv2.resize(img, (int(img.shape[1] * max_h / img.shape[0]), max_h), interpolation=cv2.INTER_AREA)
    if img.shape[2] == 4:
        rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        q = QtGui.QImage(rgba.data, rgba.shape[1], rgba.shape[0], rgba.strides[0], QtGui.QImage.Format_RGBA8888)
    else:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        q = QtGui.QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QtGui.QImage.Format_RGB888)
    return q.copy()


def _file_url(path):
    return QtCore.QUrl.fromLocalFile(str(path)).toString() + f"?{int(path.stat().st_mtime * 1000)}"


def _read_png(path):
    data = np.fromfile(str(path), np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is not None and img.ndim == 3 and img.shape[2] == 4:   # saved with rounded corners: color back
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


class Shot:
    """One shot: straightened card (BGR) + optionally the original."""

    def __init__(self, kind, card, original=None, source="camera", sid=None):
        self.id = sid or uuid.uuid4().hex[:8]
        self.kind, self.card, self.original, self.source = kind, card, original, source
        self.rev = 0

    def rotate(self):
        self.card = cv2.rotate(self.card, cv2.ROTATE_180)
        self.rev += 1


def _games():
    import games
    return [(k, n) for k, n, _ in games.GAMES if k not in games.WITHDRAWN]


class StudioBackend(QtCore.QObject):
    changed = QtCore.Signal()
    boxChanged = QtCore.Signal()
    shotTaken = QtCore.Signal(str)   # image URL of the new shot (shown briefly at the top center)
    flyToBox = QtCore.Signal(str)    # card flies into the box (image URL)
    sentAway = QtCore.Signal()       # box uploaded: the plane takes off

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self._on = False
        self.quad = None          # detected outline in the camera image (for the drawing in the middle)
        self.q = {}               # indicator lights (studiocap.quality)
        self.auto = bool(ctrl.settings.get("studio_auto", True))
        self.kind = "front"
        self.res = "std"
        self._was_paused = None
        self._busy = False
        self._ok_ticks = 0
        self._last_auto = 0.0
        self._last_quad = None
        self.since = 0.0          # time of opening/closing (overlay slides out/in)
        self.card = self._blank()
        self.editing = None       # cid of the box card currently being edited on the right
        self.parked = None        # the current card, while one from the box is being edited
        self.viewing = None       # pid of a sent card that is only viewed on the right (greyed out)
        self.bulk = False         # folder upload unlocked (the server says so at /mine)
        self.limits = {}          # {"cards", "sends", "cards_left", "sends_left"} from the server (/mine)
        self.limit_hit = False    # daily limit reached: the rest waits until tomorrow
        self.msg = ""
        self.box_msg = ""
        self._box_open, self._box_tab = False, "box"
        self.mine_msg = ""
        self.uploading = False
        self._front_gen = 0
        self._tick = QtCore.QTimer(self, interval=250, timeout=self._check)
        self.left = qform.Form(self._build_left, self)
        self.right = qform.Form(self._build_right, self)
        self.boxf = qform.Form(self._build_box, self)

    def _blank(self):
        import games
        return {"cid": uuid.uuid4().hex[:10], "game": games.current().key, "name": "", "set": "", "number": "",
                "lang": "en", "rarity": "", "purpose": "missing", "artist": "", "link": "", "shots": [],
                "keep_original": False, "own_art": False, "bulk_folder": False}

    # ---------- on/off ----------
    @QtCore.Property(bool, notify=changed)
    def on(self):
        return self._on

    @QtCore.Slot()
    def toggle(self):
        self.set_on(not self._on)

    def set_on(self, on):
        if on == self._on:
            return
        self._on = on
        self.since = time.monotonic()
        rec = self.ctrl.recognizer
        if on:   # recognition pauses – nothing is counted in the studio
            self._was_paused = rec.paused
            rec.paused = True
            self._tick.start()
            self.refresh_mine()
            self.upload_all()   # send what was left over (no network last time) now
        else:
            self._tick.stop()
            self.quad, self.q = None, {}
            self._box_open = False
            if self._was_paused is not None:
                rec.paused = self._was_paused
            rec.hold_until_empty = True   # the studio card may still be lying there: do not count it into the session
            w = int(self.ctrl.settings["resolution"].split("x")[0])
            size = getattr(self.ctrl.camera, "size", None)
            if self.res != "std" or (size and size[0] > w * 1.25):   # also when the camera stayed on 4K
                self._set_res("std")
        self.left.refresh()
        self.right.refresh()
        self.changed.emit()
        self.boxChanged.emit()

    # ---------- Camera ----------
    def _set_res(self, key):
        self.res = key
        ctrl = self.ctrl
        idx = ctrl.cam_combo.currentData()
        if idx is None or idx == getattr(ctrl.camera, "PHONE", "phone"):
            return
        if key == "max":
            ctrl.camera.start(idx, 3840, 2160)   # the camera takes the largest it can
        else:
            w, h = map(int, ctrl.settings["resolution"].split("x"))
            ctrl.camera.start(idx, w, h)
        QtCore.QTimer.singleShot(2500, ctrl.apply_cam_controls)

    def _pick_camera(self, i):
        self.ctrl.cam_combo.setCurrentIndex(i)
        self.ctrl.camera_selected()
        self.res = "std"
        self.left.soon()

    def _check(self):
        """4× per second: find the card in the image, set the indicator lights (in the background – 4K is slow)."""
        if self._busy or not self._on:
            return
        frame, _ = self.ctrl.camera.latest()
        if frame is None:
            if self.quad is not None or self.q:
                self.quad, self.q = None, {}
            self.left.soon()
            return
        self._busy = True

        def work():
            try:
                quad = studiocap.find_quad(frame)
                q = studiocap.quality(frame, quad)
            except Exception:  # noqa: BLE001
                log.exception("Studio: check")
                quad, q = None, {}
            self.quad, self.q = quad, q
            self._busy = False
            QtCore.QMetaObject.invokeMethod(self, "_checked", QtCore.Qt.QueuedConnection)
        threading.Thread(target=work, daemon=True).start()

    @QtCore.Slot()
    def _checked(self):
        self.left.soon()
        if not (self.auto and self.q.get("ok")) or self._box_open:
            self._ok_ticks = 0
            return
        self._ok_ticks += 1
        moved = self._last_quad is None or float(np.abs(np.asarray(self.quad) - self._last_quad).max()) > 40
        if self._ok_ticks >= 3 and moved and time.monotonic() - self._last_auto > 3:
            self._last_auto = time.monotonic()
            self.capture()

    @QtCore.Slot()
    def capture(self):
        """Capture: sharpest of the latest camera frames with a detected card, straightened."""
        if self.viewing is not None:   # sent card being viewed: first back to the current one
            self.backToCurrent()
        frames = [f for _, f in self.ctrl.camera.recent_frames()]
        if not frames:
            self.msg = tr("No camera image – is the camera on?")
            self.left.soon()
            return
        frame, quad = studiocap.best(frames)
        if frame is None:
            self.msg = tr("No card found – get the whole card in view, dark background.")
            self.left.soon()
            return
        card = studiocap.warp(frame, quad)
        cam = self.ctrl.camera   # mirrored display: turn the image itself the right way round again
        if cam.mirror and cam.flip_v:
            card = cv2.flip(card, -1)
        elif cam.mirror:
            card = cv2.flip(card, 1)
        elif cam.flip_v:
            card = cv2.flip(card, 0)
        self._last_quad = np.asarray(quad)
        self._add_shot(Shot(self.kind, card, frame))

    def _add_shot(self, shot):
        shots = self.card["shots"]
        if shot.kind == "front":   # one front per card – a new one replaces the old one
            shots[:] = [s for s in shots if s.kind != "front"]
            if self.kind == "front":   # then suggest the back right away
                self.kind = "back"
        shots.append(shot)
        self.msg = ""
        url = quickimages.put(f"studio-new-{shot.id}", _qimage(studiocap.rounded(shot.card), 520))
        self.shotTaken.emit(url)
        self._card_changed()

    def load_file(self):
        from ui import qdialogs
        paths = qdialogs.open_files(tr("Load image"), "", tr("Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp)"))
        if paths and self.viewing is not None:
            self.backToCurrent()
        for p in paths or []:
            card, found = studiocap.from_file(p)
            if card is None:
                self.msg = tr("Couldn't read the image.")
                continue
            if not found:
                self.msg = tr("No card outline found – the image is used as it is.")
            kind = "front" if not self._front() else (self.kind if self.kind != "front" else "back")
            self._add_shot(Shot(kind, card, None, source="file"))
        self.right.refresh()

    # ---------- current card ----------
    def _front(self):
        return next((s for s in self.card["shots"] if s.kind == "front"), None)

    def _card_changed(self):
        self._front_gen += 1
        self.left.soon()
        self.right.soon()
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def frontUrl(self):
        f = self._front()
        if f is None:
            return ""
        return quickimages.put(f"studio-front-{f.id}-{f.rev}", _qimage(studiocap.rounded(f.card), 1100))

    @QtCore.Property(bool, notify=changed)
    def viewingSent(self):
        return self.viewing is not None

    @QtCore.Property(str, notify=boxChanged)
    def viewingPid(self):
        return self.viewing or ""

    def ready(self):
        """-> "" if the card can go into the box, otherwise what is missing."""
        if not self._front():
            return tr("Front is missing")
        if not self.card["name"].strip():
            return tr("Card name is missing")
        if self.card["purpose"] == "altart" and not self.card["artist"].strip():
            return tr("Artist is missing (required for alt-arts)")
        return ""

    def _title(self, c):
        bits = [c.get("name") or tr("Unnamed")]
        if c.get("set") or c.get("number"):
            bits.append(f"{str(c.get('set') or '').upper()} #{c.get('number') or ''}".strip())
        return " · ".join(bits)

    def _save_card(self, c):
        """Write the card into the box (one folder per card) -> path of the thumbnail."""
        folder = BOX / c["cid"]
        folder.mkdir(parents=True, exist_ok=True)
        names = []
        for s in c["shots"]:
            name = f"{s.kind}-{s.id}.png"
            (folder / name).write_bytes(studiocap.encode_png(studiocap.rounded(s.card)))
            entry = {"name": name, "kind": s.kind, "source": s.source, "id": s.id}
            if c.get("keep_original") and s.original is not None:
                oname = f"{s.kind}-{s.id}-original.jpg"
                (folder / oname).write_bytes(studiocap.encode_jpg(s.original))
                entry["original"] = oname
            names.append(entry)
        keep = {e["name"] for e in names} | {e.get("original") for e in names} | {"card.json", "thumb.png"}
        for old in folder.iterdir():   # clean up shots removed/rotated while editing
            if old.name not in keep:
                try:
                    old.unlink()
                except OSError:
                    pass
        front = next(s for s in c["shots"] if s.kind == "front")
        (folder / "thumb.png").write_bytes(studiocap.encode_png(studiocap.rounded(
            cv2.resize(front.card, (120, int(120 * front.card.shape[0] / front.card.shape[1])),
                       interpolation=cv2.INTER_AREA))))
        data = {k: c.get(k, "") for k in FIELDS}
        data.update(cid=c["cid"], files=names, t=c.get("t") or int(time.time()), keep_original=c.get("keep_original"))
        (folder / "card.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        return folder / "thumb.png"

    def _load_card(self, cid):
        folder = BOX / cid
        d = json.loads((folder / "card.json").read_text("utf-8"))
        c = self._blank()
        c.update({k: d.get(k, c.get(k)) for k in FIELDS}, cid=cid, t=d.get("t"),
                 keep_original=bool(d.get("keep_original")))
        for f in d.get("files") or []:
            img = _read_png(folder / f["name"])
            if img is None:
                continue
            orig = None
            if f.get("original") and (folder / f["original"]).exists():
                orig = cv2.imdecode(np.fromfile(str(folder / f["original"]), np.uint8), cv2.IMREAD_COLOR)
            c["shots"].append(Shot(f["kind"], img, orig, f.get("source") or "camera", f.get("id")))
        return c

    def put_in_box(self):
        """Save via "Into the box" or "Apply changes", then the right side is empty again (or the parked card)."""
        if self.ready():
            return
        thumb = self._save_card(self.card)
        self.flyToBox.emit(_file_url(thumb))
        if self.editing is not None:
            self.editing = None
            self.card = self.parked or self._blank()
            self.parked = None
        else:   # next card: game and language stay (usually a stack from the same game follows)
            old = self.card
            self.card = self._blank()
            self.card.update(game=old["game"], lang=old["lang"])
        self.kind = "front"
        self.msg = ""
        self.right.refresh()
        self._card_changed()
        self.boxChanged.emit()

    # ---------- Box ----------
    def _box_ids(self):
        if not BOX.exists():
            return []
        out = []
        for d in BOX.iterdir():
            try:
                t = json.loads((d / "card.json").read_text("utf-8")).get("t") or 0
            except (OSError, ValueError):
                continue
            out.append((t, d.name))
        return [cid for _, cid in sorted(out)]

    @QtCore.Property(int, notify=boxChanged)
    def boxCount(self):
        return len(self._box_ids())

    @QtCore.Property("QVariantList", notify=boxChanged)
    def boxItems(self):
        import games
        out = []
        if self.editing is not None:   # the actual current card waits at the top
            p = self.parked or {}
            f = next((s for s in p.get("shots") or [] if s.kind == "front"), None)
            out.append({"cid": "", "parked": True, "title": tr("Current card (not in the box yet)"),
                        "sub": self._title(p) if p.get("name") else tr("go back to it"),
                        "url": quickimages.put(f"studio-park-{f.id}-{f.rev}", _qimage(studiocap.rounded(f.card), 160))
                        if f is not None else "", "editing": False})
        for cid in self._box_ids():
            try:
                d = json.loads((BOX / cid / "card.json").read_text("utf-8"))
            except (OSError, ValueError):
                continue
            purpose = dict(PURPOSES).get(d.get("purpose"), "")
            sub = " · ".join(x for x in (games.NICK.get(d.get("game"), d.get("game") or ""), (d.get("lang") or "").upper(),
                                         tr(purpose)) if x)
            thumb = BOX / cid / "thumb.png"
            out.append({"cid": cid, "parked": False, "title": self._title(d), "sub": sub,
                        "url": _file_url(thumb) if thumb.exists() else "", "editing": cid == self.editing})
        return out

    @QtCore.Property("QVariantList", notify=boxChanged)
    def sentItems(self):
        """Sent items, grouped by submission: header row (date, count), then per card title + status + note."""
        groups = {}
        for pid, meta, st in self._local():
            groups.setdefault(meta.get("bundle") or pid, []).append((pid, meta, st))
        out = []
        for bundle, rows in sorted(groups.items(), key=lambda kv: -(kv[1][0][1].get("t") or 0)):
            t = rows[0][1].get("t") or 0
            out.append({"head": True, "title": time.strftime("%d.%m.%Y %H:%M", time.localtime(t)),
                        "sub": tr("Cards") + f": {len(rows)}", "url": "", "pid": ""})
            for pid, meta, st in rows:
                thumb = DIR / pid / "thumb.png"
                status = st.get("status") or "wartet"
                out.append({"head": False, "title": meta.get("title") or pid, "pid": pid,
                            "sub": tr(STATUS.get(status, status)), "note": st.get("note") or "",
                            "error": status == "fehler", "url": _file_url(thumb) if thumb.exists() else ""})
        return out

    @QtCore.Property(bool, notify=boxChanged)
    def boxOpen(self):
        return self._box_open

    @QtCore.Property(str, notify=boxChanged)
    def boxTab(self):
        return self._box_tab

    @QtCore.Slot(bool)
    def pageVisible(self, shown):
        """Leaving/returning to the scan page: the studio stays open (with card and box) but does not look at the image
        while you are elsewhere – back = carry on right away. Only "Live scan" (or Esc) closes it."""
        if not self._on:
            return
        if shown:
            self._tick.start()
        else:
            self._tick.stop()
            self.quad, self.q = None, {}
            if self._box_open:
                self._box_open = False
                self.boxChanged.emit()

    @QtCore.Slot()
    def toggleBox(self):
        self._toggle_panel("box")

    @QtCore.Slot()
    def toggleSent(self):
        self._toggle_panel("sent")

    def _toggle_panel(self, tab):
        """Box and Sent (plane) share one panel: the same button closes, the other one switches."""
        if self._box_open and self._box_tab == tab:
            self._box_open = False
        else:
            self._box_open, self._box_tab = True, tab
            self.boxf.refresh()
            self.refresh_mine()
        self.boxChanged.emit()

    @QtCore.Property(int, notify=boxChanged)
    def sentCount(self):
        return len(self._local())

    @QtCore.Slot(str)
    def openItem(self, cid):
        """Edit a box card on the right – the current one stays parked (cid "" = back to it)."""
        if not cid:
            self.backToCurrent()
            return
        if cid == self.editing:
            return
        if self.editing is None and self.viewing is None:
            self.parked = self.card
        self.viewing = None
        try:
            self.card = self._load_card(cid)
        except (OSError, ValueError):
            log.exception("Studio: card from the box")
            return
        self.editing = cid
        self.kind = "back" if self._front() else "front"
        self.right.refresh()
        self._card_changed()
        self.boxChanged.emit()

    @QtCore.Slot(str)
    def openSent(self, pid):
        """View a sent card on the right (greyed out) – the current one stays parked."""
        if not pid or pid == self.viewing:
            return
        try:
            c = self._load_sent(pid)
        except (OSError, ValueError):
            log.exception("Studio: sent card")
            return
        if self.editing is None and self.viewing is None:
            self.parked = self.card
        self.editing = None
        self.viewing = pid
        self.card = c
        self.right.refresh()
        self._card_changed()
        self.boxChanged.emit()

    def _load_sent(self, pid):
        folder = DIR / pid
        m = json.loads((folder / "meta.json").read_text("utf-8"))
        c = self._blank()
        c.update({k: v for k, v in (m.get("card") or {}).items() if k in FIELDS}, cid="sent" + pid,
                 purpose=m.get("purpose") or "missing", artist=m.get("artist") or "", link=m.get("link") or "",
                 own_art=bool(m.get("own_art")))
        for f in m.get("files") or []:
            if f.get("kind") == "original":
                continue
            img = _read_png(folder / f["name"])
            if img is not None:
                c["shots"].append(Shot(f.get("kind") or "front", img, None, f.get("source") or "camera"))
        return c

    def _sent_state(self, pid):
        try:
            return json.loads((DIR / pid / "state.json").read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    @QtCore.Slot()
    def backToCurrent(self):
        if self.editing is None and self.viewing is None:
            return
        self.viewing = None
        self.editing = None
        self.card = self.parked or self._blank()
        self.parked = None
        self.kind = "back" if self._front() else "front"
        self.right.refresh()
        self._card_changed()
        self.boxChanged.emit()

    @QtCore.Slot(str)
    def removeItem(self, cid):
        if cid == self.editing:
            self.backToCurrent()
        shutil.rmtree(BOX / cid, ignore_errors=True)
        self.boxf.soon()
        self.boxChanged.emit()

    @QtCore.Slot()
    def uploadBox(self):
        """Everything in the box as one submission: one contribution per card (own status), shared details."""
        if not self._box_ids() or not self.ctrl.settings.get("studio_consent"):
            return
        import version
        s = self.ctrl.settings
        bundle = _now_id()
        credit = (s.get("studio_credit") or "").strip() if s.get("studio_named") else ""
        message = (s.get("studio_message") or "").strip()[:2000]
        for i, cid in enumerate(self._box_ids()):
            if cid == self.editing:
                continue
            src = BOX / cid
            try:
                d = json.loads((src / "card.json").read_text("utf-8"))
            except (OSError, ValueError):
                continue
            pid = f"{bundle}{i:03d}"[-32:]
            dst = DIR / pid
            dst.mkdir(parents=True, exist_ok=True)
            files = []
            for f in d.get("files") or []:
                shutil.copy2(src / f["name"], dst / f["name"])
                files.append({"name": f["name"], "kind": f["kind"], "source": f.get("source")})
                if f.get("original") and (src / f["original"]).exists():
                    shutil.copy2(src / f["original"], dst / f["original"])
                    files.append({"name": f["original"], "kind": "original", "of": f["name"]})
            shutil.copy2(src / "thumb.png", dst / "thumb.png")
            card = {k: d.get(k, "") for k in ("game", "name", "set", "number", "lang", "rarity")}
            meta = {"v": 2, "app": version.VERSION, "t": int(time.time()), "bundle": bundle, "game": d.get("game"),
                    "purpose": d.get("purpose"), "card": card, "artist": (d.get("artist") or "").strip(),
                    "link": (d.get("link") or "").strip(), "credit": credit, "message": message,
                    "own_art": bool(d.get("own_art")) and d.get("purpose") == "altart",
                    "share_fan": bool(s.get("studio_share_fan")), "bulk_folder": bool(d.get("bulk_folder")),
                    "files": files, "title": self._title(d), "of": len(self._box_ids())}
            (dst / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
            (dst / "state.json").write_text(json.dumps({"status": "wartet"}), "utf-8")
            shutil.rmtree(src, ignore_errors=True)
        s["studio_message"] = ""
        s["studio_consent"] = s["studio_share_fan"] = False   # next submission: consent consciously again
        self.ctrl.settings_changed()
        self.boxf._drafts.pop("smsg", None)
        self._box_tab = "sent"
        self._box_open = True
        self.box_msg = ""
        self.boxf.refresh()
        self.boxChanged.emit()
        self.sentAway.emit()
        self.upload_all()

    # ---------- Upload ----------
    def alt_arts_for(self, game, name):
        """My alt-art contributions for a card (detail view, section „Alt arts“): [{title, artist, status, thumb, t}]."""
        out = []
        for pid, meta, st in self._local():
            card = meta.get("card") or {}
            if (meta.get("purpose") or card.get("purpose")) != "altart" or (card.get("name") or "") != name:
                continue
            if game and card.get("game") and card.get("game") != game:
                continue
            thumb = DIR / pid / "thumb.png"
            status = st.get("status") or "wartet"
            out.append({"title": meta.get("title") or name, "artist": meta.get("artist") or card.get("artist") or "",
                        "status": tr(STATUS.get(status, status)), "thumb": _file_url(thumb) if thumb.exists() else "",
                        "t": meta.get("t") or 0})
        return out

    def _local(self):
        """Sent cards on this PC: [(pid, meta, state)] newest first."""
        out = []
        if DIR.exists():
            for d in sorted(DIR.iterdir(), reverse=True):
                if d.name == BOX.name:
                    continue
                try:
                    meta = json.loads((d / "meta.json").read_text("utf-8"))
                    st = json.loads((d / "state.json").read_text("utf-8"))
                except (OSError, ValueError):
                    continue
                out.append((d.name, meta, st))
        return out

    @QtCore.Slot()
    def upload_all(self):
        if self.uploading:
            return
        todo = [(pid, meta) for pid, meta, st in self._local() if st.get("status") in ("wartet", "fehler", "laedt")]
        if not todo:
            return
        self.uploading = True
        self.limit_hit = False
        settings = self.ctrl.settings

        def work():
            from net import relay
            for pid, meta in reversed(todo):   # oldest first
                folder = DIR / pid
                try:
                    self._state(pid, "laedt")
                    QtCore.QMetaObject.invokeMethod(self, "_box_signal", QtCore.Qt.QueuedConnection)
                    relay.register(settings)
                    code = relay.my_code(settings)
                    for f in meta["files"]:
                        raw = (folder / f["name"]).read_bytes()
                        n = max(1, -(-len(raw) // PART))
                        for i in range(n):
                            data = base64.b64encode(raw[i * PART:(i + 1) * PART]).decode()
                            t = int(time.time())
                            digest = hashlib.sha256(data.encode()).hexdigest()
                            relay._post(settings, "/v1/studio/part", {
                                "code": code, "pid": pid, "name": f["name"], "i": i, "n": n, "data": data, "t": t,
                                "sig": relay._signed(settings,
                                                     f"studio_part|{code}|{pid}|{f['name']}|{i}|{n}|{digest}|{t}")})
                    raw_meta = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
                    t = int(time.time())
                    res = relay._post(settings, "/v1/studio/done", {
                        "code": code, "pid": pid, "meta": raw_meta, "t": t,
                        "sig": relay._signed(settings, f"studio_done|{code}|{pid}|"
                                                       f"{hashlib.sha256(raw_meta.encode('utf-8')).hexdigest()}|{t}")})
                    self._state(pid, res.get("status") or "neu", uploaded=int(time.time()))
                except Exception as e:  # noqa: BLE001 – try again later (next time it opens)
                    log.info("Studio: upload %s: %s", pid, e)
                    if "limit" in str(e).lower():   # daily limit: not an error – simply waits until tomorrow
                        self.limit_hit = True
                        self._state(pid, "wartet", error="")
                    else:
                        self._state(pid, "fehler", error=str(e)[:200])
                    break
            self.uploading = False
            QtCore.QMetaObject.invokeMethod(self, "_after_upload", QtCore.Qt.QueuedConnection)
        threading.Thread(target=work, daemon=True).start()

    @QtCore.Slot()
    def _box_signal(self):
        self.boxChanged.emit()

    @QtCore.Slot()
    def _after_upload(self):
        self.ctrl.settings_changed()   # key/registration with the server remembered
        self.boxf.soon()
        self.boxChanged.emit()
        self.refresh_mine()

    @staticmethod
    def _state(pid, status, **kw):
        p = DIR / pid / "state.json"
        try:
            st = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            st = {}
        st.update(kw, status=status)
        p.write_text(json.dumps(st), "utf-8")

    def refresh_mine(self):
        """Fetch the status of uploaded contributions from the server (in the background)."""
        settings = self.ctrl.settings
        if not (settings.get("relay") or {}).get("registered") and not any(
                st.get("uploaded") for _, _, st in self._local()):
            return   # never registered with the mailbox: there is nothing to ask

        def work():
            from net import relay
            try:
                code = relay.my_code(settings)
                t = int(time.time())
                res = relay._post(settings, "/v1/studio/mine",
                                  {"code": code, "t": t, "sig": relay._signed(settings, f"studio_mine|{code}|{t}")})
                if isinstance(res.get("limits"), dict):
                    self.limits = res["limits"]
                bulk = bool(res.get("bulk"))
                if bulk != self.bulk:
                    self.bulk = bulk
                    QtCore.QMetaObject.invokeMethod(self.left, "refresh", QtCore.Qt.QueuedConnection)
                for it in res.get("items") or []:
                    if (DIR / str(it.get("pid")) / "state.json").exists():
                        self._state(it["pid"], it.get("status") or "neu", note=it.get("note") or "",
                                    uploaded=it.get("t"))
                self.mine_msg = ""
            except Exception as e:  # noqa: BLE001
                self.mine_msg = tr("Status not available right now.")
                log.info("Studio: Status: %s", e)
            QtCore.QMetaObject.invokeMethod(self, "_box_signal", QtCore.Qt.QueuedConnection)
        threading.Thread(target=work, daemon=True).start()

    @QtCore.Slot(str)
    def forget(self, pid):
        """Delete a sent card from this PC (only what did not arrive – uploaded items stay with the team)."""
        shutil.rmtree(DIR / pid, ignore_errors=True)
        self.boxChanged.emit()

    # ---------- Forms ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def leftForm(self):
        return self.left

    @QtCore.Property(QtCore.QObject, constant=True)
    def rightForm(self):
        return self.right

    @QtCore.Property(QtCore.QObject, constant=True)
    def boxForm(self):
        return self.boxf

    def _lamp(self, ui, on, text):
        """Indicator lights: on = bright, off = dimmed (no checkmarks)."""
        return ui.label(("● " if on else "○ ") + text, color="" if on else "gray")

    def _build_left(self, ui):
        q = self.q or {}
        found = bool(q.get("found"))
        px = q.get("px") or 0
        lamps = [self._lamp(ui, found, tr("Card found")),
                 self._lamp(ui, found and q.get("sharp", 0) >= 0.8, tr("sharp")),
                 self._lamp(ui, found and q.get("glare", 0) >= 0.6, tr("no glare")),
                 self._lamp(ui, found and q.get("light", 0) >= 0.6, tr("light is good")),
                 self._lamp(ui, found and q.get("size", 0) >= 0.55,
                            tr("big enough") + (f"  ·  {px} px" if px else ""))]

        def set_auto(on):
            self.auto = bool(on)
            self.ctrl.settings["studio_auto"] = self.auto
            self.ctrl.settings_changed()
        ctrl = self.ctrl
        cam, cams = ctrl.camera, ctrl.cam_combo
        size = f"{cam.size[0]}×{cam.size[1]}" if cam.size and ctrl.frame_rgb is not None else "–"
        mail = f'<a href="mailto:{contacts.MAIL}" style="color:#e0e0e0">{contacts.MAIL}</a>'
        many = [ui.label(tr("Are you an artist or do you have lots of cards (e.g. finished scans)? Write to {mail} who you are and what you have – artists please from their known address or profile. No real name needed. You'll get a personal upload link: then you upload whole folders right on the website, no app needed.").format(mail=mail), color="gray", rich=True)]
        return ui.col([
            ui.label(tr("Studio"), px=22, bold=True),
            # Highlighted: finished scans/photos are often much better than the webcam
            ui.label(tr("Tip: scanner images or sharp phone photos are usually much better than the webcam – just upload them on the right via “Load file …”, they get cropped the same way."),
                     color="#ffb36b", bold=True),
            ui.group(tr("Camera"), [
                ui.combo(list(enumerate(cams.items())) or [(0, tr("no camera"))],
                         cams.currentIndex(), self._pick_camera, enabled=cams.count() > 0, tip=tr("Camera")),
                ui.seg([(k, tr(t)) for k, t in RESOLUTIONS], self.res, lambda k: (self._set_res(k), self.left.refresh()),
                       tip=tr("Highest: the camera delivers what it can (up to 4K) – back to the scanning setting when you leave the studio")),
                ui.row([ui.label(tr("Delivers") + f": {size}", color="gray"), ui.stretch(),
                        ui.button("↻", lambda: (ctrl.fill_cameras(), ctrl.camera_selected()),
                                  tip=tr("Search for cameras again and reconnect"))], spacing=6),
                ui.button(tr("Focus & exposure …"), cam.open_dialog,
                          tip=tr("Camera driver settings: turn autofocus off and focus by hand, set exposure so nothing burns out")),
                ui.button(tr("More …"), lambda: ctrl.go_settings("scan"),
                          tip=tr("All camera settings: Settings → Scanning")),
            ], flat=True),
            ui.group(tr("Capture"), lamps + [
                ui.seg([(k, tr(SHOT_NAMES[k])) for k, _t in KINDS], self.kind,
                       lambda k: (setattr(self, "kind", k), self.left.refresh()), tip=tr("What the next capture is")),
                ui.check(tr("Capture automatically when everything is right"), self.auto, set_auto),
                ui.slot_note(self.msg),
            ], flat=True),
            ui.group(tr("How to get it right"), [ui.label("· " + tr(t), color="gray") for t in TIPS], flat=True),
            ui.group(tr("Lots of cards?"), many, flat=True),
        ], spacing=12)

    def _build_right(self, ui):
        c = self.card
        ro = self.viewing is not None   # already sent: view only (greyed out)

        def setf(k, refresh=False):
            def fn(v):
                c[k] = str(v).strip()
                (self.right.refresh if refresh else self.right.soon)()
            return fn
        rows = []
        if ro:
            st = self._sent_state(self.viewing)
            status = st.get("status") or "wartet"
            rows.append(ui.label(tr("Already sent – view only") + f"  ·  {tr(STATUS.get(status, status))}",
                                 bold=True))
            if st.get("note"):
                rows.append(ui.label("„" + st["note"] + "“", color="gray"))
        # Shots: the front is shown large above (QML), here rotate/remove + the others
        thumbs = []
        for sh in c["shots"]:
            url = quickimages.put(f"studio-{sh.id}-{sh.rev}", _qimage(studiocap.rounded(sh.card), 200))
            thumbs.append(ui.col([
                ui.image(url, 64, int(64 * sh.card.shape[0] / sh.card.shape[1]),
                         tip=f"{tr(SHOT_NAMES.get(sh.kind, sh.kind))} · {sh.card.shape[1]}×{sh.card.shape[0]} px"),
                None if ro else ui.row([
                    ui.button("↻", lambda sh=sh: (sh.rotate(), self._card_changed(), self.right.refresh()),
                              tip=tr("Rotate 180°")),
                    ui.button("✕", lambda sh=sh: (c["shots"].remove(sh), self._card_changed(), self.right.refresh()),
                              tip=tr("Remove capture"))], spacing=4)], spacing=4))
        rows.append(ui.row(thumbs + [ui.stretch(), None if ro else ui.button(
            tr("Load file …"), self.load_file, tip=tr("Scanner image or phone photo – cropped the same way"))],
            spacing=8))
        if not ro:
            rows.append(ui.check(tr("Send the original photo too"), bool(c.get("keep_original")),
                                 lambda on: c.__setitem__("keep_original", bool(on)),
                                 tip=tr("The uncropped camera image as well (helps checking, without metadata)")))
        from collection.collection import ALL_LANGS
        rows.append(ui.group(tr("Card"), [ui.form([
            (tr("Game"), ui.combo([(k, n) for k, n in _games()], c["game"], setf("game"), enabled=not ro)),
            (tr("Name"), ui.edit(c["name"], setf("name", True), key=f"sname{c['cid']}", enabled=not ro,
                                 live=lambda v: (c.__setitem__("name", v.strip()), self.right.soon()),
                                 placeholder=tr("as printed on the card"))),
            (tr("Set"), ui.row([ui.edit(c["set"], setf("set"), key=f"sset{c['cid']}", enabled=not ro,
                                        placeholder=tr("Code, e.g. SV8a")),
                                ui.edit(c["number"], setf("number"), key=f"snum{c['cid']}", enabled=not ro,
                                        placeholder="#")],
                               spacing=6)),
            (tr("Language"), ui.combo([(code, f"{short} · {name}") for code, short, name in ALL_LANGS], c["lang"],
                                     setf("lang"), enabled=not ro)),
            (tr("Rarity"), ui.edit(c["rarity"], setf("rarity"), key=f"srar{c['cid']}", enabled=not ro,
                                       placeholder=tr("e.g. Special Art Rare, Holo"))),
        ])], flat=True))
        # Purpose: stacked, with indicator lights like the nav buttons (on = lit)
        purpose = [ui.col([ui.button(tr(t), lambda k=k: (c.__setitem__("purpose", k), self.right.refresh()),
                                     checkable=True, checked=c["purpose"] == k, enabled=not ro)
                           for k, t in PURPOSES], spacing=10)]
        if c["purpose"] == "altart":
            own = bool(c.get("own_art"))
            mail = f'<a href="mailto:{contacts.MAIL}" style="color:#d0d0d0">{contacts.MAIL}</a>'
            purpose += [ui.check(tr("This is my own work – I am the artist"), own,
                                 lambda on: (c.__setitem__("own_art", bool(on)), self.right.refresh()),
                                 enabled=not ro),
                        ui.form([
                (tr("Artist"), ui.edit(c["artist"], setf("artist", True), key=f"sart{c['cid']}", enabled=not ro,
                                         live=lambda v: (c.__setitem__("artist", v.strip()), self.right.soon()),
                                         placeholder=tr("your artist name") if own else tr("Required – no proxies"))),
                (tr("Link"), ui.edit(c["link"], setf("link"), key=f"slink{c['cid']}", enabled=not ro,
                                     placeholder=tr("your profile (Instagram, shop …)") if own
                                     else tr("The artist's shop, Instagram …"))),
            ]), ui.label(tr("How to confirm it: send us a short mail to {mail} – ideally from the address or profile people know you by, with the card's name. Uploaded several cards? One mail covers them all. Then we'll approve them.").format(mail=mail),
                         color="gray", rich=True) if own else
                ui.note(tr("We ask the artist – the card only becomes scannable once they say yes."))]
        rows.append(ui.group(tr("What for"), purpose, flat=True))
        if ro:
            rows.append(ui.row([ui.button(tr("Back to the current card"), self.backToCurrent, primary=True),
                                ui.stretch()], spacing=8))
            return ui.col(rows, spacing=12)
        why = self.ready()
        if self.editing is not None:
            rows.append(ui.row([ui.button(tr("Apply changes"), self.put_in_box, primary=True,
                                          enabled=not why),
                                ui.button(tr("Back to the current card"), self.backToCurrent), ui.stretch()],
                               spacing=8))
        else:
            rows.append(ui.row([ui.button(tr("Into the box"), self.put_in_box, primary=True, enabled=not why),
                                ui.stretch()], spacing=8))
        rows.append(ui.slot_note(why or self.msg))   # always there: otherwise a keystroke rebuilds the form
        return ui.col(rows, spacing=12)

    def _build_box(self, ui):
        """At the bottom of the expanded box (below a divider): details for the whole submission + upload."""
        s = self.ctrl.settings
        if self._box_tab == "sent":
            failed = any(st.get("status") == "fehler" for _, _, st in self._local())
            return ui.col([ui.slot_note(self.mine_msg),
                           ui.row([ui.button(tr("Upload again"), self.upload_all), ui.stretch()])
                           if failed else None], spacing=8)

        def credit(v):
            s["studio_credit"] = str(v).strip()[:40]
            if s["studio_credit"]:   # name entered = wants to be credited
                s["studio_named"] = True
            self.ctrl.settings_changed()
            self.boxf.soon()

        def named(on):
            s["studio_named"] = bool(on)
            self.ctrl.settings_changed()

        def flag(key):
            def fn(on):
                s[key] = bool(on)
                self.ctrl.settings_changed()
                self.boxf.soon()
            return fn

        def message(v):
            s["studio_message"] = str(v)
        n = len([c for c in self._box_ids() if c != self.editing])
        return ui.col([
            ui.row([ui.check(tr("Credit me as:"), bool(s.get("studio_named")), named),
                    ui.edit(s.get("studio_credit") or "", credit, key="scred", live=credit,
                            placeholder=tr("Name or nickname"))], spacing=8),
            ui.textarea(s.get("studio_message") or "", message, key="smsg", h=64, live=message,
                        placeholder=tr("Message to Bent°Corner (optional)")),
            ui.check(tr("Bent°Corner may add these images to its card database – I'm allowed to share them."),
                     bool(s.get("studio_consent")), flag("studio_consent")),
            ui.label(tr("<span style='color:#ffb36b'><b>Required</b></span> – no upload without it. What happens to the images: {link}").format(
                link=f'<a href="{contacts.SITE}/datenschutz.html#studio" style="color:#e0e0e0">'
                     + tr("Privacy") + "</a>"), color="gray", rich=True),
            ui.check(tr("Bent°Corner may also pass them on to other fan projects like TCGdex (optional)."),
                     bool(s.get("studio_share_fan")), flag("studio_share_fan")),
            ui.slot_note(self._limit_text(n)),
            ui.row([ui.stretch(), ui.button(tr("Upload all") + f" ({n})", self.uploadBox, primary=True,
                                            enabled=bool(n) and bool(s.get("studio_consent")))]),
        ], spacing=8)

    def _limit_text(self, n):
        """Daily limit: what is still possible today – and what to do if it is not enough."""
        mail = contacts.MAIL
        if self.limit_hit:
            return tr("Daily limit reached – the remaining cards go out by themselves tomorrow. More cards? Write to {mail} – you'll get an upload link for the website.").format(mail=mail)
        lim = self.limits or {}
        if self.bulk:
            return ""
        if "cards_left" in lim:
            text = tr("Left today: {c} cards in {s} sends.").format(c=lim.get("cards_left"),
                                                                        s=lim.get("sends_left"))
            if n > (lim.get("cards_left") or 0):
                text += " " + tr("The rest goes out tomorrow – or write to {mail} for an upload link.").format(mail=mail)
            return text
        return tr("Without unlocking: up to 30 cards in 3 sends per day.")

    # ---------- Drawing over the camera image ----------
    def paint(self, p, c, frame_size):
        """Draw the detected card outline over the camera image (bright when everything fits)."""
        if self.quad is None or not frame_size[0]:
            return
        from PySide6.QtCore import QPointF
        k = c.width() / frame_size[0]
        pts = [QPointF(c.left() + float(x) * k, c.top() + float(y) * k) for x, y in self.quad]
        ok = bool(self.q.get("ok"))
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 235 if ok else 140), 4 if ok else 2)
        if not ok:
            pen.setStyle(QtCore.Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPolygon(QtGui.QPolygonF(pts))
        p.restore()
