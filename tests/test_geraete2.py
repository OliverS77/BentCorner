"""Oliver's device test 2 (12.11.2026, lead): own code on a joined device, the same code again, unique default names,
Enter everywhere, removing empties the device. Stand-ins and temp folders only – no network, no real data.

    python -m unittest tests/test_geraete2.py
"""
import os
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore  # noqa: E402

from collection import syncrun  # noqa: E402
from tests.test_geraete import form_of, typed, wid  # noqa: E402
from ui import backupui, joinui, qsync  # noqa: E402

_app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
CODE = "Wolke7 trinkt Kakao am Nordbahnhof"


def own_page(st, sent, status=None):
    c = types.SimpleNamespace(settings={}, sync_status=status if status is not None else {},
                              guard_strength=lambda t: {"score": 3 if len(t) > 20 else 0, "ok": len(t) > 20},
                              sync_backup_set=lambda v: None, sync_rescue_confirm=lambda *a, **k: None,
                              vault_delete=lambda *a: None,
                              guard_set=lambda code, own=False, old=None: sent.append((code, old)))
    holder = {}
    f = form_of(lambda ui: backupui.rescue_items(ui, c, st, lambda: holder["f"].refresh(), lambda: None, lambda: None,
                                                 form=holder.get("f")))
    holder["f"] = f
    f.refresh()
    return f, c


def lines(f):
    f.refresh()
    return [v.get("html") for v in f._vals.values() if v.get("t") == "label" and not v.get("hidden")]


class SameCodeTest(unittest.TestCase):
    """3: the current code again as the new one – a calm line, nothing sent."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_same_code_says_so(self):
        sent = []
        f, c = own_page({"mode": "own", "change": True, "old": CODE}, sent)
        self.assertEqual(typed(f, "own_a", CODE), [])
        self.assertEqual(typed(f, "own_b", CODE), [])
        f.act(wid(f, "own_b"), ["enter", CODE])
        self.assertEqual(sent, [(CODE, CODE)])          # the server checks the old code as always (the web the same)
        c.sync_status["guard"] = "ok"                   # it was right – and nothing changed
        self.assertIn(backupui.SAME_CODE, lines(f))
        self.assertNotIn(backupui.CODE_FAILED, lines(f))
        f.act(wid(f, "own_b"), ["live", CODE + "!"])   # typing again: the line goes
        self.assertNotIn(backupui.SAME_CODE, lines(f))

    def test_other_code_goes(self):
        sent = []
        f, _ = own_page({"mode": "own", "change": True, "old": "der alte Code ist ganz anders"}, sent)
        typed(f, "own_a", CODE)
        typed(f, "own_b", CODE)
        f.act(wid(f, "own_b"), ["enter", CODE])
        self.assertEqual(sent, [(CODE, "der alte Code ist ganz anders")])

    def test_german(self):
        from locales import de
        self.assertEqual(de.TEXTS[backupui.SAME_CODE], "Schutz-Code nicht geändert – das ist schon dein Code.")


class DefaultNameTest(unittest.TestCase):
    """B (lead 12.11., the web alike): „<type> <n>“ with the shared number – never „Gerät n“."""

    def test_names(self):
        self.assertEqual(qsync.default_name("pc", 2), "PC 2")
        self.assertEqual(qsync.default_name("phone", 1), "Phone 1")
        self.assertEqual(qsync.device_name({"kind": "pc", "n": 3}), "PC 3")
        self.assertEqual(qsync.device_name({"kind": "phone", "n": 1}), "Phone 1")
        self.assertEqual(qsync.device_name({"me": True, "n": 4}), "PC 4")          # this app is a PC
        self.assertEqual(qsync.device_name({"name": "Küche", "kind": "pc", "n": 4}), "Küche")   # renaming stays
        self.assertEqual(joinui.other_name({"other": "phone", "other_n": 1}), "Phone 1")
        self.assertEqual(joinui.other_name({"other": "pc", "other_n": 2}), "PC 2")

    def test_german(self):
        from locales import de
        self.assertEqual(de.TEXTS[qsync.PHONE_N], "Handy {n}")
        self.assertEqual(de.TEXTS[qsync.PC_N], "PC {n}")


class NumberAndFromTest(unittest.TestCase):
    """The showing device counts even before its own entry is in the list (ports 12.11.: the phone got „1“ like the
    PC); C: the pairing step says whose code applies when this device had its own."""

    def test_next_number(self):
        from net import sync_ctl
        self.assertEqual(sync_ctl.next_number([]), 2)                       # before: 1 – the same as the PC
        self.assertEqual(sync_ctl.next_number([], mine=3), 4)
        self.assertEqual(sync_ctl.next_number([{"n": 1}, {"n": 2}]), 3)

    def test_extra_names_the_showing_device(self):
        from net import vault
        with mock.patch("net.guard.salt_of", return_value=None):
            ex = vault.pair_extra({"device_name": "Küche"}, 2, "d1", None, dev_nick=[34, 0, 0])
            self.assertEqual((ex["dev_nick"], ex["dev_name"], ex["next_n"]), ([34, 0, 0], "Küche", 2))
            self.assertNotIn("dev_name", vault.pair_extra({}, 2, "d1", None, dev_nick=[34, 0, 0]))

    def test_line_only_with_an_own_code(self):
        from tests.test_join_ui import UI, joiner, texts
        with mock.patch.object(syncrun, "available", return_value=True):
            b = joiner(sync_status={"join": "need_guard", "join_had_own": True, "join_from": "PC 1"})
            b.ctrl.sync_join_guard = lambda code: None
            b.ctrl.sync_join_drop = lambda: None
            self.assertIn(joinui.JOIN_FROM.format(device="PC 1"), texts(joinui.join_items(UI(), b, lambda: None)))
            b.ctrl.sync_status.update(join_had_own=False)
            t = texts(joinui.join_items(UI(), b, lambda: None))
            self.assertFalse([x for x in t if "applies to all devices" in str(x)])

    def test_german(self):
        from locales import de
        self.assertEqual(de.TEXTS[joinui.JOIN_FROM], "Ab jetzt gilt der Schutz-Code von {device} für alle Geräte.")
        self.assertIn(joinui.JOIN_FROM_OTHER, de.TEXTS)


class OwnCodeJoinedTest(unittest.TestCase):
    """1 (Oliver 12.11.): never „couldn't be set up“ when the code went through, never „Setting up …“ forever; a set
    code the device didn't know of -> its field. 2: the first field takes the focus when the page opens."""

    def setUp(self):
        self.p = mock.patch.object(syncrun, "available", return_value=True)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_need_old_goes_to_the_current_code(self):
        sent = []
        st = {"mode": "own"}
        f, c = own_page(st, sent)
        typed(f, "own_a", CODE)
        typed(f, "own_b", CODE)
        f.act(wid(f, "own_b"), ["enter", CODE])
        c.sync_status["guard"] = "need_old"
        f.refresh()                                       # the page switches over (its own refresh), then draws it
        t = lines(f)
        self.assertIn(backupui.CHANGE_OLD, t)
        self.assertNotIn(backupui.CODE_FAILED, t)
        self.assertNotIn(backupui.GUARD_WRONG, t)        # not „wrong“ – it wasn't typed yet
        self.assertEqual(st.get("change"), "old")

    def test_half_never_says_not_set_up(self):
        sent = []
        f, c = own_page({"mode": "own"}, sent)
        typed(f, "own_a", CODE)
        typed(f, "own_b", CODE)
        f.act(wid(f, "own_b"), ["enter", CODE])
        c.sync_status["guard"] = "half"
        self.assertIn(backupui.HALF, lines(f))
        self.assertNotIn(backupui.CODE_FAILED, lines(f))
        f.act(wid(f, "own_b"), ["enter", CODE])           # Next again: the envelope goes once more
        self.assertEqual(len(sent), 2)

    def test_generated_need_old_no_endless_busy(self):
        c = types.SimpleNamespace(settings={}, sync_status={"rescue": "need_old"}, sync_rescue_confirm=lambda *a, **k: None,
                                  vault_delete=lambda *a: None, guard_strength=lambda t: {"score": 0, "ok": False})
        st = {"mode": "gen", "code": "ABCDE-FGHIJ", "sent": True}
        f = form_of(lambda ui: backupui.rescue_items(ui, c, st, lambda: None, lambda: None, lambda: None))
        f.refresh()
        f.refresh()
        t = lines(f)
        self.assertNotIn(backupui.CODE_BUSY, t)
        self.assertIn(backupui.CHANGE_OLD, t)

    def test_ctrl_half(self):
        from net import sync_ctl
        cls = next(v for v in vars(sync_ctl).values() if isinstance(v, type) and hasattr(v, "_guard_done"))
        c = cls.__new__(cls)
        c.settings, c.sync_status = {}, {}
        c.settings_changed = c._sync_changed = lambda: None
        c.sync_engine = types.SimpleNamespace(meta={})
        err = OSError("offline")
        err.rescue_missing = True
        c._guard_done(err)
        self.assertEqual(c.sync_status["guard"], "half")
        self.assertTrue(c.settings["sync_rescue_missing"])   # the next try sends only the envelope

    def test_first_field_takes_the_focus(self):
        f, _ = own_page({"mode": "own"}, [])
        node = next(v for v in f._vals.values() if v.get("t") == "edit" and f._keys.get(v["id"]) == "own_a")
        self.assertTrue(node.get("focus"))

    def test_german(self):
        from locales import de
        self.assertIn(backupui.HALF, de.TEXTS)


class NicknameTest(unittest.TestCase):
    """Oliver/lead 12.11.: device nicknames – one list for PC and web (the hash), DE endings, unique, renamable."""
    SHA = "d371febeeb659f84512ecdcd77ef23c5c78a8ff4683cbea5bc33d67184e0d2c7"   # ports' web copy tests the same

    def test_one_list_for_pc_and_web(self):
        from system import nicknames
        self.assertEqual(nicknames.sha256(), self.SHA)
        adj, noun = nicknames.lists()
        self.assertGreaterEqual(min(len(adj), len(noun)), 60)
        self.assertEqual(len({a["en"] for a in adj}), len(adj))
        self.assertEqual(len({n["en"] for n in noun}), len(noun))
        for a in adj:   # strong endings m -er, f -e, n -es on one stem – no spelling tricks
            m, f, n = a["de"]
            self.assertEqual((m[:-2] + "e", m[:-2] + "es"), (f, n), a)
        self.assertTrue(all(n["g"] in ("m", "f", "n") for n in noun))
        words = {a["en"] for a in adj} | {n["en"] for n in noun}
        self.assertFalse(words & {"Sweet", "Goat", "Beaver", "Peacock", "Snail", "Dragon"})   # lead 12.11.: awkward
        import random
        rng = random.Random(3)
        for _ in range(300):   # never two adjectives of one group – drawn or from an id
            for nick in (nicknames.pick(rng=rng), nicknames.fallback(str(rng.random()))):
                self.assertNotEqual(adj[nick[0]]["grp"], adj[nick[1]]["grp"])

    def test_render_both_languages(self):
        from system import nicknames
        self.assertEqual(nicknames.render([34, 0, 0], "de"), "Großer Mutiger Fuchs")
        self.assertEqual(nicknames.render([15, 2, 1], "de"), "Kleine Schlaue Eule")
        self.assertEqual(nicknames.render([0, 1, 6], "de"), "Mutiges Ruhiges Eichhörnchen")
        self.assertEqual(nicknames.render([34, 0, 0], "en"), "Tall Brave Fox")
        self.assertIsNone(nicknames.render([3, 3, 0]))                     # two different adjectives
        self.assertEqual(nicknames.fallback("dev-abc"), [31, 39, 45])      # the test vector ports checks too
        self.assertIsNone(nicknames.render([34, 15, 0]))                   # Tall + Little: the same group, never

    def test_unique(self):
        import random
        from system import nicknames
        rng = random.Random(7)
        first = nicknames.pick(rng=random.Random(7))
        second = nicknames.pick([first, "Tall Brave Fox"], rng=random.Random(7))
        self.assertNotEqual(first, second)
        taken = [nicknames.pick(rng=rng) for _ in range(50)]
        self.assertEqual(len({tuple(t) for t in taken}), 50)

    def test_list_shows_nick_name_wins(self):
        from system import nicknames
        self.assertEqual(qsync.device_name({"dev": "a", "nick": [34, 0, 0]}), "Tall Brave Fox")
        self.assertEqual(qsync.device_name({"dev": "a", "nick": [34, 0, 0], "name": "Küche"}), "Küche")
        self.assertEqual(qsync.device_name({"dev": "dev-abc"}), nicknames.render([31, 39, 45], "en"))

    def test_shown_name_cleaned_nick_stays(self):
        """Merge lowfix (lead 12.11.): a device's own name is shown cleaned (textsafe), a device without a name keeps
        showing its nickname."""
        self.assertEqual(qsync.device_name({"dev": "a", "name": "Kü\x00che\u202e\x1b"}), "Küche")
        self.assertEqual(qsync.device_name({"dev": "a", "nick": [34, 0, 0]}), "Tall Brave Fox")
        self.assertEqual(qsync.device_name({"dev": "a", "nick": [34, 0, 0], "name": None}), "Tall Brave Fox")

    def test_record_writes_and_keeps_the_nick(self):
        e = syncrun.Engine.__new__(syncrun.Engine)
        e.meta = {}
        view = {"x": {"nick": [34, 0, 0], "added": 1}}
        nick = e._my_nick("me", view, None, 5)
        self.assertNotEqual(nick, [34, 0, 0])
        self.assertEqual(e._my_nick("me", view, {"nick": nick}, 5), nick)        # kept once drawn
        clash = {"x": {"nick": nick, "added": 1}}                                  # the other one was first
        self.assertNotEqual(e._my_nick("me", clash, {"nick": nick}, 5), nick)
        e.meta = {}
        later = {"x": {"nick": [34, 0, 0], "added": 9}}                            # I was first: mine stays
        self.assertEqual(e._my_nick("me", later, {"nick": [34, 0, 0]}, 5), [34, 0, 0])


class TakenCodeTest(unittest.TestCase):
    """Bug 1 root cause (lead 12.11.): rescue/put 409 – the envelope id (from the code alone) belongs to another
    address. A first code: envelope BEFORE the code – a 409 sets nothing. A change: the code is set, its envelope can't
    be – „half“ + „Choose a different code“ (the just-set one as the old, RAM only). Never said why."""

    def run_it(self, old, fail_put):
        from net import sync_ctl, vault
        calls = []

        def put(settings, code, keys=None):
            calls.append("put")
            if fail_put:
                raise vault.VaultError(409, "taken", {})
            return True
        with mock.patch("net.pairing.code_keys", return_value={"rid": "r", "rk": b"k" * 32, "main": b"m" * 32, "salt": "s"}),                 mock.patch("net.guard.setup_salt", return_value="s"),                 mock.patch("net.guard.set_code", side_effect=lambda *a, **k: calls.append("guard")),                 mock.patch.object(vault, "rescue_put", side_effect=put):
            try:
                sync_ctl._guard_and_envelope({}, "code", old, True, wait=0)
                return calls, None
            except Exception as e:  # noqa: BLE001
                return calls, e

    def test_first_code_envelope_first(self):
        calls, err = self.run_it(None, False)
        self.assertEqual((calls, err), (["put", "guard"], None))
        calls, err = self.run_it(None, True)
        self.assertEqual(calls, ["put"])                   # 409: the code was NOT set
        self.assertTrue(err.taken)
        self.assertFalse(getattr(err, "rescue_missing", False))

    def test_not_registered_yet_registers_and_goes_on(self):
        # desk-geraete3 box run 12.11.: the code right after switching on raced the device's first registration
        from net import sync_ctl, vault
        calls, reg = [], {"ok": False}

        def put(settings, code, keys=None):
            calls.append("put")
            if not reg["ok"]:
                raise vault.VaultError(403, "dev", {"dev_required": True})
            return True
        with mock.patch("net.pairing.code_keys", return_value={"rid": "r", "rk": b"k" * 32, "main": b"m" * 32, "salt": "s"}),                 mock.patch("net.guard.setup_salt", return_value="s"),                 mock.patch("net.guard.set_code", side_effect=lambda *a, **k: calls.append("guard")),                 mock.patch.object(vault, "rescue_put", side_effect=put),                 mock.patch("net.devkeys.registered", side_effect=lambda s: reg["ok"]),                 mock.patch("net.devkeys.register", side_effect=lambda s: (calls.append("register"), reg.update(ok=True))[0] or "ok"):
            sync_ctl._guard_and_envelope({}, "code", None, True, wait=0)
        self.assertEqual(calls, ["put", "register", "put", "guard"])
        calls.clear()                                    # registered meanwhile by the sync itself: just once more
        reg["ok"] = False
        with mock.patch("net.pairing.code_keys", return_value={"rid": "r", "rk": b"k" * 32, "main": b"m" * 32, "salt": "s"}),                 mock.patch("net.guard.setup_salt", return_value="s"),                 mock.patch("net.guard.set_code", side_effect=lambda *a, **k: calls.append("guard")),                 mock.patch.object(vault, "rescue_put", side_effect=lambda *a, **k: (put(*a, **k), reg.update(ok=True))[0]
                                  if reg["ok"] else (reg.update(ok=True), put(*a, **k))[1]),                 mock.patch("net.devkeys.registered", side_effect=lambda s: reg["ok"]),                 mock.patch("net.devkeys.register", side_effect=lambda s: calls.append("register") or "ok"):
            sync_ctl._guard_and_envelope({}, "code", None, True, wait=0)
        self.assertNotIn("register", calls)
        self.assertEqual(calls[-1], "guard")

    def test_change_code_first(self):
        calls, err = self.run_it("old", True)
        self.assertEqual(calls, ["guard", "put"])          # the envelope needs the new code's signature
        self.assertTrue(err.taken and err.rescue_missing)

    def test_pages(self):
        with mock.patch.object(syncrun, "available", return_value=True):
            sent = []
            f, c = own_page({"mode": "own"}, sent)
            typed(f, "own_a", CODE)
            typed(f, "own_b", CODE)
            f.act(wid(f, "own_b"), ["enter", CODE])
            c.sync_status["guard"] = "taken"
            self.assertIn(backupui.TAKEN, lines(f))
            st = {"mode": "own"}
            f, c = own_page(st, sent)
            typed(f, "own_a", CODE)
            typed(f, "own_b", CODE)
            f.act(wid(f, "own_b"), ["enter", CODE])
            c.sync_status["guard"] = "taken_half"
            f.refresh()
            other = [v for v in f._vals.values() if v.get("t") == "button" and v.get("text") == backupui.OTHER_CODE]
            self.assertTrue(other)
            f.act(other[0]["id"], None)
            self.assertEqual((st.get("change"), st.get("old")), (True, CODE))   # the just-set code as the old one
            self.assertNotIn("a", st)

    def test_ctrl_states(self):
        from net import sync_ctl
        cls = next(v for v in vars(sync_ctl).values() if isinstance(v, type) and hasattr(v, "_guard_done"))
        c = cls.__new__(cls)
        c.settings, c.sync_status = {}, {}
        c.settings_changed = c._sync_changed = lambda: None
        c.sync_engine = types.SimpleNamespace(meta={})
        err = OSError("409")
        err.taken = True
        c._guard_done(err)
        self.assertEqual(c.sync_status["guard"], "taken")
        self.assertNotIn("sync_rescue_missing", c.settings)   # nothing was set

    def test_german(self):
        from locales import de
        self.assertEqual(de.TEXTS[backupui.TAKEN], "Diesen Code kannst du nicht verwenden – wähl bitte einen anderen.")
        self.assertIn(backupui.OTHER_CODE, de.TEXTS)


class LegalCodeConditionsTest(unittest.TestCase):
    """legal 12.11. (via lead): the rid is derived slowly (Argon2id), a self-chosen code below 60 bits is refused – on
    the page AND in the ctrl, and the new line on both setup pages."""

    def test_rid_is_argon2id(self):
        from net import pairing
        with mock.patch("nacl.pwhash.argon2id.kdf", wraps=__import__("nacl.pwhash", fromlist=["argon2id"]).argon2id.kdf) as kdf:
            pairing.rescue_rid("ABCDE-FGHIJ")
        args, kw = kdf.call_args
        self.assertEqual((kw["opslimit"], kw["memlimit"]), (3, 64 * 1024 * 1024))
        self.assertEqual(args[2], pairing.STAGE1_SALT)

    def test_weak_own_code_refused_in_the_ctrl(self):
        from net import sync_ctl
        cls = next(v for v in vars(sync_ctl).values() if isinstance(v, type) and hasattr(v, "guard_set"))
        c = cls.__new__(cls)
        c.settings, c.sync_status = {}, {}
        c._sync_changed = lambda: None
        c._sync_bg = mock.Mock()
        with mock.patch.object(syncrun, "available", return_value=True):
            c.guard_set("hallo123", own=True)                        # real strength check (collection/codestrength)
        self.assertEqual(c.sync_status["guard"], "weak")
        c._sync_bg.assert_not_called()                               # nothing sent

    def test_weak_own_code_next_off(self):
        from collection import codestrength
        with mock.patch.object(syncrun, "available", return_value=True):
            c = types.SimpleNamespace(settings={}, sync_status={}, sync_rescue_confirm=lambda *a, **k: None,
                                      vault_delete=lambda *a: None, guard_set=mock.Mock(),
                                      guard_strength=lambda t: {"score": codestrength.strength(t)["score"],
                                                                "ok": codestrength.strength(t)["ok"]})
            holder, st = {}, {"mode": "own"}
            f = form_of(lambda ui: backupui.rescue_items(ui, c, st, lambda: holder["f"].refresh(),
                                                         lambda: None, lambda: None, form=holder.get("f")))
            holder["f"] = f
            typed(f, "own_a", "hallo123")
            typed(f, "own_b", "hallo123")
            f.act(wid(f, "own_b"), ["enter", "hallo123"])
        c.guard_set.assert_not_called()
        self.assertIn(backupui.WEAK, lines(f))

    def test_share_line(self):
        from locales import de
        self.assertEqual(de.TEXTS[backupui.SHARE_LINE], "Wer deinen Schutz-Code kennt, kann deine Online-Sicherung "
                         "zurückholen. Gib ihn niemandem und nimm keinen, den du schon woanders nutzt.")
        f, _ = own_page({"mode": "own"}, [])
        self.assertIn(backupui.SHARE_LINE, lines(f))


if __name__ == "__main__":
    unittest.main()
