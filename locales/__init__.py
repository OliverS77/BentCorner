"""Sprachverwaltung – alle Sprachen der Oberfläche an einem Ort.

Die Oberfläche ist auf Englisch geschrieben (der englische Text im Code ist zugleich der Schlüssel). Jede weitere
Sprache ist eine Datei in diesem Ordner mit CODE, NAME, TEXTS und RULES (Vorlage: de.py).

Neue Sprache hinzufügen:
  1. locales/de.py kopieren, z. B. nach locales/fr.py
  2. dort CODE = "fr", NAME = "Français" setzen und die rechten Seiten von TEXTS/RULES übersetzen
  3. unten importieren und in LANGUAGES eintragen – fertig (Einstellungen → Sprache zeigt sie dann an)
Fehlende Übersetzungen findet:  python -m locales.check   (listet englische Texte ohne Übersetzung)

legacy_de.py ist die frühere Richtung (deutscher Text -> Englisch, bis v0.9.1.22): Sie übersetzt deutsche Texte, die
noch in alten Daten stehen (z. B. Listen- oder Ordnernamen) oder zur Laufzeit zusammengesetzt werden, ins Englische.
"""
from . import de, legacy_de

ENGLISH = ("en", "English")
LANGUAGES = [de]  # Reihenfolge in den Einstellungen: diese zuerst, dann Englisch


def all_languages():
    """[(Code, Name)] aller Sprachen (Deutsch vorn wie bisher, dann Englisch)."""
    return [(m.CODE, m.NAME) for m in LANGUAGES] + [ENGLISH]


def module(code):
    return next((m for m in LANGUAGES if m.CODE == code), None)
