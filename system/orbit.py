"""Bent°Corner Orbit – everything that circles around your collection, in three levels (Oliver, 2026-10-29):

    core   Core        everything stays with you – lists, binders, sub-collections; no prices are fetched
    near   Near Orbit  you only fetch something: prices, marketplaces, price alerts – nothing of yours goes out
    full   Full Orbit  you share: lists, binders and your library go end-to-end encrypted to friends (the mailbox,
                       net/relay) – trade tickets are images, they never go through the mailbox

One level = exactly what leaves the device beyond what every level needs. Card data, card images, data packs, updates
and look-ups (Scryfall …) are NOT part of Orbit – they have their own settings. Exception (Oliver/legal 16.11.2026):
Commander Spellbook and EDHTop16 only from Near Orbit on, with a switch of their own (spellbook_on). The anonymous
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
          "full": ["+ Friends & trading", "Share lists, binders and trade tickets end-to-end encrypted"]}
# E2E only where true (legal 06.11.): trade tickets go through the mailbox since the ticket sending (ports, big 0.9.7) –
# before that the point was "Share lists & binders end-to-end encrypted"
# the shared line under the columns, per level (legal 04.11.): card data and images – Magic straight from Scryfall,
# the rest mostly through our server, only if needed from the source (privacy policy §4); the prices stand in OUT.
# Only Full Orbit shares something – the encryption sentence only there
_FOOT = ("Card data and images come straight from Scryfall for Magic, otherwise mostly through our server and only if "
         "needed straight from the source – whoever delivers them sees your IP address.")
FOOTS = {"core": _FOOT, "near": _FOOT, "full": "What you share through the mailbox is end-to-end encrypted. " + _FOOT}
# directly above the age line, only at the step to Full Orbit (legal 04.11., § 305 (2) BGB – as in the web app)
TERMS_LINE = "By turning it on, you agree to the <a href='{url}'>terms of use ›</a>"
# the small print: exactly what leaves the device (privacy policy §4/§5) – honest about the IP address
OUT = {"core": "Nothing from your collection leaves the device.",
       "near": "Price downloads from our price server and the price sources (MTGJSON, Cardmarket, exchange rates) – "
               "they see your IP address like any website, but nothing from your collection. Plus, for Commander "
               "decks, Commander Spellbook and EDHTop16: Spellbook gets the card list (names and counts) of the deck "
               "you open or edit, to find combos; EDHTop16 gets only the commander's name, for tournament numbers "
               "(switch below).",
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


_bound = None   # the app's settings (bind() at start) – the display gate below reads the level live from them


def bind(settings):
    global _bound
    _bound = settings


def prices_shown():
    """Card prices (market values from the card data/price sources) may be SHOWN – from Near Orbit on (Oliver/legal
    06.11.: in Core no such price appears anywhere: library, detail, search, decks, binders, scan, logs, export). Money
    a user types in (trade money, what they spent) is no market value and stays. Unbound (tools, tests): shown."""
    return _bound is None or prices_on(_bound)


def prices_fetch_ok():
    """Prices/exchange rates may be FETCHED now (network) – prices_on of the app's settings, read live, so a level
    change at runtime counts at once (legal 15.11., R2: in Core no price request at all). For places without the
    settings at hand (scan session, game objects). Unbound: no – a network gate fails closed."""
    return _bound is not None and prices_on(_bound)


def spellbook_on(settings):
    """Commander Spellbook and EDHTop16 (combos, bracket, cEDH numbers, deck import by link) may be asked – from Near
    Orbit on and with their switch (settings["spellbook"], default on; Oliver/legal 16.11.2026). In Core nothing goes
    to either, not even an old cached result is shown."""
    return settings is not None and level(settings) != "core" and settings.get("spellbook", True) is not False


def spellbook_ok():
    """spellbook_on for the app's bound settings, read live – for code without the settings at hand (the network
    functions themselves). Unbound: no – a network gate fails closed."""
    return spellbook_on(_bound)


def friends_shown():
    """Friends and trade tickets – only in Full Orbit (Oliver 06.11., B: "Wer Core wählt, bekommt keine Freunde, auch
    nicht selbst hinzugefügt über Dateiaustausch"). Saved friends and what they sent stay on disk, only hidden.
    Unbound (tools, tests): shown."""
    return _bound is None or level(_bound) == "full"


# Friends by FILE (trade file "Import friend …" / "Create my trade file …"): off in every level (Oliver 06.11.) –
# switched off, not removed, so it can come back. Trade tickets as images are NOT this (they follow friends_shown).
FILE_FRIENDS = False

def hold_sharing(settings):
    """Once at the update to per-friend sharing (legal 06.11., condition to „Was ist neu?“ 0.9.7): whoever is NOT in
    Full Orbit then is asked first when turning it on – until the answer nothing goes out, and an old "Yes" to "Share
    library?" doesn't count. So: nobody switched on (instead of today's friends), the library rests until answered, and
    "Shared with friends" opens once on the way into Full Orbit. In Full Orbit at the update: relay's own migration
    (today's friends keep what they get). -> True if it held something now"""
    from net import relay
    st = relay.state(settings)
    if st.get("audience_v") == relay.AUDIENCE_V or relay.enabled(settings):
        return False
    st["audience"] = {"mode": "only", "codes": []}
    st["audience_v"] = relay.AUDIENCE_V
    if settings.get("share_library") is True and not settings.get("share_library_confirmed"):
        settings["share_library_paused"] = True
    if relay.friends(settings):
        settings["shared_ask_on_full"] = True
    return True


FRIENDS_NOTE = "Friends are available in Full Orbit."
FILE_FRIEND_LINE = "This friend is only connected by file – connect through your IDs to share via the mailbox."


# the note in place of prices / of the price alerts (legal 06.11.) – the key only opens the settings, never changes the level
PRICES_NOTE = "Prices are available from Near Orbit on – nothing from your collection goes out."
PRICES_SHORT = "Prices from Near Orbit"
CHANGE_LEVEL = "Change level"
PROFILE_PRIVATE = "Nobody sees your profile."


def card_price(text):
    """A formatted card price as it is – or "" in Core (the caller formats, this only gates)."""
    return text if prices_shown() else ""


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
