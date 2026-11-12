"""The device name given when adding (lead/Oliver 07.11.): the device showing the code sends the next number
(extra.next_n), the joining one prefills „Device N“ and writes the name into */devices at once – and two devices
joining at nearly the same time with the same next_n never both stay „Device 3“ (DEVICE-KEYS §5).

    python -m unittest tests.test_join_name
"""
import base64
import tempfile
import unittest
from unittest import mock

from net import sync_ctl, vault
from system.i18n import tr

SEED = base64.b64encode(b"\x09" * 32).decode()


class Offer(unittest.TestCase):
    def test_next_number_and_the_extra(self):
        self.assertEqual(sync_ctl.next_number([{"n": 1}, {"n": 4}, {}]), 5)
        self.assertEqual(sync_ctl.next_number([]), 2)   # ports/lead 12.11.: the showing device counts – never 1
        self.assertEqual(vault.pair_extra({}, 3)["next_n"], 3)
        self.assertNotIn("next_n", vault.pair_extra({}))


def joined(extra):
    c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
    c.settings, c.sync_status = {"relay": {}}, {}
    for n in ("_sync_changed", "settings_changed", "sync_setup", "sync_now"):
        setattr(c, n, mock.Mock())
    c.sync_engine = mock.Mock()
    c.sync_engine.meta = {}
    c.sync_engine.lock = mock.MagicMock()
    sync_ctl.SyncControl._join_apply(c, {"seed": SEED, "extra": extra})   # A2: after the code was taken
    return c


class Join(unittest.TestCase):
    def test_join_n_from_the_other_device(self):
        self.assertEqual(joined({"device": "pc", "next_n": 3}).sync_status["join_n"], 3)
        self.assertEqual(joined({"device": "phone"}).sync_status["join_n"], 2, "an older other side: at least 2 (12.11.)")
        self.assertEqual(joined({"next_n": "x"}).sync_status["join_n"], 0)

    def test_prefill_kept_is_the_default(self):
        c = joined({"next_n": 3})
        c.sync_engine.meta = {"dev": "me"}
        c.sync_engine.state.value.return_value = None   # not in the list yet: the first entry takes the setting
        c.settings["device_name"] = "old"
        c.sync_join_name(tr("Device 3"))
        self.assertNotIn("device_name", c.settings)
        c.sync_join_name("  Laptop   im Flur ")
        self.assertEqual(c.settings["device_name"], "Laptop im Flur")

    def test_already_listed_is_renamed(self):
        c = joined({"next_n": 3})
        c.sync_engine.meta = {"dev": "me"}
        c.sync_engine.state.value.return_value = {"n": 3}
        c.sync_engine.rename_device.return_value = True
        c.sync_now.reset_mock()   # the join itself syncs once
        c.sync_join_name("Laptop")
        c.sync_engine.rename_device.assert_called_once_with("me", "Laptop")
        c.sync_now.assert_called_once()


class ChoiceNamesTheOther(unittest.TestCase):
    def test_other_name_and_number(self):
        c = joined({"next_n": 3, "dev": "D2", "device": "pc"})
        self.assertEqual(c.sync_engine.meta["join_other_dev"], "D2")
        c.sync_engine.meta["join_hold"] = {"other": "pc", "here": {}, "there": {}}
        c.sync_engine.state.value = lambda kind, key: {"D2": {"n": 2, "name": None}}.get(key)
        got = c.sync_join_choice
        self.assertEqual((got["other_name"], got["other_n"], got["other"]), (None, 2, "pc"))
        c.sync_engine.state.value = lambda kind, key: {"D2": {"n": 2, "name": "Büro-PC"}}.get(key)
        self.assertEqual(c.sync_join_choice["other_name"], "Büro-PC")

    def test_older_other_side(self):
        c = joined({"device": "phone"})
        c.sync_engine.meta["join_hold"] = {"other": "phone", "here": {}, "there": {}}
        got = c.sync_join_choice
        self.assertEqual((got["other_name"], got["other_n"]), (None, 0))

    def test_offer_names_this_device(self):
        self.assertEqual(vault.pair_extra({}, 3, "D1")["dev"], "D1")


class KeepMineKeepsTheNumbers(unittest.TestCase):
    """ports 07.11.: „keep this device's state“ (takeover snap) wrote the joining device's entry against an empty state
    (n = 1) – the FIRST device then jumped to „Device 2“. The numbers stay: the joiner its next_n, the first its 1."""

    def test_takeover_snap(self):
        from tests import test_syncrun as ts
        with tempfile.TemporaryDirectory() as tmp:
            t = [1_790_000_000_000]
            v = ts.FakeVault()
            a, b = (ts.Device(tmp, k, v, lambda: t[0]) for k in "ab")
            a.save_decks([ts.deck("d1", "Burn", [("s1", 3)])])
            a.eng.switch_on()
            a.sync()
            self.assertEqual([e["n"] for e in a.eng.devices()], [1])
            t[0] += 1000
            b.save_decks([ts.deck("d9", "Mine", [("s7", 2)])])
            b.eng.switch_on()
            b.eng.meta["join_n"] = sync_ctl.next_number(a.eng.devices())   # from the pairing payload
            b.sync(answer="mine")   # both have data: B keeps its own state (a snap with takeover)
            for _ in range(3):
                t[0] += 1000
                for x in (a, b):
                    x.eng.catch_up()
                    x.sync()
            na = {e["me"]: e["n"] for e in a.eng.devices()}
            nb = {e["me"]: e["n"] for e in b.eng.devices()}
            self.assertEqual((na[True], na[False]), (1, 2), "the first device stays „Device 1“")
            self.assertEqual((nb[True], nb[False]), (2, 1))


class SameNumberAtOnce(unittest.TestCase):
    """lead 07.11.: two devices join at nearly the same time with the same next_n (both fetched before either sent):
    the n rule of §5 – in the end every device lists them with different numbers, the earlier one keeps 3."""

    def test_never_twice_device_3(self):
        from tests import test_syncrun as ts
        with tempfile.TemporaryDirectory() as tmp:
            t = [1_790_000_000_000]
            v = ts.FakeVault()
            a, b, c, d = (ts.Device(tmp, k, v, lambda: t[0]) for k in "abcd")
            for x in (a, b):
                x.eng.switch_on()
                x.sync()
                t[0] += 1000
            a.sync()
            self.assertEqual(sync_ctl.next_number(a.eng.devices()), 3)
            c.eng.switch_on()
            d.eng.switch_on()
            c.eng.fetch()   # both see a and b only: both take 3
            d.eng.fetch()
            self.assertEqual({e["n"] for e in c.eng.devices() if e["me"]}, {3})
            self.assertEqual({e["n"] for e in d.eng.devices() if e["me"]}, {3})
            for x in (c, d):
                x.eng.write_back()
                try:
                    x.eng.push()
                except Exception:  # noqa: BLE001 – the second one: 409, its next run sends it
                    pass
            # the next runs (minute questions) – each device settles its own number once it has seen the other: at
            # most three rounds, whichever of the two random device ids is the smaller one
            for _ in range(3):
                t[0] += 1000
                for x in (a, b, c, d):
                    x.eng.catch_up()
                    x.sync()
            ns = sorted(e["n"] for e in a.eng.devices())
            self.assertEqual(ns, [1, 2, 3, 4], "never twice „Device 3“")
            for x in (b, c, d):
                self.assertEqual(sorted(e["n"] for e in x.eng.devices()), ns, "every device lists the same")
            first = min((c, d), key=lambda x: (x.eng.devices()[0]["added"], x.eng.meta["dev"]))
            self.assertEqual(first.eng.devices()[0]["n"], 3, "the earlier (added, dev) keeps 3")


if __name__ == "__main__":
    unittest.main()
