"""UI language. tr("English text") returns the text in the selected language.

The languages themselves live centrally in the locales/ folder (one file per language, list in locales/__init__.py).
The language is set at startup from the settings (set_language). Fixed texts are in TEXTS,
texts with numbers/names are translated via RULES (regular expressions); everything else stays English.

Older German texts (old data, texts assembled at runtime) are known to locales/legacy_de.py: in English
they are translated through it, in German they stay as they are.
"""
import re

import locales

LANG = "en"
TEXTS, RULES = {}, []                  # selected language: English text -> translation
_SOURCE = set(locales.de.TEXTS)       # English source texts – never "translate" them via the legacy table
_SOURCE_RULES = [re.compile(p) for p, _ in locales.de.RULES]


def _fixed(pattern):
    """How much fixed text a pattern has (outside groups, without special characters) – measure of "specific"."""
    n, depth, i = 0, 0, 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            n += depth == 0
            i += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and c not in ".*+?[]{}^$|":
            n += 1
        i += 1
    return n


def _compile(rules):
    # most specific rule first (more fixed text): otherwise e.g. "(\d+) cards · (.*)" won over a more precise rule
    return sorted(((re.compile(p), r) for p, r in rules), key=lambda pr: -_fixed(pr[0].pattern))


_LEGACY_TEXTS = locales.legacy_de.TEXTS
_LEGACY_RULES = _compile(locales.legacy_de.RULES)


def set_language(lang):
    global LANG, TEXTS, RULES
    _memo.clear()
    mod = locales.module(lang)
    LANG = lang if mod is not None else "en"
    TEXTS = mod.TEXTS if mod is not None else {}
    RULES = _compile(mod.RULES) if mod is not None else []


def languages():
    """[(code, name)] – for the selection in Settings."""
    return locales.all_languages()


def _legacy_en(text):
    """Legacy German text -> English (or None)."""
    if text in _LEGACY_TEXTS:
        return _LEGACY_TEXTS[text]
    for pattern, repl in _LEGACY_RULES:
        m = pattern.fullmatch(text)
        if m:
            return m.expand(repl)
    return None


_memo = {}            # text -> result for the selected language (the rules are regexes: ~0.03–0.08 ms per miss)
_MEMO_MAX = 20000     # texts with numbers in them vary endlessly: start over instead of growing


def tr(text):
    if not isinstance(text, str) or not text:
        return text
    got = _memo.get(text)
    if got is None:
        if len(_memo) >= _MEMO_MAX:
            _memo.clear()
        got = _memo[text] = _tr(text)
    return got


def _tr(text):
    if LANG == "en":
        if text in _SOURCE or any(p.fullmatch(text) for p in _SOURCE_RULES):
            return text                    # already English
        en = _legacy_en(text)
        return en if en is not None else text
    if text in TEXTS:
        return TEXTS[text]
    for pattern, repl in RULES:
        m = pattern.fullmatch(text)
        if m:
            return m.expand(repl)
    return text                            # unknown: English – or a legacy German text that stays as is
