"""Language of a recognised card: the image match knows exactly where the card lies in the camera image (homography
to the reference image) – so it is straightened exactly and only the name line (if need be the type line) is read.
The read name is compared with the printed names of this card in all languages (card database, table
langs). Unambiguous -> language, otherwise None (then the program asks).
"""
import re

import cv2
import numpy as np
from rapidfuzz import fuzz

from cards import carddb
from scanner import hybrid
from scanner.common import BASE, H, W, features, make_orb, prep

OUT_W, OUT_H = 672, 936                 # straightened card (double working size, better for text recognition)
NAME_BAND = (0.06, 0.035, 0.78, 0.095)  # x0, y0, x1, y1 as shares of the card (mana cost on the right stays out)
TYPE_BAND = (0.06, 0.555, 0.85, 0.605)
MIN_SCORE, MIN_GAP = 62, 12             # best name this similar – and this much better than the next language
ASIA = ("ja", "ko", "zhs", "zht", "th", "id")
# Chinese characters and kana: the text reader (Chinese model) turns Japanese kana into Chinese characters too
_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

# type line: words per language (in case the name is the same in several languages or unreadable)
TYPE_WORDS = {
    "en": ["creature", "instant", "sorcery", "enchantment", "artifact", "land", "planeswalker", "legendary"],
    "de": ["kreatur", "spontanzauber", "hexerei", "verzauberung", "artefakt", "land", "planeswalker", "legendäre"],
    "fr": ["créature", "éphémère", "rituel", "enchantement", "artefact", "terrain", "légendaire"],
    "es": ["criatura", "instantáneo", "conjuro", "encantamiento", "artefacto", "tierra", "legendaria"],
    "it": ["creatura", "istantaneo", "stregoneria", "incantesimo", "artefatto", "terra", "leggendaria"],
    "pt": ["criatura", "mágica instantânea", "feitiço", "encantamento", "artefato", "terreno", "lendária"],
}

_orb = None


def _homography(img, ref_path):
    """Camera image crop -> coordinates of the reference image (both at W×H) or None."""
    global _orb
    ref = hybrid._ref_path(ref_path)
    if ref is None:
        return None
    if _orb is None:
        _orb = make_orb(1000)
    qp, qd = features(_orb, prep(img))
    rp, rd = ref
    if len(qd) < 10 or len(rd) < 10:
        return None
    good = [m[0] for m in hybrid._bf.knnMatch(qd, rd, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
    if len(good) < 12:
        return None
    hmat, mask = cv2.findHomography(qp[[m.queryIdx for m in good]], rp[[m.trainIdx for m in good]], cv2.RANSAC, 6.0)
    if hmat is None or mask is None or mask.sum() < 20:
        return None
    return hmat


def card_view(img, entry, frame=None, box=None):
    """Crop -> card straightened (OUT_W×OUT_H, aligned like the reference image) or None. With frame and
    box (position of the crop in the camera image) it is warped from the whole image – parts of the card outside the
    crop (top, bottom) are then included."""
    hmat = _homography(img, BASE / entry["img"])
    if hmat is None:
        return None
    h, w = img.shape[:2]
    s_in = np.diag([W / w, H / h, 1.0])            # crop -> working size
    s_out = np.diag([OUT_W / W, OUT_H / H, 1.0])   # working size -> output
    m = s_out @ hmat @ s_in
    if frame is not None and box is not None:
        shift = np.array([[1, 0, -box[0]], [0, 1, -box[1]], [0, 0, 1]], np.float64)  # camera image -> crop
        return cv2.warpPerspective(frame, m @ shift, (OUT_W, OUT_H), flags=cv2.INTER_CUBIC)
    return cv2.warpPerspective(img, m, (OUT_W, OUT_H), flags=cv2.INTER_CUBIC)


def _band(card, box):
    x0, y0, x1, y1 = box
    return card[int(y0 * OUT_H):int(y1 * OUT_H), int(x0 * OUT_W):int(x1 * OUT_W)]


def _read(part):
    from scanner import ocrscan
    res, _ = ocrscan.run(part)
    return " ".join(t for _, t, sc in (res or []) if sc > 0.4).strip()


def _norm(s):
    """Lower case, without accents/umlauts (text recognition often reads "Unterstützer" as "Unterstutzer")."""
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^\w]+", " ", s).strip()


def printed_names(entry):
    """{language: printed name} of this card – across all prints with that name (a chosen special print often exists
    only in English, while the card in the hand is German). English is always included."""
    out = {"en": entry["name"]}
    try:
        with carddb.connection() as db:
            if entry.get("plang"):   # Asian print (Pokémon: own sets) – only the languages this very print exists in
                own = {lang: name for lang, name in db.execute(
                    "select lang, name from langs where set_code = ? and number = ? and name is not null",
                    (entry["set"].lower(), str(entry["number"])))}
                return own or {entry["plang"]: entry["name"]}
            for lang, name in db.execute(
                    "select l.lang, l.name from langs l join cards c on c.set_code = l.set_code and c.number = l.number "
                    "where c.name = ? and l.name is not null", (entry["name"],)):
                out.setdefault(lang, name)
    except Exception:  # noqa: BLE001 – no language table: only English known
        pass
    return out


def print_in_lang(entry, lang):
    """If the chosen print doesn't exist in this language: a print of the same card that does (same set
    preferred) -> card database row or None (= the chosen one fits)."""
    if not lang or lang == "en":
        return None
    try:
        with carddb.connection() as db:
            if db.execute("select 1 from langs where set_code = ? and number = ? and lang = ?",
                          (entry["set"].lower(), str(entry["number"]), lang)).fetchone():
                return None
            artist = db.execute("select artist from cards where set_code = ? and number = ?",
                                (entry["set"].lower(), str(entry["number"]))).fetchone()
            # same artist first (= same artwork, e.g. the Japanese print of a western card), then the same set
            row = db.execute(
                "select c.set_code, c.number from langs l join cards c on c.set_code = l.set_code and "
                "c.number = l.number where c.name = ? and l.lang = ? "
                "order by (c.artist is ?) desc, (c.set_code = ?) desc limit 1",
                (entry["name"], lang, artist[0] if artist else None, entry["set"].lower())).fetchone()
            if row:
                return hybrid.row_by_print(row[0], row[1])
    except Exception:  # noqa: BLE001
        pass
    return None


def vote(votes):
    """[(language, score)] -> language as soon as one reading is very clear (≥ 85) or two agree."""
    for lg, sc in votes:
        if sc >= 85:
            return lg
    langs = [lg for lg, _ in votes]
    for lg in set(langs):
        if langs.count(lg) >= 2:
            return lg
    return None


def _layout():
    """Position of the name line and language words per game (games.<game>.lang_layout) – Magic: as above."""
    import games
    lay = games.current().lang_layout
    if lay is None:
        return {"name": NAME_BAND, "words": [TYPE_BAND], "type_words": TYPE_WORDS, "partial": False}
    return lay


def detect(img, entry, frame=None, box=None):
    """-> (language or None, info). None = unclear (ask) or not readable."""
    names = printed_names(entry)
    if len(names) == 1:
        return next(iter(names)), {"why": "printed in one language only"}
    card = card_view(img, entry, frame, box)
    if card is None:
        return None, {"why": "card can't be straightened"}
    lay = _layout()
    sim = fuzz.partial_ratio if lay.get("partial") else fuzz.ratio   # Pokémon: "Basis Wiesenior 110 KP"
    title, scores = "", {}
    for band in lay.get("names") or [lay["name"]]:   # several possible name lines (e.g. Trainer: below the banner)
        t = _read(_band(card, band))
        sc = {lang: sim(_norm(name), _norm(t)) if len(_norm(name)) >= 3 else fuzz.ratio(_norm(t), _norm(name))
              for lang, name in names.items()}
        if not scores or max(sc.values()) > max(scores.values()):
            title, scores = t, sc
        if max(sc.values()) >= 90:
            break
    ranked = sorted(scores.items(), key=lambda t: -t[1])
    info = {"title": title, "scores": ranked[:4]}
    best, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    # same name in several languages (e.g. EN = DE): then the type line decides
    han = "".join(_CJK.findall(title))
    if len(han) >= 2 and (score < MIN_SCORE or best in ASIA):
        # Asian card: only Asian languages come into question (never guess a western one from type words).
        # Chinese is read correctly – so Chinese only if the Chinese characters themselves match ("VSTAR" alone
        # doesn't count), unreadable kana mean Japanese.
        asia = [lg for lg in names if lg in ASIA]
        chinese = [lg for lg in asia if lg in ("zht", "zhs")
                   and fuzz.ratio("".join(_CJK.findall(names[lg])), han) >= MIN_SCORE]
        if chinese:
            return chinese[0], info
        if "ja" in asia:
            return "ja", info
        return (asia[0], info) if len(asia) == 1 else (None, info)
    tied = [lang for lang, sc in ranked if sc >= score - 2]
    if score >= MIN_SCORE and (score - second >= MIN_GAP or len(set(_norm(names[l]) for l in tied)) == 1):
        if len(tied) == 1:
            return best, info
    typ = _norm(" ".join(_read(_band(card, b)) for b in lay["words"]))
    info["type"] = typ
    cands = tied if score >= MIN_SCORE else list(names)
    hits = {lang: max((fuzz.partial_ratio(_norm(w), typ) for w in lay["type_words"].get(lang, [])), default=0)
            for lang in cands}
    ranked_t = sorted(hits.items(), key=lambda t: -t[1])
    info["type_scores"] = ranked_t[:3]
    if ranked_t and ranked_t[0][1] >= 80 and (len(ranked_t) == 1 or ranked_t[0][1] - ranked_t[1][1] >= 10):
        return ranked_t[0][0], info
    return None, info
