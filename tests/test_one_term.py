"""One term everywhere (lead 07.11.2026): „Schutz-Code“ / “protection code” – „Rettungscode“ / “rescue code” is gone from
every text the user can see (German texts and rules, the English keys behind them).

    python -m unittest tests/test_one_term.py
"""
import re
import unittest

import locales.de as de

OLD = re.compile(r"rettungs-?code|rescue[ -]code", re.I)


class OneTermTest(unittest.TestCase):
    def test_no_old_term_in_texts(self):
        bad = [k for k, v in de.TEXTS.items() if OLD.search(k) or OLD.search(str(v))]
        bad += [p for p, r in de.RULES if OLD.search(getattr(p, "pattern", str(p))) or OLD.search(str(r))]
        self.assertEqual(bad, [])

    def test_new_term_is_there(self):
        self.assertEqual(de.TEXTS.get("Protection code"), "Schutz-Code")


if __name__ == "__main__":
    unittest.main()
