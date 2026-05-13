"""
Fetch daily EUR FX rates from the ECB XML feed (free, no API key required).
Rates are cached in logs/fx_rates.json and refreshed once per calendar day.

ECB feed URL:
  https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml

Rate semantics: 1 EUR = <rate> <currency>
  → to convert GBP price to EUR: price_eur = price_gbp / rates["GBP"]
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

from config.settings import LOGS_DIR

log = logging.getLogger(__name__)

ECB_URL    = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CACHE_FILE = LOGS_DIR / "fx_rates.json"

# ECB XML namespaces
_NS_ECB = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"


def _fetch_from_ecb() -> Optional[dict[str, float]]:
    """Download and parse the ECB daily FX XML. Returns {currency: rate} or None."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(ECB_URL)
            resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as exc:
        log.warning("ECB FX fetch failed: %s", exc)
        return None

    rates: dict[str, float] = {"EUR": 1.0}
    for cube in root.iter(f"{{{_NS_ECB}}}Cube"):
        currency = cube.get("currency")
        rate_str = cube.get("rate")
        if currency and rate_str:
            try:
                rates[currency.upper()] = float(rate_str)
            except ValueError:
                pass

    if len(rates) < 2:
        log.warning("ECB XML parsed but contained no rates")
        return None

    return rates


def get_rates(force_refresh: bool = False) -> dict[str, float]:
    """
    Return EUR FX rates, using today's cache when available.

    Falls back to stale cache if the ECB is unreachable.
    Falls back to EUR-only if no cache exists and the fetch fails.
    """
    today = date.today().isoformat()

    if not force_refresh and CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if cached.get("date") == today:
                log.debug("FX: using cached rates from %s", today)
                return cached["rates"]
        except Exception:
            pass

    log.info("FX: fetching EUR rates from ECB")
    rates = _fetch_from_ecb()

    if rates:
        try:
            CACHE_FILE.write_text(
                json.dumps({"date": today, "rates": rates}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("FX: could not write cache: %s", exc)
        return rates

    # Stale cache fallback
    if CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            log.warning("FX: using stale cached rates from %s", cached.get("date", "?"))
            return cached["rates"]
        except Exception:
            pass

    log.warning("FX: no rates available — treating all prices as EUR")
    return {"EUR": 1.0}


def to_eur(price: float, currency: str, rates: dict[str, float]) -> float:
    """
    Convert *price* in *currency* to EUR.

    ECB rates express "1 EUR = X units of currency", so:
        price_eur = price / rates[currency]
    """
    currency = currency.upper()
    if currency == "EUR":
        return price
    rate = rates.get(currency)
    if rate is None or rate == 0:
        log.warning("FX: no rate for %s — treating as EUR", currency)
        return price
    return price / rate
