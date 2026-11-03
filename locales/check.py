"""Fehlende Übersetzungen finden:  python -m locales.check [Sprachcode]   (Standard: alle Sprachen)

Sucht im Programm alle Aufrufe tr("…") bzw. tr(f"…") (und in qml/ alle shell.text("…")) und meldet englische Texte, die eine Sprache weder in TEXTS
noch über RULES kennt. (Stellen, die absichtlich noch deutsch im Code stehen – mehrdeutige Übersetzungen –, kennt
locales/legacy_de.py; die zählen nicht als fehlend.) Texte, die erst zur Laufzeit zusammengesetzt werden (tr(variable)), sieht das Werkzeug
nicht – die stehen meist in Listen wie FOLDS oder ITEMS und sind trotzdem in TEXTS einzutragen.
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = {".venv", "build", "dist", "locales", "tools", "__pycache__"}


PACKAGES = ("scanner", "cards", "collection", "net", "ui", "system", "games")


def _sources():
    """Alle Programmdateien: Wurzel (app.py …) und die Pakete."""
    return sorted([*ROOT.glob("*.py"), *[f for d in PACKAGES for f in (ROOT / d).glob("*.py")]])


def calls():
    """-> [(Datei, Zeile, Text, ist_fstring)] aller tr-Aufrufe mit festem Text."""
    out = []
    for path in _sources():
        if path.name.startswith(("test_", "out_")):
            continue
        try:
            tree = ast.parse(path.read_text("utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.append((path.name, node.lineno, arg.value, False))
            elif isinstance(arg, ast.JoinedStr):  # f-String: Platzhalter als „1“ einsetzen, dann über RULES prüfen
                parts = [v.value if isinstance(v, ast.Constant) else "1" for v in arg.values]
                out.append((path.name, node.lineno, "".join(parts), True))
    qml = re.compile(r'shell\.text\("((?:[^"\\]|\\.)*)"\)')
    for path in sorted((ROOT / "qml").rglob("*.qml")):  # Qt-Quick-Oberfläche: Texte über shell.text("…")
        for i, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            for m in qml.finditer(line):
                out.append((path.name, i, m.group(1).replace('\\"', '"').replace("\\n", "\n")
                            .replace("\\\\", "\\"), False))
    return out


def _als_spiel(text, rules):
    """f-String mit „1“ als Platzhalter: passt eine Regel, wenn dort jeder echte Spielname steht? (Regeln, die mit
    Absicht nur Spielnamen annehmen, z. B. „Switch to (Magic|Pokémon|…)“, sähen sonst wie fehlend aus.)"""
    try:
        from games import NICK
    except ImportError:
        return False
    namen = list(NICK.values())
    return bool(namen) and "1" in text and all(any(r.fullmatch(text.replace("1", n)) for r in rules) for n in namen)


def missing(mod):
    from . import legacy_de
    rules = [re.compile(p) for p, _ in mod.RULES]
    old = [re.compile(p) for p, _ in legacy_de.RULES]   # noch deutsch im Code: für Deutsch richtig, Englisch über legacy
    seen, res = set(), []
    for name, line, text, fstr in calls():
        if not text.strip() or text in seen:
            continue
        seen.add(text)
        if text in mod.TEXTS or any(r.fullmatch(text) for r in rules):
            continue
        if fstr and _als_spiel(text, rules):  # Platzhalter ist ein Spielname („Switch to {games.nick_of(…)}“)
            continue
        if mod.CODE == "de" and (text in legacy_de.TEXTS or any(r.fullmatch(text) for r in old)):
            continue
        if not re.search(r"[A-Za-zÄÖÜäöüß]{2}", text):  # nur Zahlen/Symbole
            continue
        res.append((name, line, text, fstr))
    return res


UI_CALLS = {"setText", "QLabel", "setToolTip", "addItem", "QPushButton", "GlowButton", "setPlaceholderText",
            "addAction", "setWindowTitle", "Chip", "QCheckBox", "QRadioButton", "QGroupBox", "setTitle", "QToolButton",
            "setLabelText", "information", "warning", "question", "critical", "showMessage", "setHtml", "setTabText",
            "addTab", "QAction", "notify", "set_text", "setStatusTip"}
GERMAN = re.compile(r"[äöüÄÖÜß]|\b(und|oder|nicht|der|die|das|mit|für|Karte|Karten|keine?|wird|hier|alle|neu|"
                    r"löschen|Fehler|Datei|Ordner|Einstellungen|zurück|öffnen|speichern|wählen)\b")


def untranslated():
    """Deutsche Texte, die direkt (ohne tr) in Knöpfe, Beschriftungen, Tooltips … gehen."""
    out = []
    for path in _sources():
        if path.name.startswith(("test_", "out_")) or path.name in ("i18n.py",):
            continue
        try:
            tree = ast.parse(path.read_text("utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in UI_CALLS:
                continue
            for arg in node.args[:3]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and GERMAN.search(arg.value):
                    out.append((path.name, node.lineno, arg.value))
                elif isinstance(arg, ast.JoinedStr):
                    text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in arg.values)
                    if GERMAN.search(text):
                        out.append((path.name, node.lineno, text))
    return out


def main():
    sys.path.insert(0, str(ROOT))
    import locales
    if "--ohne-tr" in sys.argv:  # deutsche Texte ohne tr()
        res = untranslated()
        print(f"== {len(res)} deutsche Texte ohne tr()")
        for name, line, text in res:
            print(f"  {name}:{line}  {text[:110]!r}")
        return
    want = sys.argv[1:] or [m.CODE for m in locales.LANGUAGES]
    for mod in locales.LANGUAGES:
        if mod.CODE not in want:
            continue
        res = missing(mod)
        print(f"== {mod.NAME} ({mod.CODE}): {len(res)} Texte ohne Übersetzung")
        for name, line, text, fstr in res:
            print(f"  {name}:{line}  {'f' if fstr else ' '} {text!r}")


if __name__ == "__main__":
    main()
