"""Trade page – the folder "Shared with friends" (lead/legal 06.11.2026): everything your friends get from you, per
friend and per content, with switches. Built from the same source as the parcel (RelayControl.relay_share_contents +
relay.share_codes), so the page can never show more or less than goes out. In QML as tradeShared; the host
(TradeBackend) keeps the shared state.

    friends   one row per accepted friend: a switch (gets everything shared – or nothing but name and card back) and
              chips per content, bright = goes out, dim = doesn't
    items     the library, the open game's shareable lists, every binder of all games – one switch each
    card      (c′) only for whoever shares the library from before (the old question's highlighted "Yes"): two equal
              buttons, nothing preselected; until the answer everything stays as it is
"""
from PySide6 import QtCore

from system.i18n import tr
from ui import textsafe


def things(n_lists, n_binders):
    """"1 list and 2 binders" – singular, plural, nothing for a zero."""
    parts = ([tr("1 list") if n_lists == 1 else tr(f"{n_lists} lists")] if n_lists else []) \
        + ([tr("1 binder") if n_binders == 1 else tr(f"{n_binders} binders")] if n_binders else [])
    return tr(" and ").join(parts)


def library_line(n):
    """The library sentence with the exact number of friends (legal 06.11.: never just "your friends")."""
    return tr("You share your whole library with 1 friend (all cards and counts).") if n == 1 \
        else tr(f"You share your whole library with {n} friends (all cards and counts).")


def overview(ctrl):
    """The whole page as one dict – pure, for the tests: {full, friends, items, card, also, slots, empty}."""
    import games
    from net import relay
    from collection import trade
    s = ctrl.settings
    full = relay.enabled(s)
    ok = relay.ok_friends(s) if full else {}
    codes = set(relay.share_codes(s)) if full else set()
    c = ctrl.relay_share_contents()

    def list_name(x):
        return tr(x["name"]) if x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE) else x["name"]
    shared = ([tr("Library")] if c["library"] else []) + [list_name(x) for _k, x in c["lists"]] \
        + [tr("Binder") + f" „{b.get('name') or ''}“" for _g, b in c["binders"]]
    friends = []
    for code, f in sorted(ok.items(), key=lambda kv: (kv[1].get("name") or "").lower()):
        on = code in codes
        friends.append({"code": code, "name": textsafe.name(f.get("name") or relay.pretty(code)), "on": on,
                        "chips": [{"text": tr("Name + card back"), "on": True}]
                        + [{"text": t, "on": on} for t in shared]})
    n_on = sum(1 for f in friends if f["on"])
    cur = games.current().key
    items = [{"kind": "library", "key": "library", "game": cur, "on": c["library"], "name": tr("Library"),
              "sub": tr("all cards and counts · per game, while it is open")}]
    for kind in ("wish", "have"):
        for x in trade.lists(kind):
            if x.get("example"):
                continue
            items.append({"kind": kind, "key": x["id"], "game": cur, "on": trade.is_shared(x), "name": list_name(x),
                          "sub": games.nick_of(cur) + " · " + (tr("Wishlist") if kind == "wish" else tr("Trade list"))})
    from ui import qbinder
    for game, b in qbinder.all_binders(ctrl):
        items.append({"kind": "binder", "key": b["id"], "game": game, "on": bool(b.get("shared")),
                      "name": tr("Binder") + f" „{b.get('name') or ''}“", "sub": games.nick_of(game)})
    card = None
    if s.get("share_library_paused") and not s.get("share_library_confirmed"):   # orbit.hold_sharing: asked first
        card = {"text": tr("Before this update you had chosen to share your whole library with your friends. It is paused now – do you want to share it again?"),
                "small": tr("Only friends you switch on below get it. You can change it any time here."),
                "keep": tr("Share again"), "stop": tr("Don't share")}
    elif c["library"] and n_on and not s.get("share_library_confirmed"):
        card = {"text": library_line(n_on) + " " + tr("Do you want to keep doing that?"),
                "small": tr("You can change it any time here."), "keep": tr("Keep sharing"), "stop": tr("Stop sharing")}
    n_lists, n_binders = len(c["lists"]), len(c["binders"])
    also = ""
    if card and (n_lists or n_binders):
        what = things(n_lists, n_binders)
        also = tr(f"In addition you share {what} with this friend – change them one by one below.") if n_on == 1 \
            else tr(f"In addition you share {what} with these {n_on} friends – change them one by one below.")
    used = relay.slots_used(s)
    slots = tr(f"Almost full: you share {used} of at most {relay.MAX_SLOTS} things (lists per game and binders).") \
        if used >= relay.MAX_SLOTS - 2 else ""
    empty = "" if friends else (tr("No friends yet – add a friend by ID in the friends menu.") if full
                                else tr("Friends only exist in Full Orbit – until then you share nothing."))
    return {"full": full, "friends": friends, "items": items, "card": card or {}, "also": also, "slots": slots,
            "empty": empty, "profile": tr("Name and card back – part of the friendship, every friend sees them"),
            "others": tr("You switch lists of other games while that game is open.")}   # (lead 06.11.)


class SharedBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.ctrl = host.ctrl
        self._note = ""

    @QtCore.Slot()
    def refresh(self):
        self.changed.emit()

    @QtCore.Property("QVariantMap", notify=changed)
    def view(self):
        try:
            return overview(self.ctrl)
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger("booster").exception("Shared with friends")
            return {"friends": [], "items": [], "card": {}}

    @QtCore.Property(str, notify=changed)
    def note(self):
        """A line after switching a friend off – legal: never promise "deleted"."""
        return self._note

    @QtCore.Slot(str, bool)
    def setFriend(self, code, on):
        self.ctrl.relay_share_friend(code, on)
        self._note = "" if on else tr("We ask your friend's app to delete your shared data; they get no new data.")
        self.host.listsChanged.emit()   # the sidebar's "2/3"
        self.changed.emit()

    @QtCore.Slot(str, str, str, bool)
    def setItem(self, kind, key, game, on):
        from collection import trade
        s = self.ctrl.settings
        if kind == "library":
            s["share_library"] = bool(on)
            s["share_library_confirmed"] = True   # a choice under the new rules: no card afterwards
            s.pop("share_library_paused", None)
            self.ctrl.settings_changed()
            self.ctrl.relay_send_lists(quiet=True) if on else self.ctrl.relay_share_library_off()
        elif kind in ("wish", "have"):
            trade.set_shared(kind, key, bool(on))
            self.ctrl.relay_send_lists(quiet=True)   # nothing left: relay_send_lists withdraws
            self.host.listsChanged.emit()
        elif kind == "binder":
            pb = self.ctrl.shell.backends.get("profile")
            pb.setBinderShared(game, key, bool(on))
        self._note = ""
        self.changed.emit()

    @QtCore.Slot(bool)
    def answer(self, keep):
        """The (c′) card – once, never asked again. "Stop sharing" works at once, in every game."""
        s = self.ctrl.settings
        s["share_library_confirmed"] = True
        held = s.pop("share_library_paused", None)
        if not keep:
            s["share_library"] = False
        elif held:   # shared again after the pause: to the friends switched on
            self.ctrl.settings_changed()
            self.ctrl.relay_send_lists(quiet=True)
        self.ctrl.settings_changed()
        if not keep:
            self.ctrl.relay_share_library_off()
        self.changed.emit()
