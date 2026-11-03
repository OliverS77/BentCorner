"""Import a deck via link: Moxfield and Archidekt directly (with exact printing), all other sites via
Commander Spellbook ("card-list-from-url", card names only). The result is a text list in the usual format –
the normal import (decks.parse_text) turns it into the deck.

Moxfield and Archidekt are OFF for now (as of 2026-10-20): Moxfield only opens its API on request
(support@moxfield.com), Archidekt's terms of use forbid automated requests. Once permission is granted,
switch it on here in ALLOWED. Until then: export there, paste the text."""
import re
from net import netpolite

UA = {"User-Agent": netpolite.UA}   # netpolite sets it anyway – one source of truth
_MOX = re.compile(r"moxfield\.com/decks/([\w-]+)", re.I)
_ARCH = re.compile(r"archidekt\.com/(?:api/)?decks/(\d+)", re.I)
ALLOWED = {"moxfield": False, "archidekt": False}
_ASK = ("{} only allows other programs to fetch decks with permission – until then: copy the deck there as text "
        "via “Export” and paste it here.")   # shown via tr(str(e)) in the import view
ARCH_FORMATS = {3: "commander", 1: "standard", 2: "modern", 4: "legacy", 5: "vintage", 6: "pauper"}


def is_url(text):
    return bool(re.match(r"^\s*(https?://)?(www\.)?[\w-]+\.[\w.-]+/\S+\s*$", text or ""))


def _line(n, name, set_code=None, number=None):
    return f"{n} {name}" + (f" ({set_code.upper()}) {number}" if set_code and number else "")


def _text(sections):
    out = []
    for title, lines in sections:
        if lines:
            out += [title] + lines + [""]
    return "\n".join(out).strip()


def fetch(url, timeout=25):
    """-> {"name", "format" (or None), "text", "source"}. Raises an exception with a readable message."""
    url = url.strip()
    if not url.lower().startswith("http"):
        url = "https://" + url
    m = _MOX.search(url)
    if m and not ALLOWED["moxfield"]:
        raise RuntimeError(_ASK.format("Moxfield"))
    if m:
        r = netpolite.get(f"https://api2.moxfield.com/v3/decks/all/{m.group(1)}", headers=UA, timeout=timeout)
        if r.status_code in (403, 429):
            raise RuntimeError("Moxfield lässt den Abruf gerade nicht zu – Liste dort über „Export“ kopieren "
                               "und hier einfügen.")
        r.raise_for_status()
        d = r.json()
        boards = d.get("boards") or {}

        def lines(key):
            return [_line(e["quantity"], e["card"]["name"], e["card"].get("set"), e["card"].get("cn"))
                    for e in (boards.get(key) or {}).get("cards", {}).values()]
        fmt = d.get("format")
        return {"name": d.get("name") or "", "format": fmt, "source": "Moxfield",
                "text": _text([("Commander", lines("commanders") + lines("companions")), ("Deck", lines("mainboard")),
                               ("Sideboard", lines("sideboard")), ("Maybeboard", lines("maybeboard"))])}
    m = _ARCH.search(url)
    if m and not ALLOWED["archidekt"]:
        raise RuntimeError(_ASK.format("Archidekt"))
    if m:
        r = netpolite.get(f"https://archidekt.com/api/decks/{m.group(1)}/", headers=UA, timeout=timeout)
        if r.status_code == 404:
            raise RuntimeError("Deck nicht gefunden – ist es auf Archidekt öffentlich?")
        r.raise_for_status()
        d = r.json()
        sec = {"Commander": [], "Deck": [], "Sideboard": [], "Maybeboard": []}
        for c in d.get("cards") or []:
            cats = set(c.get("categories") or [])
            card = c.get("card") or {}
            name = (card.get("oracleCard") or {}).get("name") or card.get("displayName")
            if not name:
                continue
            ed = (card.get("edition") or {}).get("editioncode")
            line = _line(c.get("quantity", 1), name, ed, card.get("collectorNumber"))
            key = ("Commander" if "Commander" in cats else "Maybeboard" if "Maybeboard" in cats
                   else "Sideboard" if "Sideboard" in cats else "Deck")
            sec[key].append(line)
        return {"name": d.get("name") or "", "format": ARCH_FORMATS.get(d.get("deckFormat")), "source": "Archidekt",
                "text": _text(list(sec.items()))}
    # all other sites: Commander Spellbook reads the list (names only)
    r = netpolite.get("https://backend.commanderspellbook.com/card-list-from-url", params={"url": url}, headers=UA,
                     timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError("Diese Seite wird nicht unterstützt – Liste dort exportieren und hier einfügen.")
    d = r.json()
    cm = [_line(c.get("quantity", 1), c["card"]) for c in d.get("commanders") or []]
    main = [_line(c.get("quantity", 1), c["card"]) for c in d.get("main") or []]
    if not cm and not main:
        raise RuntimeError("Unter dem Link wurde keine Deckliste gefunden (privat oder leer?).")
    return {"name": "", "format": "commander" if cm else None, "source": "Commander Spellbook",
            "text": _text([("Commander", cm), ("Deck", main)])}
