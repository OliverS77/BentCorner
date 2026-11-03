"""Scan sounds: short, quiet, pleasant – only the highest matching one plays.

  tick  every automatically counted card (one soft tone)
  hit   price at or above the hit threshold (Settings → Scanning → "Hit from", same as the hit animation)
  rare  from 50 € (fixed, not configurable – always euros, whatever currency is displayed)

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
}


def _render(notes):
    """Notes -> 16-bit samples (mono). Each note: fundamental + quiet overtones, 4 ms attack, exponential decay."""
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
    scale = min(1.0, 0.8 / peak)
    return b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x * scale)) * 32767)) for x in buf)


def path(kind):
    """WAV of the sound (generated on demand) -> path or None."""
    f = FOLDER / f"scan-{kind}-v{VERSION}.wav"
    if not f.exists():
        try:
            FOLDER.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(_render(NOTES[kind]))
            tmp.replace(f)
        except OSError:
            log.exception("Creating scan sound %s", kind)
            return None
    return f


def kind_for(price_eur, hit):
    """Which sound fits? Only the highest: rare (from 50 €) > hit (from the hit threshold) > tick."""
    if price_eur is not None and price_eur >= RARE_EUR:
        return "rare"
    if price_eur is not None and hit is not None and price_eur >= hit:
        return "hit"
    return "tick"


def play(kind):
    if sys.platform != "win32":
        return
    f = path(kind)
    if f is None:
        return
    try:
        import winsound
        winsound.PlaySound(str(f), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:  # noqa: BLE001 – no audio device or similar: just stay silent
        log.info("Scan sound %s cannot be played", kind)


def prepare():
    """Generate all sounds up front (in the background at startup) – the first scan should not have to wait."""
    for kind in NOTES:
        path(kind)
