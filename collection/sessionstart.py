"""Start a new session – a short in-window flow instead of a session that is always running.

1. Which game?  2. What's happening? Open packs · buy singles · scan a trade · trade ticket
3. Depending on the kind: pack type, planned packs, paid, title – or for a ticket: load an image or scan by camera.
Started via app.MainWindow.start_session (switch game, set kind and info, enable the session).
"""
import games
from cards import packtypes
from ui import qdialogs
from system.i18n import tr

KINDS = (("cards", "Scan cards"), ("packs", "Opening boosters"), ("purchase", "Einzelkarten kaufen"),
         ("trade", "Tausch scannen"), ("ticket", "Tauschticket"))
HELP = {
    "cards": "All cards in one list – value, count and biggest hit, no packs.",
    "packs": "Jedes Pack wird einzeln gezählt (Pack-Wert, Ø pro Pack, Biggest Hit). Neues Pack: Taste N.",
    "purchase": "Gekaufte Einzelkarten – jede Karte zählt einzeln, keine Packs.",
    "trade": "Scanne die Karten, die du bekommst. Karten, die du weggibst, beim Scannen mit „Gebe ich weg“ "
             "markieren (Taste G) – beim Beenden wird beides gebucht.",
    "ticket": "Ein Tauschticket von deinem Gegenüber einlösen: als Bild (PNG/JPG aus WhatsApp & Co.) oder mit der "
              "Kamera vom Handy-Bildschirm.",
}


def open_wizard(ctrl):
    """Open the "New session" dialog (non-blocking)."""
    st = {"game": games.current().key, "kind": "cards", "pack": ctrl.session.info.get("pack_type") or packtypes.DEFAULT,
          "planned": 0, "paid": 0.0, "title": ""}

    def start(d):
        d.close("start")
        ctrl.start_session(st["game"], st["kind"], st["pack"], st["planned"], st["paid"], st["title"])

    def ticket(d, how):
        d.close("ticket")
        ctrl.start_ticket(st["game"], how)

    def pick(key, value, d):
        st[key] = value
        if key == "game":   # pack types depend on the game
            st["pack"] = packtypes.DEFAULT
        d.refresh()

    def build(ui, d):
        g_row = ui.row([ui.button(c["name"], lambda k=c["key"]: pick("game", k, d), active=st["game"] == c["key"])
                        for c in games.choices() if c["ready"]] + [ui.stretch()])
        k_row = ui.row([ui.button(tr(t), lambda k=k: pick("kind", k, d), active=st["kind"] == k) for k, t in KINDS]
                       + [ui.stretch()])
        items = [ui.label(tr("Game"), bold=True), g_row, ui.label(tr("What are you doing?"), bold=True), k_row,
                 ui.note(tr(HELP[st["kind"]]))]
        if st["kind"] == "ticket":
            items += [ui.row([ui.button(tr("Load image …"), lambda: ticket(d, "file"), active=True),
                              ui.button(tr("Scan with camera"), lambda: ticket(d, "camera")),
                              ui.button(tr("Cancel"), lambda: d.close(None)), ui.stretch()])]
            return ui.col(items, spacing=10)
        rows = []
        if st["kind"] == "packs":
            # pack types of the selected game (without singles types)
            was = games._current
            try:
                games._current = games.load(st["game"])
                opts = [(t["key"], tr(t["name"])) for t in packtypes.types(ctrl.settings)
                        if t["key"] not in packtypes.SINGLES]
            finally:
                games._current = was
            if st["pack"] not in dict(opts):
                st["pack"] = opts[0][0] if opts else packtypes.DEFAULT
            rows += [(tr("Pack type"), ui.combo(opts, st["pack"], lambda v: st.update(pack=v))),
                     (tr("Planned packs"), ui.spin(int(st["planned"]), 0, 999, lambda v: st.update(planned=v)))]
        if st["kind"] in ("packs", "purchase"):
            rows.append((tr("Paid"), ui.spin(float(st["paid"]), 0, 100000, lambda v: st.update(paid=v),
                                                decimals=2, suffix=" €")))
        rows.append((tr("Title (optional)"), ui.edit(st["title"], lambda t: st.update(title=t),
                                                     placeholder=tr("e.g. local shop"))))
        items += [ui.form(rows),
                  ui.row([ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                          ui.button(tr("Start log"), lambda: start(d), active=True)])]
        return ui.col(items, spacing=10)

    return qdialogs.show(tr("New log"), build, wait=False)
