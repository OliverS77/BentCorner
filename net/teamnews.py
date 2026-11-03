"""Messages from the Bent°Corner team (read only, no replies) – two routes, one inbox:

- News for everyone: stored in the mailbox (GET /v1/news), signed with the team key – the app verifies that
  itself (fetch_news), the server cannot slip anything in. Fetched during the update check, even with the
  exchange switched off. Older news could also sit in the update directory (manifest.json → "news").
  [{"id", "t", "until", "title", "text", "game"?}]
- Message to one ID: parcel of kind "team" via the mailbox (relay.py) – only genuine if it is signed with the
  team key (TEAM_PK). Sender: "Oliver · Bent°Corner Designer" with a badge.

Inbox: settings["inbox"] = [{"id", "t", "title", "text", "via": "news"|"direct", "read": bool}], at most 50.
Switch off: settings["team_messages"] = False (Settings → Legal & Data).
"""
import math
import time

TEAM_PK = "DB56kjhPvXem2hqE/DAEjNgw4/KUVIWjhIdzBer4lBo="   # public half of the team key
SENDER = "Oliver · Bent°Corner Designer"
MAX_INBOX = 50


def enabled(settings):
    return settings.get("team_messages", True) is not False


def inbox(settings):
    return settings.setdefault("inbox", [])


def unread(settings):
    return sum(1 for m in inbox(settings) if not m.get("read"))


def _clean(m, via):
    try:
        return {"id": str(m["id"])[:40], "t": int(m.get("t") or time.time()), "until": int(m.get("until") or 0),
                "title": str(m.get("title") or "")[:120], "text": str(m.get("text") or "")[:4000],
                "game": str(m.get("game") or "")[:20], "via": via, "read": False}
    except (KeyError, TypeError, ValueError):
        return None


def add(settings, m, via):
    """Take in a message (duplicate IDs only once). -> True if new."""
    if not enabled(settings):
        return False
    m = _clean(m, via)
    if m is None or not m["title"] and not m["text"]:
        return False
    box = inbox(settings)
    if any(x.get("id") == m["id"] for x in box):
        return False
    box.insert(0, m)
    del box[MAX_INBOX:]
    return True


def take_news(settings, news, game=None):
    """Take over news from the update directory (not expired ones or those for other games). -> number of new"""
    now, n = time.time(), 0
    for m in news or []:
        if not isinstance(m, dict) or (m.get("until") and float(m["until"]) < now):
            continue
        if m.get("game") and game and m["game"] != game:
            continue
        n += add(settings, m, "news")
    return n


def fetch_news(box_url):
    """Fetch news from the mailbox – only what the team key has signed. -> list (otherwise [])"""
    import base64
    import json
    from net import netpolite
    from nacl.signing import VerifyKey
    try:
        r = netpolite.get(box_url.rstrip("/") + "/v1/news", timeout=15)
        d = r.json() if r.status_code == 200 else {}
        raw = str(d.get("raw") or "")
        if not raw:
            return []
        VerifyKey(base64.b64decode(TEAM_PK)).verify(("news|" + raw).encode("utf-8"), base64.b64decode(d.get("sig") or ""))
        news = json.loads(raw).get("news")
    except Exception:  # noqa: BLE001 – unreachable or not genuine: simply no news
        return []
    return [m for m in news if isinstance(m, dict)][:20] if isinstance(news, list) else []


def mark_read(settings):
    changed = False
    for m in inbox(settings):
        if not m.get("read"):
            m["read"], changed = True, True
    return changed


def remove(settings, mid):
    settings["inbox"] = [m for m in inbox(settings) if m.get("id") != mid]


def is_team(sign_pk_b64):
    return bool(sign_pk_b64) and sign_pk_b64 == TEAM_PK


def badge_url(size=40):
    """Team badge: golden mini card with a purple hexagon (drawn once, kept in the cache)."""
    from scanner import common
    from PySide6 import QtCore, QtGui
    p = common.DATA / "cache" / f"team_badge_{size}.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        s = 2
        img = QtGui.QImage(size * s, size * s, QtGui.QImage.Format_ARGB32_Premultiplied)
        img.fill(QtCore.Qt.transparent)
        g = QtGui.QPainter(img)
        g.setRenderHint(QtGui.QPainter.Antialiasing)
        g.scale(size * s / 100, size * s / 100)
        g.translate(50, 50)
        g.rotate(-7)
        g.translate(-50, -50)
        grad = QtGui.QLinearGradient(25, 10, 75, 90)
        for pos, c in ((0, "#f7e3a1"), (0.45, "#d4a843"), (0.7, "#f3d27a"), (1, "#a8792a")):
            grad.setColorAt(pos, QtGui.QColor(c))
        g.setPen(QtCore.Qt.NoPen)
        g.setBrush(grad)
        g.drawRoundedRect(QtCore.QRectF(25, 12, 50, 70), 6, 6)
        hexa = QtGui.QPolygonF([QtCore.QPointF(50 + 14 * math.cos(a), 47 + 14 * math.sin(a))
                                for a in [math.pi / 6 + k * math.pi / 3 for k in range(6)]])
        g.setBrush(QtGui.QColor("#7b4dd8"))
        g.drawPolygon(hexa)
        g.end()
        img.save(str(p), "PNG")
    return QtCore.QUrl.fromLocalFile(str(p)).toString()
