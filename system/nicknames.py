"""Device nicknames (Oliver/lead 12.11.2026): three words – „Tall Brave Fox“ / „Großer Mutiger Fuchs“ – unique within
the account, renamable (a typed name is free text and wins). Stored as nick: [a1, a2, n] in the device's */devices
entry – indices into nicknames.json, so a name shows in the app's language. The web reads the very same file (ports
copies it 1:1, both sides test its sha256) and follows the same rules:
  - drawing: a1 != a2 and never from the same "grp" (no „Großer Winziger …“), the triple unique against every nick in the list (and every typed name), else draw again;
  - two at the same time: the one with the larger (added, dev) draws again (like the device number);
  - an entry without a nick (an older device): fallback(dev) until the device writes its own."""
import functools
import hashlib
import json
import pathlib
import random

FILE = pathlib.Path(__file__).with_name("nicknames.json")
GENDER = {"m": 0, "f": 1, "n": 2}


@functools.lru_cache(maxsize=1)
def lists():
    d = json.loads(FILE.read_text("utf-8"))
    return d["adj"], d["noun"]


def sha256():
    return hashlib.sha256(FILE.read_bytes()).hexdigest()


def valid(nick):
    adj, noun = lists()
    try:
        a1, a2, n = (int(x) for x in nick)
    except (TypeError, ValueError):
        return False
    return (0 <= a1 < len(adj) and 0 <= a2 < len(adj) and a1 != a2 and adj[a1]["grp"] != adj[a2]["grp"]
            and 0 <= n < len(noun))


def render(nick, lang="en"):
    """[a1, a2, n] -> „Brave Tall Fox“ (en) / „Mutiger Großer Fuchs“ (de); None for anything else."""
    if not valid(nick):
        return None
    adj, noun = lists()
    a1, a2, n = (int(x) for x in nick)
    w = noun[n]
    if lang == "de":
        g = GENDER[w["g"]]
        return " ".join([adj[a1]["de"][g], adj[a2]["de"][g], w["de"]])
    return " ".join([adj[a1]["en"], adj[a2]["en"], w["en"]])


def fallback(dev):
    """An older entry without a nick (PC = web): from sha256(dev) – bytes 0–3, 4–7, 8–11 big-endian x, y, z;
    a1 = x % A; a2 = the (y % K)-th of the K adjectives (in list order) whose grp differs from a1's; n = z % N."""
    adj, noun = lists()
    h = hashlib.sha256(str(dev or "").encode("utf-8")).digest()
    x, y, z = (int.from_bytes(h[i:i + 4], "big") for i in (0, 4, 8))
    a1 = x % len(adj)
    other = [i for i, a in enumerate(adj) if a["grp"] != adj[a1]["grp"]]
    return [a1, other[y % len(other)], z % len(noun)]


def pick(taken=(), rng=None):
    """A new nickname no device of the account has – neither as its nick nor as a typed name (either language).
    taken: nicks ([a1, a2, n]) and/or names (str)."""
    rng = rng or random.SystemRandom()
    adj, noun = lists()
    used_idx = {tuple(int(x) for x in t) for t in taken if not isinstance(t, str) and valid(t)}
    used_names = {str(t).strip().casefold() for t in taken if isinstance(t, str)}
    used_names |= {render(t, lang).casefold() for t in used_idx for lang in ("en", "de")}
    for _ in range(1000):
        a1, a2 = rng.sample(range(len(adj)), 2)
        nick = (a1, a2, rng.randrange(len(noun)))
        if adj[a1]["grp"] == adj[a2]["grp"] or nick in used_idx or {render(nick, "en").casefold(), render(nick, "de").casefold()} & used_names:
            continue
        return list(nick)
    raise RuntimeError("no free nickname")   # 60·59·60 = 212 400 – an account never gets near it


def lang():
    """The app's language for rendering ("de" / "en")."""
    from system import i18n
    return "de" if str(i18n.LANG or "").startswith("de") else "en"


def name_of(d):
    """The name a device shows: its typed name, else its nickname (its own, or the fallback from its id)."""
    if d.get("name"):
        return d["name"]
    nick = d.get("nick") if valid(d.get("nick")) else (fallback(d["dev"]) if d.get("dev") else None)
    return render(nick, lang()) if nick else None
