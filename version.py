"""Version von Bent°Corner – die einzige Stelle, an der sie steht.

Angezeigt unter Einstellungen → Rechtliches; build.ps1 schreibt daraus die Versionsinfos der .exe
(python version.py -> version_info.txt) und die Patch-Historie (patchnotes.py, aus den Commits „vX.Y.Z: …“).
Vor 1.0 = Beta.
"""
import pathlib
import re

# Arbeitsstände haben vier Stellen und zählen nach dem LETZTEN Ship (Oliver/Gordon 13.11.2026): nach 0.9.8 geht es mit
# 0.9.8.100, 0.9.8.101 … weiter – nur hier auf dem PC und auf GitHub, nie auf dem Update-Server. Erst wenn der Nutzer
# „shippen“ sagt, wird daraus die nächste Version mit drei Stellen (release_of: 0.9.9) gebaut und mit
# tools/publish_release.py veröffentlicht (das verweigert vierstellige). Danach geht es mit <Ship>.100 weiter.
# Die nächste freie Nummer für PC und Web: docs/VERSIONEN.md.
VERSION = "0.9.9"


# „Was ist neu?“ nach einem Update: je geshippter Version höchstens 5 kurze Punkte (mehr liest keiner) – englisch,
# Deutsch in locales/de.py. Alles Weitere bleibt unter Einstellungen → Updates.
HIGHLIGHTS = {
    "0.9.9": [   # legal 14.11. via lead – verbatim; the name „Scalper Invasion“ is free (Oliver, TMview 14.11.)
        'Wishlist cards while scanning: if you scan a card from your wishlist, the scan page shows it right away, and Bent°Corner takes it off the list – you can turn this off per list. New in the scan dock: a volume slider.',
        'An easier start: setting up now takes five short steps, and the new installer is dark, asks for your language first and lets you choose where your collection is kept.',
        "Adding devices now also works without a protection code – the code stays optional. If you have set one up, you still enter it. Codes are now shown with spaces instead of dashes, so they're easier to type.",
        'The mini game is now called “Scalper Invasion” and also runs during setup – for example while the card data is loading.',
        'Scan Studio uploads are now only available in Full Orbit.',
    ],
    "0.9.8": [   # hotfix (Oliver/Gordon 13.11.): nicknames.json was missing in the 0.9.7 package
        "Fixes a bug that kept the online backup from starting on the PC.",
    ],
    "0.9.7": [   # Oliver 06.11. + lead/legal 07.11./08.11.: sync, devices, protection code, backup, tickets + sharing rules (legal)
        'New in Full Orbit: your collection, decks, lists, binders and more can be backed up online, end-to-end encrypted, and kept in sync between your devices – one switch, “Online backup and sync”, which you can turn off at any time.',
        'Your devices and backups are simpler: each device with its name, add one with a code, remove one with ✕; online and offline backups in two boxes.',
        "New: the protection code. It's optional. If you have one, you need it to add or remove devices – and with it you get your online backup back even if all your devices are gone.",
        'Friends and trading are now only in Full Orbit; what you share with whom, you choose per friend under “Shared with friends”. Saved friends are kept. If you shared your whole library before, the app asks you once whether to keep doing so.',
        'In Core the app no longer shows prices – prices are available from Near Orbit on.',
    ],
    "0.9.6": [
        "The Bent°Corner icon next to the clock: pin it once and it stays there – even after updates",
        "Loading animation: cards fade in visibly and sink away when loading is done – the start window shows card after card",
        "Cleaner share pictures: no shadows under the cards, prices at the same distance",
        "Several Bent°Corner folders (e.g. a USB stick and your PC) no longer get in each other's way",
    ],
    "0.9.5": [
        "A new logo – the program icon turns light or dark to match Windows",
        "A new loading animation: a card with a dog-ear gets smoothed out",
        "Scanning: the search stays open while you pick the card up to look at it – and you get at most one question per card",
        "“Edit card” only saves with “Replace”, and columns and sections can be shown or hidden with a click",
        "Smaller screens: card search and questions now fit at 1280×720 too – plus a 1st Edition hint for old Pokémon cards",
    ],
    "0.9.4": [
        "Card search: find cards by year and artist, every line shows the set name and #/n – and the print and language question comes right in the search",
        "Scan page: a calm hint instead of a search popping up, the status line keeps running, and “End scan” confirms what was saved",
        "Group by: the path shows as chips, and each level can be switched off and on",
        "Import knows files from other games and offers to switch – and Yu-Gi-Oh! prints from Japan, Korea and Spain are back",
        "More Pokémon pictures and better recognition of older cards (EX, Diamond & Pearl, Platinum) – and friends' changes arrive right away again",
    ],
    "0.9.3": [
        "Scan page in a new look: every hit gets its own tile, and the buttons appear when you point at a card",
        "Library: “Group by” splits your collection like a tree – now also in “All cards” – and the “Select” button picks several cards at once",
        "SCAN° asks briefly when the picture isn't a sure match – instead of counting the wrong card",
        "Prices and images: Yu-Gi-Oh! shows the right price for every print (many used to show the card's cheapest one), and more Pokémon cards have a picture",
        "More stable: cameras up to 4K run smoothly, and if Bent°Corner sits in OneDrive, Dropbox & co., the program itself now lives in a local folder – your data stays where it is",
    ],
    "0.9.2": [
        "Bent°Corner Orbit: choose in three levels what leaves your PC – Core, Near Orbit, Full Orbit. We ask you once right after this; preselected is what you had set so far",
        "New names: sessions are now “Logs”, together with the statistics under “Logs / Stats” (Import/Export at the top). “Delete” is now “To the trash” – everything stays there for 60 days and can be restored",
        "Your library now comes from your logs: every change to a card leaves a line. Everything from before is in one log “By hand (everything until … combined)”",
        "Scan page: one “Scan” tile for log and cards with a big “End scan” (with undo), new tile “Biggest hit”",
        "Library: “Group by” splits your collection like a tree (set, rarity, colour …). Choose several cards at once – Ctrl/Shift-click or draw a frame – and put them on lists, into decks or in the trash",
    ],
    "0.9.1": [
        "Scanner: faster and more reliable – clear cards count right away, text recognition runs on the graphics card, no more double counts when placing or lifting a card",
        "Friends across games: switch a friend's games on at the top, several at once shows them mixed – put cards on your lists of that game or into the trade",
        "Smoother everywhere: views are only built when you open them, SCAN° runs in its own process (no more freezes while it loads) – much faster on PCs without a graphics driver",
        "Sounds while scanning (tick, hit, special sound from 50 €) and cameras up to 4K",
        "Search “name number” or “name set” in every game (e.g. “pikachu sv8”), Pokémon images in every language, binders open right in the trade",
    ],
}


# a heading above a version's points – and versions whose points stand alone: older skipped versions' highlights are
# not added below them (the sharing rules of 0.9.7 must not drown in old news)
HIGHLIGHT_TITLES = {"0.9.7": 'Sync with your devices – and new rules for friends, sharing and prices',
                    "0.9.9": 'Wishlist cards while scanning – and an easier start'}
HIGHLIGHT_ONLY = {"0.9.7"}


# Counting work-in-progress builds (Oliver/Gordon 13.11.2026): after the LAST ship – 0.9.8.100, 0.9.8.101 … come after
# 0.9.8 and lead to 0.9.9. Before (up to 0.9.8.0) they counted towards the NEXT ship (0.9.7.58 = before 0.9.7); those
# old numbers stay valid in the history. New-style builds start at AFTER_SHIP_FROM so they never meet the old ones.
AFTER_SHIP_FROM = 100
NEW_COUNT_FROM = (0, 9, 8)


def _after_ship(parts):
    """A work build counted after its ship (new style)?"""
    return len(parts) == 4 and tuple(parts[:3]) >= NEW_COUNT_FROM and parts[3] >= AFTER_SHIP_FROM


def _vkey(v):
    """Order of versions: a ship sits after its old-style work builds (0.9.7.58 < 0.9.7) and before its new-style ones
    (0.9.8 < 0.9.8.100 < 0.9.9)."""
    parts = [int(x) for x in str(v).split(".") if x.isdigit()]
    if len(parts) == 4:
        return tuple(parts)
    ship = parts + [0] * (3 - len(parts))
    return (*ship, AFTER_SHIP_FROM - 1 if tuple(ship) >= NEW_COUNT_FROM else 10 ** 9)


def highlights_since(seen, current=None):
    """„What's new?“ after an update: (title, points) of the shipped versions after `seen` up to `current` – the
    newest first, at most 5 points. A version in HIGHLIGHT_ONLY stands alone (with its title); without one the title is
    "". Work-in-progress builds never show a shipped version's points (0.9.7 > 0.9.7.45)."""
    cur = _vkey(current or VERSION)
    rel = [r for r in sorted(HIGHLIGHTS, key=_vkey, reverse=True) if (not seen or _vkey(seen) < _vkey(r)) and _vkey(r) <= cur]
    only = [r for r in rel if r in HIGHLIGHT_ONLY]
    if only:
        return HIGHLIGHT_TITLES.get(only[0], ""), list(HIGHLIGHTS[only[0]])[:5]
    return (HIGHLIGHT_TITLES.get(rel[0], "") if len(rel) == 1 else ""), [t for r in rel for t in HIGHLIGHTS[r]][:5]


def is_release(v=None):
    """Version zum Veröffentlichen (drei Stellen)? Vier Stellen = Arbeitsstand."""
    return len(str(v or VERSION).split(".")) == 3


def release_of(v=None):
    """Die Version, als die dieser Arbeitsstand geshippt würde: neu (nach dem letzten Ship) 0.9.8.100 -> 0.9.9, alt
    0.8.20.3 -> 0.8.20; eine geshippte Version ist ihr eigenes Release."""
    parts = [int(x) for x in str(v or VERSION).split(".") if x.isdigit()]
    if _after_ship(parts):
        return f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
    return ".".join(str(p) for p in parts[:3])


def label():
    return f"v{VERSION}"


def dev_build():
    """The DEV version (Oliver/Gordon 13.11.2026): every build WITHOUT the ship flag – Oliver's app\\, test copies, the
    source. It shows „DEV <version>“ and the red mark and talks only to the test box (net/boxbase.py)."""
    from collection import syncrun
    return not syncrun.ship_build()


def write_version_info():
    """Versionsnummer in version_info.txt (PyInstaller --version-file) übernehmen."""
    path = pathlib.Path(__file__).resolve().parent / "version_info.txt"
    nums = [int(x) for x in re.findall(r"\d+", VERSION)[:4]]
    while len(nums) < 4:
        nums.append(0)
    tup = "(" + ", ".join(str(n) for n in nums[:4]) + ")"
    s = path.read_text("utf-8")
    s = re.sub(r"filevers=\([^)]*\)", f"filevers={tup}", s)
    s = re.sub(r"prodvers=\([^)]*\)", f"prodvers={tup}", s)
    s = re.sub(r"StringStruct\('FileVersion', '[^']*'\)", f"StringStruct('FileVersion', '{VERSION}')", s)
    s = re.sub(r"StringStruct\('ProductVersion', '[^']*'\)", f"StringStruct('ProductVersion', '{VERSION}')", s)
    path.write_text(s, "utf-8")


# corrections of old lines (committed in English, or wording that changed since) – the history shows these
NOTE_FIX = {
    # 0.9.7.35: vier Commits – die Zeile soll die neue Einstellungsseite nennen, nicht den letzten Test
    "0.9.7.35": "Einstellungen → „Bent°Corner löschen“: deine Daten auf dem Server und/oder deine Sammlung auf diesem PC "
                "löschen – alles auf einer Seite, mit klarer Rückmeldung, ob der Server wirklich gelöscht hat",
    # 0.9.7.7: zwei Commits – der Abschnitt ist bis zum Öffentlich-Machen ausgeschaltet
    "0.9.7.7": "Vorbereitung Open Source: Lizenz-Abschnitt (GPL-3.0) für Einstellungen → Rechtliches mit der "
               "mitgelieferten LICENSE zum Lesen ohne Internet – bleibt ausgeschaltet, bis der Quellcode öffentlich ist",
    # 0.9.7.4: zwei Commits – die Zeile soll das Wichtige (DirectML) nennen, nicht nur den Build-Schutz
    "0.9.7.4": "DirectML aus Windows statt mitgeliefert – die exe enthält keine DirectML.dll mehr (10 MB kleiner); "
               "SCAN° rechnet mit der DirectML aus Windows ab Version 1.15.0, sonst auf der CPU (Grund im Log). Stürzt "
               "die Grafikkarte ab, bleibt SCAN° auf der CPU statt neu abzustürzen – bis zum nächsten Update. Dazu "
               "Build-Schutz: keine fremden Bibliotheken aus dem PATH (conda/msys) mehr in der exe",
    # 0.9.3.16: „515 → 39 ms“ war mit Pythons Standard-Umschaltzeit gemessen, die App nutzt 0,5 ms (setup_threads)
    "0.9.3.16": "Flüssiger mit laufender Kamera (Tester-Log 0.9.2) – das Entladen von SCAN° hält die Oberfläche nicht "
                "mehr an (das Beenden des Arbeitsprozesses läuft im Hintergrund, vorher bis 300 ms); Formulare wie der "
                "Kamera-Dialog lesen beim Regler-Ziehen nur noch den geänderten Baustein neu (19 → 5 ms je Schritt); die "
                "Bibliothek holt jede Kachel in einem Aufruf statt in elf; die Log-Seite ohne Binding-Schleife beim "
                "Scrollen; das Programm-Protokoll vom vorigen Start bleibt als bentcorner-previous.log, dazu "
                "„Protokoll-Ordner öffnen“ unter Über Bent°Corner (Freunde darin nur als ID-Kürzel)",
    "0.9.2.57": "Der Reiter „Test“ heißt jetzt „Spielen“ – Untertitel „Teste deine Decks – bald auch gegen Freunde“; "
                "die bisherigen Erklärungen stehen als Tooltip an „Chancen“ und „Spieltisch“",
    # 0.9.2.91 (Oliver): beim Scannen nirgends „KI“ – SCAN° ist unsere smarte Kartensuche, auch in alten Zeilen
    "0.9.2.74": "Die Erkennung heißt jetzt SCAN° – überall (Scan-Seite, Einstellungen, Datenschutz)",
    "0.9.2.45": "Webseite (noch nicht online) – neue Seite „Transparenz“ (noch nicht verlinkt): wie Bent°Corner entsteht, "
                "welche zwei fertigen Bausteine in der App stecken, was der Fingerabdruck macht und dass mit Bildern oder "
                "Nutzerdaten nichts trainiert wird; alle Seiten bekommen alle Sicherheits-Header und gehen auch ohne .html; "
                "SEO ohne Google-/Bing-Anbindung (Entscheidung des Nutzers)",
    "0.9.1.20": "SCAN° in eigenem Prozess – Fingerabdruck und Texterkennung (Grafikkarte) rechnen in einem Arbeitsprozess: "
                "die Oberfläche hält beim Laden von SCAN° nicht mehr an (auf schwachen Rechnern bis ~13 s), "
                "Grafiktreiber-Absturz trifft nur den Prozess (Neustart in ~1 s), Entladen nach Leerlauf gibt den Speicher "
                "ganz frei; gleiche Ergebnisse (bitgleich), Rückfall auf früher, falls er nicht startet; Maus auf „Scan“ "
                "lädt SCAN° schon vor",
    "0.8.21.7": "Scan-Art-Auswahl überall raus (nur noch Fingerabdruck), Wert der Sammlung neu: zählt jede Karte erst ab "
                "Besitz (Session-Datum) und erstem echten Preis, Striche für Zugänge, gestrichelt die ältesten Karten – in "
                "der Statistik (Sammlung) und in der Bibliothek über den unterstrichenen Gesamtwert (klappt unten auf, ✕, "
                "Mehr Statistik); Pokémon: N/H/RH statt F in der Pack-Liste, Holo/Reverse Holo als Namen, Zusatzinfos "
                "neben der großen Karte aus der eigenen Kartendatenbank (Typ, KP, Schwäche, Rückzug, Ausführungen, "
                "Künstler, Drucke); große Karte lädt fehlende Bilder nach (Platzhalter-Karte bis dahin); keine "
                "„–“-Seltenheit mehr",
    "0.7.60": "Pokémon ohne Download – mitgelieferter Fingerabdruck-Index und Kartendatenbank",
    "0.9.2.46": "Notschalter je Spiel – muss ein Spiel auf Bitte des Rechteinhabers vom Netz, verschwindet es bei allen "
                "aus der Spielauswahl (mit Hinweis und Grund, offenes Spiel wechselt zu Magic, Sammlung bleibt); "
                "Lorcana-Bilder kommen über unseren Bild-Spiegel (jedes Bild einmal beim Verlag geholt); Rechtliches "
                "und Webseite entsprechend; Webseite: neue Startseite mit Bent°Corner-Knopf, Transparenz-Seite im Fuß, "
                "Handy-Menü mit Trennlinien",
    "0.9.2.73": "Server – unter der alten Adresse antwortet der Download-Server nur noch für /dl/ (Updates, Pakete, "
                "Bild-Spiegel bleiben für ältere Apps erreichbar)",
    "0.9.2.59": "Umzug auf bentcorner.app – eigene Webseite (Kontakt hello@bentcorner.app, mit Impressum, Datenschutz "
                "und Nutzung); Download und Briefkasten auch unter bentcorner.app (die App nutzt noch die alte Adresse)",
    "0.9.2.58": "Server – Download-Bremse für große Dateien gelockert, Fehlerantworten werden nicht mehr ein Jahr "
                "gespeichert; Regel für Fingerabdruck-Teile vorbereitet",
    "0.9.2.54": "Server – Download-Server begrenzt je Gerät, Repo entspricht wieder dem gehärteten Server-Image",
    "0.9.2.49": "Webseite – Besucherzähler zählt nur noch echte Besucher (keine Roboter, keine eigenen Prüfungen); "
                "Datenschutz entsprechend",
    "0.9.2.25": "Briefkasten-Server – Übersicht nur mit Zahlen abrufbar (noch nicht auf dem Server)",
    "0.8.16": "Beispiel-Freunde und Beispiel-Wuensche entfernt; Neuigkeiten vom Team auch aus dem Briefkasten "
              "(Team-signiert)",
    "0.9.7.10": "Vorbereitung Open Source: Der öffentliche Quellcode wird aus dem Hauptstand erzeugt und geprüft – die "
                "exe daraus ist dasselbe Programm",
    "0.9.7.11": "Vorbereitung Open Source: Patch-Historie überarbeitet",
    # 0.9.7.13 (legal 01.11.2026): Zeilen über ein pausiertes Spiel neutral – das private Programm setzt seine eigenen
    # Fassungen wieder ein (games.extra("NOTE_FIX"), nicht im öffentlichen Quellcode)
    '0.9.7.9': 'Programm läuft auch ohne die Beschreibung eines einzelnen Spiels – ein früher installiertes Datenpaket dafür bleibt dann einfach ungenutzt (packs.PACKS nur für vorhandene Spiele, games.load meldet KeyError statt ImportError); Tests überspringen fehlende Teile (tests/optional_games.py). Vorbereitung für den öffentlichen Quellcode',
    '0.9.7.6': 'Scan-Seite ohne SCAN° Engine (models/ fehlt): Lorcana scannt über die Kartennummer, andere Spiele über den Kartentext – mit ehrlichem Hinweis statt endlosem „Kartendaten werden geladen …“; Bindungsschleife labelMode in ScanTiles.qml behoben',
    '0.9.3.24': 'Rechtliches nennt nur Spiele, die gerade angeboten werden – ein pausiertes Spiel ist aus „Quellen“ und „Datenschutz“ heraus und kommt beim Zurückholen von selbst wieder; Pokémon: Werkzeug für ergänzende Bilder von pokemontcg.io (805 englische Karten, die TCGdex nicht hat – einmal geholt, für unseren Bild-Spiegel), Dank an pokemontcg.io in Quellen, Pokémon-Hinweis und Lizenzdatei',
    '0.9.3.22': 'Ein Spiel vorerst pausiert – es wird nicht mehr angeboten (Spielknopf, Einstellungen, Profil, Binder, Scan-Studio, Rechtliches), auch nicht über das lokale Freischalten auf diesem PC; wer es als aktives Spiel gespeichert hat, landet beim Start sauber in Magic, die Sammlung dazu bleibt unberührt; für das Spiel wird kein Datenpaket mehr geholt (games.WITHDRAWN)',
    '0.9.2.80': 'Nach Review – Menüs öffnen an der Klickstelle, Sortierung als Dropdown am Knopf (dieselbe Auswahl noch einmal kehrt um); „Log“ statt „Session“ überall, im Reiter Log oben „Einträge | Statistik“; Log zeigt alle Karten und wechselt schneller, Beträge nie abgeschnitten; Statistik wieder mit Kästen, der Wertgraph baut sich ruhig auf; Schalter als Schalter erkennbar (Lämpchen im Schlitz); Reiter oben wieder kurz und gleich breit („Import“); ein Spiel ohne Kartendaten meldet freundlich, dass sie mit dem nächsten Update kommen',
    '0.9.2.62': 'Die Reiter oben behalten ihren Text länger – ob Text, kleiner Text oder nur Symbole, richtet sich jetzt nach den echten Textbreiten (z. B. bei 1600 px mit laufendem Download); Sessions „Als Liste“ öffnet die neue Liste gleich in der Bibliothek, mit Weg zurück zu den Sessions',
    '0.9.2.56': 'Datenpaket, das der Server noch nicht hat (ein neues Spiel bis zum Release): ein ruhiger Hinweis statt Fehler mit „Nochmal versuchen“',
    '0.9.2.51': 'Lorcana – schräg gehaltene Karten werden öfter erkannt: klappt das Lesen der Kartenzeile nicht, liest der Scanner sie noch einmal an den echten Ecken der Karte (nur dann, kostet sonst nichts)',
    '0.9.2.50': 'Weiteres Kartenspiel vorbereitet (kommt mit einem späteren Release); behoben: Lorcana zählte seit 0.9.2.44 oft nicht, weil die Kartensuche zu früh aufging (jetzt 4 s bei Spielen, die nur die Kartenzeile lesen), und eine ruhig liegende Karte blieb manchmal hängen',
    '0.9.2.30': 'Aufgeräumt hinter den Kulissen – Spielbeschreibungen erklären ihre Zusatzteile an einer Stelle, Set-Liste aus der Kartendatenbank für alle Spiele gleich, ungenutzter Code und alte Übersetzungen entfernt, Spielstile und Bracket-Begründungen englisch im Code (Deutsch unverändert), neue Tests für Sammlung/Rückgängig und Übersetzungen; sichtbar: Foil-Chip der Bibliothek zeigt bei Lorcana „Foil“ statt „Holo“, Englisch „1 combo“/„3 combos“ statt „combo(s)“',
    '0.9.2.28': 'Scanner zählt keine angeschnittene Lorcana-Karte mehr falsch (Zeile am Bildrand zählt nur, wenn der Name der Karte passt); Sammlung und Wunschliste aus Textlisten lesen auch Lorcana („(1) 5“) und Simulator-Listen („4xAB01-016“); Einstellungen → Kartendaten beschreibt die Quelle jedes Spiels; englische Oberfläche ohne deutsche Reste beim Pokémon-Download; Tests laufen nie mit echten Daten',
    '0.9.2.24': 'Aufräumen und Absichern – Tagespreise aller Spiele aus einem gemeinsamen Baustein (Pokémon, Yu-Gi-Oh!, Lorcana …); ein gemeinsames Gedächtnis für fehlende Bilder; Hilfswerkzeuge fragen Online-Dienste genauso höflich wie die App; Wechselkurse nach einem Fehlschlag erst nach einer Stunde wieder; behoben: eine präparierte Sicherungsdatei konnte beim Wiederherstellen neben den Zielordner schreiben, eine beschädigte Preisverlauf-Datei blieb gesperrt; rund 60 neue automatische Tests (Sicherung, Binder, Tausch, Preisverlauf)',
    '0.9.2.21': 'Lorcana-Feinschliff – Schnellsuche „hades 5“ findet Nummer 5 (zwei Zahlen wie gedruckt: „hades 5 1“), Set-Namen auch auf Deutsch („das erste kapitel hades“), exportierte Lorcana-Decks lassen sich wieder einlesen; Zähler auf der Scan-Seite je Spiel (Lorcana Enchanted/Legendary, Pokémon Ultra+/Rare, Yu-Gi-Oh! Secret+/Ultra); neue Kartendaten-Stände ohne erneuten Download; Tests für Lorcana',
    '0.9.2.19': 'Weiteres Kartenspiel vorbereitet (noch nicht freigeschaltet) – erweiterte Suche mit Farbe, Kategorie, Kosten, Kraft, Konter, Leben, Attribut, Typen, Schlüsselwörtern, Seltenheit und Block, Decks mit Leader-Regeln, Test-Seite mit Leben und DON!!, Import von Simulator-Listen; Deck-Abzeichen zählen je Kartennummer',
    '0.9.2.12': 'Rücksichtsvoller im Netz – neue Spiele-Quellen (Lorcana, Riftbound) mit großzügigen Abständen; meldet ein Dienst einen Serverfehler, lässt Bent°Corner ihn mindestens 30 Sekunden in Ruhe (wie bei „zu viele Anfragen“); Preis-Server fragt TCGCSV langsamer ab',
    '0.9.2.11': 'Vorbereitung neue Spiele – Rechtshinweise für Lorcana und Riftbound (erscheinen unter Rechtliches erst, wenn das Spiel fertig ist), Netzregeln für ihre Datenquellen, Preis-Server holt TCGplayer-Preise auch für Lorcana und Riftbound',
    '0.9.2.23': 'Testphase Scanner – Scan-Prüfstand im Repo (tools/scan-bench, feste Kartensätze je Spiel inkl. japanischer Pokémon-Drucke und Lorcana-Locations, Sollwerte, meldet Verschlechterungen), neue Unit-Tests (Chancen der Test-Seite, Session-Summen, KI-Worker-Absturz und _run_lock, verschwundene Drucke, Pokémon-Spiegel-Rückfall, Magic-Deckregeln, Simulator-Listen); Lorcana: ein knapper Bildtreffer zählt nicht mehr, wenn der Fingerabdruck die Karte kaum kennt',
    '0.8.23.8': 'eigene Pixel-Symbole je Spiel (keine Logos der Hersteller) im Spielknopf und in der Spielzeile – Magic fünf Farben, Pokémon Blitz, Yu-Gi-Oh Auge, Lorcana Funkelstern, Riftbound Strudel im orangen Ring (tools/game_icons.py)',
}
# single words in old lines (0.9.2.91, Oliver: beim Scannen nirgends „KI“) – applied to every line after NOTE_FIX
NOTE_WORDS = [("KI-Transparenz", "Transparenz-Seite"), ("KI-Worker-Absturz", "SCAN°-Prozess-Absturz"),
              ("abwechselnd mit der KI", "abwechselnd mit SCAN°"), ("KI nach 1 Minute ohne Scan raus", "SCAN° nach 1 Minute ohne Scan raus"),
              ("KI erst beim Scannen", "SCAN° erst beim Scannen"), ("nur noch KI-Scan", "nur noch Fingerabdruck-Scan"),
              # 0.9.7.11 (öffentlicher Quellcode): Personen, Chat-Namen und interne Werkzeuge nicht in der Historie
              ("Olivers Testrunde", "Testrunde"), ("Nach Olivers Test der Ship-exe", "Nach dem Test der Release-Fassung"),
              ("Olivers 0.9.2-Test", "Test von 0.9.2"), ("Nach Olivers Test von 0.9.2", "Nach dem Test von 0.9.2"),
              ("nach Olivers Test von 0.9.2", "nach dem Test von 0.9.2"), ("aus Olivers Test", "aus dem Test"),
              ("Nach Olivers Review .101", "Nach Review"), ("Nach Olivers Review", "Nach Review"),
              ("nach Olivers Review", "nach Review"), ("nach Olivers Wünschen", "nach Rückmeldungen"),
              ("(Oliver, live 0.9.2: ", "(Rückmeldung zu 0.9.2: "), ("(Oliver, live 0.9.2)", "(Rückmeldung zu 0.9.2)"),
              ("(Oliver: ", "(Rückmeldung: "), (" (Oliver)", ""), (" bei Oliver)", ")"),
              ("Owner-Konsole", "Verwaltung"),
              ("Owner-Werkzeug", "Verwaltungswerkzeug"), ("Owner-Reiter", "Verwaltung"), ("Owner: ", "Verwaltung: "),
              # keine Dateien nennen, die nicht im öffentlichen Quellcode stehen (legal; export_public.py prüft das)
              ("Bau-Skript tools/fix_pokemon_market.py", "ein Bau-Skript"), ("Scan-Prüfstand im Repo (tools/scan-bench, ",
               "Scan-Prüfstand ("), (", Studio-Platz 40 GB, tools/deploy_box.py", ", Studio-Platz 40 GB"),
              ("ein Sprachpaket (sprachen/de.py; ", "ein Sprachpaket (locales/de.py; "),   # Ordner heißt heute locales/
              (" ┃ ", " | ")]   # 0.9.7.23: ┃ hat keine Schrift der App (BC Symbols)


def _words(text):
    try:   # role and chat names (games/extras.py, private) – applied in the public history too
        from games import extra
        hide = extra("NOTE_WORDS", [])
    except ImportError:
        hide = []
    for o, n in [*NOTE_WORDS, *hide]:
        text = text.replace(o, n)
    return text


def write_patchnotes(public=False, ref="HEAD", target=None):
    """Patch-Historie aus git: jeder Commit „vX.Y.Z: Titel“ wird eine Zeile (patchnotes.py, kommt in die .exe).
    public: ohne die privaten Fassungen (games/extras.py) – so baut tools/public/export_public.py die öffentliche
    Historie aus <ref>; target: wohin (sonst patchnotes.py hier)."""
    import subprocess
    root = pathlib.Path(__file__).resolve().parent
    fix = dict(NOTE_FIX)
    if not public:
        try:
            from games import extra
            fix.update(extra("NOTE_FIX", {}))
        except ImportError:
            pass
    try:
        out = subprocess.run(["git", "log", "--pretty=%ad|%s", "--date=short", ref], cwd=root, capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return  # kein git: die vorhandene patchnotes.py bleibt
    notes = []
    for line in out.splitlines():
        date, _, subject = line.partition("|")
        m = re.match(r"v(\d+\.\d+\.\d+(?:\.\d+)?):\s*(.*)", subject)
        if m and m.group(2).startswith("Patch-Historie"):   # nur die erzeugten Dateien nachgezogen
            continue
        if m and not any(v == m.group(1) for v, _, _ in notes):
            notes.append((m.group(1), date, m.group(2)))
    if ref == "HEAD" and VERSION not in {v for v, _, _ in notes}:  # Bauen vor dem Commit: aktuelle Version trotzdem oben
        notes.insert(0, (VERSION, "", ""))
    notes = [(v, d, _words(fix.get(v, t))) for v, d, t in notes]
    body = "".join(f"    ({v!r}, {d!r}, {t!r}),\n" for v, d, t in notes)
    pathlib.Path(target or root / "patchnotes.py").write_text('"""Patch-Historie – erzeugt von version.py (nicht von Hand ändern)."""\n'
                                        f"NOTES = [\n{body}]\n", "utf-8")


if __name__ == "__main__":
    write_version_info()
    # the public source (tools/public/export_public.py) brings the finished patch history along – its repository
    # has only one commit per release, rebuilding from there would shorten the history
    if not (pathlib.Path(__file__).resolve().parent / ".public-build").exists():
        write_patchnotes()
    print("Version", label())
