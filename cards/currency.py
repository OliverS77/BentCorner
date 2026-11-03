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
_failed = 0.0   # last failed attempt: try again after RETRY at the earliest (not on every price job)
RETRY = 3600


def load():
    global _rates, _stamp
    try:
        data = json.loads(FILE.read_text("utf-8"))
        _rates = dict(data["rates"], EUR=1.0)
        _stamp = data.get("fetched", 0)
    except (OSError, ValueError, KeyError):
        pass


def refresh(max_age=86400):
    """Fetch rates from the net (call in the background). -> True if freshly loaded."""
    global _rates, _stamp, _failed
    if time.time() - _stamp < max_age and len(_rates) > 1:
        return False
    if time.time() - _failed < RETRY:   # offline / both addresses failed a moment ago: keep the last rates
        return False
    for url in URLS:
        try:
            r = netpolite.get(url, timeout=15)
            r.raise_for_status()
            rates = r.json()["rates"]
        except (requests.RequestException, ValueError, KeyError):
            continue
        _rates, _stamp = dict(rates, EUR=1.0), time.time()
        try:
            FILE.parent.mkdir(parents=True, exist_ok=True)
            FILE.write_text(json.dumps({"rates": rates, "fetched": _stamp}), "utf-8")
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


def fmt(v_eur):
    """Euro amount in the chosen currency, German formatting (1.234,56 $). Without a rate: euros."""
    code = current if current in _rates else "EUR"
    v = (v_eur or 0.0) * _rates.get(code, 1.0)
    digits = 0 if code == "JPY" else 2
    s = f"{v:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {SYMBOL[code]}"


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
