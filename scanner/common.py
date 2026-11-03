"""Shared image preprocessing for reference images (Scryfall) and the webcam crop."""
import pathlib
import re

import cv2
import numpy as np

from system import datahome
import games

# Data folder (collection, settings, card data): chosen on first start, otherwise next to the .exe or the scripts
BASE = datahome.HOME
DATA = BASE / "data"
# Folder layout: card data (from Scryfall, can be re-downloaded any time) kept apart from personal data
# Separate folders per game (games.folders): Magic directly under data/ as before, others under data/games/<game>/
GAME = games.active_key(BASE / "settings.json")
_F = games.folders(GAME, DATA)
REF = _F["ref"]        # card database, set list, extra info
IMAGES = _F["images"]  # card images, one folder per set
RECOG = _F["recog"]    # recognition data per set (card list + image features)
MINE = _F["mine"]      # sessions, collection – the personal stuff (English folder names, see datastore.py)
IMAGES_REL = IMAGES.relative_to(BASE).as_posix()   # "data/card-images" for Magic


def switch_game(key):
    """Switch the game while the program is running: reset the folders and, in every loaded module, redirect each path
    that lies under a folder of the old game to the new game (FILE, DB_PATH, SETS …). Afterwards each module may
    recompute its game values (function _game_changed). The program then reloads the data itself
    (app.MainWindow.switch_game)."""
    import sys as _sys
    global GAME, _F, REF, IMAGES, RECOG, MINE, IMAGES_REL, W, H
    old = {"ref": REF, "images": IMAGES, "recog": RECOG, "mine": MINE}
    old_vals = {"REF": REF, "IMAGES": IMAGES, "RECOG": RECOG, "MINE": MINE, "IMAGES_REL": IMAGES_REL, "W": W, "H": H}
    games._current = None
    GAME = key
    _F = games.folders(key, DATA)
    REF, IMAGES, RECOG, MINE = _F["ref"], _F["images"], _F["recog"], _F["mine"]
    IMAGES_REL = IMAGES.relative_to(BASE).as_posix()
    games._current = games.load(key)
    W, H = games._current.card_px
    new = {"ref": REF, "images": IMAGES, "recog": RECOG, "mine": MINE}
    new_vals = {"REF": REF, "IMAGES": IMAGES, "RECOG": RECOG, "MINE": MINE, "IMAGES_REL": IMAGES_REL, "W": W, "H": H}

    def moved(p):
        for k, root in old.items():
            if p == root:
                return new[k]
            try:
                return new[k] / p.relative_to(root)
            except ValueError:
                continue
        return None
    for mod in list(_sys.modules.values()):
        name = getattr(mod, "__name__", "")
        if mod is None or name == __name__ or not hasattr(mod, "__file__") or ".venv" in str(getattr(mod, "__file__", "")):
            continue
        d = getattr(mod, "__dict__", {})
        for attr, val in list(d.items()):
            if attr in old_vals and val is old_vals[attr] and attr not in ("W", "H"):
                setattr(mod, attr, new_vals[attr])
            elif isinstance(val, pathlib.Path):
                p = moved(val)
                if p is not None:
                    setattr(mod, attr, p)
    for mod in list(_sys.modules.values()):
        fn = getattr(mod, "_game_changed", None)
        if callable(fn) and getattr(mod, "__name__", "") != __name__:
            fn()


def image_rel(set_code, number, face):
    """Path of a card image relative to the program folder."""
    num = re.sub(r"[^\w-]", "_", number)
    return f"{IMAGES_REL}/{set_code.lower()}/{num}_{face}.jpg"


def lang_img(img, lang):
    """Image path of the language version: data/card-images/fin/115_0.jpg -> data/card-images/fin/ja/115_0.jpg"""
    if not lang or lang == "en":
        return img
    head, _, tail = img.rpartition("/")
    return f"{head}/{lang}/{tail}"


W, H = games.load(GAME).card_px  # the game's card format (Magic 63:88 → 336 × 468) for recognition
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def make_orb(n=800):
    return cv2.ORB_create(nfeatures=n, scaleFactor=1.2, nlevels=8,
                          edgeThreshold=15, patchSize=31, fastThreshold=12)


def prep(bgr):
    img = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return _clahe.apply(gray)


def features(orb, gray):
    kp, des = orb.detectAndCompute(gray, None)
    if des is None or len(kp) == 0:
        return np.zeros((0, 2), np.float32), np.zeros((0, 32), np.uint8)
    return np.float32([k.pt for k in kp]), des
