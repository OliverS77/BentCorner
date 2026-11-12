"""The desktop sync (docs/SYNC-PLAN.md §3, PAIRING.md §4): this device's documents <-> the own vault, ops model.

The pure rules are collection/syncops.py (with vectors, the web app does the same); this is the bookkeeping:

    <data folder>/sync/meta.json      on, seeded, device, clock, vault version
                      state.json      the merged State of every op seen (syncops.State.to_snap)
                      pending.json    own ops not in the vault yet
                      shadow/…        each document as last recorded (what the next diff starts from)

A run, in three steps (the Qt layer runs 1 and 3 in the background, 2 on the main thread – where the program itself
saves, so a sync write never overtakes an edit):
    1. fetch()       local changes not recorded yet (catch_up), then vault/get since our version: a snap replaces
                     the state (own unsent ops on top again), adds are applied op by op and their checksum compared –
                     the same ops but another result: heal (fetch everything anew). The first run after switching on
                     seeds the documents against what the vault holds (syncops.seed_ops – nothing before it is
                     recorded, so nothing counts twice).
    2. write_back()  every document the merged state changes: implode, write, shadow = what was written.
    3. push()        own ops as add packages (base = our version); 409 -> fetch again first; 413 -> a snap instead.

Scope of the first test (SYNC-TESTPLAN): decks, binders, lists, wishlist and the profile, for every game. The friend
kinds come with coupling (after_pairing); the library through the logs (§3b) in the second test.
Saving a document calls record() (decks.save, binders.save, trade.save_wishes/_write_lists); anything written another
way (undo, a restored backup) is found by catch_up() at the next run.
"""
import json
import logging
import os
import pathlib
import re
import threading
import time

from collection import synclogs, syncops

log = logging.getLogger("booster")
LOG_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")   # a log id becomes a file name (synclogs.new_id: date/kind + _<dev>)

FILES = {"decks.json": ("decks", "deckcards"), "binders.json": ("binders", "binderslots"),
         "lists.json": ("lists", "havecards"), "wishlist.json": ("wishcards",),
         "offers.json": ("offers",), "pending-trades.json": ("pending",)}   # Weg (a): trades in progress
# documents in the settings (global kinds): the path in settings.json -> its kinds (Paket 2, 07.11.)
SETTINGS_DOCS = {"relay.friends": ("friends", "friendboards"), "friend_notes": ("friendnotes",),
                 "friend_folders": ("friendfolders",), "inbox": ("inbox",), "price_alarms": ("alarms",),
                 "list_alarms": ("listalarms",)}
LOGS = "logs"      # the collection of a game: its logs, bookings, trade marks (docs/web/SYNC-LOGS.md) – one unit
PROFILE = "profile"
HEAL_PAUSE_MS = 3600 * 1000   # healing (the whole vault anew) at most once an hour
DAY_MS = 86400 * 1000   # a compacting snap after deletes at most once a day (legal 06.11.)
TRIES = 3          # 409 (another device wrote first): fetch and try again at most this often per run
# Behind a switch until Oliver releases it after his test (lead 03.11.): only a test build sets SYNC_TEST, from the
# source BC_SYNC=1. Without it nothing here runs and nothing goes to the server. A built exe ignores BC_SYNC (lead
# 06.11.): nobody may switch the sync on from outside with an environment variable.
SYNC_TEST = False
ENGINE = None      # the running Engine (net/sync_ctl.py) – the save hooks record through it
ON_RECORD = None   # called after a save produced ops (the window syncs 20 s later)


JOIN_FLAGS = ("join_merge", "join_theirs", "join_mine", "join_hold")   # one join's answer – used up by that join
SHIP_FLAG = "ship-sync.flag"   # in the exe only from `build.ps1 -Ship` (the candidate) – never in a normal build


def available():
    """Sync + online backup at all? A Ship build (build.ps1 -Ship puts SHIP_FLAG into the exe), a test build
    (SYNC_TEST), or from the source with BC_SYNC=1. A normal build: off – no engine, no network (lead 08.11.: Oliver's
    real app is built from qtquick and must not sync against a live server that doesn't have the sync yet)."""
    import os
    import sys
    return SYNC_TEST or ship_build() or (not getattr(sys, "frozen", False) and os.environ.get("BC_SYNC") == "1")


def ship_build():
    """The exe was built with build.ps1 -Ship (its bundled SHIP_FLAG)."""
    import pathlib
    import sys
    base = getattr(sys, "_MEIPASS", None)
    return bool(getattr(sys, "frozen", False) and base and (pathlib.Path(base) / SHIP_FLAG).is_file())


def wanted(settings):
    """Online backup + sync really on (the UI's state, library's pages): only behind the switch (available), in
    Full Orbit and the user's "Daten online sichern" on. The rescue/protection code is an offer, no longer a
    condition (Oliver 07.11.: without it the backup can't be restored without any device – the page says so)."""
    if not available():
        return False
    from system import orbit
    return orbit.level(settings) == "full" and bool(settings.get("sync_backup"))


# the online backup goes 183 days after its last use (box VAULT_TTL); 150 days after THIS device's last access it warns
# – computed here without the network, also while the sync pauses outside Full Orbit (legal/lead 07.11.;
# docs/web/vault-expiry.json, the web alike). Only this device's access is known: another one may keep it alive.
EXPIRY_WARN_DAYS, VAULT_TTL_DAYS = 150, 183


def expiry(meta, now_ms):
    """-> {"seen", "until"} (ms) once this device's last vault access is EXPIRY_WARN_DAYS old, else None – paired only
    (seeded), not after „deleted on another device“; no network."""
    seen = meta.get("vault_seen")
    if not seen or not meta.get("seeded") or meta.get("deleted_off"):
        return None
    if now_ms - int(seen) < EXPIRY_WARN_DAYS * DAY_MS:
        return None
    return {"seen": int(seen), "until": int(seen) + VAULT_TTL_DAYS * DAY_MS}


def test_base():
    """BC_SYNC_BASE: the sync test server – a local box.py (http://127.0.0.1:8799) or https://bentcorner.app/testapp/box.
    Only where BC_SYNC counts (from the source, switched on); a built exe never follows it (lead 06.11.). None = the
    normal mailbox (relay.url)."""
    import os
    import sys
    if getattr(sys, "frozen", False) or os.environ.get("BC_SYNC") != "1":
        return None
    return os.environ.get("BC_SYNC_BASE", "").strip().rstrip("/") or None


def saved(path, doc):
    """A save hook (decks.save, binders.save, trade.save_wishes/_write_lists): record what changed. Never breaks the
    save – a failure is logged and the next run's catch_up finds the change anyway."""
    e = ENGINE
    if e is None:
        return
    try:
        p = pathlib.Path(path).resolve()
        if p.name in ("collection.json", "bookings.json") or p.parent.name == "sessions":
            # the collection: recorded at the next run (a whole explode – not on every scanned card)
            if e.on() and e.meta.get("seeded") and ON_RECORD:
                ON_RECORD()
            return
        if p.name not in FILES:
            return
        game = next((g for g in e.docs.games() if pathlib.Path(e.docs.path(g, p.name)).resolve() == p), None)
        if game is not None and e.record(game, p.name, doc) and ON_RECORD:
            ON_RECORD()
    except Exception:  # noqa: BLE001
        log.exception("Sync: recording a save failed")


class Unreadable(OSError):
    """A document is there but can't be read (locked by OneDrive/a virus scanner, half written, damaged) – NOT the
    same as missing: nothing of it may be recorded as deleted (review 08.11., S3). A run that needs it stops instead."""


def _read_doc(p):
    """A user document: None if it doesn't exist, Unreadable if it exists but can't be read or parsed."""
    p = pathlib.Path(p)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise Unreadable(f"{p.name}: {e.__class__.__name__}") from None


def _read(p, default):
    try:
        return json.loads(pathlib.Path(p).read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _write(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")
    tmp.replace(p)


class VaultEmptied(Exception):
    """The vault is older than what this device already fetched – emptied on the server (another device deleted the
    online backup, the test instance was emptied). Nothing is overwritten or sent: the user decides
    (SYNC-PLAN §6: "Das Fach war leer – von diesem Gerät neu sichern?"), then Engine.restore_vault."""


class VaultDeleted(Exception):
    """The online backup was deliberately deleted on another device: the server answers get with {"deleted": t}
    (Gordon's box, 90 days, only a hash of the vault id + the time – legal/lead 06.11., Art. 17). This device turns the
    sync off and says so; it never offers to back it up again in this case. Switching on again by the user's own hand is
    a deliberate new backup (Engine.switch_on)."""

    def __init__(self, when):
        super().__init__(f"deleted at {when}")
        self.when = when


class Docs:
    """Where the documents are: the files of every game (games.mine) and the profile in the settings."""

    def __init__(self, settings, game_keys=None, save_settings=None):
        self.settings = settings
        self._keys = game_keys
        self.save_settings = save_settings   # writes settings.json NOW (M12: before the shadow says „written“)

    def games(self):
        if self._keys is not None:
            return list(self._keys)
        import games
        return [k for k, _name, _ready in games.GAMES if games.mine(k).is_dir()]

    def known_games(self):
        """Every game this program knows (also without a folder of its own yet)."""
        if self._keys is not None:
            return list(self._keys)
        import games
        return [k for k, _name, _ready in games.GAMES]

    def path(self, game, *parts):
        import games
        return games.mine(game, *parts)

    def read(self, game, fname):
        if fname == PROFILE:
            return dict(self.settings.get("profile") or {}) or None
        if fname in SETTINGS_DOCS:
            cur = self.settings
            for part in fname.split("."):
                cur = (cur or {}).get(part) if isinstance(cur, dict) else None
            return json.loads(json.dumps(cur)) if cur is not None else None
        return _read_doc(self.path(game, fname))

    def write(self, game, fname, doc):
        if fname == PROFILE:
            self.settings["profile"] = doc
            return
        if fname in SETTINGS_DOCS:
            parts = fname.split(".")
            cur = self.settings
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = doc
            return
        p = self.path(game, fname)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(p)

    # ---------- the collection (logs) ----------
    def read_logs(self, game):
        """-> {"logs" (hidden too), "bookings", "items", "broken", "hidden"} of a game, from its files – a log the
        scanner is about to save goes to its file first."""
        try:
            from collection import sessions
            if pathlib.Path(sessions.SESSIONS).resolve() == pathlib.Path(self.path(game, "sessions")).resolve():
                sessions.flush()
        except Exception:  # noqa: BLE001 – the file as it is then
            log.exception("Sync: flushing the logs")
        sd = pathlib.Path(self.path(game, "sessions"))
        logs = []
        for f in sorted(sd.glob("*.json")) if sd.exists() else []:
            d = _read_doc(f)   # an unreadable log must not look deleted (review 08.11., S3)
            if isinstance(d, dict) and d.get("id") == f.stem:
                logs.append(d)
        from collection.collection import split_entries
        coll = _read_doc(self.path(game, "collection.json")) or {}
        items, broken = split_entries(coll.get("items") or [])
        book = (_read_doc(self.path(game, "bookings.json")) or {}).get("bookings") or []
        return {"logs": logs, "bookings": book, "items": items, "broken": broken,
                "hidden": set(coll.get("hidden") or [])}

    def log_file(self, game, sid):
        """<game>/sessions/<sid>.json – log ids come from the vault (another own device): only harmless ids and only
        inside the folder ("../x", "C:/x", NUL never reach the disk; review 08.11., M2). -> Path or None"""
        sid = str(sid or "")
        if not LOG_ID.fullmatch(sid):
            log.warning("Sync: log id not usable as a file name, skipped: %r", sid[:20])
            return None
        folder = pathlib.Path(self.path(game, "sessions"))
        f = folder / f"{sid}.json"
        if f.resolve().parent != folder.resolve():
            log.warning("Sync: log file outside its folder, skipped: %r", sid[:20])
            return None
        return f

    def files_of(self, game, data, logs_changed=(), deleted=(), bookings=True, collection=True):
        """-> ({path: text}, [paths to delete]) for writing a game's collection documents (Engine._commit)."""
        writes, dels = {}, []
        for d in logs_changed:
            f = self.log_file(game, d.get("id"))
            if f is None:
                continue
            d = dict(d)
            try:
                from scanner import core
                d["stats"] = core.session_stats(d.get("packs") or [], d.get("info") or {})
            except Exception:  # noqa: BLE001 – the log list needs them: say so, keep the old ones
                log.exception("Sync: figures of log %s", d.get("id"))
            writes[f] = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        for sid in deleted:
            f = self.log_file(game, sid)
            if f is not None:
                dels.append(f)
        if bookings:
            writes[pathlib.Path(self.path(game, "bookings.json"))] = json.dumps(
                {"version": 1, "bookings": data["bookings"]}, ensure_ascii=False, indent=1)
        if collection:
            writes[pathlib.Path(self.path(game, "collection.json"))] = json.dumps(
                {"version": 1, "saved": time.time(), "items": [dict(i) for i in data["items"]] + list(data["broken"]),
                 "hidden": sorted(data["hidden"])}, ensure_ascii=False, indent=1)
        return writes, dels

    def card_of(self, game):
        """id -> the card's row in that game's card database (images, rarity …) or None."""
        def get(card_id):
            try:
                from cards import carddb
                from collection.collection import scryfall_id
                row = carddb.cards_by_ids([scryfall_id(card_id)], game).get(scryfall_id(card_id))
                return carddb.entry_from_row(row) if row else None   # the card as the app holds it (img, rarity …)
            except Exception:  # noqa: BLE001 – without the database: the card shows without image until it has one
                return None
        return get

    def aside(self, game_keys, why, other=""):
        """This device's own data aside (collection/syncaside.py) -> its id; OSError if it can't be copied whole."""
        from collection import syncaside
        return syncaside.put({g: self.path(g) for g in game_keys}, self.settings, why, other)

    def backup(self, reason):
        """A silent backup of everything personal before the sync first changes saved logs (lead 07.11.): its own
        folder data/backups/<reason>-<time>, outside the rotation of the automatic backups. -> the folder or None."""
        from system import datastore
        dest = datastore.BACKUPS / f"{reason}-{time.strftime('%Y-%m-%d_%H-%M-%S')}"
        try:
            datastore._copy_personal(dest)
            (dest / "reason.txt").write_text(reason, "utf-8")
            return dest
        except OSError:
            log.exception("Sync: backup before %s", reason)
            return None



def os_name():
    """The platform in the device list: "windows" | "linux" | "mac" (the web writes "web")."""
    import sys
    return "windows" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "linux"


def _app_version():
    import version
    return str(version.VERSION)


def _rid(settings):
    """This device's id in the server's device registry (net/devkeys, B5) – None before it is registered. Only read:
    the key file is never made from here."""
    try:
        from net import devkeys
        k = devkeys.mine(create=False)
        return k["dev_id"] if k and devkeys.registered(settings) else None
    except Exception:  # noqa: BLE001
        return None


def device_number(dev, view):
    """„Device N“ (DEVICE-KEYS §5): the number a device keeps. A device without one takes the largest + 1. Two with the
    same number (added at nearly the same time, or offline): the one with the larger (added, dev) moves on to the
    largest + 1, the other keeps its own – every device computes the same, and no other device's number jumps."""
    me = view.get(dev) or {}
    mine = int(me.get("n") or 0)
    others = {k: e for k, e in view.items() if k != dev}
    top = max([int(e.get("n") or 0) for e in others.values()] + [0])
    if not mine:
        return top + 1
    rank = (int(me.get("added") or 0), dev)
    if any(int(e.get("n") or 0) == mine and (int(e.get("added") or 0), k) < rank for k, e in others.items()):
        return max(top, mine) + 1
    return mine

class Engine:
    def __init__(self, home, settings, docs=None, client=None, now=None):
        self.dir = pathlib.Path(home) / "sync"
        self.settings = settings
        self.docs = docs or Docs(settings)
        if client is None:
            from net import vault as client
        self.client = client
        self._now = now
        self.lock = threading.RLock()
        self.meta = _read(self.dir / "meta.json", {})
        snap = _read(self.dir / "state.json", None)
        self.state = syncops.State.from_snap(snap) if snap else syncops.State()
        self.pending = _read(self.dir / "pending.json", [])
        self.state.ids.update(o["o"] for o in self.pending)   # in the saved state already (covered by its top)
        c = self.meta.get("clock") or {}
        self.clock = syncops.Clock(self.meta.get("dev") or "", c.get("ms", 0), c.get("n", 0), now=now)
        _finish_journals(self.dir / "journal")
        self._suffix()

    def _suffix(self):
        """New logs carry this device's id while the sync is on (SYNC-LOGS §2) – off: exactly as before."""
        synclogs.SUFFIX[0] = "_" + self.meta["dev"] if self.on() and self.meta.get("dev") else ""

    # ---------- switching ----------
    def on(self):
        return bool(self.meta.get("on"))

    def switch_on(self):
        """Nothing is recorded until the first fetch has seeded (ports 03.11.). After "deleted on another device" the
        user switching on again is a deliberate new backup: the whole state goes as a snap (the server then forgets
        its deletion note)."""
        with self.lock:
            if not self.meta.get("dev"):
                self.meta["dev"] = syncops.new_device()
                self.clock.device = self.meta["dev"]
            if self.meta.pop("deleted_off", None):
                self.meta.update(restore=True, snap_next=True)
            self.meta.update(on=True, seeded=False, version=0)
            self.meta.pop("logs_seeded", None)
            # an old join answer belongs to that join only: switched on again, the next join asks anew (review 08.11.,
            # S2: a stale join_theirs skipped the question and the seeding – the vault overwrote this device's data)
            for k in JOIN_FLAGS:
                self.meta.pop(k, None)
            self.state, self.pending = syncops.State(), []
            self._save()
            self._suffix()

    def switch_off(self):
        with self.lock:
            self.meta["on"] = False
            self._save()
            self._suffix()

    def deleted_elsewhere(self):
        """VaultDeleted: off, and remember why (the settings page says so; switching on again = new backup)."""
        with self.lock:
            self.meta.update(on=False, deleted_off=True)
            self.meta.pop("restore", None)
            self.meta.pop("snap_next", None)
            self._save()
            self._suffix()

    def _seed(self):
        return self.settings.get("relay", {}).get("seed")

    def _save(self):
        self.meta["clock"] = {"ms": self.clock.ms, "n": self.clock.n}
        _write(self.dir / "meta.json", self.meta)
        _write(self.dir / "state.json", self.state.to_snap())
        _write(self.dir / "pending.json", self.pending)

    def _shadow_path(self, game, fname):
        if fname == LOGS:
            return self.dir / "shadow" / f"{game}.logs.json"
        if fname in SETTINGS_DOCS:
            return self.dir / "shadow" / f"settings.{fname}.json"
        return self.dir / "shadow" / ("profile.json" if fname == PROFILE else f"{game}.{fname}")

    def _units(self):
        """(game, file, kinds) of everything synced – the profile once (a global kind), the collection per game."""
        gs = self._games()
        out = [(g, f, kinds) for g in gs for f, kinds in FILES.items()]
        out += [(g, LOGS, synclogs.KINDS) for g in gs]
        out += [("*", key, kinds) for key, kinds in SETTINGS_DOCS.items()]
        return out + [("*", PROFILE, ("profile",))]

    def _games(self):
        """This device's games plus every game whose entries are in the vault – a freshly paired PC has no folder yet
        for a game only the other device has (ports 07.11.: it got 0 entries). Only games this program knows."""
        own = list(self.docs.games())
        known = set(self.docs.known_games())
        more = sorted({c.split("/", 1)[0] for c in self.state.kinds} - set(own) - {"*"})
        return own + [g for g in more if g in known]

    # ---------- recording ----------
    def record(self, game, fname, doc=None):
        """A document was saved: its ops (the diff to the shadow) go into the state and the pending list."""
        if not (self.on() and self.meta.get("seeded")):
            return 0
        if fname == LOGS:
            return self._record_logs(game)
        kinds = ("profile",) if fname == PROFILE else SETTINGS_DOCS.get(fname) or FILES.get(fname)
        if not kinds:
            return 0
        with self.lock:
            try:
                doc = self.docs.read(game, fname) if doc is None else doc
            except Unreadable as e:   # not „all deleted“: skipped this run, recorded once it reads again
                log.info("Sync: %s/%s not readable – not recorded this time (%s)", game, fname, e)
                return 0
            old = _read(self._shadow_path(game, fname), None)
            ops = []
            for kind in kinds:
                more, big = syncops.diff_doc(self.clock, game, kind, old, doc)
                ops += more
                if big:   # a big import: the next push sends the whole state as one snap
                    self.meta["snap_next"] = True
            for o in ops:
                self.state.apply(o)
            if ops:
                self.pending += ops
                _write(self._shadow_path(game, fname), doc)
                self._save()
            return len(ops)

    def catch_up(self):
        return sum(self.record(g, f) for g, f, _k in self._units()) + self._record_device()

    def _record_device(self):
        """This device in the device list (docs/web/DEVICE-KEYS.md §5, the web alike): kind, os, ver when they change,
        "seen" (the day) at most once a day; n and added once. The name is not written from here after the first
        time – any own device may rename any device (rename_device) – only mirrored into the settings."""
        if not (self.on() and self.meta.get("seeded") and self.meta.get("dev")):
            return 0
        dev = self.meta["dev"]
        day = self._ms() // DAY_MS * DAY_MS
        with self.lock:
            view = self.state.view("*/devices")
            have = view.get(dev)
            want = {"kind": "pc", "os": os_name(), "ver": _app_version(), "seen": day, "rid": _rid(self.settings)}
            if have is None:   # (again) not in the list: a takeover snap or a new vault dropped it – keep what it was
                # (ports 07.11.: else the FIRST device jumped to „Device 2“); a joining device: the number it was given
                want.update(name=(str(self.settings.get("device_name") or "")[:60] or None),
                            added=int(self.meta.get("my_added") or day))
                hint = {"n": int(self.meta.get("my_n") or self.meta.get("join_n") or 0)}
            else:
                want.update(name=have.get("name"), added=have.get("added") or day)
                hint = {}
            n = device_number(dev, dict(view, **{dev: dict(have or hint, added=want["added"])}))
            want["n"] = n
            want["nick"] = self._my_nick(dev, view, have, want["added"])
            remembered = (self.meta.get("my_n"), self.meta.get("my_added")) == (n, want["added"])
            if not remembered:
                self.meta.update(my_n=n, my_added=want["added"])
            if have is not None and have.get("name") != self.settings.get("device_name"):
                if have.get("name"):   # renamed on another device: the settings follow (rekey's "removed by")
                    self.settings["device_name"] = have["name"]
                else:
                    self.settings.pop("device_name", None)
            old = {dev: {k: v for k, v in have.items() if v is not None}} if have else {}
            if have and have.get("seen", 0) >= day and all(have.get(k) == want[k] for k in ("kind", "os", "ver", "n",
                                                                                          "added", "rid", "nick")):
                if not remembered:
                    self._save()
                return 0
            ops = syncops.diff_ops(self.clock, "*/devices", old, {dev: {k: v for k, v in want.items()
                                                                         if v is not None or have is None}})
            for o in ops:
                self.state.apply(o)
            self.pending += ops
            self._save()
            return len(ops)

    def _my_nick(self, dev, view, have, added):
        """This device's nickname (Oliver/lead 12.11., system/nicknames – the web alike): kept once drawn; drawn when
        missing (a joining device drew it already for its name field: meta my_nick); the same nick as another device
        that ranks before it (added, dev) – drawn again."""
        from system import nicknames
        nick = (have or {}).get("nick") or self.meta.get("my_nick")
        others = {k: e for k, e in view.items() if k != dev}
        rank = (int(added or 0), dev)
        clash = nicknames.valid(nick) and any(
            list(e.get("nick") or []) == list(nick) and (int(e.get("added") or 0), k) < rank for k, e in others.items())
        if not nicknames.valid(nick) or clash:
            taken = [e.get("nick") for e in others.values() if e.get("nick")] + \
                [e.get("name") for e in others.values() if e.get("name")]
            nick = nicknames.pick(taken)
        nick = [int(x) for x in nick]
        if self.meta.get("my_nick") != nick:
            self.meta["my_nick"] = nick
        return nick

    def rename_device(self, dev, name):
        """Any own device renames any device in the list; empty = back to the default „Device N“. -> True if it
        changed (an op on the name only – the last writer wins, like everywhere in the vault)."""
        name = " ".join(str(name or "").split())[:60] or None
        with self.lock:
            have = self.state.value("*/devices", dev)
            if have is None or have.get("name") == name:
                return False
            ops = [syncops.op(self.clock, "*/devices", dev, s={"name": name})]
            for o in ops:
                self.state.apply(o)
            self.pending += ops
            self._save()
        if dev == self.meta.get("dev"):
            if name:
                self.settings["device_name"] = name
            else:
                self.settings.pop("device_name", None)
        return True

    def devices(self):
        """-> [{"dev", "name" (None = „Device {n}“), "n", "kind", "os", "ver", "added", "seen", "me"}] – the own
        devices the vault knows, this one first."""
        me = self.meta.get("dev")
        view = self.state.view("*/devices")
        out = [dict(e, dev=k, me=(k == me), n=int(e.get("n") or device_number(k, view))) for k, e in view.items()]
        return sorted(out, key=lambda e: (not e["me"], -int(e.get("seen") or 0), e["dev"]))

    def drop_self(self):
        """„Dieses Gerät abmelden“: this device leaves the device list (a tombstone, sent with the next push) – the
        others stop listing it. -> number of ops."""
        me = self.meta.get("dev")
        with self.lock:
            view = self.state.view("*/devices")
            if me not in view:
                return 0
            ops = syncops.diff_ops(self.clock, "*/devices", view, {k: v for k, v in view.items() if k != me})
            for o in ops:
                self.state.apply(o)
            self.pending += ops
            self._save()
            return len(ops)

    def drop_devices(self, rids):
        """After „remove one“ (B5): the removed devices (registry ids) leave the list here too."""
        rids = set(rids or ())
        with self.lock:
            view = self.state.view("*/devices")
            keep = {k: v for k, v in view.items() if v.get("rid") not in rids or not v.get("rid")}
            if len(keep) == len(view):
                return 0
            ops = syncops.diff_ops(self.clock, "*/devices", view, keep)
            for o in ops:
                self.state.apply(o)
            self.pending += ops
            self._save()
            return len(ops)

    def drop_other_devices(self):
        """After „Gerät entfernen“: the others must pair again – they leave the list (tombstones)."""
        me = self.meta.get("dev")
        with self.lock:
            view = self.state.view("*/devices")
            ops = syncops.diff_ops(self.clock, "*/devices", view, {k: v for k, v in view.items() if k == me})
            for o in ops:
                self.state.apply(o)
            self.pending += ops
            self._save()

    # ---------- 1. fetch ----------
    def fetch(self):
        """-> {"got": foreign ops applied, "healed": bool}; raises VaultError / PackError(newer)."""
        if not self.meta.get("seeded") and self.meta.get("join_mine"):
            return self._fetch_mine()
        with self.lock:
            if self.meta.get("seeded"):
                self.catch_up()
            since = self.meta.get("version", 0)
            stale = self._stale()
        if stale:
            return self._take_all("offline")
        got, bad = self._pull(since)
        healed = False
        if bad and self._ms() - int(self.meta.get("healed_at") or 0) < HEAL_PAUSE_MS:
            # healed a short while ago and it differs again: not the whole vault on every run (review 08.11.)
            log.info("Sync: checksum differs again – next healing after the pause")
            bad = False
        if bad:   # the same ops, another result: fetch everything anew, own unsent ops on top
            log.info("Sync: checksum differs – healing from the vault")
            self.meta["healed_at"] = self._ms()
            d = self._whole_vault()   # deleted or emptied in between: never heal into nothing (review 08.11., M1)
            with self.lock:
                self.state = syncops.State()
                for o in self.pending:
                    self.state.apply(o)
                got2, _bad = self._apply(d)
            got, healed = got + got2, True
        with self.lock:
            if self.meta.get("restore") and self.meta.get("version"):
                # "back it up again" – but another device already did: take theirs (done above), send only own ops
                self.meta.pop("restore", None)
                self.meta.pop("snap_next", None)
            if not self.meta.get("seeded") and not self.meta.get("join_theirs"):
                hold = None if self.meta.get("join_merge") else self._join_question()
                if hold:   # both have data: nothing is seeded, written or sent until the user chose (three buttons)
                    self.meta["join_hold"] = hold
                    self._save()
                    return {"got": got, "healed": healed, "join": True}
                self._seed_now()
            self.meta["fetched_at"] = self.client.server_ms() or self._ms()
            self._save()
        return {"got": got, "healed": healed}

    # ---------- joining when both devices have data (Oliver 06.11., docs/KOPPEL-TEXTE.md) ----------
    def _counts_here(self):
        out = {"decks": 0, "lists": 0, "binders": 0, "friends": 0, "cards": 0}
        for g in self.docs.games():
            out["decks"] += len((self.docs.read(g, "decks.json") or {}).get("decks") or [])
            out["binders"] += len((self.docs.read(g, "binders.json") or {}).get("binders") or [])
            lists = self.docs.read(g, "lists.json") or {}
            out["lists"] += sum(len(lists.get(k) or []) for k in ("wish", "have", "custom"))
            data = self.docs.read_logs(g)
            out["cards"] += sum(int(it.get("count", 1)) for it in data["items"])
        out["friends"] = sum(1 for f in ((self.settings.get("relay") or {}).get("friends") or {}).values()
                             if f.get("status") == "ok")
        return out

    def _fresh_here(self):
        """A new device without stored data (Oliver 11.11., decision 4 extended): no cards, decks, binders, friends,
        wishes, offers or own lists – only the two default lists (empty, they come by themselves). It is merged
        without asking: there is nothing of its own to choose between."""
        from collection import trade
        defaults = {trade.MAIN_WISH, trade.MAIN_HAVE}
        if (self.settings.get("relay") or {}).get("friends") and any(
                f.get("status") == "ok" for f in self.settings["relay"]["friends"].values()):
            return False
        for g in self.docs.games():
            if (self.docs.read(g, "decks.json") or {}).get("decks") or                     (self.docs.read(g, "binders.json") or {}).get("binders"):
                return False
            lists = self.docs.read(g, "lists.json") or {}
            if any(x.get("id") not in defaults or x.get("items") for k in ("wish", "have", "custom")
                   for x in lists.get(k) or []):
                return False
            if (self.docs.read(g, "wishlist.json") or {}).get("items") or                     (self.docs.read(g, "offers.json") or {}).get("offers"):
                return False
            if self.docs.read_logs(g)["items"]:
                return False
        return True

    def _counts_there(self):
        st = self.state
        out = {"decks": 0, "lists": 0, "binders": 0, "friends": len(st.view("*/friends")), "cards": 0}
        for g in self._games():
            out["decks"] += len(st.view(f"{g}/decks"))
            out["binders"] += len(st.view(f"{g}/binders"))
            out["lists"] += len(st.view(f"{g}/lists"))
            lib = synclogs.library({k: st.view(f"{g}/{k}") for k in synclogs.KINDS})
            out["cards"] += sum(v["count"] for v in lib.values())
        return out

    def _join_question(self):
        """-> {"other", "here", "there"} if this device AND the vault have data (then the user chooses), else None –
        only one side with data joins without asking (Oliver 06.11.)."""
        there = self._counts_there()
        if not any(there.values()):
            return None
        here = self._counts_here()
        if not any(here.values()) or self._fresh_here():
            return None
        if here == there:   # U6 (lead/ports 11.11.): the same numbers on both sides – merged without asking
            return None
        return {"other": self.meta.get("join_other") or "", "here": here, "there": there}

    def join_answer(self, kind):
        """The user's choice: "merge" both, "theirs" (keep the other device's state: ours aside, theirs 1:1), "mine"
        (keep this device's: a snap with takeover), "" cancel (off, nothing sent). The next run does it."""
        with self.lock:
            hold = self.meta.pop("join_hold", None) or {}
            for k in ("join_merge", "join_theirs", "join_mine"):
                self.meta.pop(k, None)
            if kind == "merge":
                self.meta["join_merge"] = True
            elif kind == "theirs":
                self.meta["join_theirs"] = True
                self.meta["aside_next"] = {"why": "theirs", "other": hold.get("other") or ""}
            elif kind == "mine":
                self.meta["join_mine"] = True
            else:
                self.meta["on"] = False
            self._save()
            self._suffix()
        if kind == "mine":
            self.keep_mine(device="pc")

    def _fetch_mine(self):
        """„Keep this device's state“ on joining: the vault's state is not taken – only its version (the base for
        the snap); this device's documents are seeded against nothing and go up whole, with takeover."""
        d = self._deleted(self._get(0))
        with self.lock:
            self.state = syncops.State()
            self.pending = []
            self.meta["version"] = int(d.get("version") or 0)
            self.meta.pop("join_mine", None)
            self._seed_now()
            self.meta["fetched_at"] = self.client.server_ms() or self._ms()
            self._save()
        return {"got": 0, "healed": False}

    # ---------- taking another device's state (SYNC-LOGS §4, legal 06.11.) ----------
    def _stale(self):
        """Out of sync longer than tombstones live (TOMB_DAYS since the last successful fetch): replaying would bring
        back what other devices deleted meanwhile – this device takes the vault's state instead (its own aside)."""
        at = self.meta.get("fetched_at")
        return bool(self.meta.get("seeded") and at and self._ms() - int(at) > syncops.TOMB_DAYS * DAY_MS)

    def _take_all(self, why, other=""):
        """The whole vault 1:1: unsent own ops dropped (they are in the state set aside at write_back), the state from
        the vault alone. -> fetch()'s answer."""
        d = self._whole_vault()
        with self.lock:
            self.pending = []
            self.state = syncops.State()
            got, _bad = self._apply(d)
            self.meta["aside_next"] = {"why": why, "other": other}
            self.meta["fetched_at"] = self.client.server_ms() or self._ms()
            self._save()
        return {"got": got, "healed": False, "aside": why}

    def _foreign_takeover(self, tk):
        """A snap's takeover {dev, at, n} newer than the last one this device knows, from another device. at/n come from
        the hybrid clock (review 08.11., M13): a device that saw a takeover always stamps a later one after it –
        a wrong PC clock can't make an old takeover win or a new one lose."""
        if not tk or tk.get("dev") == self.meta.get("dev"):
            return False
        last = self.meta.get("takeover") or {}
        key = lambda t: (int(t.get("at") or 0), int(t.get("n") or 0), str(t.get("dev") or ""))  # noqa: E731
        return key(tk) > key(last)

    def keep_mine(self, device="pc"):
        """„Stand von diesem Gerät behalten“: the next push sends this device's whole state as a snap with takeover
        {dev, at, device} – every other device sets its own aside and takes it 1:1."""
        with self.lock:
            h = self.clock.tick()   # M13: the hybrid clock – after every takeover this device has seen
            self.meta["takeover_out"] = {"dev": self.meta.get("dev") or "", "at": int(h[0]), "n": int(h[1]),
                                         "device": device}
            self.meta["snap_next"] = True
            self._save()

    def _set_aside(self, nxt):
        """Before the vault's state replaces this device's documents: its own data aside (never lost). Nothing of this
        device is seeded or moved afterwards – the taken state is the whole truth."""
        try:
            sid = self.docs.aside(self.docs.games(), nxt.get("why") or "theirs", nxt.get("other") or "")
        except OSError:
            self.meta["aside_next"] = nxt   # not copied: nothing is written back – next run again
            self._save()
            raise
        self.meta["aside_last"] = sid
        self.meta["aside_last_why"] = nxt.get("why") or "theirs"
        games = self.docs.games()
        self.meta["logs_seeded"] = dict(self.meta.get("logs_seeded") or {}, **{g: 1 for g in games})
        self.meta["logs_ready"] = dict(self.meta.get("logs_ready") or {}, **{g: 1 for g in games})
        self.meta["seeded"] = True
        self.meta.pop("join_theirs", None)   # done: this answer is used up
        self._save()
        return sid

    def _get(self, since):
        """The network part of a fetch – never under the lock (a save on the main thread must not wait for it)."""
        d = self.client.get(self.settings, since)
        with self.lock:   # the protection code: set? a request to replace it running? (the page shows it big)
            self.meta["vault_seen"] = self._ms()   # the server counts its 183 days from a signed get/put
            self.meta["guard"] = bool((d.get("guard") or {}).get("set"))
            from net import guard
            guard.learn(self.settings, d.get("guard"))   # the ID's salt (S5 = b)
            self.meta["guard_request"] = d.get("guard_request") or None
        if self.client.server_ms():
            with self.lock:
                self.clock.set_server_time(self.client.server_ms())
        return d

    def _deleted(self, d):
        """{"deleted": t} -> VaultDeleted, unless this device itself is backing up anew (then it is just empty)."""
        if d.get("deleted"):
            if not self.meta.get("restore"):
                raise VaultDeleted(d["deleted"])
            return {"version": 0, "items": []}
        return d

    def _whole_vault(self):
        """The whole vault, for taking it 1:1 (offline too long) or healing – but never an emptied/expired one: a vault
        without a snapshot that is older than what this device had, or with nothing in it, would replace all of this
        device's data with nothing (review 08.11., S4: > 90 days away + the vault expired). -> VaultEmptied (the page
        asks „back it up again from this device?“), VaultDeleted as everywhere."""
        d = self._deleted(self._get(0))
        items = d.get("items") or []
        since = int(self.meta.get("version") or 0)
        has_snap = any(it.get("kind") == "snap" for it in items)
        if not items or (since and int(d.get("version") or 0) < since and not has_snap):
            raise VaultEmptied(f"vault at version {d.get('version')} with {len(items)} items, this device had {since}")
        return d

    def _pull(self, since):
        d = self._deleted(self._get(since))
        if since and int(d.get("version") or 0) < since:
            # older than what this device fetched: emptied – or emptied and already backed up anew by another device.
            # Look at the whole vault before asking anything (ports' finding 06.11.: never two "back it up" in a row)
            d = self._deleted(self._get(0))
            items = d.get("items") or []
            if not any(it.get("kind") == "snap" for it in items):
                raise VaultEmptied(f"vault at version {d.get('version')}, this device had {since}")
            with self.lock:   # backed up anew: take it, this device's unsent ops on top
                old = self.state
                self.state = syncops.State()
                for o in self.pending:
                    self.state.apply(o)
                self.meta.pop("empty_not_now", None)
                got = self._apply(d)
                # legal (way a, 07.11.): what this device had and the new backup doesn't is never replaced silently –
                # its state goes aside first, like after „keep this device's state“ (the same line on the page)
                if self.meta.get("seeded") and any(old.view(k) != self.state.view(k)
                                                   for k in old.kinds if k.split("/", 1)[-1] not in NOT_ASIDE):
                    self.meta["aside_next"] = {"why": "takeover", "other": ""}
                return got
        with self.lock:
            return self._apply(d)

    def _apply(self, d):
        from net import pairing
        got, bad = 0, False
        for it in d.get("items") or []:
            try:
                pkg = syncops.unpack(pairing.vault_open_bytes(self._seed(), it["data"]))
            except syncops.PackError as e:
                if e.newer:
                    raise
                log.info("Sync: vault item %s not readable (%s) – skipped", it.get("seq"), e)
                continue
            except pairing.PairError:
                log.info("Sync: vault item %s not readable with this identity – skipped", it.get("seq"))
                continue
            if pkg["t"] == "snap":
                tk = pkg.get("takeover")
                if tk:   # M13: our clock never goes behind a takeover we saw
                    self.clock.seen([int(tk.get("at") or 0), int(tk.get("n") or 0)])
                if self._foreign_takeover(tk):
                    self.meta["takeover"] = dict(tk)
                    self.state = syncops.load_snap(pkg)
                    if self.meta.get("seeded"):   # another device kept its state: ours aside, theirs 1:1
                        self.pending = []
                        self.meta["aside_next"] = {"why": "takeover", "other": tk.get("device") or ""}
                    else:
                        for o in self.pending:
                            self.state.apply(o)
                    got += 1
                    continue
                self.state = syncops.load_snap(pkg)
                for o in self.pending:
                    self.state.apply(o)
                got += 1
                continue
            for o in pkg["ops"]:
                if self.state.apply(o):
                    self.clock.seen(o["h"])
                    got += 1
            if syncops.check_add(self.state, pkg) is False:
                bad = True
        self.meta["version"] = int(d.get("version") or 0)
        return got, bad

    def _seed_now(self):
        for game, fname, kinds in self._units():
            if fname == LOGS:   # on the main thread, in write_back (the transition writes the app's files)
                continue
            doc = self.docs.read(game, fname)
            ops = []
            for kind in kinds:
                ops += syncops.seed_ops(self.clock, game, kind, doc, self.state)[0]
            for o in ops:
                self.state.apply(o)
            self.pending += ops
            if doc is not None:
                _write(self._shadow_path(game, fname), doc)
        self.meta["seeded"] = True
        self.meta.pop("join_merge", None)   # done: this answer is used up
        self._record_device()   # in the device list from the first run on

    # ---------- 2. write back ----------
    def write_back(self):
        """Every document the merged state changes -> implode, write. -> [(game, file)] written."""
        written, later = [], []
        with self.lock:
            if self.meta.get("join_hold"):   # waiting for the user's choice: nothing written
                return written
            nxt = self.meta.pop("aside_next", None)
            if nxt:
                self._set_aside(nxt)
            for game, fname, kinds in self._units():
                if fname == LOGS:
                    if self.meta.get("seeded") and self._write_back_logs(game):
                        written.append((game, LOGS))
                    continue
                doc = self.docs.read(game, fname)
                new = doc
                for kind in kinds:
                    c = f"{'*' if syncops.SCHEMA[kind].get('global') else game}/{kind}"
                    if new is None and not self.state.view(c):
                        continue
                    new = syncops.implode(kind, new, self.state.view(c))
                if fname == "binders.json" and new is not None:   # F4: the derived set/number/name filled in
                    from collection import binders
                    new = binders.complete(new, game)
                if new != doc and new is not None:
                    if fname == "relay.friends":
                        self._boards_gone(doc or {}, new)
                    self.docs.write(game, fname, new)
                    written.append((game, fname))
                if new is not None:
                    if fname == PROFILE or fname in SETTINGS_DOCS:
                        later.append((game, fname, new))
                    else:
                        _write(self._shadow_path(game, fname), new)
            # M12 (review 08.11.): documents in the settings change only in memory – settings.json goes to disk FIRST,
            # then their shadow; a crash in between can't turn the entries into delete ops for the other devices
            if later:
                if any((g, f) in written for g, f, _ in later) and self.docs.save_settings is not None:
                    self.docs.save_settings()
                for game, fname, new in later:
                    _write(self._shadow_path(game, fname), new)
        return written

    def _boards_gone(self, old, new):
        """A friend's shared list board that went through the sync (they withdrew on another of my devices) goes here
        too – the same as a board_gone parcel (relay.apply): their stored list is deleted (legal 06.11.)."""
        from net import relay
        for code, f in old.items():
            for gs in (f or {}).get("boards") or {}:
                if gs in ((new.get(code) or {}).get("boards") or {}):
                    continue
                game, _, slot = gs.partition("/")
                if slot == relay.BOARD_LISTS and f.get("pid") and _from_relay(game, f["pid"]):
                    try:
                        relay._drop_list(game, f["pid"])
                    except Exception:  # noqa: BLE001 – the next board_gone/clean-up catches it
                        log.exception("Sync: a withdrawn list")

    # ---------- the collection: logs (SYNC-LOGS) ----------
    def _logs_seeded(self, game):
        return bool((self.meta.get("logs_seeded") or {}).get(game))

    def _record_logs(self, game):
        """Like record() for the collection of a game: explode its logs, bookings, marks; the diff to the shadow."""
        if not self._logs_seeded(game):
            return 0
        with self.lock:
            try:
                data = self.docs.read_logs(game)
            except Unreadable as e:
                log.info("Sync: logs of %s not readable – not recorded this time (%s)", game, e)
                return 0
            new = synclogs.explode(data["logs"], data["bookings"], data["items"])
            old = _read(self._shadow_path(game, LOGS), None) or {}
            ops = []
            for kind in synclogs.KINDS:
                ops += syncops.diff_ops(self.clock, f"{game}/{kind}", old.get(kind) or {}, new[kind])
            if len(ops) > syncops.SNAP_OPS:
                self.meta["snap_next"] = True
            for o in ops:
                self.state.apply(o)
            if ops:
                self.pending += ops
                _write(self._shadow_path(game, LOGS), new)
                self._save()
            return len(ops)

    def _ready_logs(self, game):
        """The transition, once per game, at the first sync (lead 07.11.: never with the switch off – there is no
        engine then –, a silent backup first, atomic): lines sharing a µs move apart (synclogs.spread), the „By hand“
        logs get this device's id (manual_… -> manual_…_<dev>), a log whose id the vault has from another device too
        (the same second) gets it as well, old lines get their finish/edition (shadow.fill_variant). Every reference
        moves along. Touches only this game's sessions/*.json, collection.json, bookings.json.
        -> True if files changed (the caller re-reads)."""
        done = self.meta.setdefault("logs_ready", {})
        if done.get(game):
            return False
        data = self.docs.read_logs(game)
        logs, items, hidden, book = data["logs"], data["items"], data["hidden"], data["bookings"]

        def state():
            return json.dumps([logs, items, sorted(hidden), book], sort_keys=True, ensure_ascii=False)
        before = state()
        ids = [d["id"] for d in logs]
        synclogs.spread(logs, items, hidden, book)
        dev = self.meta.get("dev") or ""
        vault = self.state.view(f"{game}/logs")
        for d in list(logs):
            sid = d["id"]
            if not dev or sid.endswith("_" + dev):
                continue
            if sid.startswith("manual_") or (sid in vault and vault[sid].get("started") != synclogs.ms(d.get("started"))):
                synclogs.rename_log(logs, items, hidden, book, sid, f"{sid}_{dev}")
        from collection import shadow
        shadow.fill_variant(items, logs)
        moved = state() != before
        if moved:
            if not self.meta.get("logs_backup"):
                dest = self.docs.backup("before-sync-logs")
                if dest is None:
                    raise OSError("no backup before the transition of the logs – nothing changed")
                self.meta["logs_backup"] = str(dest)
                self._save()
            now = {d["id"] for d in logs}
            writes, dels = self.docs.files_of(game, data, logs, [sid for sid in ids if sid not in now])
            self._commit(game, writes, dels)
        done[game] = 1
        self._save()
        return moved

    def _seed_logs(self, game):
        """The first run of a game's collection: transition, then this device's logs recorded against the vault
        (like syncops.seed_ops: unknown there -> create, different -> the difference, entries only there untouched)."""
        changed = self._ready_logs(game)
        data = self.docs.read_logs(game)
        local = synclogs.explode(data["logs"], data["bookings"], data["items"])
        ops = []
        for kind in synclogs.KINDS:
            c = f"{game}/{kind}"
            have = {k: {f: v for f, v in self.state.value(c, k).items() if v is not None}
                    for k in local[kind] if self.state.present(c, k)}
            ops += syncops.diff_ops(self.clock, c, have, local[kind])
        for o in ops:
            self.state.apply(o)
        self.pending += ops
        if len(ops) > syncops.SNAP_OPS:
            self.meta["snap_next"] = True
        _write(self._shadow_path(game, LOGS), local)
        self.meta.setdefault("logs_seeded", {})[game] = 1
        self._save()
        return changed

    def _write_back_logs(self, game):
        """The merged logs into this game's files: implode (only what differs, never a log still running here), the
        collection recomputed (synclogs.reconcile), all files as one change (_commit). -> True if files changed."""
        changed = False
        if not self._logs_seeded(game):
            changed = self._seed_logs(game)
        data = self.docs.read_logs(game)
        view = {k: self.state.view(f"{game}/{k}") for k in synclogs.KINDS}
        local = synclogs.explode(data["logs"], data["bookings"], data["items"])
        if all(synclogs.same(local[k], view[k]) for k in synclogs.KINDS):
            return changed
        running = {d["id"] for d in data["logs"] if not d.get("ended")}
        card_of = self.docs.card_of(game)
        logs_new, deleted, book = synclogs.implode(data["logs"], data["bookings"], data["items"], view, card_of,
                                                   skip=running)
        by_id = {d["id"]: d for d in data["logs"]}
        by_id.update(logs_new)
        for sid in deleted:
            by_id.pop(sid, None)
        data["logs"] = list(by_id.values())
        if book is not None:
            data["bookings"] = book
        n = synclogs.reconcile(data["items"], data["hidden"], synclogs.library(view), view, data["logs"], card_of)
        if logs_new or deleted or book is not None or n:
            writes, dels = self.docs.files_of(game, data, logs_new.values(), deleted, bookings=book is not None,
                                              collection=bool(n))
            self._commit(game, writes, dels)
            changed = True
        _write(self._shadow_path(game, LOGS), synclogs.explode(data["logs"], data["bookings"], data["items"]))
        return changed

    def _commit(self, game, writes, dels):
        """Several files as ONE change (lead 07.11.): each new content next to its file (*.sync-new), the plan, then
        the mark – only from the mark on does it count. A crash before it leaves every old file whole (the next start
        removes the new ones), after it the next start finishes (_finish_journals)."""
        j = self.dir / "journal" / game
        _drop_journal(j)
        j.mkdir(parents=True, exist_ok=True)
        plan = {"writes": [], "deletes": [str(p) for p in dels]}
        for p, text in writes.items():
            p = pathlib.Path(p)
            p.parent.mkdir(parents=True, exist_ok=True)
            new = p.with_name(p.name + ".sync-new")
            new.write_text(text, "utf-8")
            plan["writes"].append([str(p), str(new)])
        _write(j / "plan.json", plan)
        _write(j / "commit", {"t": time.time()})
        _apply_journal(j)

    # ---------- 3. push ----------
    def push(self):
        """-> ops sent. 409: fetch first, then again (TRIES); 413: the whole state as one snap instead.
        The packages are built under the lock, sent without it: ops recorded meanwhile stay pending for next time."""
        from net import pairing
        from net.vault import VaultError
        for _try in range(TRIES):
            with self.lock:
                if self.meta.get("join_hold"):   # nothing goes up before the user chose
                    return 0
                self._snap_due()
                if not self.pending and not self.meta.get("snap_next"):
                    return 0
                sending = len(self.pending)
                base = self.meta.get("version", 0)
                snap = bool(self.meta.get("snap_next"))
                big = self.meta.get("snap_too_big") or {}
                if snap and self._ms() - int(big.get("at") or 0) < DAY_MS:
                    # the server refused this snap as bigger than the whole vault (review 08.11.): not the same
                    # megabytes again on every run – once a day, the line stays meanwhile
                    raise VaultError(413, "snapshot bigger than the vault", {"max": big.get("max")})
                if snap:
                    items = [("snap", syncops.snap_package(self.meta["dev"], self.state, self._ms(),
                                                            takeover=self.meta.get("takeover_out")))]
                else:
                    items = [("add", p) for p in syncops.add_packages(self.meta["dev"], self.pending[:sending],
                                                                      self.state)]
                items = [(k, pairing.vault_seal_bytes(self._seed(), p)) for k, p in items]
            try:
                for kind, data in items:
                    base = int(self.client.put(self.settings, kind, base, data)["version"])
                    self.meta["vault_seen"] = self._ms()
            except VaultError as e:
                with self.lock:
                    self.meta["version"] = base   # the parts that went through
                    if e.status == 413 and not snap:
                        self.meta["snap_next"] = True
                    if e.status == 413 and snap and (e.data or {}).get("max"):
                        self.meta["snap_too_big"] = {"at": self._ms(), "max": (e.data or {}).get("max")}
                    self._save()
                if e.status == 409:
                    with self.lock:
                        if self.meta.pop("restore", None):   # someone backed it up first: no second snap over theirs
                            self.meta.pop("snap_next", None)
                    seen = dict(self.meta.get("takeover") or {})
                    self._pull(base)
                    with self.lock:
                        out = self.meta.get("takeover_out")
                        now = self.meta.get("takeover") or {}
                        if out and now != seen and now.get("dev") not in (None, self.meta.get("dev")):
                            # two devices chose „keep mine“ at once and the other was first: send nothing, ask again
                            self.meta.pop("takeover_out", None)
                            self.meta.pop("snap_next", None)
                            self.meta["join_again"] = True
                            self._save()
                            return 0
                    continue
                if e.status == 413 and not snap:
                    continue
                raise
            with self.lock:
                self.meta["version"] = base
                self.meta.pop("snap_next", None)
                self.meta.pop("restore", None)
                if snap:   # the vault holds no deleted values any more
                    self.meta.pop("snap_too_big", None)
                    self.meta["last_snap"] = self._ms()
                    self.meta.pop("tombs", None)
                    out = self.meta.pop("takeover_out", None)
                    if out:   # every later snap of any device carries it on
                        self.meta["takeover"] = dict(out)
                        self.state.takeover = dict(out)
                self.pending = self.pending[sending:]
                self._save()
            return sending
        raise VaultError(409, "the vault kept changing – next time")

    def _snap_due(self):
        """legal (Datenschutz 5a, 06.11.): what this device deleted must leave the vault too – its old add packages hold
        the values until a snap replaces them. A deleted friend entry, trade or waiting trade part (a purge kind): a
        snap at the next run; any other delete: a compacting snap at most once a day (the first 24 h after the last)."""
        dels = [o for o in self.pending if "x" in o]
        if dels:
            self.meta["tombs"] = True
            if any(o["c"].rpartition("/")[2] in syncops.PURGE for o in dels):
                self.meta["snap_next"] = True
        if self.meta.get("tombs") and self._ms() - int(self.meta.get("last_snap") or 0) >= DAY_MS:
            self.meta["snap_next"] = True

    def restore_vault(self):
        """The user said yes to "back it up again from this device": the next run sends this device's whole state as
        one snap into the (empty) vault – other devices then fetch it from there. If another device was quicker, its
        snap is taken instead (fetch / push 409)."""
        with self.lock:
            self.meta["version"] = 0
            self.meta.update(snap_next=True, restore=True)
            self._save()

    def _ms(self):
        return self._now() if self._now else int(time.time() * 1000)


# kinds whose documents syncaside never copies aside (friends' data, the device list, … – syncaside.OWN_*): a
# difference there alone is no reason to set aside (ports 07.11.: a new „seen“ in the device list changed nothing)
NOT_ASIDE = frozenset({"devices", "friends", "friendlibs", "friendnotes", "friendfolders", "friendboards", "inbox"})


def _from_relay(game, pid):
    """Only what came through the mailbox goes with a withdrawn board – a file the user imported himself stays
    (source "relay"; ports 07.11., the web alike)."""
    try:
        from collection import trade
        d = json.loads(trade.friend_path(trade.friends_folder(game), pid).read_text("utf-8"))
        return d.get("source") == "relay"
    except Exception:  # noqa: BLE001 – no such file: nothing to delete
        return False


def _apply_journal(j):
    """Finish a marked change: every new content over its file (one already moved is skipped), the deletions."""
    plan = _read(j / "plan.json", None) or {}
    for target, new in plan.get("writes") or []:
        if pathlib.Path(new).exists():
            os.replace(new, target)
    for p in plan.get("deletes") or []:
        pathlib.Path(p).unlink(missing_ok=True)
    _drop_journal(j, keep_new=True)


def _drop_journal(j, keep_new=False):
    """Remove a journal; without its mark the new contents it staged go too (the old files were never touched)."""
    if not j.exists():
        return
    if not keep_new:
        for _target, new in (_read(j / "plan.json", None) or {}).get("writes") or []:
            pathlib.Path(new).unlink(missing_ok=True)
    for f in j.iterdir():
        f.unlink(missing_ok=True)
    j.rmdir()


def _finish_journals(root):
    """At start: a change with its mark is finished, one without is thrown away (Engine._commit)."""
    if not root.exists():
        return
    for j in root.iterdir():
        if not j.is_dir():
            continue
        try:
            if (j / "commit").exists():
                _apply_journal(j)
            else:
                _drop_journal(j)
        except OSError:
            log.exception("Sync: journal %s", j.name)
