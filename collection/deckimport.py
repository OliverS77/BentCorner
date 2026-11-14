"""Import a deck via link: through Commander Spellbook ("card-list-from-url", card names only). The result is a text list in the usual format –
the normal import (decks.parse_text) turns it into the deck.

Moxfield and Archidekt are OFF (as of 2026-10-20): Moxfield only opens its API on request (support@moxfield.com),
Archidekt's terms of use forbid automated requests. Their links get a clear sentence: export there, paste the text.
The fetching code for both (ALLOWED switch) was removed as unused ballast on 10.11.2026 (review 0.9.7) – it is in the
history (qtquick before desk-ballast-lib) for the day permission is granted."""
import re
from net import netpolite

UA = {"User-Agent": netpolite.UA}   # netpolite sets it anyway – one source of truth
_MOX = re.compile(r"moxfield\.com/decks/([\w-]+)", re.I)
_ARCH = re.compile(r"archidekt\.com/(?:api/)?decks/(\d+)", re.I)
_ASK = ("{} only allows other programs to fetch decks with permission – until then: copy the deck there as text "
        "via “Export” and paste it here.")   # shown via tr(str(e)) in the import view


def is_url(text):
    return bool(re.match(r"^\s*(https?://)?(www\.)?[\w-]+\.[\w.-]+/\S+\s*$", text or ""))


def _line(n, name):
    return f"{n} {name}"


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
    for pattern, site in ((_MOX, "Moxfield"), (_ARCH, "Archidekt")):   # no permission (yet): never asked
        if pattern.search(url):
            raise RuntimeError(_ASK.format(site))
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
