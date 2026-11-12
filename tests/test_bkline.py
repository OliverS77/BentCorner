"""Settings → Backup, „I'm aware of the risks“ tooltip (legal 07.11.): the online-backup sentence only when the backup
runs AND there is a way back to it (another coupled device or a protection code); otherwise the old sentence.

    python -m unittest tests/test_bkline.py
"""
import types
import unittest

from ui import qsetpages


def ctrl(on=True, plan="delete", guard=False):
    return types.SimpleNamespace(sync_engine=types.SimpleNamespace(on=lambda: on), sync_switch_plan=lambda: plan,
                                 guard_on=lambda: guard)


class RiskTooltipTest(unittest.TestCase):
    def test_way_back(self):
        self.assertFalse(qsetpages._online_way_back(ctrl(on=False, plan="leave", guard=True)))   # sync off
        self.assertFalse(qsetpages._online_way_back(ctrl()))                  # only this PC, no code: no way back
        self.assertTrue(qsetpages._online_way_back(ctrl(plan="leave")))       # another coupled device
        self.assertTrue(qsetpages._online_way_back(ctrl(guard=True)))         # a protection code
        self.assertFalse(qsetpages._online_way_back(types.SimpleNamespace()))  # no sync built in

    def test_german(self):
        from locales import de
        self.assertIn(qsetpages.RISK_ONLINE, de.TEXTS)


if __name__ == "__main__":
    unittest.main()
