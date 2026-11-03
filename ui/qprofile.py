"""Profile (tab at the top right): who you are (card back, name, ID) and your binders of all games – freely
arranged, at most 8 – plus a line saying whether the profile is offline or shared with friends.
Shown by qml/pages/ProfilePage.qml. Friends are in the menu on the profile button (qml/components/FriendsMenu.qml):
own name + ID, requests, friends list as in the trade tab, "+" = add a friend by ID.

Friends: one person for all games – the friendship (ID, name, key) is stored in the settings (relay.py),
what a friend shares lives per game in the friends folder (trade.FRIENDS of the game).
"""
import html
import json
import time

from PySide6 import QtCore

import games
from ui import qform
from collection import trade
from system import userprofile
from system.i18n import tr

log = __import__("logging").getLogger("booster")


def _esc(t):
    return html.escape(str(t or ""))


_FRIEND_FILES = {}       # game -> (folder, folder mtime, time read, [dict]) – see friend_files
FRIEND_FILES_TTL = 5.0  # s: friend files changed in place show up at the latest after this


def friend_files(key):
    """Friend files of a game (read without opening it). -> [dict]
    Remembered for FRIEND_FILES_TTL – the trade and profile pages ask for them several times per click. A new or
    removed friend file changes the folder's mtime: then they are read again at once."""
    folder = trade.friends_folder(key)
    try:
        mt = folder.stat().st_mtime_ns
    except OSError:
        return []
    hit = _FRIEND_FILES.get(key)
    now = time.monotonic()
    if hit and hit[0] == folder and hit[1] == mt and now - hit[2] < FRIEND_FILES_TTL:
        return [dict(d) for d in hit[3]]
    out = []
    for f in folder.glob("*.json"):
        try:
            out.append(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            continue
    _FRIEND_FILES[key] = (folder, mt, now, out)
    return [dict(d) for d in out]


def forget_friend_files():
    """Friend files written (relay, trade): read them again next time."""
    _FRIEND_FILES.clear()


def all_friends(settings):
    """All friends across all games: [{"key", "name", "back", "pid", "code", "status", "games": {game: dict}}].
    Merged by profile ID; sample friends are left out."""
    from net import relay
    people, masked = {}, set()
    for code, f in relay.friends(settings).items():
        k = f.get("pid") or code
        people[k] = {"key": k, "name": f.get("name") or "", "back": relay.shown_back(f), "pid": f.get("pid") or "",
                     "code": code, "status": f.get("status") or "", "games": {}}
        if f.get("hide_back") or f.get("status") == "blocked":   # never their own back from a file then
            masked.add(k)
    for key, _name, ready in games.GAMES:
        if not ready:
            continue
        for d in friend_files(key):
            if d.get("example"):
                continue
            k = d.get("id")
            p = people.setdefault(k, {"key": k, "name": d.get("name") or "", "back": d.get("back"), "pid": k,
                                      "code": "", "status": "", "games": {}})
            p["name"] = p["name"] or d.get("name") or ""
            if k not in masked:
                p["back"] = p["back"] or d.get("back")
            p["games"][key] = d
    return sorted(people.values(), key=lambda p: (p["status"] == "in", (p["name"] or "").lower()), reverse=False)


def shown_name(p):
    """Display name – never "Friend" without a name: for an accepted friend "Name coming soon" (it arrives with
    their lists), otherwise their ID."""
    from net import relay
    if p.get("name"):
        return p["name"]
    if p.get("code") and p.get("status") == "ok":
        return tr("Name coming …")
    return relay.pretty(p["code"]) if p.get("code") else tr("no name")


class ProfileBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.game_filter = "all"
        self._code = ""
        self._me_form = qform.Form(self._build_me, self)
        self._back_form = qform.Form(self._build_back, self)
        from ui import qbinder
        self._binder = qbinder.BinderBackend(ctrl, self)

    @QtCore.Property(QtCore.QObject, constant=True)
    def binderView(self):
        return self._binder

    @property
    def binder(self):
        return self._binder

    @QtCore.Slot(bool)
    def setActive(self, on):
        if on:
            self.refresh()

    @QtCore.Slot()
    def refresh(self):
        self._me_form.soon()
        self.changed.emit()

    # ---------- new profile page: header, binders of all games, sharing line ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def meForm(self):
        return self._me_form

    @QtCore.Property(QtCore.QObject, constant=True)
    def backForm(self):
        return self._back_form

    def _build_me(self, ui):
        return self._me(ui, self.ctrl.settings)[0]

    def _build_back(self, ui):
        return self._me(ui, self.ctrl.settings)[1]

    @QtCore.Property(str, notify=changed)
    def backImage(self):
        from ui.qlibrary import back_image
        return back_image(userprofile.ensure(self.ctrl.settings).get("back"))

    MAX_BINDERS = 8

    def _binder_files(self):
        """[(game, binder)] of all existing games (the open one from the collection, the others read)."""
        from collection import binders
        out = []
        cur = games.current().key
        for key, _n, ready in games.GAMES:
            if not ready:
                continue
            if key == cur:
                items = binders.load()
            else:
                f = games.mine(key) / "binders.json"
                try:
                    items = json.loads(f.read_text("utf-8")).get("binders") or [] if f.exists() else []
                except (OSError, ValueError):
                    items = []
            out += [(key, b) for b in items]
        return out

    @QtCore.Property("QVariantList", notify=changed)
    def binderTiles(self):
        """Binders of all games in your own order: [{key, game, chip, id, name, value, info, owned, color}]
        – followed (while fewer than 8) by a "+ New binder"."""
        from collection import binders
        from cards import carddb
        from cards import packs
        from collection.tradelib import eur
        cur = games.current().key
        order = list(self.ctrl.settings.get("binder_order") or [])
        rows = self._binder_files()
        rows.sort(key=lambda gb: (order.index(f"{gb[0]}:{gb[1]['id']}") if f"{gb[0]}:{gb[1]['id']}" in order
                                  else len(order), -(gb[1].get("updated") or 0)))
        out = []
        for g, b in rows[:self.MAX_BINDERS]:
            owned = self._owned(g, cur)
            sids = {s["sid"] for s in b.get("slots") or [] if s and s.get("sid")}
            try:
                db = carddb.cards_by_ids(sids, game=g) if sids else {}
            except Exception:  # noqa: BLE001
                db = {}
            prices = {sid: (r.get("eur") if r.get("eur") is not None else r.get("eur_foil")) for sid, r in db.items()}
            total, _have_v = binders.value(b, owned, prices)
            have, n = binders.progress(b, owned)
            ok = g == cur or packs.game_ready(g)
            out.append({"key": f"{g}:{b['id']}", "game": g, "chip": games.SHORT.get(g, g.upper()), "id": b["id"],
                        # formerly shared only via the menu (no flag): counts as shared while on display
                        "shared": bool(b["shared"]) if "shared" in b else bool(
                            __import__("net.relay", fromlist=["relay"]).posted(self.ctrl.settings, g, f"binder-{b['id']}")),
                        "name": b.get("name") or tr("Binders"), "value": eur(total) if total else "–",
                        "info": tr(f"{have} of {n} cards"), "owned": ok, "icon": self._game_icon(g),
                        "hue": (sum(ord(c) for c in b["id"]) * 37) % 360})
        if len(out) < self.MAX_BINDERS:
            out.append({"key": "new", "new": True})
        return out

    def _owned(self, g, cur):
        """What exists of a game (binders.owned_map) – cached: your own collection until the next
        change, other games until their file changes (otherwise every refresh re-read all collections, ~0.1 s
        per large collection on the main thread)."""
        from collection import binders
        if g == cur:
            col = self.ctrl.collection
            sig = ("cur", id(col.items), col.rev, len(col.items))
        else:
            try:
                st = (games.mine(g) / "collection.json").stat()
                sig = ("file", st.st_mtime_ns, st.st_size)
            except OSError:
                sig = ("file", None)
        cache = self.__dict__.setdefault("_owned_cache", {})
        hit = cache.get(g)
        if hit is None or hit[0] != sig:
            hit = cache[g] = (sig, binders.owned_map(self.ctrl.collection.items if g == cur else
                                                     games.collection_items(g)))
        return hit[1]

    @staticmethod
    def _game_icon(key):
        from ui import quickshell
        return quickshell.Shell.game_icon(key)

    @QtCore.Slot(str, str, bool)
    def reorderBinders(self, src, target, after):
        """Drag a binder onto the edge of another = change the order (like with decks)."""
        keys = [t["key"] for t in self.binderTiles if not t.get("new")]
        if src not in keys or target not in keys or src == target:
            return
        keys.remove(src)
        i = keys.index(target) + (1 if after else 0)
        keys.insert(i, src)
        self.ctrl.settings["binder_order"] = keys
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def gameKey(self):
        return games.current().key

    @QtCore.Property("QVariantList", notify=changed)
    def binderGames(self):
        """Games to choose from when creating: installed ones only (the open one first)."""
        from cards import packs
        cur = games.current().key
        keys = [cur] + [k for k, _n, r in games.GAMES if r and k != cur and packs.game_ready(k)]
        return [{"key": k, "text": games.SHORT.get(k, k.upper()), "tip": games.name_of(k)} for k in keys]

    @QtCore.Slot(str, str, str)
    def newBinder(self, name, size, game=""):
        """The "+ New binder" tile – name, size and game from the field in the tile. In the open game it is then open;
        for another game it is ready there (without switching)."""
        from collection import binders
        import time as _t
        import uuid
        c, r = (int(x) for x in (size or "3x3").split("x"))
        name = (name or "").strip() or tr("Binders")
        cur = games.current().key
        game = game or cur
        if game == cur:
            b = binders.new(name, c, r)
        else:
            f = games.mine(game) / "binders.json"
            try:
                items = json.loads(f.read_text("utf-8")).get("binders") or [] if f.exists() else []
            except (OSError, ValueError):
                items = []
            now = _t.time()
            b = {"id": uuid.uuid4().hex[:10], "name": name[:60], "cols": c, "rows": r, "slots": [None] * (c * r * 2),
                 "created": now, "updated": now}
            items.append(b)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"version": 1, "binders": items}, ensure_ascii=False, indent=1), "utf-8")
        order = list(self.ctrl.settings.get("binder_order") or [])
        order.append(f"{game}:{b['id']}")
        self.ctrl.settings["binder_order"] = order
        self.ctrl.settings_changed()
        if game == cur:
            self._binder.open(b["id"])
            self.ctrl.stream.show_page("profile")
        else:
            self.ctrl.stream_toast(tr(f"“{name}” is now waiting in {games.nick_of(game)}."))
        self.changed.emit()

    @QtCore.Slot(str, str)
    def openBinder(self, game, bid):
        """Click on a binder: large for viewing (in the profile) – any game, without switching. Edit via the
        button in the view or the menu. Opened from trade: "Back" leads there again."""
        came_from = self.ctrl.stream.page
        self._binder.open_other(game, bid)
        if self._binder.show_in(came_from):
            return
        if came_from != "profile":
            self.ctrl.stream.show_page("profile", back=True)
        self._binder.back_to = came_from if came_from != "profile" else ""

    @QtCore.Slot(str, str, bool)
    def setBinderShared(self, game, bid, on):
        """The "private" / "shared" chip on the binder tile (profile and trade): on = put on display and keep current,
        off = take it off the server immediately."""
        from ui import qbinder
        from net import relay
        s = self.ctrl.settings
        if on and (not relay.enabled(s) or not relay.ok_friends(s)):
            self.ctrl.stream_toast(tr("To share, first turn on the exchange in your profile and add friends."))
            return
        b = qbinder.update_in(game, bid, shared=bool(on))
        if b is None:
            return
        if on:
            qbinder.share_put(self.ctrl, game, b)
        else:
            qbinder.share_withdraw(self.ctrl, game, bid)
            self.ctrl.stream_toast(tr("Binder is private again – it disappears for your friends."))
        self.ctrl.settings_changed()
        self.refresh()

    @QtCore.Slot(str, str, result="QVariantList")
    def binderMenu(self, game, bid):
        """The "Edit" button: the binder menu."""
        here = game == games.current().key
        out = [{"text": tr("Edit") if here else tr(f"Edit in {games.nick_of(game)}"),
                "key": "edit"}, {"text": tr("Rename"), "key": "rename"},
               {"text": tr("Missing to wishlist"), "key": "wish", "enabled": here},
               {"sep": True},
               {"text": tr("Delete …"), "key": "delete", "enabled": here}]
        return out

    @QtCore.Slot(str, str, str, result=bool)
    def renameBinderTo(self, game, bid, name):
        """Name field under a binder's cover (click on the name or menu → Rename, review .101) – any game."""
        from ui import qbinder
        if not name.strip():
            return False
        qbinder.rename_in(game, bid, name.strip()[:60])
        self.refresh()
        return True

    @QtCore.Slot(str, str, str)
    def binderAction(self, game, bid, key):
        if key == "edit" and game != games.current().key:
            if not self.ctrl.switch_game(game, then=lambda: (self.ctrl.stream.show_page("profile"),
                                                               self._binder.open(bid))):
                self.ctrl.stream_toast(tr("Can't switch right now – wait for the running tasks first."))
            return
        if key == "rename":   # works in every game, without switching
            from ui import qbinder
            from ui import qdialogs
            name = qdialogs.get_text(tr("Rename binder"), tr("Name:"),
                                     next((t["name"] for t in self.binderTiles if t.get("id") == bid), ""))
            if name and name.strip():
                qbinder.rename_in(game, bid, name.strip()[:60])
            self.refresh()
            return
        self._binder.open(bid)
        if key == "rename":
            self._binder.rename()
        elif key == "wish":
            self._binder.missingToWishlist()
        elif key == "share":
            self._binder.share()
        elif key == "delete":
            self._binder.remove()
        if key in ("rename", "wish", "share", "delete"):
            if key != "delete":
                self._binder.close()
        self.refresh()

    @QtCore.Property(str, notify=changed)
    def shareLine(self):
        """One line at the very bottom: offline or shared with friends."""
        from net import relay
        s = self.ctrl.settings
        if not relay.enabled(s) or not relay.ok_friends(s):
            return tr("Offline profile – nobody but you can see it.")
        parts = [tr("your name and your card back")]
        if s.get("share_library") is True:
            parts.append(tr("your library"))
        parts.append(tr("the lists you share"))
        return tr("Shared profile – your friends see ") + ", ".join(parts[:-1]) + tr(" and ") + parts[-1] + "."

    # ---------- Friends menu on the profile button ----------
    @QtCore.Property("QVariantMap", notify=changed)
    def me(self):
        from net import relay
        s = self.ctrl.settings
        prof = userprofile.ensure(s)
        try:
            code = relay.pretty(relay.my_code(s)) if relay.enabled(s) else ""
        except Exception:  # noqa: BLE001
            code = ""
        return {"name": prof.get("name") or tr("You"), "code": code, "relay": relay.enabled(s)}

    @QtCore.Property("QVariantList", notify=changed)
    def requests(self):
        """Requests: received (status in) and sent (out) – [{code, name, dir}]."""
        from net import relay
        out = []
        for p in all_friends(self.ctrl.settings):
            if p["status"] in ("in", "out"):
                out.append({"code": p["code"], "name": shown_name(p), "dir": p["status"],
                            "pretty": relay.pretty(p["code"]) if p["code"] else ""})
        return out

    @QtCore.Slot()
    def copyCode(self):
        code = self.me.get("code")
        if code:
            self.ctrl.copy_text(code, tr("ID copied"))

    @QtCore.Slot(str, result=str)
    def addFriend(self, code):
        """The "+" in the friends menu: enter a code, OK -> request sent. -> error text or ""."""
        from net import relay
        s = self.ctrl.settings
        code = (code or "").strip()
        if not relay.enabled(s):
            self.ctrl.relay_ask()
            if not relay.enabled(s):
                return tr("Turn on exchange via the server first.")
        if len(code.replace("-", "")) < 8:
            return tr("That doesn't look like an ID (e.g. 7F3A-21C9-0B44-E1D2).")
        self.ctrl.relay_add(code)
        self.ctrl.stream_toast(tr("Request sent"))
        QtCore.QTimer.singleShot(1500, self.refresh)
        return ""

    @QtCore.Slot(str, int)
    def answer(self, code, how):
        """Received request: 1 accept, 0 decline, -1 block."""
        self.ctrl.relay_answer(code, True if how == 1 else (False if how == 0 else None))
        QtCore.QTimer.singleShot(1500, self.refresh)

    @QtCore.Slot(str)
    def retract(self, code):
        self.ctrl.relay_remove(code)
        QtCore.QTimer.singleShot(800, self.refresh)

    def _me(self, ui, s):
        from net import relay
        prof = userprofile.ensure(s)
        ctrl = self.ctrl

        def changed(rebuild=True):
            ctrl.settings_changed()
            tp = getattr(ctrl, "trade_page", None)
            if tp is not None and hasattr(tp, "refresh_me"):
                tp.refresh_me()
            if rebuild:   # not while painting: rebuilding the page made every stroke stutter
                self.refresh()
        ids = []   # nobody needs to see the collection's internal identifier (prof["id"]) – only "Your ID"
        if relay.enabled(s):
            code = relay.pretty(relay.my_code(s))
            ids.insert(0, (tr("Your ID"), ui.col([
                ui.label(f"<span style='font-size:17px'><b>{code}</b></span>", rich=True, wrap=False),
                ui.row([ui.button(tr("Copy"), lambda: ctrl.copy_text(code, tr("ID copied"))), ui.stretch()])],
                spacing=4)))
        return (
            ui.group(tr("You"), [
                ui.form([(tr("Name"), ui.edit(prof.get("name") or "", lambda t: (userprofile.ensure(s, t[:40]),
                                                                                  changed()),
                                              key="name", placeholder=tr("Your name or nickname")))] + ids),
                ui.note(tr("Only your friends can see your name – a nickname is fine. Everything here stays on this computer unless you share it yourself.")),
            ], flat=True),
            ui.group(tr("Your card back"), [
                ui.note(tr("This is how your friends see you.")),
                ui.pixel(prof.get("back"), lambda back: (userprofile.ensure(s, back=back), changed(False))),
            ], flat=True))
