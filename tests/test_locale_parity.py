"""Translations keep their placeholders: every rule in locales/de.py compiles and its German side uses exactly the
groups the English pattern catches; every HTML tag (links, line breaks, bold) of an English text is also in the
German one (by name – a link may point to the German page) – a lost \\2 or <br> would only show up at runtime.

    python -m unittest tests/test_locale_parity.py
"""
import collections
import re
import unittest

from locales import de

TAG = re.compile(r"</?[a-z]+(?:\s[^>]*)?>")   # real HTML tags – not "<date>"-style placeholders in plain text
KNOWN_TAGS = {"a", "b", "i", "u", "br", "font", "span", "p", "small", "big", "li", "ul", "ol", "code", "tt"}


def tags(text):
    names = (re.match(r"</?[a-z]+", t).group(0) for t in TAG.findall(text))
    return collections.Counter(n for n in names if n.lstrip("</") in KNOWN_TAGS)


class Rules(unittest.TestCase):
    def test_rules_compile_and_use_every_group(self):
        for pattern, repl in de.RULES:
            with self.subTest(pattern=pattern[:80]):
                groups = re.compile(pattern).groups
                refs = {int(n) for n in re.findall(r"\\(\d+)", repl)}
                self.assertEqual(refs, set(range(1, groups + 1)))


class Texts(unittest.TestCase):
    def test_html_tags_survive_the_translation(self):
        for en, german in de.TEXTS.items():
            with self.subTest(text=en[:80]):
                self.assertEqual(tags(en) - tags(german), collections.Counter())


if __name__ == "__main__":
    unittest.main()
