"""Writes docs/web/synclog-vectors.json: fixed cases of the collection in the sync (collection/synclogs.py,
docs/web/SYNC-LOGS.md). The web app's JS checks the same file.

  explode  stored documents (logs, bookings, collection entries) -> the synced entries per kind, then the copies per
           key (expected), the library (fields + count + trade) and its checksum
  ops      what devices did, as the ops their save() makes (syncops.diff_ops between two explodes); every device
           reaches the same view, library and checksum whatever order it applies them in (checked here: forward,
           backward, and B's before A's)
  snaps    vault snaps (the unpacked object): with and without takeover, takeover carried on, purged entries

    python tools/make_synclog_vectors.py
"""
import copy
import json
import pathlib
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collection import syncops, synclogs  # noqa: E402

T = 1793600000.0          # fixed wall time (s, 2026-11-02)
GAME = "mtg"
OUT = ROOT / "docs" / "web" / "synclog-vectors.json"


def card(name, n=1):
    return {"id": f"{name.lower()}-id_0", "name": name, "set": "tst", "number": str(n), "rarity": "rare",
            "eur": 1.25, "eur_foil": 2.5, "img": "x.jpg", "url": ""}


def scan_log(sid, names, when, **kw):
    cards = [dict(card(n, i + 1), lang="en", foil=False, cond="near_mint", added=when + i, price=1.25)
             for i, n in enumerate(names)]
    d = {"id": sid, "started": when, "ended": when + 100, "collection": True,
         "info": {"kind": "cards", "title": sid, "active": False},
         "packs": [{"opened": when, "type": "booster", "cards": cards}]}
    d.update(kw)
    return d


def manual_log(day, when, lines=(), gone=()):
    d = {"id": f"manual_{day}", "started": when, "ended": when, "collection": False,
         "info": {"kind": "manual", "title": ""}, "packs": [{"opened": when, "type": "manual", "cards": list(lines)}]}
    if gone:
        d["gone"] = list(gone)
    return d


def line(item, delta, when, **kw):
    ln = {k: item.get(k) for k in ("id", "name", "set", "number", "rarity", "eur", "eur_foil", "img", "url")}
    ln.update(lang=item.get("lang") or "en", foil=bool(item.get("foil")), uid=item["uid"], delta=delta,
              price=1.25, added=when, cond=item.get("cond") or "near_mint")
    for k in ("finish", "edition"):
        if item.get(k):
            ln[k] = item[k]
    if item.get("src"):
        ln["src"] = item["src"]
    if delta < 0:
        ln["item"] = dict(item)
    ln.update(kw)
    return ln


def entry(c, uid, src=None, count=1, **kw):
    it = dict(c, uid=uid, lang="en", foil=False, count=count, added=T, src=src, cond="near_mint")
    it.update(kw)
    return it


def src_of(log, i):
    return f"{log['id']}/{log['packs'][0]['cards'][i]['added']!r}"


def result(view):
    lib = synclogs.library(view)
    return {"expected": dict(sorted(synclogs.expected(view).items())), "library": lib,
            "sum": synclogs.checksum(lib)}


# ---------- explode ----------
def explode_cases():
    out = []

    def case(name, about, logs, bookings, items):
        view = synclogs.explode(logs, bookings, items)
        res = result(view)
        assert res["library"] == synclogs.items_now(items), name   # the documents agree with themselves
        out.append({"name": name, "about": about, "logs": logs, "bookings": bookings, "items": items,
                    "view": view, **res})

    s1 = scan_log("2026-11-02_10-00-00", ["A", "B", "C"], T)
    imp = scan_log("import_2026-11-02_10-05-00", ["D", "E"], T + 300, info={"import": True, "title": "csv"})
    for i, e in enumerate(imp["packs"][0]["cards"]):
        e["added"] = T + 300 + i * 0.001
    a = entry(card("A", 1), "ua", src_of(s1, 0), trade=1)
    b = entry(card("B", 2), "ub", src_of(s1, 1))
    c = entry(card("C", 3), "uc", src_of(s1, 2))
    d = entry(card("D", 1), "ud", src_of(imp, 0))
    e = entry(card("E", 2), "ue", src_of(imp, 1))
    f = entry(card("F", 9), "uf", None, count=2, lang="fr", finish="etched", edition="1st")
    day = manual_log("2026-11-02", T + 400, [
        line(dict(f, lang="de"), 1, T + 400),
        line(dict(f, lang="de"), 1, T + 400 + 1e-6),                  # same instant: the next µs
        line(dict(f, lang="fr"), 0, T + 410, edit={"lang": ["de", "fr"]}),
        line(b, -1, T + 420),                                         # a scanned copy taken out by hand
        line(dict(e, src=None), 1, T + 430)])                         # an old line: no src – key from the entry
    e2 = dict(e, count=2)
    booking = {"id": "bk_1", "t": T + 500, "kind": "trade", "partner": ["X", "Max"], "give": [["tst", "3", "en", False]],
               "get": [], "taken": [{"uid": "uc", "n": 1, "item": c}], "short": [], "session": None}
    case("scan_import_hand_booking_mark",
         "a scan log, an import (1-ms steps), lines by hand (two in one instant, an edit, a removal with its saved "
         "entry, an old line without src), a trade booking, a trade mark",
         [s1, imp, day], [booking], [a, d, e2, f])

    run = scan_log("2026-11-02_11-00-00", ["G"], T + 600, ended=None)
    tr = scan_log("trade_2026-11-02_11-10-00", ["H", "I"], T + 700, info={"kind": "singles", "title": "Tausch"})
    tr["packs"][0]["cards"][1]["out"] = True
    off = scan_log("2026-11-02_11-20-00", ["J"], T + 800, collection=False)
    h = entry(card("H", 1), "uh", src_of(tr, 0))
    case("running_out_and_off",
         "a log still running (counts when it ends), a trade scan's outgoing card, a log out of the library",
         [run, tr, off], [], [h])

    s2 = scan_log("2026-11-02_12-00-00", ["K", "L"], T + 900)
    gone = manual_log("2026-11-02", T + 950, gone=[src_of(s2, 1)])
    k = entry(card("K", 1), "uk", src_of(s2, 0))
    hid = scan_log("2026-11-02_12-30-00", ["M"], T + 1000, hidden={"at": T + 1100, "kept": True})
    m = entry(card("M", 1), "um", src_of(hid, 0))
    case("gone_and_hidden",
         "a log card that left without a line (the gone list), a log in the trash that keeps its cards",
         [s2, gone, hid], [], [k, m])
    return out


# ---------- ops ----------
class Device:
    """A device: its documents (logs by id, bookings, items) and the clock its save() uses."""

    def __init__(self, fake, dev):
        self.fake, self.dev = fake, dev
        self.clock = syncops.Clock(dev, now=lambda: fake[0])
        self.logs, self.bookings, self.items = {}, [], []
        self.ops = []

    def view(self):
        return synclogs.explode(list(self.logs.values()), self.bookings, self.items)

    def change(self, fn):
        """fn changes the documents; the ops are the difference of the synced form before and after."""
        old = self.view()
        fn(self)
        new = self.view()
        made = []
        for kind in synclogs.KINDS:
            made += syncops.diff_ops(self.clock, f"{GAME}/{kind}", old[kind], new[kind])
        self.ops += made
        return made

    def take(self, ops, state=None):
        """Another device's ops arrived: apply them to its own documents (write back, like syncrun.write_back)."""
        st = state or syncops.State()
        for o in self.ops + ops:
            st.apply(o)
        view = {k: st.view(f"{GAME}/{k}") for k in synclogs.KINDS}
        return view


def run_ops(ops):
    st = syncops.State()
    for o in ops:
        st.apply(o)
    return st, {k: st.view(f"{GAME}/{k}") for k in synclogs.KINDS}


def op_cases():
    out = []

    def case(name, about, build):
        fake = [int(T * 1000)]
        a, b = Device(fake, "aaaa"), Device(fake, "bbbb")
        build(fake, a, b)
        ops = a.ops + b.ops
        st, view = run_ops(ops)
        res = result(view)
        for order in (list(reversed(ops)), b.ops + a.ops):
            assert result(run_ops(order)[1])["sum"] == res["sum"], name
        out.append({"name": name, "about": about, "ops": ops,
                    "view": {k: view[k] for k in synclogs.KINDS}, **res,
                    "kind_sums": {k: st.sum(f"{GAME}/{k}") for k in synclogs.KINDS}})

    def union(fake, a, b):
        la = scan_log("2026-11-02_10-00-00_aaaa", ["A", "B"], T)
        lb = scan_log("2026-11-02_10-00-00_bbbb", ["C"], T)          # the same second on both: ids per device
        a.change(lambda d: d.logs.update({la["id"]: la}))
        fake[0] += 1000
        f = entry(card("F", 9), "uf_bbbb", None)
        b.change(lambda d: (d.logs.update({lb["id"]: lb,
                                           "manual_2026-11-02_bbbb": manual_log("2026-11-02_bbbb", T + 5,
                                                                                [line(f, 1, T + 5)])}),
                            d.items.append(f)))
    case("union", "two devices scan at the same second (log ids with the device), one adds by hand: merging = "
         "both sets of logs", union)

    def edit_lww(fake, a, b):
        s = scan_log("2026-11-02_10-00-00_aaaa", ["A", "B"], T)
        a.change(lambda d: d.logs.update({s["id"]: s}))
        b.logs[s["id"]] = copy.deepcopy(s)                            # B has fetched it
        fake[0] += 1000

        def lang(d, v, i):
            d.logs[s["id"]]["packs"][0]["cards"][i]["lang"] = v
        a.change(lambda d: lang(d, "de", 0))
        fake[0] += 1000
        b.change(lambda d: lang(d, "fr", 0))                          # later: wins
        b.change(lambda d: d.logs[s["id"]]["packs"][0]["cards"][1].update(cond="excellent"))
    case("edit_lww", "the same log card changed on both devices: the later change wins per field; another field "
         "of another card changed meanwhile stays", edit_lww)

    def delete_log(fake, a, b):
        s = scan_log("2026-11-02_10-00-00_aaaa", ["A", "B"], T)
        a.change(lambda d: d.logs.update({s["id"]: s}))
        b.logs[s["id"]] = copy.deepcopy(s)
        fake[0] += 1000

        def forget(d):   # app.log_for_good: the cards stay, as lines by hand without src (+n per key)
            held = [entry(card("A", 1), "ua", None), entry(card("B", 2), "ub", None)]
            d.items = held
            del d.logs[s["id"]]
            d.logs["manual_2026-11-02_aaaa"] = manual_log("2026-11-02_aaaa", T + 2, [
                line(held[0], 1, T + 2, why="from a log deleted for good"),
                line(held[1], 1, T + 2 + 1e-6, why="from a log deleted for good")])
        a.change(forget)
        fake[0] += 1000
        b.change(lambda d: d.logs[s["id"]]["packs"][0]["cards"][0].update(lang="it"))   # late edit on the log
    case("delete_log_keeps_cards", "a log deleted for good: tombstone + one line by hand per key (+n, no src); a "
         "later edit of a card of that log on the other device brings nothing back (its log is gone)", delete_log)

    def same_ms(fake, a, b):
        f = entry(card("F", 9), "uf", None)
        g = entry(card("G", 8), "ug", None)
        a.change(lambda d: (d.logs.update({"manual_2026-11-02_aaaa": manual_log("2026-11-02_aaaa", T, [
            line(f, 1, T + 0.0004), line(g, 1, synclogs.us(T + 0.0004) / 1e6 + 1e-6)])}), d.items.extend([f, g])))
    case("two_rows_same_ms", "two lines by hand in the same millisecond (and µs neighbours): their own keys",
         same_ms)

    def undo(fake, a, b):
        f = entry(card("F", 9), "uf", None)
        day = "manual_2026-11-02_aaaa"
        a.change(lambda d: (d.logs.update({day: manual_log("2026-11-02_aaaa", T, [line(f, 1, T)])}),
                            d.items.append(f)))
        fake[0] += 1000
        a.change(lambda d: d.logs[day]["packs"][0]["cards"].append(
            line(dict(f, lang="de"), 0, T + 1, edit={"lang": ["en", "de"]})))
        fake[0] += 1000
        a.change(lambda d: d.logs[day]["packs"][0]["cards"].append(                 # undo of the edit
            line(dict(f, lang="en"), 0, T + 2, edit={"lang": ["de", "en"]}, why="undone")))
        g = entry(card("G", 8), "ug", None)
        fake[0] += 1000
        a.change(lambda d: d.logs[day]["packs"][0]["cards"].append(line(g, 1, T + 3)))
        fake[0] += 1000
        a.change(lambda d: d.logs[day]["packs"][0]["cards"].append(line(g, -1, T + 4, why="undone")))   # undo add
    case("undo_counter_rows", "Undo writes counter lines: after an edit the edit back, after adding by hand the "
         "same copies out (uid key) – nothing is removed, so the undo syncs", undo)

    def marks(fake, a, b):
        s = scan_log("2026-11-02_10-00-00_aaaa", ["A"], T)
        it = entry(card("A", 1), "ua", src_of(s, 0))
        a.change(lambda d: (d.logs.update({s["id"]: s}), d.items.append(dict(it, trade=1))))
        b.logs[s["id"]] = copy.deepcopy(s)
        b.items.append(dict(it, trade=1))
        fake[0] += 1000
        b.change(lambda d: d.items[0].update(trade=0))               # B: no longer for trade (tombstone)
    case("trade_mark", "a trade mark set on one device, taken off on the other later", marks)
    return out


# ---------- snaps ----------
def snap_obj(data):
    return json.loads(zlib.decompress(data).decode("utf-8"))


def snap_cases():
    out = []
    fake = [int(T * 1000)]
    a = Device(fake, "aaaa")
    s = scan_log("2026-11-02_10-00-00_aaaa", ["A", "B"], T)
    a.change(lambda d: d.logs.update({s["id"]: s}))
    fake[0] += 1000
    a.change(lambda d: d.logs[s["id"]]["packs"][0]["cards"].pop())   # B out of the log: a tombstone
    st, view = run_ops(a.ops)
    now = fake[0]
    plain = snap_obj(syncops.snap_package("aaaa", st, now))
    out.append({"name": "snap", "about": "a snap of the state: the removed row keeps only its clocks (no fields)",
                "ops": a.ops, "now": now, "snap": plain, **result(view)})
    take = snap_obj(syncops.snap_package("bbbb", st, now, takeover={"dev": "bbbb", "at": now, "device": "phone"}))
    out.append({"name": "snap_takeover", "about": "„keep this device's data“: the snap carries takeover {dev, at}",
                "ops": a.ops, "now": now, "snap": take})
    st2 = syncops.load_snap(take)
    fake[0] += 1000
    later = snap_obj(syncops.snap_package("aaaa", st2, fake[0]))
    out.append({"name": "snap_takeover_carried", "about": "a later snap (another device compacts) carries the last "
                "takeover on unchanged", "from": take, "now": fake[0], "snap": later})
    assert later["takeover"] == take["takeover"]

    # purge: a deck deleted, a late older op on it, a counted deck card deleted
    c = syncops.Clock("aaaa", now=lambda: fake[0])
    o = [syncops.op(c, "mtg/decks", "d1", s={"name": "Burn", "notes": "for Max"}, create=True),
         syncops.op(c, "mtg/deckcards", "d1|s1|main", d={"n": 3}, create=True)]
    fake[0] += 1000
    o += [syncops.op(c, "mtg/decks", "d1", delete=True), syncops.op(c, "mtg/deckcards", "d1|s1|main", delete=3)]
    old = syncops.op(syncops.Clock("bbbb", now=lambda: int(T * 1000) + 500), "mtg/decks", "d1", s={"name": "Burn 2"})
    stp = syncops.State()
    for x in o + [old]:
        stp.apply(x)
    pur = snap_obj(syncops.snap_package("aaaa", stp, fake[0]))
    assert pur["kinds"]["mtg/decks"]["d1"]["f"] == {} and pur["kinds"]["mtg/deckcards"]["d1|s1|main"]["cnt"] == {}
    out.append({"name": "snap_purged", "about": "deleted entries in a snap: no fields, counters only net (here 0); "
                "an older change of another device after the delete stays out", "ops": o + [old], "now": fake[0],
                "snap": pur})
    return out


def build():
    return {"about": "Vectors for the collection in the sync (docs/web/SYNC-LOGS.md). Times: µs/ms = floor(t*1e6 "
                     "resp. *1e3 + 0.5); prices whole cents; info/doc/item JSON text, carried as is.",
            "game": GAME, "kinds": list(synclogs.KINDS), "card_fields": list(synclogs.CARD),
            "sync_fields": list(synclogs.SYNC_FIELDS), "local_info": list(synclogs.LOCAL_INFO),
            "explode": explode_cases(), "ops": op_cases(), "snaps": snap_cases()}


def main():
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(data['explode'])} explode, {len(data['ops'])} ops, "
          f"{len(data['snaps'])} snaps")


if __name__ == "__main__":
    main()
