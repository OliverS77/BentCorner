"""The pairing sphere in the app (ui/sphere.py): the same band as the readers were built for, one full turn, and the
pictures leave memory with the code. With labs/webapp/stripcode present (private repo): pixel for pixel the same as
labs' sphere.py, and Python's reader reads the app's frames through the phone camera model back to the code.

    python -m unittest tests/test_sphere.py
"""
import hashlib
import os
import pathlib
import sys
import unittest

import numpy as np

from net import pairing
from ui import sphere

CODE = "GTVP5 9R7VC"   # shown with a space since lead 13.11. (the picture bytes stay the same)
PAYLOAD = pairing.picture_bytes(CODE)
LABS = pathlib.Path(__file__).resolve().parents[2] / "labs" / "webapp" / "stripcode"
if not LABS.is_dir():   # a worktree: work/<name>/tests -> BentCorner/labs
    LABS = pathlib.Path(__file__).resolve().parents[3] / "labs" / "webapp" / "stripcode"


def labs():
    if not (LABS / "sphere.py").exists():
        return None
    os.environ.setdefault("SLIM_SAMPLE", "12")
    if str(LABS) not in sys.path:
        sys.path.insert(0, str(LABS))
    import sphere as L
    return L


class Band(unittest.TestCase):
    def test_band_is_fixed(self):
        """The band for a known code – the readers (sphere.js, sphere.py) depend on exactly this."""
        self.assertEqual(sphere.strip_values(PAYLOAD)[:16], [2, 3, 2, 2, 0, 0, 1, 2, 3, 1, 1, 2, 0, 1, 3, 0])
        self.assertEqual(hashlib.sha256(sphere.texture(PAYLOAD).tobytes()).hexdigest(),
                         "bfac63ffc443681ce48428c19dbf5de4bcf2bcfd32653415af58b93163729a12")

    def test_one_turn(self):
        fr = sphere.frames(PAYLOAD, n=8, size=120)
        self.assertEqual(len(fr), 8)
        self.assertEqual(fr[0].shape, (120, 120))
        self.assertEqual(fr[0].dtype, np.uint8)
        self.assertFalse(np.array_equal(fr[0], fr[2]), "it turns")
        self.assertEqual(sphere.PERIOD * sphere.FPS, 120)

    def test_payload_length(self):
        with self.assertRaises(ValueError):
            sphere.cells(b"\x02" * 7)


@unittest.skipIf(labs() is None, "labs/webapp/stripcode not here (public repo)")
class AsLabs(unittest.TestCase):
    def test_same_pictures_as_labs(self):
        L = labs()
        ta, tl = sphere.texture(PAYLOAD), L.texture(PAYLOAD)
        self.assertTrue(np.array_equal(ta, tl))
        for rot in (0.0, 1.3, 4.0):
            self.assertTrue(np.array_equal(sphere.render(ta, rot, size=200, radius=84),
                                           L.render(tl, rot, size=200, radius=84)), rot)

    def test_python_reader_reads_the_app_frames(self):
        """The app's turn on a screen, photographed (labs' phone model, set "phone"), read back to the code."""
        L = labs()
        fr = sphere.frames(PAYLOAD)
        rng = np.random.default_rng(7)
        p = dict(L.BASE, **L.SETS["phone"])
        p = dict(p, _pose=rng.uniform(-p.get("tilt", 0), p.get("tilt", 0), (4, 2)))
        rd, out = L.Reader(sphere.PERIOD), None
        for i in range(3 * len(fr)):
            out = rd.add(L.photo(rng, fr[(37 + i) % len(fr)], p)[0], i / sphere.FPS)
            if out is not None:
                break
        self.assertIsNotNone(out)
        self.assertEqual(pairing.code_of_picture(out), CODE)


class Memory(unittest.TestCase):
    def test_pictures_leave_with_the_code(self):
        from unittest import mock
        from net import sync_ctl
        from ui import quickimages
        kept = dict.fromkeys(["paircode9", "paircode9_blur", "paircode9_sblur", "paircode9_s0", "paircode9_s1",
                              "paircode9_s2", "other"], 1)
        ctl = type("C", (), {})()
        ctl.pair = {"img": "paircode9", "turn": 3}
        with mock.patch.object(quickimages, "drop", lambda key: kept.pop(key, None)):
            sync_ctl.SyncControl._pair_drop_images(ctl)
        self.assertEqual(list(kept), ["other"])

    def test_only_the_sphere_is_opaque(self):
        """lead 06.11.: no square behind the sphere – around it the card shows through."""
        from net import sync_ctl
        f = sphere.frames(PAYLOAD, n=1, size=120)[0]
        img = sync_ctl._sphere_image(f)
        self.assertEqual(img.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(img.pixelColor(119, 119).alpha(), 0)
        self.assertEqual(img.pixelColor(60, 60).alpha(), 255)
        self.assertEqual(img.pixelColor(60, 60).red(), f[60, 60])
        edge = int(60 + sphere.outline_radius(120) - 1)   # the outline itself is still there
        self.assertGreater(img.pixelColor(edge, 60).alpha(), 200)

class Vectors(unittest.TestCase):
    """docs/web/sphere-vectors.json is what ui/sphere.py draws now (the web's JS port checks the same file)."""

    def test_vectors_are_current(self):
        import json
        import pathlib
        from tools import make_sphere_vectors
        have = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs" / "web" / "sphere-vectors.json")
                          .read_text("utf-8"))
        self.assertEqual(json.loads(json.dumps(make_sphere_vectors.build())), have)

if __name__ == "__main__":
    unittest.main()
