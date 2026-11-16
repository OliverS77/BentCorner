"""Display currency for collection and library.

Prices come in euros (Cardmarket); for display they are converted with the ECB rates (frankfurter.dev,
loaded once a day; offline, the last known rates apply).
"""
import json
import time

import requests

from scanner.common import REF
from net import netpolite
from system.i18n import tr

# names are English UI texts (translated with tr() where shown, ui/qsetpages.py)
CURRENCIES = [("EUR", "€", "Euro"), ("USD", "$", "US dollar"), ("GBP", "£", "British pound"),
              ("CHF", "CHF", "Swiss franc"), ("CAD", "C$", "Canadian dollar"),
              ("AUD", "A$", "Australian dollar"), ("JPY", "¥", "Japanese yen"), ("PLN", "zł", "Polish złoty"),
              ("SEK", "kr", "Swedish krona"), ("DKK", "kr", "Danish krone"), ("NOK", "kr", "Norwegian krone"),
              ("CZK", "Kč", "Czech koruna")]
SYMBOL = {c: s for c, s, _ in CURRENCIES}
FILE = REF / "exchange-rates.json"
URLS = ["https://api.frankfurter.dev/v1/latest?base=EUR", "https://api.frankfurter.app/latest?from=EUR"]

current = "EUR"
_rates = {"EUR": 1.0}
_stamp = 0.0
_day = None     # the day of the rates (ECB reference rate: "date" of the source, else the day they were fetched)
_failed = 0.0   # last failed attempt: try again after RETRY at the earliest (not on every price job)
RETRY = 3600


def _day_of(date, fetched):
    if isinstance(date, str) and len(date) == 10:
        return date
    return time.strftime("%Y-%m-%d", time.gmtime(fetched)) if fetched else None


def load():
    global _rates, _stamp, _day
    try:
        data = json.loads(FILE.read_text("utf-8"))
        _rates = dict(data["rates"], EUR=1.0)
        _stamp = data.get("fetched", 0)
        _day = _day_of(data.get("date"), _stamp)
    except (OSError, ValueError, KeyError):
        pass


def rate_day():
    """Day of the exchange rate in use ("YYYY-MM-DD") or None – stored with every converted price (price_est)."""
    return _day


def refresh(max_age=86400):
    """Fetch rates from the net (call in the background). -> True if freshly loaded."""
    global _rates, _stamp, _failed, _day
    if time.time() - _stamp < max_age and len(_rates) > 1:
        return False
    if time.time() - _failed < RETRY:   # offline / both addresses failed a moment ago: keep the last rates
        return False
    for url in URLS:
        try:
            r = netpolite.get(url, timeout=15)
            r.raise_for_status()
            body = r.json()
            rates = body["rates"]
        except (requests.RequestException, ValueError, KeyError):
            continue
        _rates, _stamp = dict(rates, EUR=1.0), time.time()
        date = body.get("date") if isinstance(body, dict) else None
        _day = _day_of(date, _stamp)
        try:
            FILE.parent.mkdir(parents=True, exist_ok=True)
            FILE.write_text(json.dumps({"rates": rates, "fetched": _stamp, "date": _day}), "utf-8")
        except OSError:
            pass
        return True
    _failed = time.time()
    return False


def set_current(code):
    global current
    current = code if code in SYMBOL else "EUR"


def available():
    """Currency usable? (rate known)"""
    return current in _rates


def convert(v_eur):
    return None if v_eur is None else v_eur * _rates.get(current, 1.0)


def fmt(v_eur, est=False):
    """Euro amount in the chosen currency, German formatting (1.234,56 $). Without a rate: euros.
    est: the amount is (or contains) a price converted from dollars – „≈ " in front (legal 14.11.2026; real
    Cardmarket euros stay without a sign)."""
    code = current if current in _rates else "EUR"
    v = (v_eur or 0.0) * _rates.get(code, 1.0)
    digits = 0 if code == "JPY" else 2
    s = f"{v:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'≈ ' if est else ''}{s} {SYMBOL[code]}"


APPROX = "≈"


def approx_tip(day=None):
    """The legal text on every „≈" and once in the price legend (legal 14.11.2026, word for word):
    „umgerechnet aus dem US-Preis von TCGplayer (Kurs EZB vom 14.11.2026)“ – without a known day, no bracket."""
    if day:
        try:
            shown = time.strftime("%d.%m.%Y", time.strptime(str(day)[:10], "%Y-%m-%d"))
        except ValueError:
            shown = ""
        if shown:
            return tr("converted from the TCGplayer US price (ECB rate of {date})").replace("{date}", shown)
    return tr("converted from the TCGplayer US price")


def approx_sum(parts):
    """parts: iterable of (amount or None, sid or None) -> (sum, converted?, newest rate day or None). A sum with
    at least one converted price gets „≈" (legal 14.11.)."""
    total, est, day = 0.0, False, None
    for v, sid in parts:
        if not v:
            continue
        total += v
        if sid and estimated(sid):
            est = True
            d = rate_day_of(sid)
            if d and (day is None or d > day):
                day = d
    return total, est, day


def estimated(sid, game=None):
    """Is this printing's euro price converted from dollars? The open game's card database – or another game's
    (game=key: a card of another game in a mixed trade, another game's binder – lead 14.11.2026)."""
    if not sid:
        return False
    try:
        import games
        if game and game != games.current().key:
            from games.base import price_est_map
            return sid in price_est_map(game)
        return games.current().price_estimated(sid)
    except Exception:  # noqa: BLE001 – a mark must never break a price
        return False


def rate_day_of(sid, game=None):
    try:
        import games
        if game and game != games.current().key:
            from games.base import price_est_map
            return price_est_map(game).get(sid)
        return games.current().price_rate_day(sid)
    except Exception:  # noqa: BLE001
        return None


def from_usd(v_usd):
    """US dollars -> euros (for TCGplayer prices); None without a rate."""
    rate = _rates.get("USD")
    return None if v_usd is None or not rate else v_usd / rate


def rate_info():
    if current == "EUR":
        return ""
    if current not in _rates:
        return tr("Rate not loaded yet – shown in euro")
    stamp = time.strftime("%d.%m.%Y", time.localtime(_stamp)) if _stamp else "?"
    return tr(f"1 € = {_rates[current]:.4f} {SYMBOL[current]} (ECB, as of {stamp})")   # German: decimal comma (RULES)


load()
