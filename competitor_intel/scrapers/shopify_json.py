"""
Scrape competitor Shopify stores via /products.json endpoint.

No Playwright — pure HTTP + pagination. Reads competitor list from
config/competitors.yaml. Respects a 2s delay between requests and
skips a competitor if it returns 403/429/451 or exhausts retries.
"""

import logging
import time
from pathlib import Path
from typing import Optional

import httpx
import yaml

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "competitors.yaml"

_REQUEST_DELAY = 2.0   # seconds between paginated requests
_MAX_RETRIES   = 3
_TIMEOUT       = 20
_PAGE_SIZE     = 250   # Shopify /products.json max per page

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Vault34-PriceMonitor/1.0)",
    "Accept":     "application/json",
}

# HTTP status codes that mean "we're blocked" — skip this competitor immediately
_BLOCK_STATUSES = {403, 429, 451}


def load_competitors() -> list[dict]:
    """Return list of competitor dicts from config/competitors.yaml."""
    if not _CONFIG_PATH.exists():
        log.warning("config/competitors.yaml not found — no competitor data")
        return []
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("competitors", [])


def _fetch_page(
    client: httpx.Client,
    domain: str,
    page: int,
) -> Optional[list[dict]]:
    """
    Fetch one page of /products.json. Returns product list or None on
    unrecoverable error (blocked) so the caller can skip the competitor.
    """
    url = f"https://{domain}/products.json?limit={_PAGE_SIZE}&page={page}"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.get(url, timeout=_TIMEOUT)
            if resp.status_code == 200:
                ctype = resp.headers.get("content-type", "")
                if "json" not in ctype:
                    log.debug("Competitor %s returned non-JSON content-type: %s", domain, ctype)
                    return []
                try:
                    return resp.json().get("products", [])
                except Exception:
                    log.debug("Competitor %s returned non-JSON body on page %d", domain, page)
                    return []
            if resp.status_code in _BLOCK_STATUSES:
                log.warning(
                    "Competitor %s blocked (HTTP %d) — skipping",
                    domain, resp.status_code,
                )
                return None
            log.warning(
                "Competitor %s HTTP %d on page %d (attempt %d/%d)",
                domain, resp.status_code, page, attempt, _MAX_RETRIES,
            )
        except httpx.RequestError as exc:
            log.warning(
                "Competitor %s request error on page %d (attempt %d/%d): %s",
                domain, page, attempt, _MAX_RETRIES, exc,
            )
        if attempt < _MAX_RETRIES:
            time.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s

    log.warning("Competitor %s failed after %d attempts on page %d", domain, _MAX_RETRIES, page)
    return []  # empty list = no products on this page, but not a hard block


def _normalize_price(price_str: str, includes_vat: bool, currency: str) -> float:
    """
    Parse a Shopify price string and return an ex-VAT EUR float.
    Currency conversion (non-EUR) is handled later by pricing/fx.py;
    here we only strip VAT if the competitor includes it.
    The raw price and currency are kept on the returned dict for the engine.
    """
    try:
        price = float(price_str)
    except (ValueError, TypeError):
        return 0.0
    if includes_vat:
        price = price / 1.21   # assume standard EU VAT; refined in engine if needed
    return price


def scrape_competitor(competitor: dict) -> list[dict]:
    """
    Scrape all product variants from one competitor's Shopify store.

    Each returned dict:
    {
        "domain":       str,
        "name":         str,
        "market":       str,
        "currency":     str,
        "includes_vat": bool,
        "sku":          str,
        "title":        str,
        "vendor":       str,
        "price_raw":    float,   # original price (may include VAT)
        "price_eur":    float,   # ex-VAT, pre-FX (EUR assumed; engine applies FX)
        "tags":         list[str],
    }
    """
    domain       = competitor["domain"]
    name         = competitor.get("name", domain)
    market       = competitor.get("market", "EU")
    includes_vat = competitor.get("includes_vat", False)
    currency     = competitor.get("currency", "EUR").upper()

    results: list[dict] = []
    page = 1

    with httpx.Client(headers=_HEADERS, follow_redirects=True) as client:
        while True:
            if page > 1:
                time.sleep(_REQUEST_DELAY)

            products = _fetch_page(client, domain, page)
            if products is None:
                # Hard block — skip entire competitor
                return []
            if not products:
                break

            for prod in products:
                title  = prod.get("title", "")
                vendor = prod.get("vendor", "")
                tags   = prod.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]

                for variant in prod.get("variants", []):
                    price_str = variant.get("price", "0") or "0"
                    try:
                        price_raw = float(price_str)
                    except (ValueError, TypeError):
                        price_raw = 0.0

                    if price_raw <= 0:
                        continue

                    price_eur = _normalize_price(price_str, includes_vat, currency)

                    results.append({
                        "domain":       domain,
                        "name":         name,
                        "market":       market,
                        "currency":     currency,
                        "includes_vat": includes_vat,
                        "sku":          (variant.get("sku") or "").strip(),
                        "title":        title,
                        "vendor":       vendor,
                        "price_raw":    price_raw,
                        "price_eur":    price_eur,
                        "tags":         tags,
                    })

            log.info("Competitor %s: page %d → %d variants so far", name, page, len(results))

            if len(products) < _PAGE_SIZE:
                break   # last page
            page += 1

    log.info("Competitor %s: total %d variants scraped", name, len(results))
    return results


def scrape_all_competitors() -> dict[str, list[dict]]:
    """
    Scrape every competitor in config/competitors.yaml.
    Returns {domain: [product_dicts]}.
    """
    competitors = load_competitors()
    if not competitors:
        return {}

    results: dict[str, list[dict]] = {}
    for i, competitor in enumerate(competitors):
        domain = competitor["domain"]
        name   = competitor.get("name", domain)
        log.info("Scraping competitor %d/%d: %s", i + 1, len(competitors), name)
        products = scrape_competitor(competitor)
        if products:
            results[domain] = products
        if i < len(competitors) - 1:
            time.sleep(_REQUEST_DELAY)

    log.info(
        "Competitor scrape complete: %d/%d sites yielded data",
        len(results), len(competitors),
    )
    return results
