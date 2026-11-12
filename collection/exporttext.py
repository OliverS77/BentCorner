"""„Mit Kartentext“ for our own CSV (Excel format) of the collection and of decks (Oliver 05.11.2026, legal's conditions
in Legal\\bentcorner\\2026-11-05-csv-export-kartentext.md):
  - only the user's own cards (collection, decks) – never a whole set or all cards,
  - per game the allowed columns; a game not listed not at all, Lorcana only colour and cost (no card text, no "Quelle"),
  - the attribution as the LAST column "Quelle" on every row (not as a header/footer line),
  - Yu-Gi-Oh!: prints from ygo-locale.sqlite (YGOJSON/Yugipedia, CC BY-SA 4.0) add that licence to their row.
The web twin is web/scan/logic/exporttext.js – the same bytes (tools/web_tradefile_fixture.py, tradefile.test.js).
Values come from the card database row: type_line, oracle_text, mana_cost already join the faces of double-faced
cards with " // " (carddb._row); power/toughness/loyalty stay empty there (Scryfall keeps them per face only)."""
from games import load as _game

# per game: the extra columns (key, header) – None = no card text export at all
COLUMNS = {
    "mtg": [("type", "Typ"), ("mana", "Manakosten"), ("mv", "Manawert"), ("colors", "Farben"),
            ("pt", "Stärke/Widerstand"), ("loy", "Loyalität"), ("text", "Kartentext")],
    "pokemon": [("type", "Kategorie/Typ"), ("hp", "KP"), ("colors", "Energietyp"), ("text", "Kartentext")],
    "yugioh": [("type", "Typ"), ("colors", "Attribut"), ("mv", "Stufe/Rang/Link"), ("atk", "ATK"), ("def", "DEF"),
               ("loy", "Pendelbereich"), ("text", "Kartentext")],
    "lorcana": [("colors", "Farbe"), ("mv", "Kosten")],
}
SOURCE = {
    "mtg": "Daten: Scryfall · Kartentext © Wizards of the Coast",
    "pokemon": "Daten: TCGdex (MIT) · Kartentext © Pokémon/Nintendo/Creatures/GAME FREAK",
    "yugioh": "Daten: YGOPRODeck · Kartentext © Konami",
}
YGOJSON = " · Yugipedia via YGOJSON, CC BY-SA 4.0, creativecommons.org/licenses/by-sa/4.0"


def allowed(game):
    """Is there a "mit Kartentext" for this game at all?"""
    return bool(COLUMNS.get(game))


def headers(game):
    """The extra headers for this game, "Quelle" last where the game has a source line."""
    cols = COLUMNS.get(game) or []
    return [h for _, h in cols] + (["Quelle"] if game in SOURCE else [])


def _num(v):
    if v is None or v == "":
        return ""
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _colors(game, letters):
    names = getattr(_game(game), "color_names", {}) or {}
    if not letters:
        return ""
    if not names:   # Magic: the letters as everyone writes them (WUBRG)
        return letters
    return ", ".join(names.get(x, x) for x in letters)


def values(game, row, locale=False):
    """The extra cells for one card (row = card database row, {} if unknown) – same order as headers()."""
    row = row or {}
    p, t = row.get("power"), row.get("toughness")
    # Yu-Gi-Oh! Link monsters: the database has no link rating in cmc (it holds 0) – empty rather than a wrong 0
    link = game == "yugioh" and "Link" in (row.get("type_line") or "").split(" — ")
    v = {"type": row.get("type_line") or "", "mana": row.get("mana_cost") or "", "mv": "" if link else _num(row.get("cmc")),
         "colors": _colors(game, row.get("colors") or ""),
         "pt": f"{p}/{t}" if p not in (None, "") and t not in (None, "") else "",
         "loy": row.get("loyalty") or "", "text": row.get("oracle_text") or "",
         "hp": row.get("power") or "", "atk": row.get("power") or "", "def": row.get("toughness") or ""}
    out = [str(v[k]) for k, _ in COLUMNS.get(game) or []]
    if game in SOURCE:
        out.append(SOURCE[game] + (YGOJSON if game == "yugioh" and locale else ""))
    return out
