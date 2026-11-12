"""B5 – remove ONE device (Oliver 07.11., docs/web/DEVICE-KEYS.md, box 7fe65d1), the client without network: device
keys (never in a backup), the added_by chain, envelopes only the right device opens, following an envelope, signing out
deletes seed and key, the page's plan and answers. The whole chain against a local box: tools/boxchecks/b5_check.py.

    python -m unittest tests.test_b5
"""
import base64
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from net import devkeys, pairing, relay


class Home:
    """Each test its own data folder for the key file (never the real one)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch("system.datahome.HOME", pathlib.Path(self.tmp.name))
        self.p.start()
        devkeys._cache.clear()

    def tearDown(self):
        devkeys._cache.clear()
        self.p.stop()
        self.tmp.cleanup()


def identity():
    return {"relay": {"seed": base64.b64encode(b"\x11" * 32).decode()}}


class Keys(Home, unittest.TestCase):
    def test_made_once_kept_and_not_in_a_backup(self):
        from system import datahome, datastore
        a = devkeys.mine()
        devkeys._cache.clear()
        self.assertEqual(devkeys.mine(), a)
        path = datahome.HOME / devkeys.FILE
        self.assertTrue(path.exists())
        with mock.patch.object(datastore, "DATA", datahome.HOME / "data"), \
                mock.patch.object(datastore, "SETTINGS", datahome.HOME / "settings.json"):
            for root, _name in datastore.personal_roots():
                self.assertFalse(path == root or root in path.parents, root)

    def test_update_never_drops_the_keys(self):
        """Regression (b5_check 07.11.): an update with an empty cache wrote a file without keys."""
        a = devkeys.mine()
        devkeys._cache.clear()
        devkeys._update(code="ABC")
        devkeys._cache.clear()
        self.assertEqual(devkeys.mine(), a)
        self.assertEqual(devkeys._load(False)["code"], "ABC")

    def test_attach_only_when_registered(self):
        s = identity()
        devkeys.mine()
        self.assertEqual(devkeys.attach(s, {"x": 1}, "m"), {"x": 1})
        devkeys._update(code=relay.my_code(s))
        got = devkeys.attach(s, {"x": 1}, "m")
        from nacl.signing import VerifyKey
        VerifyKey(base64.b64decode(devkeys.mine()["sign_pk"])).verify(b"m", base64.b64decode(got["sig_dev"]))
        self.assertEqual(got["dev_id"], devkeys.mine()["dev_id"])

    def test_forget(self):
        devkeys.mine()
        devkeys.forget()
        self.assertIsNone(devkeys.mine(create=False))


class Chain(unittest.TestCase):
    def test_removed_with_what_it_added(self):
        rows = [{"dev_id": "A", "added_by": "A"}, {"dev_id": "B", "added_by": "A"}, {"dev_id": "C", "added_by": "B"},
                {"dev_id": "D", "added_by": "C"}, {"dev_id": "E", "added_by": "A"}, {"dev_id": "F", "added_by": ""}]
        self.assertEqual(devkeys.chain(rows, "B"), ["B", "C", "D"])
        self.assertEqual(devkeys.chain(rows, "F"), ["F"])
        rows.append({"dev_id": "B", "added_by": "D"})   # a loop never hangs
        self.assertEqual(set(devkeys.chain(rows, "B")), {"B", "C", "D"})


class Envelope(Home, unittest.TestCase):
    """Review 08.11. (S6): the letter is signed with the OLD identity key – only a holder of the old seed (the remover)
    can write one this device takes; the server, which knows every box key, can't slip it a seed of its own."""

    def letter(self, s, new_seed, dev=None, t=1_800_000_000):
        new = pairing.code_of_seed(new_seed)
        return devkeys.letter_for(s, relay.my_code(s), new, new_seed, dev or devkeys.mine()["dev_id"], t)

    def test_only_this_device_opens_it(self):
        s = identity()
        seed = base64.b64encode(b"\x22" * 32).decode()
        sealed = devkeys.seal_for(devkeys.mine()["box_pk"], self.letter(s, seed))
        self.assertEqual(devkeys.open_fwd(s, sealed)["seed"], seed)
        devkeys.forget()
        devkeys.mine()   # another device
        self.assertIsNone(devkeys.open_fwd(s, sealed))

    def test_a_server_made_letter_is_refused(self):
        """Sealed for this device's box key (the server knows it), but not signed by this identity."""
        s = identity()
        seed = base64.b64encode(b"\x22" * 32).decode()
        other = {"relay": {"seed": base64.b64encode(b"\x99" * 32).decode()}}
        forged = dict(self.letter(other, seed), old=relay.my_code(s))   # right fields, wrong signer
        self.assertIsNone(devkeys.open_fwd(s, devkeys.seal_for(devkeys.mine()["box_pk"], forged)))
        unsigned = {"v": 2, "seed": seed, "code": pairing.code_of_seed(seed)}   # the old unsigned form
        self.assertIsNone(devkeys.open_fwd(s, devkeys.seal_for(devkeys.mine()["box_pk"], unsigned)))

    def test_letter_for_another_device_or_identity_is_refused(self):
        s = identity()
        seed = base64.b64encode(b"\x22" * 32).decode()
        box = devkeys.mine()["box_pk"]
        self.assertIsNone(devkeys.open_fwd(s, devkeys.seal_for(box, self.letter(s, seed, dev="dsomeoneelse0"))))
        moved = {"relay": {"seed": base64.b64encode(b"\x44" * 32).decode()}}   # this device is on another identity
        self.assertIsNone(devkeys.open_fwd(moved, devkeys.seal_for(box, self.letter(s, seed))))

    def test_a_wrong_code_is_refused(self):
        s = identity()
        seed = base64.b64encode(b"\x22" * 32).decode()
        bad = dict(self.letter(s, seed), code="AAAAAAAAAAAAAAAA")
        self.assertIsNone(devkeys.open_fwd(s, devkeys.seal_for(devkeys.mine()["box_pk"], bad)))


class Vectors(unittest.TestCase):
    """docs/web/fwd-vectors.json – the web signs and checks the same line (tools/make_fwd_vectors.py)."""

    def test_line_and_signature(self):
        import json
        import pathlib
        v = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs/web/fwd-vectors.json").read_text("utf-8"))
        s = {"relay": {"seed": v["old_seed"]}}
        self.assertEqual(relay.my_code(s), v["old"])
        self.assertEqual(devkeys.fwd_line(v["old"], v["new"], v["dev"], v["t"], v["new_seed"]), v["line"])
        self.assertEqual(relay._signed(s, v["line"]), v["sig"])


class PhantomDevice(Home, unittest.TestCase):
    """Review 08.11. (H1-6): only devices this identity lists itself (sealed */devices) get the new seed."""

    def test_a_device_only_the_server_knows_stops_the_removal(self):
        from net import rekey
        from nacl.public import PrivateKey
        s = identity()
        me = devkeys.mine()
        devkeys._update(code=relay.my_code(s))
        keys = {k: PrivateKey.generate() for k in ("dB", "dX")}
        rows = [{"dev_id": me["dev_id"], "added_by": me["dev_id"], "box_pk": me["box_pk"]}] + [
            {"dev_id": k, "added_by": me["dev_id"], "box_pk": base64.b64encode(bytes(v.public_key)).decode()}
            for k, v in keys.items()]
        sent = []
        with mock.patch.object(devkeys, "listing", lambda st: {"list": rows, "reg_version": 1}),                 mock.patch.object(relay, "register", lambda st: None),                 mock.patch.object(relay, "_post", lambda st, path, p: sent.append(p) or {}):
            with self.assertRaises(rekey.UnknownDevice) as c:
                rekey.remove_one(s, "dB", known={me["dev_id"], "dB"})
            self.assertEqual(c.exception.devs, ["dX"])
            self.assertEqual(sent, [], "nothing sent")
            rekey.remove_one(s, "dB", known={me["dev_id"], "dB", "dX"})
        self.assertEqual(len(sent), 1)


class Follow(Home, unittest.TestCase):
    def test_per_device_follows_its_envelope(self):
        s = identity()
        new_seed = base64.b64encode(b"\x33" * 32).decode()
        got = {"seed": new_seed, "code": pairing.code_of_seed(new_seed)}
        data = {"moved": True, "per_device": True}
        with mock.patch.object(devkeys, "fetch_fwd", lambda st, old: got):
            self.assertTrue(relay.moved_away(s, data))
        self.assertEqual(s["relay"]["seed"], new_seed)
        self.assertTrue(data.get("fwd"), "the callers see „followed“, not „removed“")
        self.assertNotIn("identity_gone", s["relay"])

    def test_no_envelope_means_removed(self):
        s = identity()
        old = s["relay"]["seed"]
        devkeys.mine()
        data = {"moved": True, "per_device": True}
        with mock.patch.object(devkeys, "fetch_fwd", lambda st, old: None):
            self.assertTrue(relay.moved_away(s, data))
        self.assertNotEqual(s["relay"]["seed"], old)
        self.assertTrue(data.get("gone") and s["relay"].get("identity_gone"))
        self.assertIsNone(devkeys.mine(create=False), "its device key went with the old identity")


def ctl():
    from net import devices_ctl, sync_ctl
    c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
    for n in [n for n in dir(devices_ctl.DevicesControl) if not n.startswith("__")]:
        setattr(c, n, getattr(devices_ctl.DevicesControl, n).__get__(c))
    c.settings, c.sync_status = identity(), {"busy": False}
    for n in ("_sync_changed", "settings_changed", "sync_setup", "sync_now", "_rekey_done", "_sync_bg"):
        setattr(c, n, mock.Mock())
    c.guard_on = lambda: False
    c.sync_engine = mock.Mock()
    c.sync_engine.meta = {"seeded": True}
    c.sync_engine.lock = mock.MagicMock()
    return c


class Page(Home, unittest.TestCase):
    def test_plan_names_what_goes_with_it(self):
        c = ctl()
        c.sync_devices = lambda: [{"dev": "a", "rid": "dA", "name": None, "n": 1, "me": True},
                                  {"dev": "b", "rid": "dB", "name": "Laptop", "n": 2, "me": False},
                                  {"dev": "c", "rid": "dC", "name": None, "n": 3, "me": False}]
        c._dev_reg = {"list": [{"dev_id": "dA", "added_by": "dA"}, {"dev_id": "dB", "added_by": "dA"},
                               {"dev_id": "dC", "added_by": "dB"}]}
        plan = c.sync_remove_plan("b")
        self.assertEqual((plan["name"], plan["n"], plan["guard"]), ("Laptop", 2, False))
        self.assertEqual(plan["with"], [{"dev": "c", "name": None, "n": 3}])
        self.assertEqual(c.sync_remove_plan("c")["with"], [])
        c._dev_refresh = mock.Mock()
        self.assertIsNone(c.sync_remove_plan("zz"))
        c._dev_refresh.assert_called_once()   # an unknown device: fetch the list again

    def test_with_a_code_it_asks_first(self):
        c = ctl()
        c.guard_on = lambda: True
        c.sync_devices = lambda: [{"dev": "b", "rid": "dB"}]
        with mock.patch("collection.syncrun.available", lambda: True):
            c.sync_remove("b")
        self.assertEqual(c.sync_status["delete_guard"], "need")
        c._sync_bg.assert_not_called()

    def test_answers(self):
        from net.relay import RelayError
        c = ctl()
        c._remove_done(None, RelayError("x", 409, {}))
        self.assertEqual(c.sync_status["remove"], "conflict")
        c._remove_done(None, RelayError("x", 403, {"main_required": True}))
        self.assertEqual(c.sync_status["delete_guard"], "wrong")
        c._remove_done({"old": "O", "new": "N", "gone": ["dB"]}, None)
        self.assertEqual(c.sync_status["remove"], "ok")
        c.sync_engine.drop_devices.assert_called_once_with(["dB"])

    def test_allow_needs_the_code_decline_never(self):
        c = ctl()
        c.guard_on = lambda: True
        c.sync_join_request_answer("dX", True)
        self.assertEqual(c.sync_status["delete_guard"], "need")
        c._sync_bg.assert_not_called()
        c.sync_join_request_answer("dX", False)
        c._sync_bg.assert_called_once()

    def test_let_in_after_waiting(self):
        c = ctl()
        devkeys.mine()
        devkeys._update(pending=relay.my_code(c.settings))
        me = devkeys.mine()["dev_id"]
        c._dev_listing = True
        c._dev_done("dev_list", {"list": [{"dev_id": me}], "dev_request": []}, None)
        self.assertTrue(devkeys.registered(c.settings))


class ListLoaded(Home, unittest.TestCase):
    def test_registered_device_fetches_the_list_once(self):
        """Guide run 07.11.: the ✕ said „not in the list any more“ – the registry list was never fetched."""
        c = ctl()
        c.sync_engine.on = lambda: True
        devkeys.mine()
        devkeys._update(code=relay.my_code(c.settings))
        c._dev_refresh = mock.Mock()
        with mock.patch("collection.syncrun.available", lambda: True):
            c._dev_ensure()
            c._dev_reg = {"list": []}
            c._dev_ensure()
        c._dev_refresh.assert_called_once()


class SignOut(Home, unittest.TestCase):
    def test_signing_out_deletes_seed_and_device_key(self):
        """legal 07.11. (condition a): „Dieses Gerät abmelden“ with B5 – out of the registry, then seed and key gone."""
        from net import sync_ctl
        c = ctl()
        old = c.settings["relay"]["seed"]
        devkeys.mine()
        sync_ctl.SyncControl._leave_done(c, {"registry": True}, None)
        self.assertNotEqual(c.settings["relay"]["seed"], old)
        self.assertNotIn("identity_gone", c.settings["relay"], "not the „backup of a removed identity“ hint")
        self.assertIsNone(devkeys.mine(create=False))
        self.assertTrue(c.sync_status["left"])


class SignedOutList(unittest.TestCase):
    def test_off_lists_only_this_device(self):
        from net import sync_ctl
        c = sync_ctl.SyncControl.__new__(sync_ctl.SyncControl)
        c.sync_engine = mock.Mock()
        c.sync_engine.devices.return_value = [{"dev": "a", "me": True}, {"dev": "b", "me": False}]
        c.sync_engine.on.return_value = False
        self.assertEqual([d["dev"] for d in c.sync_devices()], ["a"])
        c.sync_engine.on.return_value = True
        self.assertEqual(len(c.sync_devices()), 2)


class RemoveOnePayload(Home, unittest.TestCase):
    def test_the_signed_line_and_the_envelopes(self):
        """What goes to /v1/rekey: gone/fwd/notes as JSON text, hashed as sent; one envelope per remaining device but
        this one; the box checks exactly this line (box 7fe65d1 _rekey_one)."""
        import hashlib
        from net import rekey
        s = identity()
        me = devkeys.mine()
        devkeys._update(code=relay.my_code(s))
        from nacl.public import PrivateKey
        keys = {k: PrivateKey.generate() for k in ("dB", "dC", "dD")}
        rows = [{"dev_id": me["dev_id"], "added_by": me["dev_id"], "box_pk": me["box_pk"]}] + [
            {"dev_id": k, "added_by": "dB" if k == "dC" else me["dev_id"],
             "box_pk": base64.b64encode(bytes(v.public_key)).decode()} for k, v in keys.items()]
        sent = []
        with mock.patch.object(devkeys, "listing", lambda st: {"list": rows, "reg_version": 7}), \
                mock.patch.object(relay, "register", lambda st: None), \
                mock.patch.object(relay, "_post", lambda st, path, p: sent.append(p) or {}):
            res = rekey.remove_one(s, "dB")
        p = sent[0]
        self.assertEqual(res["gone"], ["dB", "dC"])
        self.assertEqual(json.loads(p["gone"]), ["dB", "dC"])
        self.assertEqual(set(json.loads(p["fwd"])), {"dD"})
        h = lambda x: hashlib.sha256(x.encode("utf-8")).hexdigest()  # noqa: E731
        line = f"rekey1|{res['old']}|{res['new']}|7|{h(p['gone'])}|{h(p['fwd'])}|{h(p['notes'])}|{p['t']}"
        from nacl.signing import VerifyKey
        VerifyKey(base64.b64decode(me["sign_pk"])).verify(line.encode(), base64.b64decode(p["sig_dev"]))
        from nacl.public import SealedBox
        letter = json.loads(SealedBox(keys["dD"]).decrypt(base64.b64decode(json.loads(p["fwd"])["dD"])))
        self.assertEqual(letter["code"], res["new"])
        self.assertEqual(p["mode"], "remove_one")
        self.assertTrue(devkeys.registered(s), "this device stays registered at the new address")


if __name__ == "__main__":
    unittest.main()
