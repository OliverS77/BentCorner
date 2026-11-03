"""LICENSES.txt für die Datenpakete (publish_packs.py, make_bundle.py): Quellen und Lizenzen der Daten im jeweiligen
Paket – liegt nach dem Download in data/packs/<paket>/ neben den Dateien.

    from pack_licenses import write
    write("pokemon", ordner)      # -> ordner/LICENSES.txt
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))   # the repo root: games.extra (private packs)

NAME = "LICENSES.txt"

MIT = """Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."""

HEAD = """Bent°Corner data pack "{key}" – sources and licenses
=====================================================

Bent°Corner is a free, unofficial fan project. This pack contains data prepared by Bent°Corner from the sources
below; they keep their own licenses. Bent°Corner is not affiliated with any of them.
"""

PARTS = {
    "mtg": """
fingerprints-all.npz – recognition index
  Image fingerprints computed by Bent°Corner from card images of Scryfall (https://scryfall.com). It contains no card
  images or card texts. Card data and images themselves are not in this pack: the app loads them from Scryfall.

cardback.npy – card-back filter
  A feature vector computed from the Magic card back (contains no image), for the card-back filter of SCAN°.

langs.tsv.gz, setnames.json – card and set names in other languages
  From MTGJSON (https://mtgjson.com), MIT License:

  MIT License
  Copyright (c) 2018-Present Zach Halpern

{mit}

Magic: The Gathering
  Bent°Corner is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards.
  Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.
  https://company.wizards.com/en/legal/fancontentpolicy
""",
    "pokemon": """
cards.sqlite, setnames.json – card database and set names in other languages
  From TCGdex (https://tcgdex.dev, https://github.com/tcgdex/cards-database), converted by Bent°Corner into an SQLite
  database. MIT License:

  MIT License
  Copyright (c) 2021 TCGdex

{mit}

  Print variants (normal, holofoil, reverse holofoil …) were supplemented by Bent°Corner from TCGplayer product
  data via TCGCSV (https://tcgcsv.com).

fingerprints-all.npz – recognition index
  Image fingerprints computed by Bent°Corner from TCGdex card images. It contains no card images.

Card images (not in this pack)
  From TCGdex, through the Bent°Corner image mirror. For English cards TCGdex has no image of, the mirror holds
  supplementary images from pokemontcg.io (https://pokemontcg.io), fetched once by Bent°Corner; the database
  links them under assets.tcgdex.net/en/ptcgio/… (served by our mirror).

cm_fix.json – marketplace corrections
  Corrections of Cardmarket product assignments, made by Bent°Corner from TCGdex, Cardmarket and TCGplayer data.

Pokémon
  Pokémon, card names and images are property of Nintendo, Creatures Inc., GAME FREAK inc. and The Pokémon Company.
  Bent°Corner is not produced, endorsed, supported or affiliated with Nintendo or The Pokémon Company.
""",
    "yugioh": """
cards.sqlite – card database
  Card data from YGOPRODeck (https://ygoprodeck.com, API: https://ygoprodeck.com/api-guide/). Card images are
  self-hosted by Bent°Corner, as YGOPRODeck requires; they are not part of this file. Prices in the database:
  Cardmarket via YGOPRODeck, TCGplayer via TCGCSV (https://tcgcsv.com) – guide values without guarantee.

fingerprints-all.npz – recognition index
  Image fingerprints computed by Bent°Corner from the card images. It contains no card images.

ygo-locale.sqlite – prints from Japan, Korea, Asia and Spain, card names in other languages
  Data from YGOJSON (https://github.com/iconmaster5326/YGOJSON), which collects it from Yugipedia
  (https://yugipedia.com), Yaml Yugi (https://github.com/DawnbrandBots/yaml-yugi) and YGOPRODeck. The Yugipedia
  content is © Yugipedia contributors and licensed under the Creative Commons Attribution-ShareAlike 4.0
  International License (CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/).
  Changes by Bent°Corner: only the prints of the Japanese, Korean, Asian-English and Spanish regions and the card
  names in other languages were taken, filtered and converted into an SQLite database; the card ID (passcode) links
  them to cards.sqlite. Nothing from cards.sqlite is in this file.
  This file is licensed under CC BY-SA 4.0 as well: you may share and adapt it under that license. Bent°Corner's terms
  of use do not restrict it. No warranty – see section 5 of the license. Card names are © Konami; the license
  covers only the compilation, not Konami's rights.

  YGOJSON – MIT License
  Copyright 2024 iconmaster

{mit}

Yu-Gi-Oh!
  Yu-Gi-Oh! is a trademark of Konami Digital Entertainment; card texts and images © 4K Media Inc. / Konami.
  Bent°Corner is not affiliated with Konami or 4K Media.
""",
    **__import__("games").extra("PACK_LICENSES", {}),   # private games (games/extras.py)
}

# The web app's packs (/dl/web/<game>/, tools/publish_web.py) hold other files than the desktop's: card data as JSON,
# the recognition index, names in other languages (wording: legal 02.11., Legal\bentcorner\2026-11-02-web-pokemon-yugioh.md)
RECOGNITION = """index.bin, meta.json, scale.bin – recognition index
  Image fingerprints computed by Bent°Corner from {source} card images. They contain no card images.
"""
WEB_PARTS = {
    "mtg": """
cards.json, details.json – card data
  From Scryfall's bulk data (https://scryfall.com), converted by Bent°Corner. Card images are not in this pack: the
  app loads them from Scryfall. Bent°Corner is not affiliated with Scryfall.

""" + RECOGNITION.format(source="Scryfall's") + """
names-<lang>.json – card names in other languages
  From MTGJSON (https://mtgjson.com), MIT License:

  MIT License
  Copyright (c) 2018-Present Zach Halpern

{mit}

Magic: The Gathering
  Bent°Corner is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards.
  Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.
  https://company.wizards.com/en/legal/fancontentpolicy
""",
    "pokemon": """
cards.json, details.json, names-<lang>.json – card data, details and names in other languages
  From TCGdex (https://tcgdex.dev, https://github.com/tcgdex/cards-database), converted by Bent°Corner. Marketplace
  links in cards.json were corrected by Bent°Corner from TCGdex, Cardmarket and TCGplayer data. MIT License:

  MIT License
  Copyright (c) 2021 TCGdex

{mit}

  Print variants (normal, holofoil, reverse holofoil …) were supplemented by Bent°Corner from TCGplayer product
  data via TCGCSV (https://tcgcsv.com).

""" + RECOGNITION.format(source="TCGdex") + """
Card images (not in this pack)
  From TCGdex, through the Bent°Corner image mirror. For English cards TCGdex has no image of, the mirror holds
  supplementary images from pokemontcg.io (https://pokemontcg.io), fetched once by Bent°Corner.

Pokémon
  Pokémon, card names and images are property of Nintendo, Creatures Inc., GAME FREAK inc. and The Pokémon Company.
  Bent°Corner is not produced, endorsed, supported or affiliated with Nintendo or The Pokémon Company.
""",
    "yugioh": """
cards.json, details.json, names-de.json, names-fr.json, names-it.json, names-pt.json – card data
  From YGOPRODeck (https://ygoprodeck.com, API: https://ygoprodeck.com/api-guide/), converted by Bent°Corner. Card
  images are self-hosted by Bent°Corner, as YGOPRODeck requires; they are not part of this pack.

""" + RECOGNITION.format(source="the") + """
names-es.json, names-ja.json – card names in other languages
  From YGOJSON (https://github.com/iconmaster5326/YGOJSON), which collects them from Yugipedia
  (https://yugipedia.com), Yaml Yugi (https://github.com/DawnbrandBots/yaml-yugi) and YGOPRODeck. The Yugipedia
  content is © Yugipedia contributors and licensed under the Creative Commons Attribution-ShareAlike 4.0
  International License (CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/).
  Changes by Bent°Corner: only the card names were taken, filtered and converted; they are not mixed into cards.json.
  These files are licensed under CC BY-SA 4.0 as well: you may share and adapt them under that license. Bent°Corner's
  terms of use do not restrict them. No warranty – see section 5 of the license. Card names are © Konami; the license
  covers only the compilation, not Konami's rights.

  YGOJSON – MIT License
  Copyright 2024 iconmaster

{mit}

Yu-Gi-Oh!
  Yu-Gi-Oh! is a trademark of Konami Digital Entertainment; card texts and images © 4K Media Inc. / Konami.
  Bent°Corner is not affiliated with Konami or 4K Media.
""",
}


def text(key, web=False):
    """LICENSES.txt for a pack ("mtg", "pokemon", "yugioh" …); web=True: the web app's pack (/dl/web)."""
    mit = "\n".join(("  " + line) if line else "" for line in MIT.splitlines())
    return HEAD.format(key=key) + (WEB_PARTS if web else PARTS)[key].format(mit=mit)


def write(key, folder, web=False):
    """Write LICENSES.txt into folder (only if the content changed – keeps the checksum stable). -> path"""
    p = pathlib.Path(folder) / NAME
    t = text(key, web)
    if not p.exists() or p.read_text("utf-8") != t:
        p.write_text(t, "utf-8", newline="\n")
    return p
