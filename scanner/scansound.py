"""Scan sounds: short, quiet, pleasant – only the highest matching one plays.

  tick  every automatically counted card (one soft tone)
  hit   price at or above the hit threshold (Settings → Scanning → "Hit from", same as the hit animation)
  rare  from 50 € (fixed, not configurable – always euros, whatever currency is displayed)
  wish  the card is on a wish list (0.9.9, Oliver via Gordon 14.11.2026) – before all others

Volume (dock key "Sound" on the scan page, setting scan_volume 0–10, 0 = off): winsound knows no volume, so the level
is rendered into the WAV – one file per sound and level, made only when needed. Level 7 (the default) is exactly the
sound of before (factor 1.0, lead 14.11.); below and above on a quadratic curve, which sounds like even steps.

The program synthesizes the sounds itself (sine with overtones and a soft decay, no third-party material) and stores
them once as small WAV files in data/cache/sounds. Playback: on Windows via winsound (runs in the background, blocks
nothing; a new sound replaces the old one). Other systems: silent for now.
"""
import logging
import math
import struct
import sys
import wave

from scanner.common import DATA

log = logging.getLogger(__name__)

RARE_EUR = 50.0
RATE = 44100
VERSION = 1   # sound changed: bump the number and the files get regenerated
FOLDER = DATA / "cache" / "sounds"

# per sound: [(frequency Hz, onset s, decay s, volume)]
NOTES = {
    "tick": [(1046.5, 0.0, 0.028, 0.28)],                                     # C6, very short
    "hit": [(1318.5, 0.0, 0.09, 0.30), (1975.5, 0.075, 0.12, 0.30)],          # E6 → B6, rising
    "rare": [(1046.5, 0.0, 0.16, 0.23), (1318.5, 0.065, 0.16, 0.23),          # C6 E6 G6 C7 – a small arpeggio,
             (1568.0, 0.13, 0.18, 0.23), (2093.0, 0.195, 0.30, 0.26)],        # the last note rings out long
    "wish": [(1568.0, 0.0, 0.22, 0.24), (2349.3, 0.11, 0.42, 0.24),          # G6 → D7, bell-like, a long tail –
             (3136.0, 0.11, 0.10, 0.05)],                                       # with a faint shimmer above: a star
}
LEVELS = 10
DEFAULT_LEVEL = 7


def gain(level):
    """Level 0–10 -> factor on the samples: 7 = 1.0 (the sound of before), quadratic (0 → silent, 10 ≈ 2.0)."""
    level = max(0, min(LEVELS, int(level)))
    return (level / DEFAULT_LEVEL) ** 2


def level_of(settings):
    """The volume level from the settings; older settings with scan_sounds off = 0 (whoever switched off stays off)."""
    v = settings.get("scan_volume")
    if v is None:
        return DEFAULT_LEVEL if settings.get("scan_sounds", True) else 0
    try:
        return max(0, min(LEVELS, int(v)))
    except (TypeError, ValueError):
        return DEFAULT_LEVEL


def _render(notes, factor=1.0):
    """Notes -> 16-bit samples (mono). Each note: fundamental + quiet overtones, 4 ms attack, exponential decay.
    factor: the volume (gain()) – applied after the normalisation, so 1.0 gives exactly the samples of before."""
    length = max(start + tau * 7 for _f, start, tau, _a in notes)
    n = int(length * RATE)
    buf = [0.0] * n
    for f, start, tau, amp in notes:
        s0 = int(start * RATE)
        for i in range(n - s0):
            t = i / RATE
            env = min(1.0, t / 0.004) * math.exp(-t / tau)
            if env < 1e-4 and t > 0.01:
                break
            w = math.sin(2 * math.pi * f * t) + 0.22 * math.sin(4 * math.pi * f * t) + 0.06 * math.sin(6 * math.pi * f * t)
            buf[s0 + i] += amp * env * w
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = min(1.0, 0.8 / peak) * factor
    return b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x * scale)) * 32767)) for x in buf)


def path(kind, level=DEFAULT_LEVEL):
    """WAV of the sound at this volume level (generated on demand) -> path or None (also for level 0)."""
    level = max(0, min(LEVELS, int(level)))
    if level == 0:
        return None
    f = FOLDER / f"scan-{kind}-v{VERSION}-l{level}.wav"
    if not f.exists():
        try:
            FOLDER.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(_render(NOTES[kind], gain(level)))
            tmp.replace(f)
        except OSError:
            log.exception("Creating scan sound %s", kind)
            return None
    return f


def kind_for(price_eur, hit, wish=False):
    """Which sound fits? Only the highest: wish (on a wish list) > rare (from 50 €) > hit (from the threshold) > tick."""
    if wish:
        return "wish"
    if price_eur is not None and price_eur >= RARE_EUR:
        return "rare"
    if price_eur is not None and hit is not None and price_eur >= hit:
        return "hit"
    return "tick"


def play(kind, level=DEFAULT_LEVEL):
    if sys.platform != "win32" or level <= 0:
        return
    f = path(kind, level)
    if f is None:
        return
    try:
        import winsound
        winsound.PlaySound(str(f), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:  # noqa: BLE001 – no audio device or similar: just stay silent
        log.info("Scan sound %s cannot be played", kind)


def prepare(level=DEFAULT_LEVEL):
    """Generate all sounds of the level in use up front (in the background at startup or after a change on the
    slider) – the first scan should not have to wait."""
    for kind in NOTES:
        path(kind, level)


def sample(level):
    """The slider was moved: play one tick at the new level (a hint how loud it is now) – nothing at 0."""
    play("tick", level)
