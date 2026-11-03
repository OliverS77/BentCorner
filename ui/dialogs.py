"""Sheets of the scan workflow: manage pack types, end session. Moved from app.py (re-exported there)."""
from cards import packtypes
from system.i18n import tr
from ui import qdialogs
from ui.scanlook import eur


def pack_types_dialog(settings):
    """Manage pack types: rename, "counts as pack" on/off, create/delete custom types.
    -> new list or None (cancelled)."""
    items = [dict(t) for t in packtypes.types(settings)]
    st = {"new": ""}

    def add():
        name = st["new"].strip()
        if name:
            items.append({"key": packtypes.new_key({"pack_types": items}, name), "name": name, "counts": True,
                          "builtin": False})
            st["new"] = ""

    def build(ui, d):
        rows = []
        for i, t in enumerate(items):
            parts = [ui.edit(t["name"], lambda v, t=t: t.update(name=v.strip() or t["name"]), key=f"name{t['key']}",
                             live=lambda v, t=t: t.update(name=v.strip() or t["name"])),
                     ui.check(tr("counts as pack"), t["counts"], lambda on, t=t: t.update(counts=on))]
            if not t.get("builtin"):
                parts.append(ui.button("✕", lambda t=t: items.remove(t),
                                       tip=tr("Delete custom type (packs of this type then count as “Booster”)")))
            rows.append(ui.row(parts))
        new = ui.edit(st["new"], lambda v: (st.update(new=v), add()), key="new", live=lambda v: st.update(new=v),
                      placeholder=tr("Custom type, e.g. prerelease kit, Secret Lair drop …"))
        return ui.col([
            ui.note(tr("“counts as pack”: included in Ø value per pack, pack values and pack count – that's what the stats show by default. You can still switch each type on or off in the stats.")),
            ui.col(rows, spacing=6),
            ui.row([new, ui.button(tr("+ Add"), lambda: (d.form._drafts.pop("new", None), add()))]),
            ui.row([ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                    ui.button(tr("Apply"), lambda: d.close(items), primary=True)]),
        ], spacing=12)
    return qdialogs.show(tr("Pack types"), build, wide=760)


def end_session_dialog(stats, to_coll=True, note=""):
    """End session: cards into the collection? Save session? Create deck?
    -> (into the collection, save, as deck, as list) or None (cancelled)."""
    st = {"coll": bool(to_coll), "keep": True, "deck": False, "list": False}

    def build(ui, d):
        def question(text, key):
            return ui.row([ui.label(text, px=15),
                           ui.button(tr("Yes"), lambda: st.update({key: True}), checkable=True, checked=st[key]),
                           ui.button(tr("No"), lambda: st.update({key: False}), checkable=True,
                                     checked=not st[key])], spacing=8)   # switch with lamp: on = selected
        hint = [tr("The cards go into your collection.") if st["coll"] else
                tr("The cards do not go into your collection."),
                tr("The log stays under Logs & stats.") if st["keep"] else
                tr("The log is deleted (its packs don't count in the statistics).")]
        return ui.col([
            ui.label(tr(f"{stats['packs']} packs · {stats['cards']} cards · value {eur(stats['total'])}"),
                     color="gray"),
            question(tr("Add the scanned cards to your collection?"), "coll"),
            question(tr("Save the log (logs & statistics)?"), "keep"),
            question(tr("Create a deck from the cards (e.g. an opened precon)?"), "deck"),
            question(tr("Create an own list from the cards (Library → Lists)?"), "list"),
            ui.note(" ".join(hint)),
            ui.label(note, color="#d9b46a") if note else None,   # a trade log: what leaves the collection, no Undo
            ui.row([ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                    ui.button(tr("Confirm"), lambda: d.close((st["coll"], st["keep"], st["deck"], st["list"])),
                              primary=True)]),
        ], spacing=14)
    return qdialogs.show(tr("End log"), build, wide=760)
