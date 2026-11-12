"""The online backup's expiry warning (legal 07.11.2026; performance' sync_status["expiry"] = {"seen", "until"} in ms –
150 days after THIS device's last vault access, locally, also while the sync pauses outside Full Orbit). Only this
device's access is known – hence legal's "if none of your other devices …".
  - on „Your devices“: in its own frame at the top, with a dot on the side list, while it applies
  - at program start: the same line as a notice at the top (no pop-up, closable) – twice: from day 150 and from day 176
    (a week before); once more when the date has passed. Closed stages are remembered per expiry (settings
    "expiry_notice": {until: stage}).
The key: outside Full Orbit [Switch to Full Orbit] (→ the Orbit slider); in it none (lead 07.11., PC = web: the app syncs
right at opening, the warning then goes by itself)."""
import time

from system.i18n import tr

DAY_MS = 86400 * 1000
SOON_DAYS = 176   # legal: the second notice a week before the 183 days
BEFORE = ("This device hasn't used your online backup since {seen}. If none of your other devices uses it either, it "
          "will be deleted on {until}.")
AFTER = ("This device hasn't used your online backup since {seen}. If none of your other devices used it either, it "
         "was deleted on {until} – your data on this device stays.")
TO_ORBIT = "Switch to Full Orbit"
SYNC_NOW = "Sync now"


def _day(ms):
    return time.strftime("%d.%m.%Y", time.localtime(int(ms) / 1000))


def info(ctrl, now_ms=None):
    """-> None or {"text", "stage" (1 from day 150, 2 from day 176, 3 past), "until", "key"} for this device."""
    exp = (getattr(ctrl, "sync_status", None) or {}).get("expiry")
    if not exp or not exp.get("seen") or not exp.get("until"):
        return None
    now = int(time.time() * 1000) if now_ms is None else now_ms
    seen, until = int(exp["seen"]), int(exp["until"])
    past = now >= until
    stage = 3 if past else 2 if now - seen >= SOON_DAYS * DAY_MS else 1
    text = tr(AFTER if past else BEFORE).format(seen=_day(seen), until=_day(until))
    full = bool(getattr(ctrl, "sync_orbit_ok", lambda: True)())
    return {"text": text, "stage": stage, "until": until, "key": "" if full else TO_ORBIT}


def act(ctrl):
    """The key: in Full Orbit a sync now (it touches the vault – the warning goes), else the Orbit slider."""
    if getattr(ctrl, "sync_orbit_ok", lambda: True)():
        if hasattr(ctrl, "sync_now"):
            ctrl.sync_now(manual=True)
    else:
        ctrl.stream.show_page("settings", back=True)
        ctrl.show_settings("privacy")


def notice_due(ctrl, now_ms=None):
    """The start notice: this stage not closed yet for this expiry. -> info or None"""
    i = info(ctrl, now_ms)
    if not i:
        return None
    closed = (getattr(ctrl, "settings", None) or {}).get("expiry_notice") or {}
    return i if i["stage"] > int(closed.get(str(i["until"]), 0)) else None


def notice_closed(ctrl, now_ms=None):
    i = info(ctrl, now_ms)
    if not i:
        return
    ctrl.settings["expiry_notice"] = {str(i["until"]): i["stage"]}   # only the current expiry is kept
    if hasattr(ctrl, "settings_changed"):
        ctrl.settings_changed()


def items(ui, ctrl):
    """„Your devices“: the line in its own frame (stays after the start notice was closed)."""
    i = info(ctrl)
    if not i:
        return []
    key = [ui.row([ui.button(tr(i["key"]), lambda: act(ctrl)), ui.stretch()])] if i["key"] else []
    return [ui.group(tr("Online backup"), [ui.label(i["text"], bold=True)] + key)]
