"""Marketplace links for a card (they only open the page in the browser – nothing is queried automatically).

market_links(card, settings) -> [{"key", "label", "host", "url"}] by importance: with euro/German Cardmarket
first, otherwise TCGplayer. Kleinanzeigen only with euro/German (nobody knows it abroad). Each can be switched off
via settings["shops_off"]. Cardhoarder (Magic Online, digital) doesn't belong here – only in the "Links" section.
"""
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urlparse, urlunparse

import games

SHOPS = (("cardmarket", "Cardmarket"), ("tcgplayer", "TCGplayer"), ("ebay", "eBay"), ("kleinanzeigen", "Kleinanzeigen"))


def _german(settings):
    from system import i18n
    return i18n.LANG == "de" or (settings or {}).get("currency", "EUR") == "EUR"


def primary(settings):
    """Main shop: setting "My main shop" (main_shop), otherwise automatic – with euro/German Cardmarket, otherwise
    TCGplayer. Determines the order of the shop links and the condition scale "Like my shop"."""
    s = settings or {}
    want = s.get("main_shop") or "auto"
    off = set(s.get("shops_off") or [])
    if want in ("cardmarket", "tcgplayer") and want not in off:
        return want
    return "cardmarket" if _german(s) and "cardmarket" not in off else "tcgplayer"


def _slug(text):
    """Kleinanzeigen puts the search in the path: words joined by hyphens, no punctuation."""
    words = "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()
    return "-".join(words)


def available(settings):
    """Which marketplaces exist for these settings (for the choice in the settings)."""
    de = _german(settings)
    return [(k, lb) for k, lb in SHOPS if k != "kleinanzeigen" or de]


def _with_param(url, key, value):
    """Append a parameter to a URL (existing parameters are kept)."""
    u = urlparse(url)
    q = parse_qs(u.query, keep_blank_values=True)
    q[key] = [value]
    return urlunparse(u._replace(query=urlencode(q, doseq=True)))


def _foil(key, url):
    """Same page, but straight to the foil offers: Cardmarket ?isFoil=Y, TCGplayer ?Printing=Foil (in Scryfall's
    affiliate links the actual URL sits in the parameter u)."""
    if key == "cardmarket":
        return _with_param(url, "isFoil", "Y")
    if key == "tcgplayer":
        u = urlparse(url)
        inner = parse_qs(u.query).get("u")
        if inner:
            return _with_param(url, "u", _with_param(inner[0], "Printing", "Foil"))
        return _with_param(url, "Printing", "Foil")
    return url


def market_links(card, settings=None, foil=False):
    card = card or {}
    name = card.get("name") or ""
    if not name:
        return []
    face = name.split(" // ")[0]
    set_name = card.get("set_name") or ""
    uris = card.get("purchase_uris") or {}
    de = _german(settings)
    off = set((settings or {}).get("shops_off") or [])
    lang = "de" if de else "en"
    mk = games.current().market   # game: Cardmarket folder, TCGplayer category, search word
    word = mk.get("search_word", "")
    links = {
        # Scryfall provides the exact link for most printings – otherwise search by name
        "cardmarket": uris.get("cardmarket")
        or f"https://www.cardmarket.com/{lang}/{mk.get('cardmarket', '')}/Products/Search?searchString={quote_plus(face)}",
        "tcgplayer": uris.get("tcgplayer")
        or f"https://www.tcgplayer.com/search/{mk.get('tcgplayer', '')}/product?q={quote_plus(face)}",
        "ebay": f"https://www.ebay.{'de' if de else 'com'}/sch/i.html?_nkw="
                + quote_plus(f"{face} {set_name} {'foil ' if foil else ''}{word}".replace("  ", " ").strip()),
        "kleinanzeigen": "https://www.kleinanzeigen.de/s-" + quote(_slug(f"{face} {'foil ' if foil else ''}{word}")) + "/k0",
    }
    if foil:
        links = {k: _foil(k, u) for k, u in links.items()}
    hosts = {"cardmarket": "cardmarket.com", "tcgplayer": "tcgplayer.com",
             "ebay": "ebay.de" if de else "ebay.com", "kleinanzeigen": "kleinanzeigen.de"}
    # big marketplaces first, then (set apart) the local Kleinanzeigen
    first = primary(settings)
    order = ["cardmarket", "tcgplayer", "ebay", "kleinanzeigen"] if de else ["tcgplayer", "cardmarket", "ebay"]
    if order[0] != first:   # main shop to the front
        order.remove(first)
        order.insert(0, first)
    return [{"key": k, "label": dict(SHOPS)[k], "host": hosts[k], "url": links[k],
             "group": "local" if k == "kleinanzeigen" else "main"} for k in order if k not in off]
