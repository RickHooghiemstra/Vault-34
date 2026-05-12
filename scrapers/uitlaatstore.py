"""
Scraper for uitlaatstore.nl.

IMPORTANT — WAF restriction:
  uitlaatstore.nl blocks all datacenter/cloud IPs. Run this script from a
  home or office internet connection, or set PROXY_URL in your .env file
  to a residential proxy (e.g. Bright Data, Oxylabs).

Usage:
  python main.py --brands akrapovic,arrow         # scrape specific brands
  python main.py --brands akrapovic --discover    # dump selector candidates first
  python main.py --all-brands                     # scrape all TOP_BRANDS
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse, quote

import requests
from bs4 import BeautifulSoup

from config.settings import (
    BASE_URL, BRAND_LISTING_PATH, PAGE_SIZE,
    REQUEST_DELAY, MAX_RETRIES, REQUEST_TIMEOUT,
    PROXY_URL, LOGS_DIR, SELECTORS,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    if PROXY_URL:
        session.proxies = {"http": PROXY_URL, "https": PROXY_URL}
        log.info("Using proxy: %s", PROXY_URL)
    return session


def fetch(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    """Fetch a URL with retries and exponential back-off. Returns None on failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                body = soup.get_text(strip=True).lower()
                if "host_not_allowed" in body or "host not in allowlist" in body:
                    _waf_abort()
                return soup

            if resp.status_code in (403, 429):
                wait = attempt * 10
                log.warning(
                    "HTTP %s on %s (attempt %d/%d) — waiting %ds",
                    resp.status_code, url, attempt, MAX_RETRIES, wait,
                )
                if resp.status_code == 403:
                    body = resp.text.lower()
                    if "host_not_allowed" in body or "host not in allowlist" in body:
                        _waf_abort()
                time.sleep(wait)
            else:
                log.warning("HTTP %s on %s — skipping", resp.status_code, url)
                return None

        except requests.RequestException as exc:
            wait = attempt * 5
            log.warning("Request error on %s: %s — retrying in %ds", url, exc, wait)
            time.sleep(wait)

    log.error("Giving up on %s after %d attempts", url, MAX_RETRIES)
    return None


def _waf_abort() -> None:
    raise SystemExit(
        "\n\n"
        "  ╔══════════════════════════════════════════════════════════════╗\n"
        "  ║  NETWORK BLOCKED — uitlaatstore.nl WAF rejected this IP.    ║\n"
        "  ║                                                              ║\n"
        "  ║  Solutions:                                                  ║\n"
        "  ║  1. Run from a home or office internet connection.           ║\n"
        "  ║  2. Set PROXY_URL in .env to a residential proxy.           ║\n"
        "  ╚══════════════════════════════════════════════════════════════╝\n"
    )


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------

def brand_listing_url(brand_slug: str, offset: int = 0) -> str:
    path = BRAND_LISTING_PATH.format(brand=quote(brand_slug, safe="-"))
    url = urljoin(BASE_URL, path)
    return url if offset == 0 else f"{url}?offset={offset}"


def discover_product_urls(
    session: requests.Session,
    brand_slug: str,
    *,
    checkpoint_file: Optional[Path] = None,
) -> list[str]:
    """
    Paginate the brand listing and collect all product page URLs.
    Results are saved to a checkpoint file and resumed if interrupted.
    """
    urls: list[str] = []

    if checkpoint_file and checkpoint_file.exists():
        urls = json.loads(checkpoint_file.read_text())
        log.info(
            "Resumed %d URLs from checkpoint: %s", len(urls), checkpoint_file
        )
        return urls

    offset = 0
    seen: set[str] = set()

    while True:
        listing_url = brand_listing_url(brand_slug, offset)
        log.info("Listing page offset=%d — %s", offset, listing_url)
        soup = fetch(session, listing_url)

        if soup is None:
            log.warning("Failed to fetch listing page at offset %d — stopping", offset)
            break

        page_urls = _extract_product_urls(soup)

        if not page_urls:
            log.info("No product URLs at offset %d — end of brand listing", offset)
            break

        new = [u for u in page_urls if u not in seen]
        if not new:
            log.info("All URLs on this page already seen — stopping")
            break

        seen.update(new)
        urls.extend(new)
        log.info("  +%d URLs (total %d)", len(new), len(urls))

        # Check whether more pages exist
        if len(page_urls) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    if checkpoint_file:
        checkpoint_file.write_text(json.dumps(urls, indent=2))
        log.info("Saved %d URLs → %s", len(urls), checkpoint_file)

    return urls


def _extract_product_urls(soup: BeautifulSoup) -> list[str]:
    """Extract product page URLs from a listing page."""
    urls: set[str] = set()

    # Standard approach: anchors inside product card elements
    for a in soup.select("a[href]"):
        href = a["href"]
        full = urljoin(BASE_URL, href)
        parsed = urlparse(full)
        # Product URLs on uitlaatstore.nl are root-level slugs (no category nesting)
        if (
            parsed.netloc == urlparse(BASE_URL).netloc
            and _is_product_url(parsed.path)
        ):
            urls.add(full)

    return list(urls)


# Patterns that identify listing/category pages — exclude these from product URLs
_NON_PRODUCT_PATTERNS = re.compile(
    r"/(alle-merken|alle-producten|motormerk|uitlaten-tuning|faq|over-ons|contact"
    r"|cart|checkout|account|login|register|search|categorie|category|tag|page|filter)(/|$)",
    re.I,
)

_PRODUCT_SLUG = re.compile(r"^/[a-z0-9][a-z0-9\-]{3,}$", re.I)


def _is_product_url(path: str) -> bool:
    if _NON_PRODUCT_PATTERNS.search(path):
        return False
    return bool(_PRODUCT_SLUG.match(path))


# ---------------------------------------------------------------------------
# Selector discovery helper
# ---------------------------------------------------------------------------

def discover_selectors(soup: BeautifulSoup) -> None:
    """
    Print candidate HTML elements for each data field.
    Run with  python main.py --discover --url <product_url>  to tune SELECTORS.
    """
    fields = {
        "title":       ["h1", "[itemprop='name']"],
        "price":       [
            "[data-price-type='finalPrice'] .price",
            ".price-final_price .price",
            ".special-price .price",
            ".price ins",
            ".price",
            "[class*='price']",
        ],
        "sku":         ["[itemprop='sku']", ".sku", "[class*='sku']"],
        "description": ["[itemprop='description']", "[class*='description']", ".product-description"],
        "brand":       ["[itemprop='brand']", "[class*='brand']"],
        "images":      ["img[src*='/media/catalog/product/']", "img[src*='product']", ".gallery img"],
        "breadcrumb":  ["nav a", ".breadcrumb a", "[class*='breadcrumb'] a"],
    }

    print("\n=== SELECTOR DISCOVERY ===")
    for field, candidates in fields.items():
        print(f"\n--- {field.upper()} ---")
        for sel in candidates:
            els = soup.select(sel)
            if els:
                for el in els[:2]:
                    preview = el.get_text(strip=True)[:100] or el.get("src", "")[:100]
                    print(f"  [{sel}] → {preview!r}")
    print("\n=== END DISCOVERY ===\n")
