# Ein neues Spiel einbauen

Bent°Corner kennt Spiele nur über eine **Spielbeschreibung** (`games/<spiel>.py`) und eine **Kartendatenbank** im
gemeinsamen Format (`carddb.SCHEMA`). Sammlung, Sessions, Bibliothek, Suche, Deckbau, Tausch, Tickets und Scan sind
für alle Spiele derselbe Code. Ein neues Spiel heißt also: zwei Dateien schreiben, Daten bauen, Paket schnüren.

## 1. Daten: `tools/build_<spiel>_db.py`

Aus **offenen Quelldaten** (ein Download, keine Anfrage je Karte – siehe `netpolite.py`) eine `cards.sqlite` bauen.
Die Spalten sind die von Magic. Ein Spiel legt seine Werte so hinein, dass die vorhandene Suche sie findet:

| Spalte        | Magic                 | Pokémon (Beispiel)                         | Wofür                              |
|---------------|-----------------------|--------------------------------------------|------------------------------------|
| `type_line`   | Legendary Creature — Elf | Pokémon — Stage1 — Fire / Trainer — Item | Kartentyp, „Stufe / Art“ (Wörter)  |
| `colors`      | WUBRG                 | Energietypen G R W L P F D M N Y C         | Farbfilter (`palette`)             |
| `oracle_text` | Regeltext             | Fähigkeiten + Attacken                     | Textsuche, Deck-Funktionen         |
| `keywords`    | Flying, Trample       | ex, ACE SPEC, Radiant, Regulierung H       | Merkmale, Deckregeln (`limits`)    |
| `power`/`cmc` | Stärke / Manawert     | KP / Rückzug                               | Wertebereiche (`ranges`)           |
| `legalities`  | {"modern": "legal"}   | {"standard": "legal"}                      | „Legal in“, Deckregeln (`legal`)   |
| `langs`       | Namen je Sprache      | DE FR IT ES PT, asiatische Sets            | Suche in allen Sprachen            |

Asiatische Drucke, die eigene Sets sind (Pokémon: SV1S …), kommen als eigene Sets mit `cards.lang` = ja usw. dazu.
`meta.pk_build` (bzw. ein eigener Schlüssel) hochzählen – vorhandene Installationen übernehmen die mitgelieferte
Datenbank dann von selbst und behalten ihre Preise (`carddb._from_bundle(upgrade=True)`).

## 2. Beschreibung: `games/<spiel>.py`

Von `base.Game` erben und nur überschreiben, was anders ist (alle Felder stehen oben in `games/base.py`):

- **Grunddaten:** `key`, `name`, `formats`, `default_format`, `type_order`, `card_types`, `supertypes`, `rarities`,
  `finishes`, `foil_word`, `card_px` (Seitenverhältnis), `pack_types`, `languages`.
- **Suche:** `palette`, `color_specials`, `color_hex`, `color_names`, `ranges`, `text_fields`, `adv_titles`,
  `adv_hidden`, `legal_short`, dann `adv_search = True`.
- **Deckbau:** `deck_rules` je Format (`size`, `exact`, `copies`, `limits`, `require`, `legal`), dazu `deck_curve()`,
  `deck_roles()`, `deck_kpis()`, `deck_unlimited()`. Magic-Zusätze (EDHREC, Commander, Kombos) sind `deck_extras`.
- **Preise:** `update_prices()` (eine Tagesdatei je Marktplatz) und `price_lookup()`.
- **Bilder und Scan:** `image_url()`, `lang_layout` (wo Name und Sprach-Wörter auf der Karte stehen),
  `finish_info()`.
- **Reiter:** `features` – was noch fehlt, zeigt „Coming soon“.

Dann in `games/__init__.py` bei `GAMES` auf `ready = True` setzen und in `load()` eintragen.

## 3. Erkennung und Paket

- `tools/build_fingerprints.py --game <spiel>` baut den Erkennungs-Index aus den Kartenbildern (`models/<spiel>/`).
- `tools/make_bundle.py` packt Datenbank und kleine Bilder fürs Offline-Paket (ein Paket je Spiel).

## 4. Prüfen

Ein Test wie `test_pksearch.py` / `test_pkdeck.py`: Datenbank übernommen, Suche je Abschnitt, Deckregeln, Reiter
ohne „Coming soon“, Spielwechsel hin und zurück.

## Ausblick: die nächsten Spiele

| Spiel      | Datenquelle (frei)                         | Besonderheiten                                                    |
|------------|--------------------------------------------|-------------------------------------------------------------------|
| Yu-Gi-Oh!  | YGOPRODeck-API (ein Dump aller Karten)     | ATK/DEF/Stufe als `power`/`toughness`/`cmc`; Main/Extra/Side; 40–60 Karten, 3 Kopien, Bannliste je Format; Karten 59 × 86 mm |
| Riftbound  | noch offen                                 | Legende + Champion (wie Commander), Runen-Deck                    |

Was dort wie „Commander“ funktioniert (ein Leader bestimmt die Farben), kann `deck_extras = ("commander",)` und die
vorhandene Farbidentität nutzen.
