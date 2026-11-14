"""The wish-list bar on the scan page (0.9.9, Oliver via Gordon 14.11.2026 – an exception to the feature stop).

A counted card (really counted – not a preview, not a discarded scan, lead 14.11.) is asked once at library's
collection.wishhit: is it on one of my wish lists, or on a friend's shared one? Then a bar at the top of the camera
image, headed by the Orbit sign + "Orbit" (Oliver's texts, 14.11.):
    "Wish card hit – removed from Modern · Undo"              one own list, auto-remove on
    "Wish card hit – removed from 3 lists · Details"          several: Details = a second bar, each list its own Undo
    "Wish card hit – on Modern" / "… – on 3 lists · Details"  auto-remove off (nothing to undo)
    "Wish card hit – removed from 1 list, on 2 more · Details" mixed: auto-remove is set per list (library 14.11.)
    "Kim is looking for this card"                            one friend
    "3 friends are looking for this card · Details"           several: Details = every friend with their lists
Friends stay local – nothing goes to the friend or the server (legal, via library).
Both bars can be dragged (positions kept, 0–1 of the image), have no ✕, dim after 8 s and stay; the next hit replaces
them. Undo holds until the next hit; taking the card back (U, Delete, the list's ✕) undoes every list.
The token is library's and opaque – kept only in memory, never stored.
"""
import logging

from system.i18n import tr

log = logging.getLogger(__name__)

DIM_AFTER = 8.0


def _fns():
    try:
        from collection import wishhit
    except ImportError:          # library's part not there yet: no wish hits at all
        return None, None
    return wishhit.hit, wishhit.undo


class WishBar:
    """The bar's state: nothing until the first hit. hit/undo are injectable (tests)."""

    def __init__(self, hit=None, undo=None):
        if hit is None:
            hit, undo = _fns()
        self._hit, self._undo = hit, undo
        self.entry = None        # the counted session entry that was the hit (identity – for U/✕)
        self.result = None       # library's answer
        self.token = None
        self.undone = set()      # list ids put back
        self.serial = 0          # counts hits – QML lights the bars up again on every new one (and closes Details)
        self.rev = 0             # counts changes (an undo) – QML re-reads

    # ---- library ----
    def check(self, entry, settings):
        """A card was counted -> True when it is a wish hit (own lists or a friend's; then the bar is new).
        Never raises."""
        if self._hit is None or not entry:
            return False
        try:
            r = self._hit(entry, settings)
        except Exception:  # noqa: BLE001 – a wish list problem must never stop scanning
            log.exception("Wish hit for %s", entry.get("name"))
            return False
        if not r or not (r.get("lists") or r.get("friends")):
            return False
        self.entry, self.result = entry, r
        self.token = r.get("undo") if r.get("removed") else None
        self.undone = set()
        self.serial += 1
        self.rev += 1
        return True

    def _ids(self):
        """The lists something was taken from (each list says "removed" itself – auto-remove is per list)."""
        return [str(x.get("id")) for x in (self.result or {}).get("lists") or [] if x.get("removed", True)]

    def undo(self, list_id=None):
        """Undo in the bar (None = every list – also U/✕) or in Details (one list) -> True when something changed."""
        if self.token is None or self._undo is None:
            return False
        todo = [i for i in self._ids() if i not in self.undone]
        if list_id is not None:
            todo = [i for i in todo if i == str(list_id)]
        if not todo:
            return False
        try:
            if list_id is None and not self.undone:
                self._undo(self.token)              # everything at once
            else:                                   # one list – or U after single ones: only those still out (lead)
                orig = {str(x.get("id")): x.get("id") for x in self.result.get("lists") or []}
                for i in todo:
                    self._undo(self.token, orig.get(i, i))   # library's own id (int or str)
        except Exception:  # noqa: BLE001
            log.exception("Undoing a wish hit")
            return False
        self.undone.update(todo)
        self.rev += 1
        return True

    def card_removed(self, entry):
        """The hit card itself was taken back (U, Delete, ✕) -> all its wishes go back."""
        if entry is not None and entry is self.entry:
            return self.undo()
        return False

    # ---- for QML ----
    def view(self):
        """{} = no bar; else {serial, rev, head, text, link, linkKind, friendText, friendLink, lists, friends, dimMs}.
        linkKind: "undo" · "details" · "" (nothing to click, or undone); lists/friends: the Details rows."""
        r = self.result
        if not r:
            return {}
        lists = [x for x in r.get("lists") or [] if str(x.get("name", "")).strip()]
        live = self.token is not None

        def took(x):   # something was taken from this list
            return live and bool(x.get("removed", True))
        n_took = sum(1 for x in lists if took(x))
        all_undone = n_took > 0 and all(str(x.get("id")) in self.undone for x in lists if took(x))
        text, link, kind = "", "", ""
        if len(lists) == 1:
            name = str(lists[0]["name"])
            if n_took:
                text = tr("Wish card hit – removed from {list}").format(list=name)
                link, kind = (tr("Undone"), "") if all_undone else (tr("Undo"), "undo")
            else:
                text = tr("Wish card hit – on {list}").format(list=name)
        elif lists:
            if n_took == len(lists):
                text = tr("Wish card hit – removed from {n} lists").format(n=len(lists))
            elif not n_took:
                text = tr("Wish card hit – on {n} lists").format(n=len(lists))
            elif n_took == 1:
                text = tr("Wish card hit – removed from 1 list, on {k} more").format(k=len(lists) - 1)
            else:
                text = tr("Wish card hit – removed from {r} lists, on {k} more").format(r=n_took, k=len(lists) - n_took)
            link, kind = tr("Details"), "details"
        friends = []
        for f in r.get("friends") or []:
            if isinstance(f, dict):
                nm, fl = str(f.get("name", "")), [str(x) for x in f.get("lists") or []]
            else:                      # a bare name (library's first shape)
                nm, fl = str(f), []
            if nm.strip():
                friends.append({"name": nm, "lists": ", ".join(fl)})
        if len(friends) == 1:
            ftext, flink = tr("{name} is looking for this card").format(name=friends[0]["name"]), ""
        elif friends:
            ftext, flink = tr("{n} friends are looking for this card").format(n=len(friends)), tr("Details")
        else:
            ftext, flink = "", ""
        rows = [{"id": str(x.get("id")), "name": str(x["name"]), "n": int(x.get("n") or 1),
                 "undone": str(x.get("id")) in self.undone,
                 "link": (tr("Undone") if str(x.get("id")) in self.undone else tr("Undo")) if took(x) else "",
                 "note": "" if took(x) else tr("stays")}   # the list keeps its wish (auto-remove off – lead 14.11.)
                for x in lists]
        return {"serial": self.serial, "rev": self.rev, "head": "Orbit", "text": text, "link": link,
                "linkKind": kind, "friendText": ftext, "friendLink": flink, "lists": rows, "friends": friends,
                "listsTitle": tr("Your wish lists"), "friendsTitle": tr("Friends looking for this card"),
                "dimMs": int(DIM_AFTER * 1000)}
