"""The Settings sections as forms (qform) – built straight from settings and program state, without widgets.

build(key, ui, b) builds the section key; b = qsettings.SettingsBackend (b.ctrl = main window logic).
"""
import html
import os
import time

from PySide6 import QtCore, QtGui

from cards import currency
from system import i18n
from ui import look
from cards import conditions
from cards import shoplinks
from system.i18n import tr


def build(key, ui, b):
    fn = PAGES.get(key)
    return fn(ui, b) if fn else ui.col([])


# ---------- Helpers ----------
def _set(ctrl, key, value, after=None):
    ctrl.settings[key] = value
    ctrl.settings_changed()
    if after:
        after(value)


def _shop(ctrl, key, on):
    """Show or hide a marketplace in the "Marketplaces" button."""
    off = [k for k in ctrl.settings.get("shops_off") or [] if k != key]
    if not on:
        off.append(key)
    _set(ctrl, "shops_off", off)


def _check(ui, ctrl, text, key, tip="", after=None, enabled=True):
    return ui.check(tr(text), bool(ctrl.settings.get(key)), lambda on: _set(ctrl, key, bool(on), after), tip=tr(tip),
                    enabled=enabled)


def _spin(ui, ctrl, key, lo, hi, *, step=1, suffix="", decimals=0, tip="", enabled=True):
    return ui.spin(ctrl.settings[key], lo, hi, lambda v: _set(ctrl, key, v), step=step, suffix=suffix,
                   decimals=decimals, tip=tr(tip), enabled=enabled)


def _choice(ui, options, current, fn, *, tip="", enabled=True):
    """Choice: up to 4 values as a row of buttons (the chosen one bright, one click changes it – no dropdown),
    longer lists stay a dropdown (STREAMLINE §4, design rule "selection = brightness")."""
    opts = [o if isinstance(o, (list, tuple)) else (o, o) for o in options]
    if len(opts) <= 4 and enabled:
        # "Glide – all cards move to their new place": the button says "Glide", the explanation goes to the tooltip
        long = [str(lb) for _, lb in opts if " – " in str(lb) or " (" in str(lb)]
        short = [(v, str(lb).split(" – ")[0].split(" (")[0]) for v, lb in opts]
        return ui.seg(short, current, fn, tip="\n".join([tip] + long if tip else long))
    return ui.combo(opts, current, fn, tip=tip, enabled=enabled)


def _seg(ui, options, current, fn):
    """Row of buttons, the selected one highlighted (qform ui.seg)."""
    return ui.seg(options, current, fn)


def _fold(ui, b, key, title, items, *, note="", start=False):
    """Box that expands/collapses in place (no switch to another page)."""
    opened = b.state.setdefault("folds", {})
    on = opened.get(key, start)

    def toggle():
        opened[key] = not on
        b.form.soon()
    head = ui.row([ui.button(("▾  " if on else "▸  ") + title, toggle), ui.note(note) if note else None, ui.stretch()])
    return ui.col([head] + (items if on else []), spacing=10)


def _open_folder(path):
    path.mkdir(parents=True, exist_ok=True)
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))


# ========================================================================================================= Scan window
def page_scan(ui, b):
    import app
    ctrl = b.ctrl
    s = ctrl.settings
    cams = ctrl.cam_combo

    def pick_camera(i):
        cams.setCurrentIndex(i)
        ctrl.camera_selected()

    def set_resolution(v):
        _set(ctrl, "resolution", v)
        ctrl.res_combo.setCurrentText(v)
        ctrl.camera_selected()

    camera = ui.group(tr("Camera"), [ui.form([
        (tr("Device"), ui.row([ui.combo(list(enumerate(cams.items())) or [(0, tr("no camera"))],
                                       cams.currentIndex(), pick_camera, enabled=cams.count() > 0),
                              ui.button("↻", ctrl.fill_cameras, tip=tr("Reload camera list"))])),
        (tr("Image"), ui.row([
            ui.button(tr("Image controls …"), ctrl.open_cam_controls,
                      tip=tr("Focus, exposure, gain, sharpness, white balance, zoom – apply immediately and are saved for this camera. Tip: autofocus off and focus fixed on the distance to the card.")),
            ui.button(tr("Driver dialog …"), ctrl.camera.open_dialog,
                      tip=tr("Opens the camera driver's settings dialog (all of the manufacturer's controls).")),
            ui.stretch()])),
        (tr("Resolution"), ui.combo([("3840x2160", "3840 × 2160 (4K)"), ("2560x1440", "2560 × 1440"),
                                    ("1920x1080", "1920 × 1080 (Full HD)"), ("1280x720", "1280 × 720")],
                                   s["resolution"], set_resolution,
                                   tip=tr("Higher = sharper collector line (set, number, language), but needs more computing time. If the camera can't do it, it takes the next smaller one."))),
        (tr("Mirror"), ui.row([
            _check(ui, ctrl, "horizontal ↔", "mirror", "Tick if the text appears mirrored",
                   after=lambda v: setattr(ctrl.camera, "mirror", v)),
            _check(ui, ctrl, "vertical ↕", "mirror_v",
                   "Tick if the image is upside down (e.g. camera mounted overhead).\n"
                   "Both ticks = image rotated by 180°.", after=lambda v: setattr(ctrl.camera, "flip_v", v)),
            ui.stretch()])),
    ])])
    matching = ui.group(tr("Matches & confirmations"), [
        ui.note(tr("How sure must the recognition be before a card counts?")),
        ui.form([
            (tr("Minimum matches"), _spin(ui, ctrl, "min_inliers", 8, 100,
                                          tip="Höher = strenger (weniger Fehlerkennungen). Niedriger = erkennt auch "
                                              "schwierige Karten.")),
            (tr("Confirmations"), _spin(ui, ctrl, "stable", 1, 10,
                                        tip="How often in a row the same card must be recognized")),
        ]),
        ui.note(tr("Minimum matches: how many image features have to match. Confirmations: how many times in a row the same card has to be recognized. Higher = fewer mistakes, but slower.")),
        _check(ui, ctrl, "Scan hints (glare, too dark, blurry)", "scan_hints",
               "Wird eine Karte länger nicht erkannt, steht in der Statuszeile, woran es liegen könnte – "
               "beurteilt über mehrere Kamerabilder."),
    ])
    # Preview: mini scan page (camera image + overlay, 16:9, clickable) – or for setting up the scan frames
    mode = s.get("scan_preview") or "stream"
    frame = mode == "frame"
    preview = ui.col([
        ui.row([_seg(ui, [("stream", tr("Stream preview")), ("frame", tr("Set up scan frame"))], mode,
                     lambda v: _set(ctrl, "scan_preview", v)), ui.stretch(),
                ui.button(tr("Leave preview → Scanning"), lambda: ctrl.stream.show_page("scan"),
                          primary=True)]),
        ui.camera("preview" if frame else "overlay"),
        ui.label(ctrl.status.text(), px=15, bold=True),
        ui.note(tr("Drag the scan frame with the mouse · wheel = size · Ctrl+wheel = zoom · right mouse button = move the view") if frame else
                tr("This is what the stream looks like right now – clicks work like on the Scanning page (e.g. ⚙ on the info blocks).")),
    ], spacing=8)

    timing = ui.group(tr("Hits and cards"), [ui.form([
        (tr("Hit from"), _spin(ui, ctrl, "hit", 0.5, 1000, step=1, suffix=" €", decimals=2,
                             tip="Hit animation from this price")),
        (tr("Keep card visible"), _spin(ui, ctrl, "hold", 1, 60, suffix=" s", enabled=not s["hold_forever"],
                                          tip="So lange bleibt die letzte Karte stehen, nachdem sie aus dem Rahmen "
                                              "genommen wurde")),
        (None, _check(ui, ctrl, "permanently (until the next card)", "hold_forever")),
        (None, _check(ui, ctrl, "Sounds while scanning", "scan_sounds",
                      tip="Ein kurzer Ton bei jeder gescannten Karte, ein anderer bei einem Hit (ab „Hit ab“) "
                          "und ein besonderer ab 50 €")),
    ])])
    # two columns that stack independently (no gaps): left preview + camera + recognition, right hits and cards
    return ui.col([
        ui.row([ui.col([preview, camera] + ([phone_camera_group(ui, ctrl)] if ctrl.PHONE_CAMERA else []),
                       spacing=14, w=6),
                ui.col([timing, ui.note(tr("Log name, what you paid and – when opening boosters – the pack type are set right on the scan page (log tile) – they belong to the log."))], spacing=14, w=4)],
               spacing=14),
        matching,
    ], spacing=14)


def _scan_data_group(ui, ctrl):
    from scanner import scandata
    return ui.group(tr("Scan data – to make recognition better"), [
        ui.note(tr("When you correct a misrecognized card, only the crop of that card is saved (no camera image) plus a line saying what was recognized and what is right. At most 20 MB – stays on this computer until you click “Send”.")),
        _check(ui, ctrl, "Collect misrecognized cards", "scan_data"),
        ui.row([ui.label(ctrl.scandata_info.text()),
                ui.button(tr("View"), lambda: _open_folder(scandata.DIR), tip=tr("Open the folder with the crops")),
                ui.button(tr("Send …"), ctrl.scandata_zip,
                          tip=tr("For now: save as a ZIP file and pass it on yourself (later directly to Bent°Corner)")),
                ui.button(tr("Delete"), ctrl.scandata_clear, tip=tr("Delete all collected scan data"))]),
    ])


# ========================================================================================================== Collection
def page_collection(ui, b):
    from collection.collection import LANGS
    ctrl = b.ctrl
    s = ctrl.settings

    def set_currency(code):
        _set(ctrl, "currency", code)
        currency.set_current(code)
        ctrl.currency_changed()
        if code != "EUR":
            from ui.librarycore import run_async
            run_async(ctrl, currency.refresh, lambda res, err: ctrl.currency_changed())

    def set_card_lang(code):
        _set(ctrl, "card_lang", code)
        ctrl.session.default_lang = code

    rate = ctrl.cur_info.text()
    return ui.col([
        # one line: the language breakdown ("EN 13 · DE 2", after <br>) goes to the tooltip
        ui.row([ui.label(ctrl.coll_info.text().split("<br>")[0], rich=True, fixed=True,
                         tip=(ctrl.coll_info.text().split("<br>") + [""])[1]),
                ui.button(tr("Open library  (B)"), ctrl.open_library, primary=True), ui.stretch()]),
        ui.row([ui.group(tr("Display"), [ui.form([
            (tr("My currency"), _choice(ui, [(c, f"{c}  ·  {sym}  ·  {tr(n)}") for c, sym, n in currency.CURRENCIES],
                                           s["currency"], set_currency)),
            ("", ui.note(rate)) if rate else None,
            (tr("My main shop"), _choice(ui, [("auto", tr("Automatic")),
                                              ("cardmarket", "Cardmarket"), ("tcgplayer", "TCGplayer")],
                                             s.get("main_shop") or "auto",
                                             lambda k: (_set(ctrl, "main_shop", k), ctrl.condition_scale_changed()),
                                             tip=tr("Automatic: euro/German Cardmarket, otherwise TCGplayer.") + " " + tr("Comes first in the shop links and sets the condition scale “Same as my shop”. Prices themselves come from the best source per game (Cardmarket or TCGplayer)."))),
            (tr("Default language"), _choice(ui, [(c, f"{short} · {name}") for c, short, name in LANGS], s["card_lang"],
                                              set_card_lang,
                                              tip=tr("Language of newly scanned cards; the library's detail view opens cards in this language (if the printing exists in it)."))),
            (tr("Condition"), _choice(ui, [(k, tr(lb)) for k, lb in conditions.SCALES], s.get("cond_scale") or "auto",
                                     lambda k: (_set(ctrl, "cond_scale", k), ctrl.condition_scale_changed()),
                                     tip=tr("Scale for your cards' condition – like Cardmarket (7 steps) or TCGplayer (5 steps). Converted roughly as usual; prices are always for Near Mint."))),
            ("", ui.note(tr("Prices are always Near Mint prices – the condition doesn't change them."))),
            (tr("Condition when scanning"), _choice(ui, [("near_mint", "Near Mint"), ("mint", "Mint")],
                                                  s.get("cond_default") or "near_mint",
                                                  lambda k: _set(ctrl, "cond_default", k),
                                                  tip=tr("New cards come in like this – click the abbreviation in the scan list (or press Z) to cycle."))),
            (None, _check(ui, ctrl, "Show card names in the card's language", "printed_names",
                          "While scanning and in the logs: e.g. “Das Schicksal des Sonnen-Gespinsts” instead of “Fate "
                          "of the Sun-Cryst DE”. Off: always the English name with a language code.",
                          after=lambda _: ctrl.stream.view.update())),
            (None, _check(ui, ctrl, "when ending a log: cards preselected for the collection",
                          "collection_auto", "Default in the “End log” dialog")),
            (None, _check(ui, ctrl, "Show MTGO price (Tix)", "show_tix",
                          "Price on Magic Online (digital cards) in the detail view – irrelevant for paper cards")),
            (tr("Marketplaces"), ui.row([ui.check(lb, k not in (ctrl.settings.get("shops_off") or []),
                                                 lambda on, k=k: _shop(ctrl, k, on))
                                        for k, lb in shoplinks.available(ctrl.settings)] + [ui.stretch()], spacing=14)),
        ])]), ui.col([
        ui.group(tr("Export"), [
            ui.note(tr("CSV for ManaBox, Moxfield, Deckbox or Excel – in the Import/Export tab.")),
            ui.row([ui.button(tr("Export collection …"), lambda: ctrl.go_export("coll_export")), ui.stretch()])]),
        ], spacing=12)], spacing=12),
        _prices_group(ui, ctrl),
        ui.note(ctrl.coll_msg.text()) if ctrl.coll_msg.text() else None,
    ], spacing=12)


def _price_history(ui, ctrl):
    return [
        ui.check(tr("Save price history (Cardmarket & TCGplayer)"), ctrl.ph_check.isChecked(),
                 lambda on: (ctrl.ph_check.setChecked(on), ctrl.toggle_price_history(on)),
                 tip=tr("Loads the prices of the last 90 days from MTGJSON (about 60 MB download, about 50 MB on disk) and then the new prices once a day (about 4 MB). The detail view shows a history chart under “Prices”.")),
        ui.row([ui.note(ctrl.ph_info.text()),
                ui.button(tr("Reload completely"),
                          lambda: ctrl.enqueue("pricehist", "ph", label="€", name=tr("Price history")),
                          tip=tr("Load the last 90 days from MTGJSON again"))
                if ctrl.ph_btn.isVisible() else None]),
    ]


def _prices_group(ui, ctrl):
    import app
    import games
    from system import orbit
    s = ctrl.settings
    if not orbit.prices_on(s):   # Orbit's Core: no prices are fetched – the way to Near Orbit
        return ui.group(tr("Prices"), [
            ui.note(tr("Core: Bent°Corner fetches no prices. Prices, marketplaces and price alerts come with Near Orbit.")),
            ui.row([ui.button(tr("Bent°Corner Orbit …"), lambda: ctrl.show_settings("privacy")), ui.stretch()])])
    if games.current().price_source == "daily":   # Cardmarket price list + TCGplayer (TCGCSV), history automatic
        return ui.group(tr("Prices"), [
            ui.label(tr("Update prices (Cardmarket trend & TCGplayer market, all cards):")),
            ui.row([_choice(ui, app.PRICE_MODES, s["price_update"], lambda v: _set(ctrl, "price_update", v)),
                    ui.button(tr("Update prices"), ctrl.update_all,
                              tip=tr("Cardmarket's official daily price guide (one file, ~16 MB) and TCGplayer via TCGCSV (one daily file from the Bent°Corner server). Once a day at most. The price history grows by one point every day.")), ui.stretch()]),
            ui.note(tr("This setting applies to all games.")),
            ui.line(),
            ui.row([ui.note(tr("You set price alerts in Orbit – on lists and on single cards.")),
                    ui.button(tr("Price alerts …"), ctrl.show_alarms)]),
        ])
    return ui.group(tr("Prices"), [
        ui.label(tr("Update prices (Cardmarket trend & TCGplayer market, all cards):")),
        ui.row([_choice(ui, app.PRICE_MODES, s["price_update"], lambda v: _set(ctrl, "price_update", v)),
                ui.button(tr("Update prices"), ctrl.update_all,
                          tip=tr("One download from MTGJSON (~4 MB) with today's prices of all cards: Cardmarket trend (€) and TCGplayer market ($).\nUpdates sets, collection, library and – if enabled – the price history.")), ui.stretch()]),
        ui.line(),
    ] + _price_history(ui, ctrl) + [
        ui.line(),
        ui.row([ui.note(tr("You set price alerts in Orbit – on lists and on single cards.")),
                ui.button(tr("Price alerts …"), ctrl.show_alarms)]),
    ])


# ================================================================================================== Sets & card data
def lang_pack(ctrl):
    """Language pack of the open game -> (on?, status, button text, function). Button "" = nothing to do (Pokémon:
    built into the bundled database)."""
    from cards import carddb
    import games
    st = carddb.status()
    if games.current().lang_pack == "bundled":
        return True, tr("built into this game – cards in other languages are separate prints and can't be split off"), "", None
    has = bool(st and st["langs"])
    # Magic: all languages come with the game data (package) – no separate language pack to load/remove anymore
    if has:
        return True, tr(f"all languages included · {st['langs']:,} prints").replace(",", "."), "", None
    return False, tr("comes with the game's data"), "", None


def _carddata_group(ui, ctrl):
    """Card data of the open game – the same rows for every game: "Card data" (required, update only)
    and "Languages" (always included). The first-run setup (onboarding.py) loads everything along – if something
    changes here, adjust it there too."""
    import games
    g = games.current()
    busy = (ctrl.current or {}).get("kind") == "carddb" or any(j["kind"] == "carddb" for j in ctrl.jobs)

    def line(title, text, buttons, dim=False):
        color = "gray" if dim else ""
        return ui.row([ui.label(f"<b>{html.escape(title)}</b><br><span style='color:gray'>{html.escape(text)}</span>",
                                rich=True, color=color), ui.stretch()] + buttons)
    rows = [line(tr("Card data"), ctrl.db_info.text() + " · " + tr("required, can't be turned off"),
                 [ui.button(tr("Refresh"), lambda: ctrl.enqueue("carddb", "db"), enabled=not busy,
                            tip=tr("Download all cards again and rebuild the searchable database. Library and search then work without internet."))])]
    has, text, _btn, _fn = lang_pack(ctrl)   # all languages belong to the game's data – nothing to choose
    rows.append(line(tr("Languages"), text, [], dim=not has))
    if g.key == "mtg":   # set list for search (Scryfall) – reachable for everyone, not only with old set downloads
        import app
        rows.append(ui.row([ui.label(f"<b>{html.escape(tr("Set list for search"))}</b>", rich=True), ui.stretch(),
                            _choice(ui, app.CATALOG_MODES, ctrl.settings["catalog_update"],
                                     lambda v: _set(ctrl, "catalog_update", v)),
                            ui.button(tr("Update set list"), lambda: ctrl.load_catalog(0, manual=True),
                                      tip=tr("Reloads the list of all sets from Scryfall (about 1 s) so new sets show up in search."))]))
    return ui.group(tr(f"Card data · {g.name}"), rows + [
        ui.note(tr("The same for every game – switch the game to see its card data."))])


def page_sets(ui, b):
    import app
    ctrl = b.ctrl
    s = ctrl.settings

    db = _carddata_group(ui, ctrl)

    store = ctrl.image_store
    rows = []
    for key, title, text, info in store.rows():
        parts = [ui.label(f"<b>{title}</b> <span style='color:gray'>· {info}</span>", tip=text)]
        if key == "cache":
            parts += [ui.label(tr("at most"), fixed=True),
                      ui.spin(int(s.get("image_cache_mb", 1000)), 50, 50000, store.set_limit, step=100, suffix=" MB",
                              tip=tr("Limit for the cache. Checked at start and every 30 minutes; the oldest images are deleted."))]
        if key != "sets":
            parts.append(ui.button(tr("Delete"), lambda k=key: store.delete_groups([k])))
        rows.append(ui.row(parts))
    images = ui.group(tr("Card images"), [
        ui.note(tr("All card images are in data/card-images. They are loaded and saved when you look at a card.")),
        ui.col(rows, spacing=6),
        ui.row([ui.note(store.total()),
                ui.button(tr("Delete everything except sets"),
                          lambda: store.delete_groups(["library", "sessions", "cache"])),
                ui.button("↻", store.refresh, tip=tr("Recount"))]),
    ])

    # --- Sets: queue, list of sets already loaded ---
    queue = [ui.row([ui.label(f"<b>{e['label'].upper()}</b> {html.escape(e['name'])} "
                              f"<span style='color:gray'>· {e['state']}</span>"),
                     ui.label(e["est"], color="gray", fixed=True),
                     ui.button("✕", lambda j=e["job"]: ctrl.cancel_job(j), tip=tr("Cancel"))])
             for e in ctrl.queue_view()]
    prog = ctrl.progress
    progress = ui.progress(prog.value(), prog.minimum(), prog.maximum(), prog.text()) \
        if prog.isVisible() else None
    entries = []
    for e in ctrl.sets_view():
        if e["kind"] == "group":
            n, root = len(e["codes"]), e["root"]
            entries.append(ui.row([
                ui.button("▾" if e["expanded"] else "▸", lambda r=root: ctrl.toggle_group(r),
                          tip=tr("Click to expand/collapse")),
                ui.check("", e["n_on"] == n, lambda on, c=e["codes"], k=e["n_on"] < n: ctrl.set_enabled(c, k),
                         tip=tr("All sets of this group on/off")),
                ui.label(f"<b>{root.upper()}</b>&nbsp; {html.escape(e['title'])} "
                         f"<span style='color:gray'>· {tr(str(n) + ' Sets')} · {e['n_on']} {tr("active")}</span>"),
                ui.label(tr(f"≈ {e['ram']}"), fixed=True, tip=tr("Memory of the enabled sets in this group")),
                ui.button(tr("↻"), lambda c=sorted(e["codes"]): [ctrl.enqueue("update", x) for x in c],
                          tip=tr(f"Update prices of all {root.upper()} sets")),
                ui.button("✕", lambda r=root, ss=e["sets"]: ctrl.remove_group(r, ss),
                          tip=tr(f"Remove all {root.upper()} sets")),
            ]))
        else:
            st = e["set"]
            code = st["code"]
            entries.append(ui.row(([ui.label("&nbsp;" * 8, fixed=True)] if e["indent"] else []) + [
                ui.check("", e["on"], lambda on, c=code: ctrl.set_enabled({c}, on),
                         tip=tr("Set on/off for SCAN (off = no memory used, stays saved)")),
                ui.label(f"<b>{code.upper()}</b>&nbsp; {html.escape(st['name'])}<br>"
                         f"<span style='color:gray'>{e['sub']}</span>", tip=e["tip"],
                         color="" if e["on"] else "gray"),
                ui.label(e["ram"], fixed=True),
                ui.button(tr("↻"), lambda c=code: ctrl.enqueue("update", c),
                          tip=tr(f"Update prices and card list of {code.upper()}")),
                ui.button("✕", lambda x=st: ctrl.remove_set(x), tip=tr(f"Remove {code.upper()}")),
            ]))
    if ctrl.set_filter.strip() and not entries:
        entries.append(ui.note(tr("No downloaded sets found.")))

    def set_filter(t):
        ctrl.set_filter = t

    sets = ui.group(tr("Sets"), [
        ui.row([ui.button(tr("Update the sets' card lists"), ctrl.update_lists,
                          tip=tr("Asks Scryfall for newly released cards of each loaded set (e.g. during spoiler season) and downloads their images.\nAbout 1.5 s per set. Not needed for prices.")),
                ui.stretch()]),
        ui.note(tr("Downloading sets (offline use) is off for now – SCAN° recognizes all cards anyway. Sets you already loaded stay here.")),
        progress,
        ui.label(ctrl.data_info.text()) if ctrl.data_info.text() else None,
        ui.col(queue, spacing=6) if queue else None,
        ui.label(ctrl.set_total.text(), rich=True),
        ui.edit(ctrl.set_filter, set_filter, key="setfilter", live=set_filter,
                placeholder=tr("Filter downloaded sets …")) if ctrl.installed else None,
        ui.col(entries, spacing=6) if entries else None,
    ], )
    # Overview: status + action per box; "Settings ▸" expands the details right below
    detail = {"db": db, "sets": sets, "images": images}   # price history: only under Collection & prices
    opened = b.state.setdefault("offline_open", set())
    rows = []
    tiles = []
    for key, title, ok, state, desc, btn, fn in offline_rows(ctrl):
        def toggle(k=key):
            (opened.discard if k in opened else opened.add)(k)
            b.form.soon()
        tiles.append((key, ui.group("", [ui.col([
            ui.label(f"<b>{title}</b>", px=14),
            ui.label(("● " if ok else "○ ") + state, color="" if ok else "gray"),
            ui.note(desc),
            ui.row([ui.button(btn, fn) if btn else None,
                    ui.button(("▾  " if key in opened else "▸  ") + tr("Settings"), toggle,
                              active=key in opened) if key in detail else None,
                    ui.stretch()])], spacing=4)])))
    for i in range(0, len(tiles), 2):
        pair = tiles[i:i + 2]
        rows.append(ui.row([t for _, t in pair], spacing=14))
        rows += [detail[k] for k, _ in pair if k in opened and k in detail]   # expands right below its box
    return ui.col([ui.label(tr("Searching and scanning run on your computer once the game's data is loaded. Card images come from the internet when you look at them and stay saved. Everything is in the <b>data</b> folder next to the program."))] + rows, spacing=12)


# ============================================================================================================= Display
def page_display(ui, b):
    from collection.collection import LANGS
    from ui.librarycore import display
    ctrl = b.ctrl
    disp = display(ctrl.settings)

    def rarity(on):
        _set(ctrl, "rarity_colors", bool(on))
        look.RARITY_NAMES = bool(on)
        for host in (getattr(ctrl, "library_win", None), getattr(ctrl, "sess_host", None)):
            if host is None:
                continue
            for panel in host.detail_panels():
                if panel.row is not None:
                    panel.fill_text()
        lib = getattr(ctrl, "library_win", None)
        if lib is not None:
            lib.refresh(keep=True)

    def save(key, value):
        d = dict(ctrl.settings.get("display") or {})
        d[key] = value
        _set(ctrl, "display", d)
        libs = [getattr(ctrl, "library_win", None)]
        page = getattr(ctrl, "trade_page", None)
        if page is not None and hasattr(page, "libraries"):
            libs += list(page.libraries())
        for lib in libs:
            if lib is not None:
                lib.refresh(keep=True)

    from system import hwinfo
    from ui import morph
    from ui import perf
    from app import PAGE_ANIMS

    def _perf_hints(ui):
        """Honest notes instead of a pop-up: no graphics driver / the UI often stutters in this session."""
        from ui import lagwatch
        out = []
        if os.environ.get("QT_QUICK_BACKEND") == "software":
            out.append(ui.label(tr("No graphics driver found – the interface is drawn in software. With your graphics card's driver Bent°Corner runs more smoothly.")))
        if (perf.level() != "performance" and lagwatch.started is not None
                and lagwatch.stalls_since(lagwatch.started + 60) >= 3):
            out.append(ui.label(tr("The interface stuttered several times this session – “Performance” might help.")))
        return out

    def set_perf(level):
        _set(ctrl, "perf_level", level)
        perf.set_level(level)
        b.form.soon()
    hw = hwinfo.read()
    anim = ui.group(tr("Animations & performance"), [ui.form([
        (tr("Performance"), ui.col([_seg(ui, perf.LEVELS, perf.level(), set_perf),
                                 ui.label(tr(perf.HELP[perf.level()])),
                                 *_perf_hints(ui),
                                 ui.label(tr("Detected: ") + hwinfo.summary(hw) + "  →  " + tr("Suggested: ")
                                          + dict(perf.LEVELS)[perf.detect(hw)], color="gray", px=11,
                                          tip=tr("Read on this computer only, to set up the animations – nothing of it is sent anywhere."))])),
        (tr("Rearranging"), _choice(ui, [(k, tr(lb)) for k, lb in morph.STYLES],
                                     ctrl.settings.get("anim_style") or "glide",
                                     lambda v: _set(ctrl, "anim_style", v),
                                     tip=tr("How the library cards rearrange when the detail view opens or closes – takes effect on the next click."))),
        (tr("Speed"), _choice(ui, [(f, tr(lb)) for f, lb in morph.SPEEDS],
                                         min((f for f, _ in morph.SPEEDS),
                                             key=lambda f: abs(f - float(ctrl.settings.get("anim_speed") or 1.0))),
                                         lambda v: _set(ctrl, "anim_speed", v),
                                         tip=tr("For a close look: slow transitions down a lot."))),
        (tr("Page change"), _choice(ui, [(k, tr(lb)) for k, lb in PAGE_ANIMS],
                                       ctrl.settings.get("page_anim") or "flip",
                                       lambda v: _set(ctrl, "page_anim", v),
                                       tip=tr("How pages change when you click the bar at the top – the direction depends on whether you click right or left of the current page."))),
    ])])
    return ui.col([ui.row([
        ui.group(tr("Cards"), [
            ui.check(tr("Rarity as the color of the card name"), bool(ctrl.settings.get("rarity_colors")), rarity),
            ui.note(tr("Off (default): everything in shades of gray. On: card names everywhere – library, deck builder, detail view – appear in the color of their rarity (common, uncommon, rare, mythic). Set the colors themselves in Appearance.")),
        ]),
        ui.group(tr("Tiles in library and trade"), [ui.form([
            (None, ui.check(tr("Group the same printing (other language or foil = chips on the card)"),
                            disp["group_prints"], lambda on: save("group_prints", on))),
            (None, ui.check(tr("Group the same card across sets"), disp["group_sets"],
                            lambda on: save("group_sets", on),
                            tip=tr("One tile per card name – all sets are listed below it, the detail view shows your own printings"))),
            (tr("Show chips"), _seg(ui, [("count", tr("count only")), ("foil", tr("count + foil")),
                                           ("lang", tr("count + foil + language"))], disp["chips"],
                                      lambda v: save("chips", v))),
            (tr("At most"), _seg(ui, [(1, tr("1 chip")), (3, tr("3 chips")), (5, tr("5 chips"))], disp["chip_max"],
                                   lambda v: save("chip_max", v))),
            (None, _check(ui, ctrl, "Show condition on the tiles", "cond_chip",
                          "Umrandetes Kästchen unten links im Bild (z. B. „LP“ oder „PSA 10“) – nur bei Karten, die "
                          "nicht Near Mint sind", after=lambda _: ctrl.condition_scale_changed())),
            (tr("Below the name"), _seg(ui, [("set", tr("Set")), ("setnum", tr("Set + number"))], disp["set_line"],
                                         lambda v: save("set_line", v))),
            (tr("With several languages"),
             _choice(ui, [(c, f"{short} · {name}") for c, short, name in LANGS]
                      + [("most", tr("the one I have most of"))], disp["show_lang"],
                      lambda v: save("show_lang", v),
                      tip=tr("If you own a card in several languages, the tile shows this one – if you have it"))),
        ])]),
    ], spacing=14), anim], spacing=14)


# =========================================================================================================== Appearance
def page_appearance(ui, b):
    """Skin: base look, fonts, colors, corners (animations & performance are under Display).
    Changes take effect immediately (colors are passed to QML again)."""
    ctrl = b.ctrl
    cfg = look.cfg
    st = b.state

    def changed(restart=False):
        look.save(ctrl.settings)
        ctrl.settings_changed()
        if restart:
            st["restart"] = True
        b.shell_theme()

    def set_look(key):
        if cfg.get("look") != key:
            cfg["look"] = key
            look._build_color_map()
            changed(restart=True)

    def set_font(key, family):
        cfg[f"font_{key}"] = look.resolve_family(family, cfg[f"font_{key}"])
        changed()

    def add_fonts():
        from ui import qdialogs
        paths = qdialogs.open_files(tr("Add font"), "", tr("Fonts (*.ttf *.otf *.zip)"))
        if not paths:
            return
        try:
            fams = look.import_fonts(paths)
        except Exception as e:  # noqa: BLE001
            st["font_msg"] = tr(f"Could not be loaded: {e}")
            return
        st["font_msg"] = (tr("Added: ") + ", ".join(fams) + tr(" – now selectable above.")) if fams else \
            tr("No font files found (.ttf/.otf, also inside .zip).")

    def pick_color(key, skin=False):
        from ui import qdialogs
        cur = look.skin_color(key) if skin else look.color(key)
        c = qdialogs.get_color(cur, tr("Choose color"))
        if c:
            look.set_skin_color(key, c)
            changed(restart=not skin and key != "bg")

    def reset_color(key):
        look.set_skin_color(key, None)
        changed()

    def set_radius(kind, value=None, unit=None):
        v, u = look.group(kind)
        cfg[f"radius_{kind}"] = float(v if value is None else value)
        cfg[f"radius_{kind}_unit"] = u if unit is None else unit
        changed()

    def reset_all():
        from ui import qdialogs
        if not qdialogs.question(tr("Skin"),
                                 tr("Reset fonts, size, corners and colors to the defaults?"),
                                 yes=tr("Reset"), no=tr("Cancel"), danger=True):
            return
        cfg.clear()
        cfg.update(dict(look.DEFAULTS, colors={}, elements={}, elements_saved={}, skin={}, fx={}, pages={}))
        look._build_color_map()
        look.set_background(None)
        changed(restart=True)

    def confirm():
        if st.get("restart"):
            ctrl.restart()
            return
        look.save(ctrl.settings)
        if hasattr(ctrl, "save_settings"):
            ctrl.save_settings()
        st["done_msg"] = time.time()

    fams = sorted(set(QtGui.QFontDatabase.families()))

    def font_row(key, label):
        return (label, _choice(ui, fams, cfg[f"font_{key}"], lambda f, k=key: set_font(k, f)))

    def color_row(key, label, skin=False):
        val = look.skin_color(key) if skin else (look.background() if key == "bg" else look.color(key))
        return (ui.label(tr(label), wrap=False),
                ui.row([ui.swatch(val, lambda k=key: pick_color(k, skin)),
                        ui.label(val, color="gray", fixed=True),
                        ui.button("↺", lambda k=key: reset_color(k), tip=tr("Default")), ui.stretch()]))

    def radius_row(kind, label):
        v, u = look.group(kind)
        return (label, ui.row([ui.spin(v, 0, 100, lambda x, k=kind: set_radius(k, value=x), step=0.5, decimals=1),
                               _choice(ui, ["%", "px"], u, lambda x, k=kind: set_radius(k, unit=x)), ui.stretch()]))

    skin_keys = [k for k, _, _ in look.SKIN_COLORS if not k.startswith("bg_")]  # Section backgrounds: old pages only
    look_seg = _seg(ui, [(k, tr(n)) for k, n in look.LOOKS], look.look(), set_look)
    disp = look.display_font().family()
    preview = ui.group(tr("Preview"), [
        ui.label("Sheoldred, the Apocalypse", px=26, font=disp),
        ui.label("259,79 €  ·  +64 %", px=30, bold=True, font=disp),
        ui.label(tr("Whenever you draw a card, you gain 2 life. – Normal text in the interface, tables, descriptions.")),
        ui.row([ui.button(tr("Button"), lambda: None), ui.button(tr("Active"), lambda: None, primary=True),
                ui.stretch()]),
    ])
    done = time.time() - st.get("done_msg", 0) < 3
    note = tr("Base look changed – applies everywhere after a restart.") if st.get("restart") else \
        (tr("✓ Applied and saved.") if done else "")
    return ui.col([
        ui.note(tr("Everything here is your skin – change it, see it right away.")),
        ui.row([ui.label(tr("Base look"), bold=True, fixed=True), look_seg]),
        ui.row([ui.col([
        ui.group(tr("Fonts"), [
            ui.form([font_row("text", tr("Text")), font_row("display", tr("Headings & numbers"))]),
            ui.row([ui.button(tr("Add font …"), add_fonts),
                    ui.label(f"<a href='https://fonts.google.com'>{tr("Find fonts (Google Fonts)")}</a>",
                             tip=tr("Pick a font there, click “Download family” and add the ZIP file here. All Google Fonts are free to use.")), ui.stretch()]),
            ui.note(st.get("font_msg", "")) if st.get("font_msg") else None,
            preview,
        ]),
        ui.group(tr("Corners"), [ui.form([radius_row("ctrl", tr("All controls")),
                                        radius_row("panel", tr("All surfaces"))])]),
        ], spacing=12),
        ui.col([
            ui.group(tr("Colors"), [ui.form([color_row(k, lb) for k, lb, _ in look.PALETTE])]),
            ui.group(tr("Card names & mana"), [ui.form([color_row(k, look.skin_label(k), skin=True)
                                                         for k in skin_keys])]),
        ], spacing=12)], spacing=14),
        ui.row([ui.label(note, color="gray"),
                ui.button(tr("Restore defaults"), reset_all, danger=True),
                ui.button(tr("Restart & apply") if st.get("restart") else tr("Confirm"), confirm,
                          primary=True)]),
    ], spacing=12)


# ========================================================================================================= Offline use
_COUNTS = {}
_counting = set()
_count_done = []   # [QObject with a signal]: created in the main thread, a finished count reports back through it


def _cached_count(key, compute, ttl=60):
    """Count over many files (collection images, card details) at most once per minute – the page rebuilds
    on every progress step during downloads, and every exists() costs time (stuttered while loading). Counted in
    the background (1900 files: ~120 ms in the main thread, more in a cloud folder) -> the last count, or None
    while the first one runs; the page refreshes when it is done."""
    now = time.monotonic()
    hit = _COUNTS.get(key)
    if (hit is None or now - hit[0] > ttl) and key not in _counting:
        if not _count_done:
            class _Done(QtCore.QObject):
                done = QtCore.Signal()
            _count_done.append(_Done())
            from ui import qstate
            _count_done[0].done.connect(qstate._changed)   # queued: arrives in the main thread
        _counting.add(key)

        def work():
            try:
                _COUNTS[key] = (time.monotonic(), compute())
            except Exception:  # noqa: BLE001 – a count is only a hint
                _COUNTS[key] = (time.monotonic(), hit[1] if hit else 0)
            finally:
                _counting.discard(key)
            _count_done[0].done.emit()
        import threading
        threading.Thread(target=work, name="settings-count", daemon=True).start()
    return hit[1] if hit else None


def offline_rows(ctrl):
    """-> [(key, title, ok?, status, description, button text, function)]."""
    from cards import carddb
    from cards import library
    from cards import pricehist

    def mb(n):
        return f"{n / 1e6:.0f} MB".replace(".", ",") if n >= 1e6 else f"{n / 1e3:.0f} KB"
    out = []
    st = carddb.status()
    import games
    out.append(("db", tr("Card database"), bool(st),
                tr(f"loaded · {st['cards']:,} cards · as of {time.strftime('%d.%m.%Y', time.localtime(st['updated']))} · {mb(st['size'])}").replace(",", ".") if st
                else tr("not loaded – comes with the game's data"),
                tr(games.current().data_note),   # per game: where the data comes from
                tr("Download"), lambda: ctrl.enqueue("carddb", "db")))
    # Language pack: the same tile for every game (Pokémon: built in, no button)
    has, state, btn, fn = lang_pack(ctrl)
    out.append(("langs", tr("Languages"), has, state,
                tr("Search and scanner know the cards in all languages (e.g. German, Japanese) – part of the game's data, nothing extra to load."), "", None))
    inst = ctrl.installed
    if inst:   # only for sets already loaded (downloading is off for now)
        out.append(("sets", tr("Sets for SCAN°"), bool(inst),
                tr(f"{len(inst)} sets downloaded · {sum((s['count'] for s in inst))} cards recognizable · {mb(sum((s['disk'] for s in inst)))}") if inst else tr("no sets downloaded yet"),
                tr("Not needed for scanning – SCAN° recognizes all cards. Sets you already loaded stay here."),
                "", None))
    items = ctrl.collection.items
    have = _cached_count(("img", id(items), len(items)),
                         lambda: sum(1 for it in items if (library.BASE / it["img"]).exists()))
    out.append(("images", tr("Collection images"), bool(items) and have == len(items),
                (tr(f"{have} of {len(items)} images saved") if have is not None else tr("counting …"))
                if items else tr("Collection is empty"),
                tr("Card images are loaded and saved when you look at a card."), "", None))
    import games
    if games.current().price_source == "daily":   # loadable price history and Scryfall details: only "mtgjson"
        out.append(("rates", tr("Exchange rates"), True,
                    currency.rate_info() or tr("Shown in euro – no conversion needed"),
                    tr("Exchange rates (ECB) are saved daily."), "", None))
        return out
    ph = pricehist.status()
    on = bool(ph and ctrl.settings.get("price_history"))
    out.append(("hist", tr("Price history"), on,
                tr(f"on · {ph['cards']:,} cards · as of {pricehist.date_of(ph['updated']).strftime('%d.%m.%Y')} · {mb(ph['size'])}").replace(",", ".") if on else tr("off"),
                tr("Cardmarket and TCGplayer history of the last 90 days, updated daily. Optional."),
                tr("Collection & prices →"), lambda: ctrl.show_settings("collection")))
    n_full = _cached_count(("full",), lambda: sum(1 for _ in library.FULL.glob("*.json")) if library.FULL.exists() else 0)
    out.append(("details", tr("Card details from Scryfall"), bool(n_full),
                tr(f"{n_full} cards with details saved") if n_full is not None else tr("counting …"),
                tr("Rulings, all printings, IDs and current prices are loaded and saved the first time you view a card (refreshed daily). Offline you see the last state."), "", None))
    out.append(("rates", tr("Exchange rates & set list"), True,
                currency.rate_info() or tr("Shown in euro – no conversion needed"),
                tr("Exchange rates (ECB) are saved daily; the set list ships with the app and is updated weekly."), "", None))
    return out


# ============================================================================================================= General
def page_general(ui, b):
    from system import datahome
    from app import BASE
    ctrl = b.ctrl

    def set_lang(code):
        _set(ctrl, "language", code)

    datafolder = ui.group(tr("Data folder"), [
            ui.note(tr("This is where your collection, logs, settings, card data and images live.")),
            ui.label(str(BASE)),
            ui.row([ui.button(tr("Open"), lambda: _open_folder(BASE), tip=tr("Open folder in Explorer")),
                    ui.button(tr("Change …"), ctrl.change_data_home, enabled=datahome.FROZEN,
                              tip=tr("Move all data to another place. The program restarts for this.")
                              if datahome.FROZEN else tr("Only in the built program (.exe) – during development the data sits next to the scripts.")), ui.stretch()]),
        ])
    import games

    def set_game(key):
        ctrl.switch_game(key)
        b.form.soon()
    def game_gaps():
        """Pages a game can't do yet ("Coming soon") – read from games.<key>.features like quickshell.pageSource does,
        so the note doesn't go stale again (it said "Pokémon can only scan …" long after trade and import arrived)."""
        from app import NAV_ITEMS
        out = []
        for c in games.choices():
            feats = games.load(c["key"]).features if c["ready"] else None
            if feats is None:
                continue
            missing = [tr(t).replace("\n", " & ") for k, t in NAV_ITEMS if k not in feats and k not in ("settings", "stats", "profile")]
            if missing:
                out.append(f"{games.nick_of(c['key'])}: {', '.join(missing)}")
        return out
    gaps = game_gaps()
    game = ui.group(tr("Game (preview)"), [
        ui.note(tr("Each game has its own card data, collection and logs – nothing gets mixed. Load card data afterwards under “Card data”. You can also switch with the game button on the left of the bar.")
                + (" " + tr("Not available yet:") + " " + "; ".join(gaps) + "." if gaps else "")),
        ui.row([_choice(ui, [(c["key"], c["name"]) for c in games.choices() if c["ready"]], games.current().key,
                         set_game), ui.stretch()])])
    language = ui.group(tr("Sprache / Language"), [ui.row([
            _choice(ui, list(i18n.languages()), ctrl.settings["language"], set_lang),
            ui.note(tr("Takes effect after a restart.")),
            ui.button(tr("Restart now"), ctrl.restart, primary=True)
            if ctrl.settings["language"] != i18n.LANG else None])])
    from ui import tray

    def set_tray(on):
        _set(ctrl, "tray_mode", bool(on))
        ctrl.tray.apply()
        if not on and tray.autostart_enabled():
            tray.set_autostart(False)
    s = ctrl.settings
    auto_ok = bool(s.get("tray_mode")) and tray.autostart_possible()
    background = ui.group(tr("In the background"), [
        ui.check(tr("Keep running in the system tray (daily prices, price alerts)"), bool(s.get("tray_mode")), set_tray,
                 tip=tr("Closing the window then doesn't quit: Bent°Corner stays as a small icon next to the clock – camera and SCAN are off, memory is freed. To quit: right-click the icon.")),
        ui.check(tr("Start with Windows (hidden in the system tray)"), tray.autostart_enabled(),
                 lambda on: (tray.set_autostart(on), b.form.soon()), enabled=auto_ok,
                 tip=tr("Then prices are up to date every morning without opening the program.")
                 if tray.autostart_possible() else tr("Only possible in the built program (.exe).")),
    ])
    window = ui.group(tr("Program window"), [
            ui.form([(tr("Start page"), _choice(ui, [(k, tr(v)) for k, v in __import__("app").START_PAGES.items()],
                                                 ctrl.settings.get("start_page") or "library",
                                                 lambda v: _set(ctrl, "start_page", v),
                                                 tip=tr("Which page the program opens with.")))]),
            _check(ui, ctrl, "Start in fullscreen", "start_fullscreen",
                   "Sonst startet das Programm maximiert (ganzer Bildschirm mit Taskleiste). F11 schaltet jederzeit "
                   "um."),
        ])
    return ui.row([ui.col([game, language, window], spacing=14), ui.col([background, datafolder], spacing=14)],
                  spacing=14)


# ============================================================================================================= Profile
# =============================================================================================================== Legal
from system.contacts import SITE   # noqa: E402  (our website)
from urllib.parse import urlparse   # noqa: E402


def _web(url):
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


def _updates_group(ui, ctrl):
    """Updates via our own server: status, progress, pause/resume, install now."""
    from net import updater
    import version
    u = getattr(ctrl, "updater", None)
    s = ctrl.settings
    def set_updates(v):
        s["updates"] = bool(v)
        ctrl.settings_changed()
        ctrl.updater_apply()
    rows = [ui.check(tr("Check for updates and let me know"), s.get("updates", True), set_updates),
            ui.check(tr("Download updates automatically"), bool(s.get("update_download")),
                     lambda v: (s.update(update_download=bool(v)), ctrl.settings_changed()),
                     enabled=s.get("updates", True),
                     tip=tr("Off: Bent°Corner only tells you, and downloads when you click – handy when nothing should slow your connection (e.g. while gaming online)."))]
    if u is not None:
        state = {"idle": tr("not checked yet"), "checking": tr("checking …"),
                 "none": tr(f"up to date ({version.label()})"),
                 "available": tr(f"Version {u.latest} available"),
                 "downloading": tr(f"Downloading version {u.latest} … {int(u.progress * 100)} %"),
                 "paused": tr(f"Version {u.latest} paused at {int(u.progress * 100)} %"),
                 "ready": tr(f"Version {u.latest} ready"),
                 "error": tr(f"Error: {u.error}")}.get(u.state, u.state)
        rows.append(ui.label(state))
        if u.state in ("downloading", "paused"):
            rows.append(ui.progress(int(u.progress * 100), 0, 100))
        btns = [ui.button(tr("Check now"), lambda: u.check(auto_download=bool(s.get("update_download"))),
                          enabled=u.state not in ("checking", "downloading"))]
        if u.state == "downloading":
            btns.append(ui.button(tr("Pause"), u.pause))
        if u.state in ("available", "paused", "error") and u.entry:
            btns.append(ui.button(tr("Resume download") if u.state == "paused" else tr("Load"), u.download))
        if u.state == "ready":
            btns.append(ui.button(tr("Update now"), ctrl.update_install, active=True,
                                  enabled=u.can_install()))
        rows.append(ui.row(btns + [ui.stretch()]))
    rows.append(ui.note(tr("Updates come from {host} and are signed – Bent°Corner only installs what carries the signature. Nothing is installed without your consent.").format(
        host=urlparse(SITE).hostname)))
    return ui.group(tr("Updates") + f" · {updater.platform_key().title()}", rows)


def page_updates(ui, b):
    """Updates: status and download, the patch history below."""
    import version
    try:
        import patchnotes
        notes = patchnotes.NOTES
    except ImportError:
        notes = []
    items = [ui.label(f"<b>Bent°Corner</b>&nbsp;&nbsp;<span style='color:gray'>{version.label()}</span>", px=15,
                      tip=tr("Version number – before 1.0 Bent°Corner is in beta")),
             _updates_group(ui, b.ctrl)]
    if notes:
        rows = []
        for num, date, text in notes:
            when = ".".join(reversed(date.split("-"))) if date else ""
            rows.append(f"<tr><td style='padding:2px 14px 2px 0'><b>v{num}</b></td>"
                        f"<td style='padding:2px 14px 2px 0; color:gray'>{when}</td>"
                        f"<td style='padding:2px 0'>{html.escape(text)}</td></tr>")
        items.append(ui.group(tr("Patch history"), [
            ui.scroll([ui.label("<table>" + "".join(rows) + "</table>", rich=True)], h=520)]))
    return ui.col(items, spacing=12)


def page_privacy(ui, b):
    """Friends & privacy: everything the program shares or sends – each switch exists only here (STREAMLINE §4)."""
    from net import relay
    from system import orbit
    ctrl = b.ctrl
    s = ctrl.settings
    full = relay.enabled(s)

    # down from Full Orbit the slider only moves: what leaving does and "Stay / Leave" stand right under it, nothing
    # changes before "Leave" (no extra sheet); up, and between Core and Near, applies at once
    leave = getattr(b, "orbit_leave", None)
    if leave and not orbit.leaving(s, leave):   # the exchange went off elsewhere meanwhile
        leave = b.orbit_leave = None

    def pick(i):
        lv = orbit.LEVELS[i]
        b.orbit_leave = lv if orbit.leaving(s, lv) else None
        # up to Full Orbit without the age confirmation: the line under the slider first, the level stays
        b.orbit_join = lv == "full" and not orbit.age_ok(s) and orbit.level(s) != "full"
        if b.orbit_leave is None and not b.orbit_join:
            orbit.set_level(ctrl, lv)
        b.form.soon()

    def confirm(on):
        if not on:
            return
        orbit.confirm_age(s)
        if getattr(b, "orbit_join", False):
            b.orbit_join = False
            orbit.set_level(ctrl, "full")
        else:
            ctrl.settings_changed()
        b.form.soon()

    def decide(go):
        lv, b.orbit_leave = b.orbit_leave, None
        if go and lv:
            orbit.set_level(ctrl, lv)
        b.form.soon()
    # Bent°Corner Orbit on top: the same slider as in the setup – the exchange is Full Orbit (no switch of its own)
    # "Leave Full Orbit? [Stay] [Leave]" sits in the slider's reserved place under the columns (nothing jumps)
    joining = getattr(b, "orbit_join", False) and orbit.level(s) != "full"
    orbit_items = [ui.orbit(orbit.LEVELS.index(leave) if leave else (2 if joining else orbit.index(s)), pick, compact=True,
                            leave=tr(orbit.LEAVE) if orbit.level(s) == "full" else "", decide=decide)]
    # the age line (legal 03.11.): when moving up to Full Orbit – and once for those already there
    if joining or (orbit.level(s) == "full" and not orbit.age_ok(s)):
        orbit_items += [ui.check(tr(orbit.AGE), False, confirm), ui.note(tr(orbit.AGE_NOTE))]
    orbit_group = ui.group(tr("Bent°Corner Orbit"), orbit_items)
    friends = ui.group(tr("Friends"), [
        ui.check(tr("Share library with friends (visible to friends, encrypted)"),
                 s.get("share_library") is True,
                 lambda v: (s.update(share_library=bool(v)), ctrl.settings_changed(),
                            relay.enabled(s) and ctrl.relay_send_lists(quiet=True)),
                 tip=tr("Friends see your whole collection of the open game. Lists are shared one by one – new lists always start private."),
                 enabled=full),
        ui.check(tr("Messages from the Bent°Corner team (news, questions about your contributions)"),
                 s.get("team_messages", True) is not False,
                 lambda v: (s.update(team_messages=bool(v)), ctrl.settings_changed()),
                 tip=tr("Read only – you can't reply. They are genuine only with the team's signature."), enabled=full),
    ] + ([] if full else [ui.note(tr("Only in Full Orbit – the exchange with friends runs through the Bent°Corner mailbox."))]))
    numbers = ui.group(tr("Numbers"), [
        ui.check(tr("Send anonymous numbers (once a week, without identifier)"), s.get("stats_share") is True,
                 lambda v: (s.update(stats_share=bool(v)), ctrl.settings_changed()),
                 tip=tr("Which games, and on how many days you use which parts of the app, plus rough amounts – no ID, no name, no cards.")),
    ])
    return ui.col([orbit_group, friends, _scan_data_group(ui, ctrl), numbers,
                   ui.note(tr("Online requests (Scryfall, TCGdex, Commander Spellbook …) only contain the cards or decks you look up – no personal data. There is no tracking."))],
                  spacing=12)


def phone_camera_group(ui, ctrl):
    """Settings → Scanning: phone as camera – QR code, instructions, "use now"."""
    from scanner import phonecam
    on = ctrl.cam_combo.currentData() == "phone"
    url = phonecam.url() or (ctrl.phone_start() if on else "")
    items = [ui.note(tr("Your phone films, Bent°Corner on the PC recognizes – everything stays in your Wi-Fi, nothing goes through a server. On first opening the phone browser warns about the certificate (it is self-made): “Advanced → proceed anyway”. Windows asks once about the firewall: allow “Private networks”."))]
    if url:   # blurred until you press "Show" (no address in the picture – nobody should read along)
        shown = getattr(ctrl, "_phone_qr_shown", False)

        def toggle():
            ctrl._phone_qr_shown = not shown
            sb = getattr(getattr(ctrl, "shell", None), "backends", {}).get("settings")
            if sb is not None:
                sb.form.refresh()
        items.append(ui.row([ui.image("image://cards/phoneqr" + ("" if shown else "_blur"), 180, 180),
                             ui.col([ui.label(f"<b>{tr("Scan with your phone")}</b>", rich=True),
                                     ui.button(tr("Hide QR code") if shown else tr("Show QR code"), toggle)],
                                    spacing=6), ui.stretch()]))
        items.append(ui.note(tr("Phone not getting through? Some Wi-Fi networks keep devices apart. A cable always works: plug the phone into the PC, tap the USB notification → “USB tethering” (iPhone: “Personal Hotspot”, needs the “Apple Devices” app). The QR code switches over – scan again. Turn tethering off afterwards, otherwise the PC may use the phone for internet. Also: Android browsers need the “Nearby devices” permission; disconnect a VPN on the PC briefly.")))
    items.append(ui.row([ui.button(tr("Use phone as camera") if not on else tr("✓ Phone is the camera"),
                                   ctrl.use_phone, active=not on, enabled=not on), ui.stretch()]))
    return ui.group(tr("Phone as camera"), items)


def auto_backup_group(ui, ctrl, refresh):
    """Automatic backup (Settings → Backup): on/off, how often, up to three targets with status."""
    import html
    import time
    from system import autobackup
    from ui import qdialogs
    s = ctrl.settings
    c = autobackup.cfg(s)

    def save():
        ctrl.settings_changed()
        ctrl.autobackup_badge()
        refresh()

    def add():
        folder = qdialogs.get_dir(tr("Where should automatic backups go? (stick, drive, cloud folder)"), "")
        if folder and autobackup.add_target(s, folder):
            s.pop("backup_risk_ok", None)   # now there is a target: reminders apply again
            save()
            ctrl.autobackup_check(force=True)

    def remove(path):
        autobackup.remove_target(s, path)
        save()

    def risk(on):
        if on:
            s["backup_risk_ok"] = True
        else:
            s.pop("backup_risk_ok", None)
        save()
    kinds = {"cloud": tr("cloud folder"), "other": tr("other drive"), "same": tr("same disk as your data")}
    warn = autobackup.attention(s)
    items = []
    if warn:
        items.append(ui.label(f"<b>{tr(warn)}</b>", rich=True))
    items.append(ui.row([ui.check(tr("On"), c["on"], lambda v: (c.update(on=bool(v)), save())),
                         _choice(ui, [(k, tr(n)) for k, n in autobackup.EVERY_NAMES], c["every"],
                                  lambda v: (c.update(every=v), save())), ui.stretch()]))
    for t in c["targets"]:
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(t["ok"])) if t.get("ok") else tr("never")
        state = tr(f"last {when}") + (f" · {tr(t['error'])}" if t.get("error") else "")
        items.append(ui.row([ui.label(f"<b>{html.escape(t['path'])}</b><br><span style='color:gray'>"
                                      f"{kinds[autobackup.kind(t['path'])]} · {state}</span>", rich=True),
                             ui.stretch(), ui.button(tr("Remove"), lambda p=t["path"]: remove(p))]))
    items.append(ui.row([ui.button(tr("Add destination …"), add, primary=not c["targets"],
                                   enabled=len(c["targets"]) < autobackup.MAX_TARGETS),
                         ui.button(tr("Back up now"), lambda: ctrl.autobackup_check(force=True),
                                   enabled=bool(c["targets"])), ui.stretch()]))
    items.append(ui.note(tr("Up to three places – ideally two: e.g. a USB stick and a cloud folder (OneDrive, Google Drive, Dropbox). Everything personal of all games is saved as one ZIP file in the folder “BentCorner backups” – only when something has changed. Bent°Corner keeps your last 5 backups, at most one per hour. If the stick isn't plugged in, Bent°Corner catches up later.")))
    if not c["targets"]:
        if s.get("backup_risk_ok"):
            items.append(ui.row([ui.note(tr("You're continuing without a backup – the lamp is off.")), ui.stretch(),
                                 ui.button(tr("Remind me again"), lambda: risk(False))]))
        else:
            items.append(ui.row([ui.stretch(), ui.button(tr("I'm aware of the risks"),   # (wording: Oliver, review .101)
                                                        
                                                         lambda: risk(True),
                                                         tip=tr("If the computer breaks, everything is gone – you'd have to scan everything again. The lamp goes off then."))]))
    return ui.group(tr("Automatic backup"), items, lamp=autobackup.lamp(s))   # the hint above may stay without the lamp


def page_backup(ui, b):
    """Settings → Backup – the only place for backups: automatic backup, one-off backup and restore, silent backups,
    what is lost without a backup, what is on the server, moving."""
    ctrl = b.ctrl

    def refresh():
        b.form.refresh() if hasattr(b, "form") else None

    from system import datastore
    ip = ctrl.import_page   # logic of the one-off backup (importview.ImportPage) – shown only here
    info, silent = ip.backup_info()
    once = ui.group(tr("Back up once, by hand"), [
        ui.note(tr("A backup contains everything personal: collection, logs, decks, friends, lists and settings. Card images and card data are downloaded again when needed – they don't need to come along. Handy before moving to a new PC: just restore it there.")),
        ui.label(info),
        ui.row([ui.button(tr("Create backup …"), lambda: (ip.make_backup(), refresh()),
                          tip=tr("Choose a folder, e.g. a USB stick – a folder “BentCorner backup <date>” is created there")),
                ui.button(tr("Restore backup …"), lambda: (ip.restore_backup(), refresh()),
                          tip=tr("Bring back a backup – your current state is saved automatically first")),
                ui.button(tr("Open data folder"), lambda: _open_folder(datastore.DATA)), ui.stretch()]),
        ui.note(ip.bk_msg) if ip.bk_msg else None,
        ui.line(),
        ui.label(f"<b>{tr("Silent backups")}</b><br>" + tr(
            "On top of that, Bent°Corner puts a copy into the data folder under data/backups/auto on start (at most every 6 hours) – the last 7 are kept. That protects against crashes, not against a broken drive: that's what the backup above is for."), rich=True),
        ui.note(silent),
    ])
    why_open = bool(getattr(b, "backup_why", False))

    def why():
        b.backup_why = not why_open
        refresh()
    why = [ui.button(tr("Why is this important?") + (" ‹" if why_open else " ›"), why)]
    if why_open:
        why.append(ui.note(tr(
            "Bent°Corner has no server for your collection: it lives only on this computer. If the computer breaks, gets "
            "lost or is set up anew, it is gone without a backup – we can't restore it either. The copies Bent°Corner "
            "makes on this computer at start only help with errors. That's why: a place outside – a USB stick, an external "
            "drive or a cloud folder. Bent°Corner backs up there by itself, as often as you set it below, keeps the last 7 "
            "and one per week for four weeks, and catches up as soon as the stick is back.")))
    return ui.col([
        ui.col([ui.row(why[:1] + [ui.stretch()])] + why[1:], spacing=6),
        auto_backup_group(ui, ctrl, refresh),
        once,
        ui.group(tr("What is on the server"), [ui.note(tr(
            "Only what you share with friends: shared lists, your library (if you share it) and shared binders – encrypted, only your friends can read it. It stays for 6 months after you last shared it (while you use the app, it re-shares regularly); if you take something back, it's gone at once. This is not a backup: logs, decks, private lists and settings are never there.")), ui.note(tr(
            "Your ID is like an address: anyone who knows it can send you a friend request, but can't read anything – so it's fine to pass it on. The key to your ID lives in your settings and therefore in every backup. Without a backup a new installation gets a new ID: your friends have to add you again, and what you shared before expires after 6 months."))]),
        ui.group(tr("Moving to another PC"), [ui.note(tr(
            "Restore a backup on the new PC (Settings → Backup) – then everything is back, including your ID and your friends. Two PCs at the same time with the same backup doesn't work: both would have the same ID and overwrite each other's shared lists. If your data folder is in a cloud folder you can use it on two PCs – but only one at a time, never open on both at once."))]),
    ], spacing=12)


LICENSE_FILES = ("THIRD_PARTY_NOTICES.md", "LICENSE", "LICENSE-ASSETS.md")   # bundled next to the program (build.ps1)
LICENSE_DIR = "licenses"   # full license texts of the components (tools/collect_licenses.py, bundled by build.ps1)
# Required attribution under the additional terms (GPL-3.0 section 7(b)) – word for word in every language, never tr()
GPL_ATTRIBUTION = "Based on Bent°Corner – https://bentcorner.app"


def _bundled(name):
    """A file or folder bundled with the program (in the exe: _MEIPASS, in development: the project folder)."""
    import pathlib
    import sys
    return pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1])) / name


def _license_text(names=LICENSE_FILES, folder=LICENSE_DIR):
    """Bundled license files (+ every text in the licenses folder) as one text – readable without internet."""
    files = [(n, _bundled(n)) for n in names]
    if folder and _bundled(folder).is_dir():   # with the path: packages/numpy-2.5.3/LICENSE.txt, not just "LICENSE.txt"
        base = _bundled(folder)
        files += [(f"{folder}/{p.relative_to(base).as_posix()}", p) for p in sorted(base.rglob("*")) if p.is_file()]
    parts = []
    for label, f in files:
        try:
            parts.append(f"===== {label} =====\n\n" + f.read_text("utf-8", errors="replace").strip())
        except OSError:
            continue
    return "\n\n\n".join(parts) or tr("The license files are missing from this installation.")


def _show_text(title, text):
    """A long text in a sheet inside the program window (no pop-up)."""
    from ui import qdialogs
    qdialogs.show(title, lambda ui, d: ui.col([
        ui.textarea(text, lambda v: None, read_only=True, h=560)]), wide=True, wait=False)   # nothing to answer


def _third_party_notices():
    """Third-party notices and licenses."""
    _show_text(tr("Third-party notices"), _license_text())


def _gpl_license():
    """The program's own license (LICENSE: GPL-3.0 + additional terms), bundled – opens without internet."""
    _show_text(tr("License"), _license_text(("LICENSE",), None))


def gpl_notice(ui):
    """GPL-3.0 notices ("Appropriate Legal Notices", section 5(d), + the attribution of our section 7 terms) – at the
    very top of Settings → Legal, a normal section (no pop-up). Texts: legal (app-rechtliches-gpl.md, 31.10.2026).
    The switch is system/contacts.SOURCE_URL: empty (repository not public yet) -> None, the page
    looks as before – a version can never say "GPL" without a link to its source code."""
    import version
    from system import contacts
    if not contacts.SOURCE_URL:
        return None
    # a release links its own tag in the public repository (commit_public.py tags v<version>; GPL § 6, legal 03.11.)
    source = contacts.SOURCE_URL.rstrip("/") + (f"/tree/v{version.VERSION}" if version.is_release() else "")
    rows = [
        ui.label(tr("<b>Bent°Corner</b> – version {version}").format(version=version.VERSION), rich=True),
        ui.label("Copyright (C) 2026 Oliver Schunn"),
        ui.label(tr("Bent°Corner is free software: you can redistribute it and/or modify it under the terms of the "
                    "GNU General Public License version 3, with additional terms under section 7 (see LICENSE).")),
        ui.label(tr("This program comes with ABSOLUTELY NO WARRANTY, to the extent permitted by law.")),
        ui.label(tr("Source code: {url}").format(url=f"<a href='{source}'>{source}</a>"),
                 rich=True),
    ]
    rows += [
        ui.row([ui.label(tr("License:"), fixed=True),
                ui.button(tr("GNU GPL v3.0 + additional terms"), _gpl_license), ui.stretch()]),
        ui.label(GPL_ATTRIBUTION),
        ui.note(tr("The SCAN° recognition data (models and card index) and the card data packs are not covered by "
                   "the GPL; they may only be used with Bent°Corner.")),
    ]
    return ui.group(tr("License"), rows)


def page_legal(ui, b):
    """Legal: the GPL notices, legal notice, privacy policy, terms (website), third-party notices and the legal texts
    of the app."""
    from app import legal_entries, legal_text
    legal = [_fold(ui, b, "legal:" + title, tr(title), [ui.label(legal_text(text), rich=True)])
             for title, text in legal_entries()]
    return ui.col([
        gpl_notice(ui),
        ui.row([ui.button(tr("Legal notice"), lambda: _web(SITE + "/impressum.html")),
                ui.button(tr("Privacy"), lambda: _web(SITE + "/datenschutz.html")),
                ui.button(tr("Terms of use"), lambda: _web(SITE + "/nutzung.html")),
                ui.button(tr("Third-party notices"), _third_party_notices), ui.stretch()]),
        ui.group(tr("Legal"), legal),
    ], spacing=12)


COFFEE_URL = "https://buymeacoffee.com/oliverschunn"


def coffee_sticker(ui):
    """The "Buy me a coffee" sticker: yellow area, official cup logo (assets/bmc-logo.svg, provided by Buy Me a Coffee
    for links to your own page), stuck on slightly tilted – a click opens the page in the browser."""
    import pathlib
    import sys
    from ui import quickimages
    from PySide6 import QtSvg
    w, h, k = 236, 64, 2   # Size (points) and sharpness
    img = QtGui.QImage(w * k, h * k, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing | QtGui.QPainter.SmoothPixmapTransform)
    p.scale(k, k)
    p.translate(w / 2, h / 2)
    p.rotate(-3)   # stuck on crooked
    r = QtCore.QRectF(-104, -22, 208, 44)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(0, 0, 0, 70))   # Shadow
    p.drawRoundedRect(r.translated(2, 3), 12, 12)
    p.setBrush(QtGui.QColor("#FFDD00"))
    p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2.5))   # white border like a sticker
    p.drawRoundedRect(r, 12, 12)
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))   # .exe or development
    svg = QtSvg.QSvgRenderer(str(base / "assets" / "bmc-logo.svg"))
    svg.render(p, QtCore.QRectF(r.left() + 14, r.top() + 7, 21, 30))
    f = look.text_font(17, QtGui.QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QtGui.QColor("#0D0C22"))
    p.drawText(QtCore.QRectF(r.left() + 44, r.top(), r.width() - 52, r.height()), QtCore.Qt.AlignVCenter,
               "Buy me a coffee")
    p.end()
    url = quickimages.put("coffee_sticker", img)
    return ui.image(url, w, h, tip=tr("Opens buymeacoffee.com/oliverschunn in the browser"), link=COFFEE_URL)


def page_game(ui, b):
    """Easter egg: Scalper Invaders – the same game as in the first-run setup (scalper.py, ScalperGame.qml)."""
    from ui import scalper
    ctrl = b.ctrl
    return ui.col([ui.note(tr("Your card back is the ship. Collect boosters, shoot scalpers – don't let any cross the line. Your best score is saved.")),
                   scalper.node(ui, ctrl.settings, ctrl.settings_changed)], spacing=12)


def page_about(ui, b):
    """About Bent°Corner: who is behind it, version, website – and the coffee sticker."""
    import version
    from ui import iconkit
    from ui import quickimages
    on = "light" if look.is_light() else "dark"
    img, w, h = iconkit.lockup_image(30, on)   # the brand: long version (card + BENT°CORNER)
    return ui.col([
        ui.group(tr("Bent°Corner"), [
            ui.image(quickimages.put(f"lockup_{on}", img), round(w), round(h)),
            ui.label(tr("Concept &amp; design: Oliver Schunn · Code: Claude (AI by Anthropic)."), rich=True),
            ui.label(tr("Bent°Corner is free and is not sold. If you like, you can buy me a coffee – thank you!")),
            coffee_sticker(ui),
            ui.note(tr(f"Version {version.VERSION}")),
            ui.row([ui.button(tr("Website"), lambda: _web(SITE + "/")),
                    ui.button(tr("Legal & sources …"), lambda: b.ctrl.stream.show_page("settings", tab="legal")),
                    ui.stretch()]),
        ]),
        ui.group(tr("Program log"), [
            ui.note(tr("What the program did since it started – and the log of the start before. Helpful if something went wrong: send both files along with your message. They contain folder paths of your PC, card names and device details (camera, graphics card) – no keys, passwords or names of your friends. Have a look first if you like.")),
            ui.row([ui.button(tr("Open log folder"), _open_logs, tip=tr("Shows bentcorner.log in Explorer")), ui.stretch()]),
        ]),
    ], spacing=12)


def _open_logs():
    """Explorer with bentcorner.log selected (bentcorner-previous.log lies next to it) – otherwise just the folder."""
    from app import BASE
    from system import startup
    log_file = BASE / startup.LOG
    if os.name == "nt" and log_file.exists():
        import subprocess
        subprocess.Popen(["explorer", "/select,", str(log_file)])
    else:
        _open_folder(BASE)


PAGES = {"scan": page_scan, "collection": page_collection, "sets": page_sets, "display": page_display,
         "backup": page_backup,
         "appearance": page_appearance, "offline": page_sets, "general": page_general,
         "updates": page_updates, "privacy": page_privacy, "legal": page_legal, "game": page_game,
         "about": page_about}
