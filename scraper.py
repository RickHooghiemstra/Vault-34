#!/usr/bin/env python3
"""
Bunkerparts.nl Exhaust Scraper → Shopify CSV Exporter
======================================================
Scrapes exhaust (uitlaten) products from bunkerparts.nl, applies
non-EU export pricing logic, and exports a Shopify-ready CSV.

Pricing logic:
  Net Price   = Original Price / 1.21      (strip 21% Dutch VAT)
  Final Price = Net Price * 1.30           (add 30% export markup)

Usage:
  pip install requests beautifulsoup4 lxml playwright
  playwright install chromium              # only needed for JS-rendered pages
  python scraper.py

Output: shopify_import.csv
"""

import csv
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://bunkerparts.nl"

# Known exhaust category paths — the scraper tries each in order and uses
# whichever one yields products.
CATEGORY_PATHS = [
    "/uitlaten/",
    "/uitlaatsystemen/",
    "/categorie/uitlaten/",
    "/product-category/uitlaten/",
    "/shop/uitlaten/",
]

VENDOR = "Akrapovič"
OUTPUT_FILE = Path("shopify_import.csv")

VAT_RATE = 1.21        # Dutch VAT
MARKUP = 1.30          # 30% export markup

REQUEST_DELAY = 1.5    # seconds between requests (be polite)
MAX_RETRIES = 3
REQUEST_TIMEOUT = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Product:
    title: str = ""
    sku: str = ""
    original_price: float = 0.0
    url: str = ""
    description: str = ""
    image_src: str = ""
    brand: str = ""
    category: str = ""
    tags: list = field(default_factory=list)

    @property
    def net_price(self) -> float:
        """Price excluding 21% Dutch VAT."""
        return self.original_price / VAT_RATE

    @property
    def final_price(self) -> float:
        """Export price: net + 30% markup."""
        return self.net_price * MARKUP

    @property
    def handle(self) -> str:
        """Shopify-style URL handle derived from title."""
        s = self.title.lower()
        s = unicodedata.normalize("NFKD", s)
        s = s.encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
        return s or "product"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
    "Referer": BASE_URL + "/",
}


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    # Warm up with a homepage visit so cookies are set
    try:
        r = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
        log.info("Homepage status: %s", r.status_code)
    except Exception as exc:
        log.warning("Homepage warm-up failed: %s", exc)
    return session


def get_page(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    """Fetch *url* with retries and return a BeautifulSoup tree, or None."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "lxml")
            if resp.status_code in (403, 429):
                wait = attempt * 5
                log.warning(
                    "HTTP %s on %s — waiting %ds (attempt %d/%d)",
                    resp.status_code, url, wait, attempt, MAX_RETRIES,
                )
                time.sleep(wait)
            else:
                log.warning("HTTP %s on %s", resp.status_code, url)
                return None
        except requests.RequestException as exc:
            log.warning("Request error on %s: %s (attempt %d)", url, exc, attempt)
            time.sleep(attempt * 3)
    return None


# ---------------------------------------------------------------------------
# Playwright fallback (only imported if needed)
# ---------------------------------------------------------------------------

def get_page_playwright(url: str) -> Optional[BeautifulSoup]:
    """
    Render *url* with a headless Chromium browser via Playwright.
    Used when the site blocks plain requests (Cloudflare, JS-rendering, etc.).
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.error(
            "playwright not installed. Run: pip install playwright && "
            "playwright install chromium"
        )
        return None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=BROWSER_HEADERS["User-Agent"],
            locale="nl-NL",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
        except PWTimeout:
            log.warning("Playwright timeout on %s", url)
            html = page.content()
        finally:
            browser.close()

    return BeautifulSoup(html, "lxml") if html else None


# ---------------------------------------------------------------------------
# Scraping helpers — WooCommerce / generic shop patterns
# ---------------------------------------------------------------------------

def find_category_url(session: requests.Session) -> Optional[str]:
    """
    Try known exhaust category paths and return the first one that works.
    Also attempts to discover the URL via the homepage navigation.
    """
    # 1. Try hard-coded paths
    for path in CATEGORY_PATHS:
        url = BASE_URL + path
        log.info("Trying category path: %s", url)
        soup = get_page(session, url)
        if soup and _has_products(soup):
            log.info("Found products at %s", url)
            return url

    # 2. Try to discover via navigation links
    log.info("Trying to discover exhaust URL from homepage navigation")
    soup = get_page(session, BASE_URL)
    if soup:
        keywords = ["uitlaat", "exhaust", "uitlaatsysteem"]
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = a.get_text(strip=True).lower()
            if any(kw in href or kw in text for kw in keywords):
                full = urljoin(BASE_URL, a["href"])
                log.info("Discovered potential exhaust URL: %s", full)
                s = get_page(session, full)
                if s and _has_products(s):
                    return full

    log.warning("Could not find exhaust category automatically.")
    return None


def _has_products(soup: BeautifulSoup) -> bool:
    """Return True if the page appears to contain product listings."""
    indicators = [
        soup.find("ul", class_=re.compile(r"products")),
        soup.find("div", class_=re.compile(r"products")),
        soup.find("li", class_=re.compile(r"product")),
        soup.find("div", class_=re.compile(r"product-item")),
        soup.find("article", class_=re.compile(r"product")),
    ]
    return any(indicators)


def paginate(session: requests.Session, category_url: str):
    """
    Yield BeautifulSoup objects for every page of a WooCommerce category.
    Supports both /page/N/ and ?page=N patterns.
    """
    page_num = 1
    while True:
        # Build paginated URL
        if page_num == 1:
            url = category_url
        else:
            # Try WooCommerce-style /page/N/
            base = category_url.rstrip("/")
            url = f"{base}/page/{page_num}/"

        log.info("Fetching listing page %d: %s", page_num, url)
        soup = get_page(session, url)

        if soup is None:
            log.warning("Failed to fetch page %d, stopping pagination", page_num)
            break

        # Detect 404/empty page (WooCommerce redirects to page 1 on overflow)
        if page_num > 1 and _is_redirect_to_page1(soup, page_num):
            log.info("Reached end of pagination at page %d", page_num)
            break

        if not _has_products(soup):
            log.info("No products found on page %d, stopping", page_num)
            break

        yield soup
        page_num += 1


def _is_redirect_to_page1(soup: BeautifulSoup, expected_page: int) -> bool:
    """Heuristic: if the current page number widget doesn't show expected_page."""
    current = soup.find("span", class_=re.compile(r"current"))
    if current:
        try:
            return int(current.get_text(strip=True)) != expected_page
        except ValueError:
            pass
    return False


def extract_product_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract individual product URLs from a category/listing page."""
    urls = set()

    # WooCommerce standard: <ul class="products"> <li class="product"> <a>
    for a in soup.select("ul.products li.product a.woocommerce-LoopProduct-link"):
        href = a.get("href", "")
        if href:
            urls.add(urljoin(base_url, href))

    # Fallback: any <a> inside an element classed "product"
    if not urls:
        for article in soup.find_all(["li", "article", "div"], class_=re.compile(r"\bproduct\b")):
            a = article.find("a", href=True)
            if a:
                href = a["href"]
                if BASE_URL in href or href.startswith("/"):
                    urls.add(urljoin(base_url, href))

    # Deduplicate and remove category/pagination links
    product_urls = [
        u for u in urls
        if not re.search(r"/(page|categorie|category|tag|filter)/", u)
    ]
    return product_urls


# ---------------------------------------------------------------------------
# Product detail parser
# ---------------------------------------------------------------------------

def parse_product(soup: BeautifulSoup, url: str) -> Optional[Product]:
    """Parse a WooCommerce product detail page into a Product dataclass."""
    p = Product(url=url)

    # --- Title ---
    title_el = (
        soup.find("h1", class_=re.compile(r"product[_-]title|entry-title"))
        or soup.find("h1", itemprop="name")
        or soup.find("h1")
    )
    p.title = title_el.get_text(strip=True) if title_el else _url_to_title(url)

    # --- SKU ---
    sku_el = (
        soup.find("span", class_="sku")
        or soup.find(itemprop="sku")
        or soup.find("span", class_=re.compile(r"sku"))
    )
    if sku_el:
        p.sku = sku_el.get_text(strip=True)
    else:
        # Try to extract from URL slug
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        p.sku = slug

    # --- Price ---
    # WooCommerce puts the sale price in .price > ins > .amount,
    # or just .price > .amount for regular prices.
    price_el = soup.find("p", class_="price") or soup.find("span", class_="price")
    if price_el:
        # Prefer the sale (ins) price
        ins = price_el.find("ins")
        amount_el = (ins or price_el).find("span", class_="woocommerce-Price-amount")
        if not amount_el:
            amount_el = (ins or price_el).find("bdi")
        if amount_el:
            p.original_price = _parse_price(amount_el.get_text(strip=True))

    # --- Description ---
    desc_el = (
        soup.find("div", class_=re.compile(r"woocommerce-product-details__short-description"))
        or soup.find("div", id="tab-description")
        or soup.find("div", class_=re.compile(r"product-description|entry-content"))
    )
    if desc_el:
        # Keep HTML for Shopify Body (HTML) field
        p.description = str(desc_el)
    else:
        p.description = f"<p>{p.title}</p>"

    # --- Image ---
    img_el = (
        soup.find("div", class_=re.compile(r"woocommerce-product-gallery"))
        or soup.find("figure", class_=re.compile(r"woocommerce-product-gallery"))
    )
    if img_el:
        img = img_el.find("img")
        if img:
            # Prefer data-large_image (full-size), fall back to src
            p.image_src = img.get("data-large_image") or img.get("src", "")
    if not p.image_src:
        img = soup.find("img", class_=re.compile(r"wp-post-image|attachment-woocommerce"))
        if img:
            p.image_src = img.get("data-large_image") or img.get("src", "")

    # --- Brand / Vendor ---
    brand_el = soup.find(itemprop="brand") or soup.find("span", class_=re.compile(r"brand"))
    if brand_el:
        p.brand = brand_el.get_text(strip=True)

    # --- Category tags ---
    breadcrumb_tags = []
    breadcrumb = soup.find("nav", class_=re.compile(r"breadcrumb|woocommerce-breadcrumb"))
    if breadcrumb:
        for crumb in breadcrumb.find_all("a"):
            text = crumb.get_text(strip=True)
            if text and text.lower() not in ("home", "winkel", "shop"):
                breadcrumb_tags.append(text)
    p.tags = breadcrumb_tags or ["uitlaten"]
    p.category = breadcrumb_tags[-1] if breadcrumb_tags else "uitlaten"

    return p if p.title else None


def _url_to_title(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").title()


def _parse_price(raw: str) -> float:
    """Convert price strings like '€ 1.299,95' or '1299.95' to float."""
    cleaned = re.sub(r"[€$£\s]", "", raw)
    # Dutch format: dot = thousands separator, comma = decimal
    if re.search(r"\d\.\d{3}", cleaned):          # e.g. 1.299,95
        cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(re.sub(r"[^\d.]", "", cleaned))
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Shopify CSV export
# ---------------------------------------------------------------------------

SHOPIFY_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Type",
    "Tags",
    "Published",
    "Option1 Name",
    "Option1 Value",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Taxable",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "Source URL",
    "Original Price (incl. VAT)",
    "Net Price (excl. VAT)",
]


def product_to_shopify_row(p: Product) -> dict:
    tags = p.tags + [f"source:bunkerparts.nl"]
    return {
        "Handle": p.handle,
        "Title": p.title,
        "Body (HTML)": p.description,
        "Vendor": VENDOR,
        "Type": p.category or "Uitlaten",
        "Tags": ", ".join(tags),
        "Published": "TRUE",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Variant SKU": p.sku,
        "Variant Grams": "5000",
        "Variant Inventory Tracker": "shopify",
        "Variant Inventory Qty": "1",
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": f"{p.final_price:.2f}",
        "Variant Compare At Price": "",
        "Variant Taxable": "FALSE",
        "Image Src": p.image_src,
        "Image Position": "1",
        "Image Alt Text": p.title,
        # Extra informational columns (ignored by Shopify importer)
        "Source URL": p.url,
        "Original Price (incl. VAT)": f"{p.original_price:.2f}",
        "Net Price (excl. VAT)": f"{p.net_price:.2f}",
    }


def export_csv(products: list[Product], output: Path) -> None:
    rows = [product_to_shopify_row(p) for p in products]
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SHOPIFY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("Exported %d products → %s", len(products), output)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def scrape(use_playwright: bool = False) -> list[Product]:
    """
    Full scrape pipeline.
    Set use_playwright=True if the site blocks requests-based scraping.
    """
    session = make_session()
    products: list[Product] = []
    seen_urls: set[str] = set()

    if use_playwright:
        log.info("Using Playwright for category page discovery")
        soup = get_page_playwright(BASE_URL + CATEGORY_PATHS[0])
        if not soup:
            log.error("Playwright failed to load the page")
            return products
        cat_url = BASE_URL + CATEGORY_PATHS[0]
    else:
        cat_url = find_category_url(session)
        if not cat_url:
            log.warning(
                "Falling back to Playwright (requests blocked or no category found)"
            )
            # Try Playwright as automatic fallback
            for path in CATEGORY_PATHS:
                url = BASE_URL + path
                soup = get_page_playwright(url)
                if soup and _has_products(soup):
                    cat_url = url
                    break
            if not cat_url:
                log.error("Could not find exhaust category via any method.")
                return products

    log.info("Scraping category: %s", cat_url)

    for listing_soup in paginate(session, cat_url):
        product_urls = extract_product_urls(listing_soup, cat_url)
        log.info("Found %d product URLs on this page", len(product_urls))

        for prod_url in product_urls:
            if prod_url in seen_urls:
                continue
            seen_urls.add(prod_url)

            log.info("Scraping product: %s", prod_url)
            if use_playwright:
                detail_soup = get_page_playwright(prod_url)
            else:
                detail_soup = get_page(session, prod_url)
                if detail_soup is None and not use_playwright:
                    log.info("Retrying with Playwright: %s", prod_url)
                    detail_soup = get_page_playwright(prod_url)

            if detail_soup is None:
                log.warning("Skipping (failed to load): %s", prod_url)
                continue

            product = parse_product(detail_soup, prod_url)
            if product:
                if product.original_price == 0:
                    log.warning(
                        "No price found for '%s' (%s) — skipping", product.title, prod_url
                    )
                    continue
                products.append(product)
                log.info(
                    "  %-60s  €%7.2f → export €%7.2f",
                    product.title[:60],
                    product.original_price,
                    product.final_price,
                )

    return products


def main():
    log.info("=== Bunkerparts.nl Exhaust Scraper ===")
    log.info("VAT removal: /%.2f   Export markup: x%.2f", VAT_RATE, MARKUP)

    products = scrape(use_playwright=False)

    if not products:
        log.error(
            "No products collected.\n"
            "The site may require Playwright. Re-run with:\n"
            "  python scraper.py --playwright"
        )
        return

    export_csv(products, OUTPUT_FILE)

    # Print pricing summary
    print(f"\n{'='*70}")
    print(f"{'PRODUCT':<45} {'ORIG':>8} {'NET':>8} {'EXPORT':>9}")
    print(f"{'-'*70}")
    for p in products:
        print(
            f"{p.title[:44]:<45} "
            f"€{p.original_price:>7.2f} "
            f"€{p.net_price:>7.2f} "
            f"€{p.final_price:>8.2f}"
        )
    print(f"{'='*70}")
    print(f"Total products exported: {len(products)}")
    print(f"Output file: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    import sys
    if "--playwright" in sys.argv:
        products = scrape(use_playwright=True)
        if products:
            export_csv(products, OUTPUT_FILE)
    else:
        main()
