"""
Scrape competitor WooCommerce stores via the Block Store API.

Uses /wp-json/wc/store/v1/products — public, no authentication required.
Prices are returned in currency minor units (e.g. 1299 = €12.99).
"""

import logging
import re
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_REQUEST_DELAY = 2.0
_MAX_RETRIES   = 3
_TIMEOUT       = 20
_PAGE_SIZE     = 100  # WooCommerce store API typical max

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Vault34-PriceMonitor/1.0)",
    "Accept":     "application/json",
}

_BLOCK_STATUSES = {403, 429, 451}


def is_woocommerce(domain: str) -> bool:
    """Return True if the domain responds to the WooCommerce Block Store API."""
    url = f"https://{domain}/wp-json/wc/store/v1/products?per_page=1"
    try:
        with httpx.Client(headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url, timeout=_TIMEOUT)
            return resp.status_code == 200 and isinstance(resp.json(), list)
    except Exception:
        return False


def _parse_price(prices: dict) -> float:
    """Convert WooCommerce prices dict to a plain float."""
    raw = prices.get("price") or prices.get("regular_price") or "0"
    minor = int(prices.get("currency_minor_unit", 2))
    try:
        return int(raw) / (10 ** minor)
    except (ValueError, TypeError):
        # Fallback: strip non-numeric chars and parse
        clean = re.sub(r"[^\d]", "", str(raw))
        try:
            return int(clean) / (10 ** minor)
        except (ValueError, TypeError):
            return 0.0


def _fetch_page(
    client: httpx.Client,
    domain: str,
    page: int,
) -> Optional[list[dict]]:
    """Fetch one page from WooCommerce Store API. Returns None on hard block."""
    url = (
        f"https://{domain}/wp-json/wc/store/v1/products"
        f"?per_page={_PAGE_SIZE}&page={page}"
    )
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.get(url, timeout=_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else []
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
            time.sleep(2 ** (attempt - 1))

    log.warning("Competitor %s failed after %d attempts on page %d", domain, _MAX_RETRIES, page)
    return []


def scrape_competitor(competitor: dict) -> list[dict]:
    """
    Scrape all products from one WooCommerce store via the Block Store API.

    Returns the same dict structure as shopify_json.scrape_competitor so the
    rest of the pipeline (matcher, pricing engine) is unchanged.
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
                return []
            if not products:
                break

            for prod in products:
                title    = prod.get("name", "")
                sku      = (prod.get("sku") or "").strip()
                tags     = [t.get("name", "") for t in prod.get("tags", [])]
                # Brand/vendor: WooCommerce has no native vendor field;
                # use first category name as a proxy when available.
                cats     = prod.get("categories", [])
                vendor   = cats[0].get("name", "") if cats else ""

                prices   = prod.get("prices", {})
                price_f  = _parse_price(prices)
                if price_f <= 0:
                    continue

                price_eur = price_f / 1.21 if includes_vat else price_f

                results.append({
                    "domain":       domain,
                    "name":         name,
                    "market":       market,
                    "currency":     currency,
                    "includes_vat": includes_vat,
                    "sku":          sku,
                    "title":        title,
                    "vendor":       vendor,
                    "price_raw":    price_f,
                    "price_eur":    price_eur,
                    "tags":         tags,
                })

            log.info("Competitor %s: page %d → %d products so far", name, page, len(results))

            if len(products) < _PAGE_SIZE:
                break
            page += 1

    log.info("Competitor %s: total %d products scraped (WooCommerce)", name, len(results))
    return results
