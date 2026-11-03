"""Deck editor, Library and detail view: every reference from QML and from other Python files to one of these backends
points to a member that exists – on the right class (docs/BACKEND-SPLIT.md). Guards the coming split of
DeckEditorBackend / LibraryBackend into parts (lib.lists, de.missing …): a member that moved but is still called on
the old object would only fail when clicked.

Unlike the trade page these backends are not context names but properties handed down: DeckEditor.qml `de`,
LibraryView.qml / ListsPanel.qml `lib`, DetailView.qml / MyLists.qml `det` (in DetailView also `d.det`), and chains
like `de.detail`, `lib.compare` (-> DetailBackend) or `de.listsLib` (-> LibraryBackend).

Static: reads the QML files, the Python sources and the backends' Qt meta objects, creates nothing.

    python -m unittest tests/test_backend_qml.py
"""
import ast
import importlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLASSES = {"DeckEditorBackend": "ui.qdeckedit", "LibraryBackend": "ui.qlibrary", "DetailBackend": "ui.qdetail"}
# QML file -> {variable: class}; DetailView also reaches its backend as d.det
ROOTS = {
    "qml/components/DeckEditor.qml": {"de": "DeckEditorBackend"},
    "qml/components/LibraryView.qml": {"lib": "LibraryBackend"},
    "qml/components/ListsPanel.qml": {"lib": "LibraryBackend"},
    "qml/components/DetailView.qml": {"det": "DetailBackend", "d.det": "DetailBackend"},
    "qml/components/MyLists.qml": {"det": "DetailBackend"},
}
# property of a backend that hands out another backend: (class, property) -> class of the result
CHAINS = {("DeckEditorBackend", "detail"): "DetailBackend", ("DeckEditorBackend", "compare"): "DetailBackend",
          ("DeckEditorBackend", "listsLib"): "LibraryBackend",
          ("LibraryBackend", "detail"): "DetailBackend", ("LibraryBackend", "compare"): "DetailBackend"}
# Python: attribute names that hold one of the backends (self.<name> / obj.<name>) -> class
HOLDERS = {"editor_b": "DeckEditorBackend", "_lib_b": "LibraryBackend", "ed_b": "LibraryBackend",
           "detail_b": "DetailBackend", "compare_b": "DetailBackend", "det_b": "DetailBackend",
           "cmp_b": "DetailBackend"}


def cls(name):
    return getattr(importlib.import_module(CLASSES[name]), name)


def members(c):
    """{name} of a QObject class from its meta object (slots, signals, properties) – own and inherited."""
    mo = c.staticMetaObject
    out = {bytes(mo.method(i).name()).decode() for i in range(mo.methodCount())}
    out |= {mo.property(i).name() for i in range(mo.propertyCount())}
    return out


def python_members(name):
    """Everything reachable on an instance from Python: class attributes and what __init__ assigns to self."""
    c = cls(name)
    names = set(dir(c))
    tree = ast.parse((ROOT / (CLASSES[name].replace(".", "/") + ".py")).read_text("utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    for f in node.body:
        if isinstance(f, ast.FunctionDef) and f.name == "__init__":
            for x in ast.walk(f):
                if isinstance(x, ast.Attribute) and isinstance(x.ctx, ast.Store) and getattr(x.value, "id", "") == "self":
                    names.add(x.attr)
    return names


def references():
    """[(file, line, class, member)] of every <root>(.<chain>)?.<member> in the QML files above."""
    out = []
    for f, roots in ROOTS.items():
        names = sorted(roots, key=len, reverse=True)
        rx = re.compile(r"(?<![\w.])(%s)((?:\.[A-Za-z_]\w*)+)" % "|".join(re.escape(n) for n in names))
        for n, line in enumerate((ROOT / f).read_text("utf-8").splitlines(), 1):
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line.split("//", 1)[0])   # no comments, no strings
            for m in rx.finditer(code):
                c = roots[m.group(1)]
                parts = m.group(2).split(".")[1:]
                for i, part in enumerate(parts):
                    out.append((f, n, c, part))
                    nxt = CHAINS.get((c, part))
                    if nxt is None:
                        break   # a plain value (string, list, JS object): its own fields aren't backend members
                    c = nxt
    return out


class BackendQml(unittest.TestCase):
    def test_every_reference_exists_on_its_backend(self):
        have = {name: members(cls(name)) for name in CLASSES}
        missing = [f"{f}:{n} {member} – not on {c}" for f, n, c, member in references() if member not in have[c]]
        self.assertEqual(missing, [])

    def test_roots_are_declared(self):
        """Every root variable is a property of its file (if a file renames it, the table above must follow)."""
        for f, roots in ROOTS.items():
            src = (ROOT / f).read_text("utf-8")
            for r in roots:
                if "." not in r:
                    self.assertRegex(src, r"property var %s\b" % r, f"{f}: {r} not declared")

    def test_chains_are_properties(self):
        """de.detail, lib.compare, de.listsLib … are Qt properties of the backend (QML reads them)."""
        for (c, prop), _target in CHAINS.items():
            self.assertIn(prop, members(cls(c)), f"{c}.{prop}")

    def test_finds_references(self):
        refs = references()
        for name, at_least in (("DeckEditorBackend", 80), ("LibraryBackend", 50), ("DetailBackend", 50)):
            self.assertGreater(sum(1 for r in refs if r[2] == name), at_least, name)   # guards the test itself


def python_references():
    """[(file, line, class, member)] – <x>.<holder>.<member> for the holder names above, in every Python file. Writes
    count too (detail_b.quiet_next = …): after a split they would silently create the attribute on the wrong object."""
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith((".venv/", "build/", "dist/", "tests/", "tools/")):
            continue
        src = p.read_text("utf-8", errors="replace")
        if not any(h in src for h in HOLDERS):
            continue
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and n.value.attr in HOLDERS:
                out.append((rel, n.lineno, HOLDERS[n.value.attr], n.attr))
    return out


class BackendPython(unittest.TestCase):
    def test_python_callers_hit_existing_members(self):
        have = {name: python_members(name) for name in CLASSES}
        missing = [f"{f}:{n} .{member} – not on {c}" for f, n, c, member in python_references()
                   if member not in have[c]]
        self.assertEqual(missing, [])

    def test_finds_python_callers(self):
        files = {f for f, _n, _c, _m in python_references()}
        self.assertTrue({"ui/qbinder.py", "ui/qtrade.py", "ui/qlibrary.py"} <= files, files)   # measured 26.10.


if __name__ == "__main__":
    unittest.main()
