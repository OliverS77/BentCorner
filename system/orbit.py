"""Bent°Corner Orbit – everything that circles around your collection, in three levels (Oliver, 2026-10-29):

    core   Core        everything stays with you – lists, binders, sub-collections; no prices are fetched
    near   Near Orbit  you only fetch something: prices, marketplaces, price alerts – nothing of yours goes out
    full   Full Orbit  you share: lists, binders and tickets go end-to-end encrypted to friends (the mailbox, net/relay)

One level = exactly what leaves the device beyond what every level needs. Card data, card images, data packs, updates
and look-ups (EDHREC, Commander Spellbook …) are NOT part of Orbit – they have their own settings. The anonymous
numbers (net/anonstats) and the scan data stay their own consent, never bundled in here.

Stored in settings["orbit"]. The exchange itself stays net/relay's switch: Full Orbit = the exchange is on, so the
level always follows a change made elsewhere (e.g. turning the exchange off). Nobody is ever moved up to Full Orbit
silently: only set_level() does that, and only on the user's own choice.
"""
from system.i18n import tr

LEVELS = ("core", "near", "full")
NAMES = {"core": "Core", "near": "Near Orbit", "full": "Full Orbit"}
# Oliver's sentences (2026-10-29), word for word in German (locales/de.py) – the rings show how far your data travels
LINES = {"core": "Your collection stays with you.",
         "near": "You only fetch something: prices and marketplaces. Nothing from your collection goes out.",
         "full": "You share what you choose: lists, binders or your library go end-to-end encrypted only to your friends."}
# the columns under the slider (.92: short – "not 15 lines nobody reads"); checked against prices_on/relay:
# Core never says "nothing leaves the device" – card data, images and updates come in every level
SHORT = {"core": "Your collection stays with you.", "near": "You only fetch.", "full": "You share – encrypted."}
POINTS = {"core": ["No prices", "No friends", "Your collection stays with you"],
          "near": ["Prices & marketplaces", "Price alerts", "Your collection stays with you"],
          "full": ["+ Friends & trading", "Shared lists & binders", "End-to-end encrypted"]}
# the one shared line: only what you share is encrypted; the sources see the IP address (privacy policy §4)
FOOT = ("What you share is end-to-end encrypted. Card data, images and prices come from sources like Scryfall, "
        "which see your IP address.")
# the small print: exactly what leaves the device (privacy policy §4/§5) – honest about the IP address
OUT = {"core": "Nothing from your collection leaves the device.",
       "near": "Price downloads from our price server and the price sources (MTGJSON, Cardmarket, exchange rates) – "
               "they see your IP address like any website, but nothing from your collection.",
       "full": "On top: a random ID at the Bent°Corner mailbox and end-to-end encrypted parcels only to your friends – "
               "the server can't read them."}


def level(settings):
    """The current level. Full Orbit exactly while the exchange is on; otherwise what was chosen – without a choice
    yet (users from before Orbit) derived from today's settings: prices only by hand = Core, otherwise Near."""
    from net import relay
    if relay.enabled(settings):
        return "full"
    lv = settings.get("orbit")
    if lv in ("core", "near"):
        return lv
    return "core" if settings.get("price_update") == "manual" else "near"


def index(settings):
    return LEVELS.index(level(settings))


def prices_on(settings):
    """Prices, exchange rates, price history and price alerts are fetched/checked – from Near Orbit on."""
    return level(settings) != "core"


def price_mode(settings):
    """When prices are loaded automatically: the setting – in Core never ("manual" and the button says why)."""
    return settings.get("price_update", "start") if prices_on(settings) else "manual"


# Full Orbit and age (legal 03.11.2026, Oliver's OK): confirmed once, inline under the level – only "confirmed" is stored,
# on this device (settings["orbit_age"] = {"ok": True, "t": seconds}; the web keeps the same in its settings store)
AGE = "I'm at least 13. If I'm under 18, my parents agree."
AGE_NOTE = "We can't check your age, so we only ask this once. Your answer stays on your device."   # grey, right under it
TRADE_TIP = ("Tip: Trade only with people you know and check the value first. Don't give your address to people you "
             "only know online. If you're under 18, talk to your parents first.")


def age_ok(settings):
    a = settings.get("orbit_age")
    return isinstance(a, dict) and a.get("ok") is True


def confirm_age(settings, now=None):
    import time
    settings["orbit_age"] = {"ok": True, "t": int(now if now is not None else time.time())}


def asked(settings):
    return bool(settings.get("orbit_asked"))


# what leaving Full Orbit does – shown right under the slider while it stands below Full (no extra question sheet)
LEAVE = ("Leaving Full Orbit deletes your shared lists and binders from the server, and your friends delete their "
         "copy. Your friends and your ID stay – switch back any time.")


def leaving(settings, lv):
    """The slider stands below Full Orbit while the exchange is still on – the consequence belongs under it."""
    return level(settings) == "full" and lv != "full"


def set_level(ctrl, lv):
    """Change the level – the caller decides when (setup and "What's new?": with Next/Done; settings: up at once,
    down from Full Orbit only with "Leave" under the slider). Never asks itself: a sheet opened from the slider's
    release covered the Orbit sheet and ran its own event loop inside the mouse release (Oliver, 0.9.2.86).
    -> True if it changed."""
    if lv not in LEVELS:
        return False
    s = ctrl.settings
    if lv == "full" and not age_ok(s) and level(s) != "full":   # without the confirmation Full Orbit stays off
        return False
    before = level(s)
    s["orbit"] = "near" if lv == "full" else lv   # Full = the exchange on top of Near (turned off elsewhere: Near)
    s["orbit_asked"] = True
    if (lv == "full") != (before == "full"):
        ctrl.relay_toggle(lv == "full")   # saves the settings and sets the mailbox up or down
    else:
        ctrl.settings_changed()
    return lv != before


def describe(settings):
    """One quiet line for the top of the Orbit tab, e.g. "Near Orbit · prices and alerts on, friends off"."""
    lv = level(settings)
    rest = {"core": tr("prices and friends off"), "near": tr("prices and alerts on, friends off"),
            "full": tr("prices, alerts and friends on")}[lv]
    return f"{tr(NAMES[lv])} · {rest}"
