"""Around scanning (no widgets): asking about unclear printing and language, camera controls, card image storage."""
import os
import re
import threading
import time

import cv2
from PySide6 import QtCore, QtGui

from scanner import camctl
from scanner import hybrid
from cards import carddb
from cards import imgcache
from ui import qdialogs
from ui import qstate
from system.i18n import tr



def _mb(b):
    return f"{b / 1024 / 1024:,.0f} MB".replace(",", ".") if b >= 1024 * 1024 else f"{b / 1024:,.0f} KB"


# ---------- question: which printing? (asked in the card search – panels.CardPanel.open_question) ----------
def _bgr_url(img, key):
    """Camera image (BGR) as an image for Qt Quick."""
    from ui import quickimages
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    q = QtGui.QImage(rgb.data, w, h, rgb.strides[0], QtGui.QImage.Format_RGB888).copy()
    return quickimages.put(key, q), w, h


def _stamp(row):
    """A stamped promo: what the stamp is (the picture may not show it – Scryfall's often doesn't)."""
    kinds = str(row.get("promo_types") or "")
    return (tr("Prerelease (stamp)") if "prerelease" in kinds else tr("Promo pack (stamp)") if "promopack" in kinds
            else tr("Stamped promo") if "stamped" in kinds else "")


def print_question(pending):
    """Which printing? -> {"rows", "star", "name", "cam", "loupe", "note"} for the card search: the most likely print
    first (carddb.print_likeliness: the image match's pick, booster print …), its stamped twins right after it, then
    the candidates and every other print of the name by set; star = those matching the camera image (★)."""
    likely = lambda row: carddb.print_likeliness(row, pick=pending.get("pick"))   # noqa: E731
    matched = sorted((row for row, sc in pending["cands"] if sc > 0), key=likely)
    rest = sorted((row for row, sc in pending["cands"] if sc <= 0), key=likely)
    if not matched:
        matched, rest = rest, []
    cands = matched + rest
    name = (cands[0]["name"] if cands else (pending.get("r") or {}).get("name")) or ""
    others = []
    if name:
        try:
            with carddb.connection() as con:
                ids = {c.get("id") for c in cands}
                seen = {f"{c['set_code']}|{c['number']}" for c in cands}
                others = sorted((dict(r) for r in con.execute("SELECT * FROM cards WHERE name = ?", (name,))
                                 if r["id"] not in ids and f"{r['set_code']}|{r['number']}" not in seen), key=likely)
        except Exception:  # noqa: BLE001 – without a card database: only the candidates
            others = []
    # the ★ ones (matching the camera image) on top, the most likely first; then the rest by set
    rows = matched + sorted(rest + others, key=lambda r: (r["set_code"].lower(), carddb.number_key(r["number"])))
    if rows:   # the suggestion's stamped twins (prerelease 46s …) right beside it – that's the choice that matters
        from scanner import aiscan
        near = [r for r in rows[1:] if aiscan._stamp_twins(r, rows[0])]
        rows = rows[:1] + near + [r for r in rows[1:] if r not in near]
    star = {f"{r['id']}_0" for r in matched}
    cam = _bgr_url(pending["img"], f"pa_cam_{id(pending)}")[0] if pending.get("img") is not None else ""
    loupe = _bgr_url(pending["loupe"], f"pa_loupe_{id(pending)}")[0] if pending.get("loupe") is not None else ""
    twins = any(_stamp(r) for r in rows) and any(not _stamp(r) for r in rows)
    note = ""
    if twins:
        note = (tr("The stamp is on the front – turn the card over. A stamp (e.g. “20/25”)? → the promo. No stamp → the regular print.")
                if pending.get("stamp_front") else
                tr("A stamp (e.g. “20/25”) to see? → the promo. No stamp → the regular print."))
    return {"rows": rows, "star": star, "name": name, "cam": cam, "loupe": loupe, "note": note}


# ---------- camera controls ----------
LABELS = {k: lab for k, lab, _, _ in camctl.PROPS}
TIPS = {
    "focus": "Turn autofocus off and set the focus once to the distance to the card – otherwise the camera refocuses "
             "with every hand movement (often on the table).",
    "exposure": "Shorter exposure = less motion blur, but needs more light. On auto, the camera lengthens the exposure "
                "in the dark – then the frame rate drops and everything blurs.",
    "gain": "Gain brightens the image but adds noise. Only works with manual exposure.",
    "sharpness": "In-camera sharpening adds bright edges around letters – better keep it low.",
    "white": "White balance: low = warmer (yellow room), high = cooler.",
    "zoom": "Digital zoom only crops, it adds no real detail. Better move the camera closer to the card.",
    "backlight": "Backlight compensation brightens dark areas – usually off for the scanner.",
}


def fmt_control(key, value, is_auto):
    if is_auto:
        return tr("auto")
    if key == "exposure":  # 2^value seconds
        return f"1/{round(2 ** -value)} s" if value < 0 else f"{2 ** value:g} s"
    if key == "zoom":
        return f"{value / 100:.2f}×"
    if key == "white":
        return f"{value} K"
    if key == "backlight":
        return tr("on") if value else tr("off")
    return str(value)


def camera_controls(controls, name, save_cb):
    """Sliders for focus, exposure, sharpness … – take effect immediately, are saved per camera.
    -> open dialog (bar on the right, the preview image stays visible)."""
    keys = [k for k, *_ in camctl.PROPS if k in controls.ranges]

    def current(key):
        try:
            return controls.get(key)
        except Exception:  # noqa: BLE001
            return None

    def set_value(key, value, is_auto):
        try:
            controls.set(key, value, is_auto)
        except Exception:  # noqa: BLE001
            pass
        save_cb(controls.snapshot())

    def reset():
        controls.reset()
        save_cb({})

    def build(ui, d):
        rows = []
        for key in keys:
            rng, cur = controls.ranges[key], current(key)
            if cur is None:
                continue
            value, is_auto = cur
            parts = []
            if rng["auto"]:
                parts.append(ui.check(tr("auto"), is_auto, lambda on, k=key, v=value: set_value(k, v, on)))
            if not is_auto:
                parts.append(ui.slider(value, rng["min"], rng["max"], lambda v, k=key: set_value(k, v, False),
                                       tip=tr(TIPS.get(key, ""))))
            parts.append(ui.label(fmt_control(key, value, is_auto), wrap=False, fixed=True))
            rows.append((ui.label(tr(LABELS[key]), wrap=False, tip=tr(TIPS.get(key, ""))), ui.row(parts)))
        return ui.col([
            ui.note(name + " · " + tr("Changes apply immediately to the preview and are saved for this camera.")),
            ui.form(rows),
            ui.row([ui.button(tr("Default"), reset, tip=tr("All controls to the camera's factory defaults")),
                    ui.stretch(), ui.button(tr("Close"), lambda: d.close(None))]),
        ], spacing=12)
    return qdialogs.show(tr("Camera controls"), build, side=True, wait=False)


# ---------- card image storage ----------
class ImageStore(QtCore.QObject):
    """Overview of data/card-images (shown under Settings → Sets & card data): count groups (in the
    background), delete. ctrl = main window controller (collection, sets, Settings)."""
    GROUPS = [("library", "Bibliothek (Sammlung)", "Bilder der Karten in deiner Bibliothek, inkl. Sprachversionen."),
              ("sessions", "Log", "Karten aus gespeicherten Logs (Statistik, Verlauf)."),
              ("cache", "Zwischenspeicher", "Vom Scanner zum Vergleichen geladen oder beim Stöbern angesehen. Wird "
                                            "automatisch begrenzt – die ältesten fliegen zuerst raus."),
              ("sets", "Erkennungs-Sets", "Gehören zu heruntergeladenen Sets – löschen über die Set-Liste unten.")]

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl = ctrl
        self._groups, self._summary, self._busy, self.message = None, None, False, ""
        self._timer = QtCore.QTimer(self, interval=200, timeout=self._poll)

    def _classify(self):
        inst = [s["code"] for s in (self.ctrl.installed or [])]
        return imgcache.classify(self.ctrl.collection.items, inst)

    def refresh(self):
        if self._busy:
            return
        self._busy, self._summary = True, None
        qstate._changed()

        def work():
            try:
                self._groups = self._classify()
            finally:
                self._busy = False
        threading.Thread(target=work, daemon=True).start()
        self._timer.start()

    def _poll(self):
        if self._busy:
            return
        self._timer.stop()
        if self._groups is not None:
            self._summary = imgcache.summary(self._groups)
        qstate._changed()

    def rows(self):
        """-> [(key, title, help text, text)] for display."""
        out = []
        for key, title, text in self.GROUPS:
            if self._summary is None:
                info = tr("counting …") if self._busy else "–"
            else:
                n, b = self._summary[key]
                info = f"{n:,} {tr("images")} · {_mb(b)}".replace(",", ".")
            out.append((key, tr(title), tr(text), info))
        return out

    def total(self):
        if self.message:
            return self.message
        if self._summary is None:
            return ""
        n = sum(x[0] for x in self._summary.values())
        b = sum(x[1] for x in self._summary.values())
        return tr(f"Total: {n:,} images · {_mb(b)}").replace(",", ".")

    def set_limit(self, mb):
        self.ctrl.settings["image_cache_mb"] = int(mb)
        self.ctrl.settings_changed()
        self.ctrl.trim_image_cache()

    def delete_groups(self, keys):
        if self._groups is None:
            return
        titles = dict((k, tr(t)) for k, t, _ in self.GROUPS)
        names = ", ".join(titles[k] for k in keys)
        if not qdialogs.question(tr("Card images"), tr(f"Delete images: {names}?\nThey are loaded again when needed (internet required).")):
            return
        files = [f for k in keys for f in self._groups[k]]
        freed = imgcache.delete(files)
        self.message = tr(f"{_mb(freed)} freed")
        qstate._changed()

        def again():
            self.message = ""
            self.refresh()
        QtCore.QTimer.singleShot(1500, again)


def trim_cache(collection_items, installed_codes, limit_mb):
    """Limit the cache (call in the background). -> freed bytes."""
    t = time.time()
    groups = imgcache.classify(collection_items, installed_codes)
    freed = imgcache.enforce_limit(groups, limit_mb)
    return freed, time.time() - t
