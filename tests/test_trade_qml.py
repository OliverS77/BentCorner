"""Trade page: every reference from QML to a trade backend points to a slot, property or signal that exists – on the
right backend (docs/TRADE-SPLIT.md). Guards the split of TradeBackend into tradePage/tradeLists/tradeAlarms/
tradeFriends: a member that moved but is still called on the old object would only fail when clicked.

Static: reads the QML files and the backends' Qt meta objects, creates nothing.

    python -m unittest tests/test_trade_qml.py
"""
import pathlib
import re
import unittest

from PySide6 import QtCore

import importlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = ["qml/pages/TradePage.qml", "qml/components/FriendRail.qml", "qml/components/FriendsMenu.qml",
         "qml/components/ForeignFriend.qml", "qml/components/AlarmEditor.qml"]
# QML alias in these files -> context name of the backend (the split adds tl/ta/tf)
ALIASES = {"tp": "tradePage", "tradePage": "tradePage", "tl": "tradeLists", "tradeLists": "tradeLists",
           "ta": "tradeAlarms", "tradeAlarms": "tradeAlarms", "tf": "tradeFriends", "tradeFriends": "tradeFriends"}
# context name -> backend class (only those that exist yet)
SHARED_SIGNALS = ("changed", "listsChanged", "entriesChanged", "detailChanged", "railChanged", "alarmChanged",
                  "syncChanged")   # forwarded from TradeBackend to the parts (notify of the moved properties)
CLASSES = {"tradePage": "TradeBackend", "tradeLists": "ListsBackend", "tradeAlarms": "AlarmsBackend",
           "tradeFriends": "FriendsBackend"}
MODULES = {"TradeBackend": "ui.qtrade", "ListsBackend": "ui.qtrade_lists", "AlarmsBackend": "ui.qtrade_alarms",
           "FriendsBackend": "ui.qtrade_friends"}


def _cls(name):
    """The backend class from its module (None if it doesn't exist yet)."""
    try:
        return getattr(importlib.import_module(MODULES[name]), name, None)
    except ImportError:
        return None


def members(cls):
    """{name: kind} of a QObject class from its meta object (slots, signals, properties) – own and inherited."""
    mo = cls.staticMetaObject
    out = {}
    for i in range(mo.methodCount()):
        m = mo.method(i)
        out[bytes(m.name()).decode()] = "signal" if m.methodType() == QtCore.QMetaMethod.MethodType.Signal else "slot"
    for i in range(mo.propertyCount()):
        out[mo.property(i).name()] = "property"
    return out


def backends():
    return {ctx: _cls(name) for ctx, name in CLASSES.items() if _cls(name) is not None}


def references():
    """[(file, line, alias, member)] of every alias.member in the trade QML files."""
    rx = re.compile(r"\b(%s)\.([A-Za-z_]\w*)" % "|".join(sorted(ALIASES, key=len, reverse=True)))
    out = []
    for f in FILES:
        for n, line in enumerate((ROOT / f).read_text("utf-8").splitlines(), 1):
            code = line.split("//", 1)[0]
            for m in rx.finditer(code):
                out.append((f, n, m.group(1), m.group(2)))
    return out


class TradeQml(unittest.TestCase):
    def test_every_reference_exists_on_its_backend(self):
        have = {ctx: members(cls) for ctx, cls in backends().items()}
        missing = []
        for f, n, alias, name in references():
            ctx = ALIASES[alias]
            if ctx not in have:
                missing.append(f"{f}:{n} {alias}.{name} – backend {ctx} doesn't exist")
            elif name not in have[ctx]:
                missing.append(f"{f}:{n} {alias}.{name} – not on {CLASSES[ctx]}")
        self.assertEqual(missing, [])

    def test_each_member_on_one_backend_only(self):
        """After the split a slot/property may live on one backend only (otherwise QML may call the stale one)."""
        base = members(QtCore.QObject)
        seen, twice = {}, []
        for ctx, cls in backends().items():
            for name in members(cls):
                if name in base or name in SHARED_SIGNALS:   # QObject's own and the forwarded signals
                    continue
                if name in seen:
                    twice.append(f"{name}: {seen[name]} and {ctx}")
                seen[name] = ctx
        self.assertEqual(twice, [])

    def test_aliases_are_declared(self):
        """Every alias used in a file is declared there (a property) – or the file gets it from its parent."""
        for f in FILES:
            src = (ROOT / f).read_text("utf-8")
            used = {a for a in ALIASES if re.search(r"\b%s\." % a, src) and len(a) == 2}
            for a in used:
                self.assertRegex(src, r"property var %s\b" % a, f"{f}: {a} used but not declared")

    def test_finds_references(self):
        self.assertGreater(len(references()), 150)   # the pattern still matches the QML (guards the test itself)


# ---------- Python callers outside qtrade.py (tour 2026-10-26: qlibrary.editList called a moved openList) ----
SUBS = {"lists_b": "ListsBackend", "alarms_b": "AlarmsBackend", "friends_b": "FriendsBackend"}


def _python_members(cls_name):
    """Everything reachable on an instance: class attributes (methods, Qt properties/slots/signals) and what
    __init__ assigns to self."""
    import ast
    cls = _cls(cls_name)
    names = set(dir(cls))
    tree = ast.parse((ROOT / (MODULES[cls_name].replace(".", "/") + ".py")).read_text("utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    for f in node.body:
        if isinstance(f, ast.FunctionDef) and f.name == "__init__":
            for x in ast.walk(f):
                if isinstance(x, ast.Attribute) and isinstance(x.ctx, ast.Store) and getattr(x.value, "id", "") == "self":
                    names.add(x.attr)
                if isinstance(x, ast.Tuple) and isinstance(x.ctx, ast.Store):
                    names |= {e.attr for e in x.elts if isinstance(e, ast.Attribute)}
    return names


def python_references():
    """[(file, line, chain)] – attribute chains on a variable (or expression) that holds the trade backend
    (backends["trade"] / backends.get("trade")) in every Python file except qtrade.py and the tests."""
    import ast
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith((".venv/", "build/", "dist/", "tests/", "tools/")) or rel.startswith("ui/qtrade"):
            continue
        src = p.read_text("utf-8", errors="replace")
        if '"trade"' not in src and "'trade'" not in src:
            continue
        tree = ast.parse(src)

        def is_trade(e):
            t = ast.unparse(e)
            return "backends" in t and re.search(r"""\[\s*["']trade["']\s*\]|\.get\(\s*["']trade["']""", t) is not None
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module))]:
            holders = {}   # variable -> line from which on it holds the trade backend
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign) and is_trade(n.value):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            holders[t.id] = min(holders.get(t.id, 10 ** 9), n.end_lineno + 1)

            def held(e):
                return isinstance(e, ast.Name) and e.id in holders and e.lineno >= holders[e.id]
            for n in ast.walk(fn):
                if isinstance(n, ast.Attribute) and not isinstance(n.ctx, ast.Store):
                    base = n.value
                    if held(base) or (not isinstance(base, ast.Name) and is_trade(base)):
                        chain = [n.attr]
                        out.append((rel, n.lineno, chain))
                    elif isinstance(base, ast.Attribute) and base.attr in SUBS and (held(base.value) or is_trade(base.value)):
                        out.append((rel, n.lineno, [base.attr, n.attr]))
    return out


class TradePython(unittest.TestCase):
    def test_python_callers_hit_existing_members(self):
        core = _python_members("TradeBackend")
        missing = []
        for rel, line, chain in python_references():
            if len(chain) == 1:
                if chain[0] not in core and chain[0] not in SUBS:
                    missing.append(f"{rel}:{line} tb.{chain[0]} – not on TradeBackend")
            else:
                sub = SUBS[chain[0]]
                if _cls(sub) is None or chain[1] not in _python_members(sub):
                    missing.append(f"{rel}:{line} tb.{chain[0]}.{chain[1]} – not on {sub}")
        self.assertEqual(missing, [])

    def test_finds_python_callers(self):
        files = {rel for rel, _l, _c in python_references()}
        self.assertTrue({"ui/qlibrary.py", "ui/qimport.py", "ui/quickshell.py", "app.py"} <= files, files)


if __name__ == "__main__":
    unittest.main()
