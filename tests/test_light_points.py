"""Review 08.11., the light points: a snap the server refused as bigger than the vault isn't sent again on every run;
damaged pairing/rescue payloads are a PairError (never half paired); dev/list rows without a dev_id are left out; two
removals at once show the conflict line; no pairing or leaving side by side with a sync run; signing out offline
still deletes seed and device key here.

    python -m unittest tests.test_light_points
"""
import base64
import json
import tempfile
import unittest
from unittest import mock

from net import devices_ctl, pairing, relay, sync_ctl, vault
from tests.test_syncrun import SEED as SYNC_SEED, Device, FakeVault, deck

from tests import livebox  # noqa: E402
setUpModule, tearDownModule = livebox.module()   # the live box, as a Ship build (DEV split 13.11.)

SEED = base64.b64encode(b"\x11" * 32).decode()


class BigSnap(unittest.TestCase):
    def test_refused_snap_not_sent_again_the_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = [1793600000000]
            v = FakeVault()
            a = Device(tmp, "a", v, lambda: t[0])
            a.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)])]})
            a.eng.switch_on()
            a.sync()
            sent = []
            real = v.put

            def put(settings, kind, base, data):
                sent.append(kind)
                if kind == "snap":
                    raise vault.VaultError(413, "Schnappschuss größer als das Fach", {"max": 10})
                return real(settings, kind, base, data)
            v.put = put
            a.eng.meta["snap_next"] = True
            with self.assertRaises(vault.VaultError):
                a.eng.push()
            with self.assertRaises(vault.VaultError):
                a.eng.push()
            self.assertEqual(sent, ["snap"], "the second run sends nothing")
            t[0] += 86400 * 1000 + 1
            with self.assertRaises(vault.VaultError):
                a.eng.push()
            self.assertEqual(sent, ["snap", "snap"], "a day later: once more")


class Damaged(unittest.TestCase):
    def test_pairing_payloads(self):
        code = "ABCDEFGHJK"
        _pid, key = pairing.slot(code)
        from nacl.secret import SecretBox
        for raw in (b"[1, 2]", json.dumps({"v": 1, "seed": 5, "code": "X"}).encode(),
                    json.dumps({"v": 1, "seed": "kaputt!", "code": "X"}).encode()):
            data = base64.b64encode(bytes(SecretBox(key).encrypt(raw))).decode()
            with self.assertRaises(pairing.PairError):
                pairing.open_sealed(code, data, key=key)
        with self.assertRaises(pairing.PairError):
            pairing.open_sealed(code, None, key=key)

    def test_rescue_payloads(self):
        code, salt = pairing.new_rescue_code(), pairing.new_salt()
        keys = pairing.guard_keys(code, salt)
        from nacl.secret import SecretBox
        for raw in (b"[1]", json.dumps({"v": 2, "seed": None, "code": "X", "salt": salt}).encode()):
            box = base64.b64encode(bytes(SecretBox(keys["rk"]).encrypt(raw))).decode()
            data = base64.b64encode(json.dumps({"box": box, "salt": salt, "v": 2}).encode()).decode()
            with self.assertRaises(pairing.PairError):
                pairing.rescue_open(code, data, keys)


class DevList(unittest.TestCase):
    def test_rows_without_dev_id_left_out(self):
        rows = {"list": [{"dev_id": "dA"}, {"name": "x"}, "junk", {"dev_id": 5}], "dev_request": [{}], "reg_version": 3}
        with mock.patch("net.devkeys._post", return_value=rows):
            from net import devkeys
            d = devkeys.listing({"relay": {"seed": SEED}})
        self.assertEqual(d["list"], [{"dev_id": "dA"}])
        self.assertEqual(d["dev_request"], [])


class Conflicts(unittest.TestCase):
    def test_two_removals_at_once(self):
        c = mock.Mock()
        c.sync_status = {"remove": "busy"}
        devices_ctl.DevicesControl._remove_done(c, None, relay.RelayError("moved", 410, {"moved": True}))
        self.assertEqual(c.sync_status["remove"], "conflict")

    def test_no_pairing_or_leaving_during_a_run(self):
        c = mock.Mock()
        c.sync_status = {"busy": True}
        c.sync_on.return_value = True
        c.sync_orbit_ok.return_value = True
        c.pair = {}
        sync_ctl.SyncControl.pair_show(c)
        c._sync_bg.assert_not_called()
        self.assertTrue(c.pair["error"])
        c.sync_leave_plan.return_value = "leave"
        sync_ctl.SyncControl.sync_leave(c)
        c._sync_bg.assert_not_called()
        c.sync_status = {"busy": False}
        c.pair = {"busy": True}
        sync_ctl.SyncControl.sync_now(c)
        c._sync_bg.assert_not_called()

    def test_leaving_ends_the_earlier_join(self):
        """Guide run 09.11.: signed out, then „Enter a code“ again – an old join "ok" must not close the field."""
        c = mock.Mock()
        c.sync_status = {"join": "ok", "join_n": 2}
        c.settings = {"relay": {"seed": SEED}}
        sync_ctl.SyncControl._leave_done(c, {"registry": True}, None)
        self.assertNotIn("join", c.sync_status)
        self.assertTrue(c.sync_status["left"])

    def test_leaving_offline_still_drops_the_keys(self):
        c = mock.Mock()
        c.sync_status = {}
        c.settings = {"relay": {"seed": SEED, "registered": 1}}
        with mock.patch("net.devkeys.forget") as forget:
            sync_ctl.SyncControl._leave_done(c, None, vault.VaultError(0, "offline"))
        self.assertNotEqual(c.settings["relay"]["seed"], SEED)
        forget.assert_called_once()


class HealPause(unittest.TestCase):
    def test_heals_at_most_once_an_hour(self):
        from collection import syncops
        with tempfile.TemporaryDirectory() as tmp:
            t = [1793600000000]
            v = FakeVault()
            a = Device(tmp, "a", v, lambda: t[0])
            b = Device(tmp, "b", v, lambda: t[0])
            a.eng.switch_on()
            a.sync()
            b.eng.switch_on()
            b.sync()

            def broken(name):
                t[0] += 1000
                a.save_decks([deck("d1", name, [("s1", 2)])])
                a.sync()
                item = v.items[-1]   # a broken client: the same ops, a wrong sum
                pkg = syncops.unpack(pairing.vault_open_bytes(SYNC_SEED, item["data"]))
                pkg["sum"] = {k: "0" * 64 for k in pkg["sum"]}
                item["data"] = pairing.vault_seal_bytes(SYNC_SEED, syncops.pack(pkg))
            broken("Burn 1")
            self.assertTrue(b.eng.fetch()["healed"])
            broken("Burn 2")
            self.assertFalse(b.eng.fetch()["healed"], "again within the hour: no second whole download")
            t[0] += 3600 * 1000
            broken("Burn 3")
            self.assertTrue(b.eng.fetch()["healed"])


if __name__ == "__main__":
    unittest.main()
