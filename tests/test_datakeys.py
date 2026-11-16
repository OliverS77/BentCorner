"""Card data signed by the server's data key (cards/datakeys.py, lead/Gordon 07.11.): which keys count (only the
release manifest's data_keys), what a data key may deliver (the hard list), and that every delivered file is treated
as foreign – on the release path too. Keys are made here and thrown away; none is in the repository.

    python -m unittest tests.test_datakeys
"""
import base64
import gzip
import hashlib
import io
import json
import pathlib
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

import numpy as np
from nacl.signing import SigningKey

from cards import datakeys, packs
from net import updater

NOW = time.time()
DAY = 86400


def b64(k):
    return base64.b64encode(bytes(k.verify_key)).decode()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.rk, self.dk, self.dk2 = SigningKey.generate(), SigningKey.generate(), SigningKey.generate()
        self.cache = self.tmp / "updates"
        self.seq = self.tmp / "packs" / ".dataseq.json"
        for p in (mock.patch.object(updater, "PUBLIC_KEY", b64(self.rk)),
                  mock.patch.object(datakeys, "_cache_dir", lambda: self.cache),
                  mock.patch.object(datakeys, "_seq_file", lambda: self.seq)):
            p.start()
            self.addCleanup(p.stop)

    def release(self, data_keys=None, date="2026-11-07", t=None, key=None, keep=True):
        m = {"v": 1, "latest": "0.9.7", "date": date, "t": int(t if t is not None else NOW), "platforms": {}}
        if data_keys is not None:
            m["data_keys"] = data_keys
        raw = json.dumps(m).encode()
        sig = base64.b64encode((key or self.rk).sign(raw).signature).decode()
        if keep:
            self.assertTrue(updater.verify(raw, sig))
            datakeys.remember_release(raw, sig)
        return raw, sig

    def entry(self, kid="data-1", key=None, until="2099-01-01"):
        return {"id": kid, "pk": b64(key or self.dk), "until": until}

    def data(self, packs_=None, kid="data-1", seq=1, t=None, key=None, extra=None):
        m = {"v": 1, "key_id": kid, "seq": seq, "t": t if t is not None else NOW - 60,
             "packs": packs_ if packs_ is not None else
             {"pokemon": {"files": [{"name": "cards.sqlite", "size": 10, "sha256": "x"}]}}}
        m.update(extra or {})
        raw = json.dumps(m).encode()
        sig = base64.b64encode((key or self.dk).sign(datakeys.PREFIX2 + raw).signature).decode()   # packs-data2
        return raw, sig


class WhichKeysCount(Base):
    def test_nothing_built_in(self):
        self.assertEqual(datakeys.keys(), {})
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data())
        # the real public data key lives only in tools/datakeys_public.py (PC + web release) – never in the app's code
        root = pathlib.Path(__file__).resolve().parents[1]
        pk = "z9gwDxbizKziQGLdReDJ4UYpybPOluzuqjbj+eqn2Jg="
        for f in ("cards/datakeys.py", "cards/packs.py", "net/updater.py"):
            self.assertNotIn(pk, (root / f).read_text("utf-8"), f)
        shared = root / "tools/datakeys_public.py"   # private like publish_release (tools/public/manifest.txt)
        if shared.exists():
            self.assertIn(pk, shared.read_text("utf-8"))

    def test_release_reads_the_shared_list(self):
        """After the 0.9.7 ship (lead 12.11.): publish_release has no list of its own – it names exactly the keys of
        tools/datakeys_public.py (the same file the web's publish_web reads)."""
        root = pathlib.Path(__file__).resolve().parents[1]
        if not (root / "tools/publish_release.py").exists():
            self.skipTest("private tool not here")
        import sys
        sys.path.insert(0, str(root / "tools"))
        import datakeys_public
        import publish_release
        self.assertFalse(hasattr(publish_release, "DATA_KEYS"))
        self.assertNotIn("z9gwDxbizKziQGLdReDJ4UYpybPOluzuqjbj", (root / "tools/publish_release.py").read_text("utf-8"))
        self.assertEqual(publish_release.data_keys(), datakeys_public.DATA_KEYS)
        self.assertTrue(datakeys_public.DATA_KEYS)
        got = publish_release.data_keys()
        got[0]["until"] = "1999-01-01"                      # a copy: the shared list stays as it is
        self.assertNotEqual(datakeys_public.DATA_KEYS[0]["until"], "1999-01-01")

    def test_no_field_empty_or_unknown_id(self):
        for dk in (None, [], [self.entry(kid="other")]):
            with self.subTest(dk=dk):
                shutil_rm(self.cache)
                self.release(dk)
                with self.assertRaises(datakeys.DataRejected):
                    datakeys.verify_data(*self.data())

    def test_allowed_key_works(self):
        self.release([self.entry()])
        self.assertEqual(datakeys.verify_data(*self.data())["seq"], 1)

    def test_revoked_although_cached(self):
        self.release([self.entry()], t=NOW - 100)
        datakeys.verify_data(*self.data())
        self.release([], t=NOW)   # the new release manifest drops it
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data(seq=2))
        # the old manifest played back does not bring it back
        self.release([self.entry()], t=NOW - 100)
        self.assertEqual(datakeys.keys(), {})

    def test_until_passed(self):
        self.release([self.entry(until="2020-01-01")])
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data())

    def test_a_data_key_never_unlocks_itself(self):
        self.release([self.entry()])
        # data_keys inside a data manifest: ignored
        out = datakeys.verify_data(*self.data(extra={"data_keys": [self.entry("data-9", self.dk2)]}))
        self.assertNotIn("data_keys", out)
        self.assertEqual(set(datakeys.keys()), {"data-1"})
        # a "release manifest" signed with the data key: never kept, never the source of keys
        raw, sig = self.release([self.entry("data-9", self.dk2)], t=NOW + 50, key=self.dk, keep=False)
        datakeys.remember_release(raw, sig)
        self.assertEqual(set(datakeys.keys()), {"data-1"})

    def test_manifest_cache_with_a_bad_signature_counts_nothing(self):
        self.release([self.entry()])
        (self.cache / "release-manifest.json.sig").write_text(base64.b64encode(b"\0" * 64).decode())
        self.assertEqual(datakeys.keys(), {})


class DataKeyOnlyForCardData(Base):
    def setUp(self):
        super().setUp()
        self.release([self.entry(), self.entry("data-2", self.dk2)])

    def test_program_model_ocr_signed_with_the_data_key_refused(self):
        raw = json.dumps({"v": 1, "latest": "9.9.9", "platforms": {"windows": {"file": "x.exe"}}}).encode()
        for signed in (raw, datakeys.PREFIX + raw, datakeys.PREFIX2 + raw):
            sig = base64.b64encode(self.dk.sign(signed).signature).decode()
            self.assertFalse(updater.verify(raw, sig))
            r = mock.Mock(status_code=200, content=raw)
            s = mock.Mock(status_code=200, text=sig)
            with mock.patch("net.netpolite.get", side_effect=[r, s]), \
                    mock.patch.object(updater, "_first_today", return_value=False):
                with self.assertRaises(updater.UpdateError):
                    updater.fetch_manifest("https://x.invalid/dl")
        # the pack list (programs' data, release key) neither
        sig = base64.b64encode(self.dk.sign(raw).signature).decode()
        with mock.patch("net.netpolite.get", side_effect=[mock.Mock(status_code=200, content=raw),
                                                          mock.Mock(status_code=200, text=sig)]):
            with self.assertRaises(packs.PackError):
                packs.manifest()

    def test_non_data_entries_refuse_the_whole_manifest(self):
        good = {"name": "cards.sqlite", "size": 10}
        for bad in ({"lorcana": {"files": [{"name": "cards.sqlite", "size": 10}]}},
                    {"newgame": {"files": [{"name": "cards.sqlite", "size": 10}]}},
                    {"program": {"files": [{"name": "BentCorner.exe", "size": 10}]}},
                    {"pokemon": {"files": [good, {"name": "model.onnx", "size": 10}]}},
                    {"pokemon": {"files": [good, {"name": "ocr.onnx", "size": 10}]}},
                    {"mtg": {"files": [{"name": "cardback.npy", "size": 10}]}},
                    {"pokemon": {"files": [good]}, "models": {"files": [{"name": "scan.onnx", "size": 1}]}}):
            with self.subTest(bad=bad):
                with self.assertRaises(datakeys.DataRejected):
                    datakeys.verify_data(*self.data(bad))

    def test_only_three_games_ever(self):
        # the fixed list itself, independent of games/extras.py: no other game, never (lead 12.11.)
        self.assertEqual(set(datakeys.DATA_FILES), {"mtg", "pokemon", "yugioh"})

    def test_a_game_that_becomes_ready_later_stays_out(self):
        spec = {"name": "Lorcana", "dir": "lorcana", "files": ["cards.sqlite"]}
        with mock.patch.dict(packs.PACKS, {"lorcana": spec, "newgame": dict(spec, dir="newgame")}):
            for g in ("lorcana", "newgame"):
                with self.assertRaises(datakeys.DataRejected):
                    datakeys.verify_data(*self.data({g: {"files": [{"name": "cards.sqlite", "size": 1}]}}))
                # … while the release key still delivers it
                datakeys.check_files(g, [{"name": "cards.sqlite", "size": 1}], datakeys.release_names(g))

    def test_path_tricks(self):
        tricks = ["../cards.sqlite", "..\\cards.sqlite", "/cards.sqlite", "C:cards.sqlite", "C:\\x\\cards.sqlite",
                  "sub/cards.sqlite", "Cards.sqlite", "CARDS.SQLITE", "cards.sqlite.exe", "cards.sqlite ",
                  "cards.sqlite\0", "cards.db", "cards.sqlite:stream", "./cards.sqlite", ""]
        for name in tricks:
            with self.subTest(name=name):
                with self.assertRaises(datakeys.DataRejected):
                    datakeys.verify_data(*self.data({"pokemon": {"files": [{"name": name, "size": 1}]}}))
                with self.assertRaises(datakeys.DataRejected):   # the release path refuses the same
                    datakeys.check_files("pokemon", [{"name": name, "size": 1}], datakeys.release_names("pokemon"))
        for gz in ("cards.sqlite.GZ", "../cards.sqlite.gz", "cards.gz", "x.gz"):
            with self.assertRaises(datakeys.DataRejected):
                datakeys.check_files("pokemon", [{"name": "cards.sqlite", "size": 1, "gz": {"name": gz, "size": 1}}],
                                     datakeys.DATA_FILES["pokemon"])

    def test_release_key_still_counts_for_everything(self):
        for g in packs.PACKS:
            names = datakeys.release_names(g)
            datakeys.check_files(g, [{"name": n, "size": 1} for n in names], names)
        listing = {"packs": {"pokemon": {"files": [{"name": "cards.sqlite", "size": 1}], "date": "2026-11-07"}}}
        raw = json.dumps(listing).encode()
        sig = base64.b64encode(self.rk.sign(raw).signature).decode()
        with mock.patch("net.netpolite.get", side_effect=[mock.Mock(status_code=200, content=raw),
                                                          mock.Mock(status_code=200, text=sig),
                                                          mock.Mock(status_code=404), mock.Mock(status_code=404)]):
            self.assertEqual(packs.manifest(), listing["packs"])

    def test_sizes(self):
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data({"pokemon": {"files": [{"name": "cm_fix.json", "size": 21 << 20}]}}))

    def test_seq_per_key(self):
        datakeys.verify_data(*self.data(seq=5))
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data(seq=4))
        with self.assertRaises(datakeys.DataRejected):   # a stolen key's huge seq: refused, nothing remembered
            datakeys.verify_data(*self.data(seq=2 ** 62))
        datakeys.verify_data(*self.data(seq=6))
        # the next key starts on its own – data-1's seq never blocks it
        self.assertEqual(datakeys.verify_data(*self.data(kid="data-2", key=self.dk2, seq=1))["seq"], 1)
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data(seq=6 + datakeys.MAX_SEQ_JUMP + 1))

    def test_wrong_key_for_the_id_and_no_prefix(self):
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data(key=self.dk2))   # data-1 signed by data-2's key
        raw, _ = self.data()
        sig = base64.b64encode(self.dk.sign(raw).signature).decode()   # without the prefix
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(raw, sig)

    def test_t_in_the_future(self):
        with self.assertRaises(datakeys.DataRejected):
            datakeys.verify_data(*self.data(t=NOW + 2 * DAY))

    def test_only_packs_ever_leave_a_data_manifest(self):
        out = datakeys.verify_data(*self.data(extra={"games_off": {"pokemon": "x"}, "latest": "9.9.9",
                                                     "platforms": {"windows": {"file": "evil.exe"}}}))
        self.assertEqual(set(out), {"key_id", "seq", "t", "packs"})
        merged = datakeys.merge({}, out)
        self.assertEqual(set(merged), {"pokemon"})
        self.assertEqual(set(merged["pokemon"]), {"files", "t", "src", "rel_names"})


class WhichEntryWins(unittest.TestCase):
    rel = {"pokemon": {"name": "Pokémon-Daten", "files": [{"name": "cards.sqlite"}], "t": 1000},
           "yugioh": {"files": [{"name": "cards.sqlite"}], "date": "2026-11-07"}}

    def data(self, t, game="pokemon"):
        return {"t": t, "packs": {game: {"files": [{"name": "cards.sqlite", "size": 2}]}}}

    def test_newer_data_wins(self):
        out = datakeys.merge(self.rel, self.data(1001))
        self.assertEqual(out["pokemon"]["src"], "data")
        self.assertEqual(out["pokemon"]["name"], "Pokémon-Daten")
        self.assertNotIn("src", out["yugioh"])

    def test_release_wins_when_newer_or_equal(self):
        for t in (999, 1000):
            self.assertNotIn("src", datakeys.merge(self.rel, self.data(t))["pokemon"])

    def test_release_with_only_a_date_wins_the_whole_day(self):
        end = datakeys.release_time(self.rel["yugioh"])
        self.assertNotIn("src", datakeys.merge(self.rel, self.data(end - 1, "yugioh"))["yugioh"])
        self.assertEqual(datakeys.merge(self.rel, self.data(end + 1, "yugioh"))["yugioh"]["src"], "data")

    def test_a_game_only_in_the_data(self):
        self.assertEqual(datakeys.merge({}, self.data(5))["pokemon"]["src"], "data")


def shutil_rm(p):
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        for i in range(0, len(self.body), n):
            yield self.body[i:i + n]


class DeliveredFilesAreForeign(unittest.TestCase):
    """The hardening counts for both keys – here through the release path (packs.download)."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        p = mock.patch.object(packs, "ROOT", self.tmp / "packs")
        p.start()
        self.addCleanup(p.stop)
        self.dest = packs.folder("pokemon")
        self.dest.mkdir(parents=True)
        (self.dest / "cm_fix.json").write_text("{}", "utf-8")   # the old state

    def run_dl(self, entry, body, src=None):
        e = {"files": [entry]}
        if src:
            e["src"] = src
        with mock.patch.object(packs, "manifest", return_value={"pokemon": e}), \
                mock.patch("net.netpolite.get", return_value=Resp(body)):
            return packs.download("pokemon")

    def test_path_outside_refused(self):
        body = b"{}"
        with self.assertRaises(packs.PackError):
            self.run_dl({"name": "../evil.json", "size": len(body), "sha256": sha(body)}, body)
        self.assertFalse((self.tmp / "packs" / "evil.json").exists())

    def test_gz_bomb(self):
        raw = b"[" + b" " * (30 << 20) + b"]"
        gz = gzip.compress(raw)
        f = {"name": "cm_fix.json", "size": 10, "sha256": sha(raw), "gz": {"name": "cm_fix.json.gz", "size": len(gz),
                                                                           "sha256": sha(gz)}}
        with self.assertRaises(packs.PackError):
            self.run_dl(f, gz)
        self.assertEqual((self.dest / "cm_fix.json").read_text("utf-8"), "{}")

    def test_more_bytes_than_signed(self):
        body = b"{ }" + b" " * 100
        with self.assertRaises(packs.PackError):
            self.run_dl({"name": "cm_fix.json", "size": 3, "sha256": sha(body)}, body)
        self.assertEqual((self.dest / "cm_fix.json").read_text("utf-8"), "{}")

    def test_bad_json(self):
        body = b"\"just a string\""
        with self.assertRaises(packs.PackError):
            self.run_dl({"name": "cm_fix.json", "size": len(body), "sha256": sha(body)}, body)
        self.assertEqual((self.dest / "cm_fix.json").read_text("utf-8"), "{}")

    def db(self, extra_sql=""):
        p = self.tmp / "x.sqlite"
        p.unlink(missing_ok=True)
        con = sqlite3.connect(p)
        con.executescript("CREATE TABLE cards(id TEXT); CREATE TABLE meta(k TEXT, v TEXT);"
                          "CREATE VIRTUAL TABLE cards_fts USING fts5(name);" + extra_sql)
        con.commit()
        con.close()
        return p.read_bytes()

    def test_sqlite_probe(self):
        good = self.db()
        self.run_dl({"name": "cards.sqlite", "size": len(good), "sha256": sha(good)}, good)
        for bad in (self.db("CREATE TRIGGER t AFTER INSERT ON cards BEGIN DELETE FROM meta; END;"),
                    self.db("CREATE VIEW v AS SELECT * FROM cards;"),
                    b"SQLite format 3\0" + b"\x00" * 200):
            with self.subTest(n=len(bad)):
                with self.assertRaises(packs.PackError):
                    self.run_dl({"name": "cards.sqlite", "size": len(bad), "sha256": sha(bad)}, bad, src="data")
                self.assertEqual((self.dest / "cards.sqlite").read_bytes(), good, "the old state stays")
        con = sqlite3.connect(self.tmp / "y.sqlite")
        con.execute("CREATE TABLE other(x)")
        con.commit()
        con.close()
        body = (self.tmp / "y.sqlite").read_bytes()
        with self.assertRaises(packs.PackError):   # without its tables
            self.run_dl({"name": "cards.sqlite", "size": len(body), "sha256": sha(body)}, body)

    def npz(self, **arrays):
        b = io.BytesIO()
        np.savez(b, **arrays)
        return b.getvalue()

    def test_numpy_probe(self):
        good = self.npz(ids=np.array(["a", "b"]), vecs=np.zeros((2, 4), np.float16), meta=np.array("m"))
        self.run_dl({"name": "fingerprints-all.npz", "size": len(good), "sha256": sha(good)}, good, src="data")
        for bad in (self.npz(ids=np.array([{"x": 1}, 2], dtype=object), vecs=np.zeros((2, 4), np.float16)),
                    self.npz(ids=np.array(["a"]), vecs=np.zeros((2, 4), np.float16)),
                    self.npz(ids=np.array(["a", "b"]), vecs=np.zeros(8, np.float16)),
                    self.npz(ids=np.array(["a", "b"]))):
            with self.subTest(n=len(bad)):
                with self.assertRaises(packs.PackError):
                    self.run_dl({"name": "fingerprints-all.npz", "size": len(bad), "sha256": sha(bad)}, bad)
                self.assertEqual((self.dest / "fingerprints-all.npz").read_bytes(), good)


class ValuesFromTheData(unittest.TestCase):
    def test_set_codes_never_leave_the_image_folder(self):
        from scanner.common import IMAGES_REL, image_rel
        self.assertEqual(image_rel("sv3.5", "12", 0), f"{IMAGES_REL}/sv3.5/12_0.jpg")
        self.assertEqual(image_rel("MKM", "1", 0), f"{IMAGES_REL}/mkm/1_0.jpg")
        for sc in ("..", "../..", "..\\x", "/abs", "C:\\x", ".", "a/../b", "x\0y"):
            rel = image_rel(sc, "../1", 0)
            parts = pathlib.PurePosixPath(rel).parts
            self.assertEqual(len(parts), len(pathlib.PurePosixPath(IMAGES_REL).parts) + 2, rel)
            self.assertNotIn("..", parts)
            self.assertNotIn("\\", rel)
            self.assertNotIn(":", rel)

    def test_image_hosts(self):
        from cards import imgcache
        for ok in ("https://cards.scryfall.io/normal/front/a.jpg", "https://assets.tcgdex.net/en/sv/sv1/1/high.webp",
                   "https://bentcorner.app/dl/packs/yugioh/img/1.jpg",
                   "https://api.lorcana.ravensburger.com/images/x.jpg"):
            self.assertTrue(imgcache.host_ok(ok), ok)
        for bad in ("http://cards.scryfall.io/a.jpg", "https://evil.example/a.jpg", "https://scryfall.io.evil.example/a",
                    "https://user:pw!@cards.scryfall.io/a", "https://cards.scryfall.io:8443/a", "file:///C:/x.jpg",
                    "https://evilscryfall.io/a", "javascript:alert(1)", "http://127.0.0.1:8000/a.jpg"):
            self.assertFalse(imgcache.host_ok(bad), bad)

    def test_a_refused_host_is_not_fetched(self):
        from cards import imgcache
        with mock.patch.object(imgcache, "_images_off", return_value=False), \
                mock.patch.object(imgcache, "_same_image_on_disk", return_value=None), \
                mock.patch.object(imgcache, "offline", return_value=False), \
                mock.patch("net.netpolite.get") as get:
            self.assertFalse(imgcache.fetch(pathlib.Path(tempfile.mkdtemp()) / "a.jpg", "https://evil.example/a.jpg"))
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
