"""
Auto-detecting competitor scraper dispatcher.

For each competitor in config/competitors.yaml:
  1. If `type: shopify`     → use Shopify /products.json scraper directly
  2. If `type: woocommerce` → use WooCommerce Store API scraper directly
  3. If `type` is absent or `auto` → probe Shopify first, then WooCommerce

Exposes scrape_all_competitors() with the same signature as shopify_json so
main.py needs only a one-line import change.
"""

import logging
import time
from pathlib import Path

import yaml

from competitor_intel.scrapers import shopify_json
from competitor_intel.scrapers import woocommerce_json

log = logging.getLogger(__name__)

_CONFIG_PATH           = Path(__file__).parent.parent.parent / "config" / "competitors.yaml"
_INTER_COMPETITOR_DELAY = 2.0


def _load_competitors() -> list[dict]:
    if not _CONFIG_PATH.exists():
        log.warning("config/competitors.yaml not found — no competitor data")
        return []
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("competitors", [])


def _scrape_one(competitor: dict) -> list[dict]:
    """Dispatch to the right scraper; auto-detect when type is unset."""
    domain     = competitor["domain"]
    name       = competitor.get("name", domain)
    store_type = competitor.get("type", "auto").lower()

    if store_type == "shopify":
        log.info("  [shopify]     %s", name)
        return shopify_json.scrape_competitor(competitor)

    if store_type == "woocommerce":
        log.info("  [woocommerce] %s", name)
        return woocommerce_json.scrape_competitor(competitor)

    # --- auto-detect ---
    log.info("  [auto]        %s — probing Shopify …", name)
    products = shopify_json.scrape_competitor(competitor)
    if products:
        log.info("  [shopify]     %s identified (%d variants)", name, len(products))
        return products

    log.info("  [auto]        %s — probing WooCommerce …", name)
    if woocommerce_json.is_woocommerce(domain):
        products = woocommerce_json.scrape_competitor(competitor)
        if products:
            log.info("  [woocommerce] %s identified (%d products)", name, len(products))
            return products

    log.warning("  [skip]        %s — no supported API found", name)
    return []


def scrape_all_competitors() -> dict[str, list[dict]]:
    """
    Scrape every competitor in config/competitors.yaml.
    Returns {domain: [product_dicts]}.
    """
    competitors = _load_competitors()
    if not competitors:
        return {}

    results: dict[str, list[dict]] = {}
    for i, competitor in enumerate(competitors):
        domain = competitor["domain"]
        name   = competitor.get("name", domain)
        log.info("Scraping competitor %d/%d: %s", i + 1, len(competitors), name)
        products = _scrape_one(competitor)
        if products:
            results[domain] = products
        if i < len(competitors) - 1:
            time.sleep(_INTER_COMPETITOR_DELAY)

    log.info(
        "Competitor scrape complete: %d/%d sites yielded data",
        len(results), len(competitors),
    )
    return results
