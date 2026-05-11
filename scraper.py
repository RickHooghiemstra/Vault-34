#!/usr/bin/env python3
"""
Bunkerparts.nl Exhaust Scraper → Shopify CSV Exporter
======================================================
Scrapes exhaust (uitlaten) products from bunkerparts.nl, applies
non-EU export pricing logic, and exports a Shopify-ready CSV.

Pricing logic:
  Net Price   = Original Price / 1.21      (strip 21% Dutch VAT)
  Final Price = Net Price * 1.50           (add 50% export markup)

Usage:
  pip install requests beautifulsoup4 lxml playwright
  playwright install chromium              # only needed for JS-rendered pages
  python scraper.py                        # tries requests first, auto-falls back
  python scraper.py --playwright           # force headless browser for every page

Output: shopify_import.csv
"""

import csv
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://bunkerparts.nl"

CATEGORY_PATHS = [
    "/uitlaten/",
    "/uitlaatsystemen/",
    "/categorie/uitlaten/",
    "/product-category/uitlaten/",
    "/shop/uitlaten/",
]

OUTPUT_FILE = Path("shopify_import.csv")

VAT_RATE = 1.21
MARKUP = 1.50

REQUEST_DELAY = 1.5
MAX_RETRIES = 3
REQUEST_TIMEOUT = 20

# Pre-installed Chromium paths (checked in order)
CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
]

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
        return self.original_price / VAT_RATE

    @property
    def final_price(self) -> float:
        return self.net_price * MARKUP

    @property
    def handle(self) -> str:
        s = self.title.lower()
        s = unicodedata.normalize("NFKD", s)
        s = s.encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
        return s or "product"


# ---------------------------------------------------------------------------
# Requests-based fetcher
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
    try:
        r = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
        log.info("Homepage status: %s", r.status_code)
    except Exception as exc:
        log.warning("Homepage warm-up failed: %s", exc)
    return session


def fetch_requests(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
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
            log.warning("Request error on %s: %s", url, exc)
            time.sleep(attempt * 3)
    return None


# ---------------------------------------------------------------------------
# Playwright-based fetcher — persistent browser across all pages
# ---------------------------------------------------------------------------

class PlaywrightSession:
    """
    Keeps a single Chromium browser + context alive for the full scrape run.
    Use as a context manager:

        with PlaywrightSession() as pw:
            soup = pw.fetch("https://...")
    """

    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        exec_path = next((p for p in CHROMIUM_CANDIDATES if Path(p).exists()), None)
        if exec_path:
            log.info("Playwright using Chromium at %s", exec_path)
        else:
            log.info("Playwright using default Chromium")

        self._pw = sync_playwright().start()
        launch_kwargs = {"headless": True}
        if exec_path:
            launch_kwargs["executable_path"] = exec_path

        self._browser = self._pw.chromium.launch(**launch_kwargs)
        self._context = self._browser.new_context(
            user_agent=BROWSER_HEADERS["User-Agent"],
            locale="nl-NL",
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        self._page = self._context.new_page()
        return self

    def __exit__(self, *_):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    def fetch(self, url: str) -> Optional[BeautifulSoup]:
        from playwright.sync_api import TimeoutError as PWTimeout
        try:
            self._page.goto(url, wait_until="networkidle", timeout=30_000)
        except PWTimeout:
            log.warning("Playwright timeout on %s — using partial content", url)
        except Exception as exc:
            log.warning("Playwright error on %s: %s", url, exc)
            return None

        html = self._page.content()
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")
        body_text = soup.get_text(strip=True)

        # Detect sandbox / network allowlist block
        if "host not in allowlist" in body_text.lower():
            log.error(
                "\n\n"
                "  NETWORK BLOCKED: This environment does not allow outbound\n"
                "  connections to %s\n"
                "  ('Host not in allowlist' returned at the network level).\n\n"
                "  Run the scraper on a machine with open internet access:\n"
                "    pip install -r requirements.txt\n"
                "    playwright install chromium\n"
                "    python scraper.py --playwright\n",
                url,
            )
            return None

        # Detect bot-block / Cloudflare challenge
        if len(body_text) < 200 and any(
            kw in body_text.lower() for kw in ("captcha", "access denied", "challenge")
        ):
            log.warning("Bot block detected on %s", url)
            return None

        return soup


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def _has_products(soup: BeautifulSoup) -> bool:
    indicators = [
        soup.find("ul", class_=re.compile(r"products")),
        soup.find("div", class_=re.compile(r"products")),
        soup.find("li", class_=re.compile(r"product")),
        soup.find("div", class_=re.compile(r"product-item")),
        soup.find("article", class_=re.compile(r"product")),
    ]
    return any(indicators)


def find_category_url(fetcher: Callable) -> Optional[str]:
    for path in CATEGORY_PATHS:
        url = BASE_URL + path
        log.info("Trying category path: %s", url)
        soup = fetcher(url)
        if soup and _has_products(soup):
            log.info("Found products at %s", url)
            return url

    # Discover via navigation
    log.info("Trying to discover exhaust URL from homepage navigation")
    soup = fetcher(BASE_URL)
    if soup:
        keywords = ["uitlaat", "exhaust", "uitlaatsysteem"]
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = a.get_text(strip=True).lower()
            if any(kw in href or kw in text for kw in keywords):
                full = urljoin(BASE_URL, a["href"])
                s = fetcher(full)
                if s and _has_products(s):
                    log.info("Discovered exhaust URL: %s", full)
                    return full

    return None


def paginate(fetcher: Callable, category_url: str):
    """Yield BeautifulSoup pages for every listing page of a WooCommerce category."""
    page_num = 1
    while True:
        url = category_url if page_num == 1 else f"{category_url.rstrip('/')}/page/{page_num}/"
        log.info("Fetching listing page %d: %s", page_num, url)
        soup = fetcher(url)

        if soup is None:
            log.warning("Failed to fetch listing page %d, stopping", page_num)
            break

        if page_num > 1:
            current_el = soup.find("span", class_=re.compile(r"current"))
            if current_el:
                try:
                    if int(current_el.get_text(strip=True)) != page_num:
                        log.info("End of pagination at page %d", page_num)
                        break
                except ValueError:
                    pass

        if not _has_products(soup):
            log.info("No products on listing page %d, stopping", page_num)
            break

        yield soup
        page_num += 1


def extract_product_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls = set()
    for a in soup.select("ul.products li.product a.woocommerce-LoopProduct-link"):
        href = a.get("href", "")
        if href:
            urls.add(urljoin(base_url, href))

    if not urls:
        for el in soup.find_all(["li", "article", "div"], class_=re.compile(r"\bproduct\b")):
            a = el.find("a", href=True)
            if a:
                href = a["href"]
                if BASE_URL in href or href.startswith("/"):
                    urls.add(urljoin(base_url, href))

    return [
        u for u in urls
        if not re.search(r"/(page|categorie|category|tag|filter)/", u)
    ]


# ---------------------------------------------------------------------------
# Product detail parser
# ---------------------------------------------------------------------------

def parse_product(soup: BeautifulSoup, url: str) -> Optional["Product"]:
    p = Product(url=url)

    title_el = (
        soup.find("h1", class_=re.compile(r"product[_-]title|entry-title"))
        or soup.find("h1", itemprop="name")
        or soup.find("h1")
    )
    p.title = title_el.get_text(strip=True) if title_el else _url_to_title(url)

    sku_el = (
        soup.find("span", class_="sku")
        or soup.find(itemprop="sku")
        or soup.find("span", class_=re.compile(r"sku"))
    )
    if sku_el:
        p.sku = sku_el.get_text(strip=True)
    else:
        p.sku = urlparse(url).path.rstrip("/").split("/")[-1]

    price_el = soup.find("p", class_="price") or soup.find("span", class_="price")
    if price_el:
        ins = price_el.find("ins")
        amount_el = (ins or price_el).find("span", class_="woocommerce-Price-amount")
        if not amount_el:
            amount_el = (ins or price_el).find("bdi")
        if amount_el:
            p.original_price = _parse_price(amount_el.get_text(strip=True))

    desc_el = (
        soup.find("div", class_=re.compile(r"woocommerce-product-details__short-description"))
        or soup.find("div", id="tab-description")
        or soup.find("div", class_=re.compile(r"product-description|entry-content"))
    )
    p.description = str(desc_el) if desc_el else f"<p>{p.title}</p>"

    img_el = soup.find(
        ["div", "figure"], class_=re.compile(r"woocommerce-product-gallery")
    )
    if img_el:
        img = img_el.find("img")
        if img:
            p.image_src = img.get("data-large_image") or img.get("src", "")
    if not p.image_src:
        img = soup.find("img", class_=re.compile(r"wp-post-image|attachment-woocommerce"))
        if img:
            p.image_src = img.get("data-large_image") or img.get("src", "")

    brand_el = soup.find(itemprop="brand") or soup.find("span", class_=re.compile(r"brand"))
    if brand_el:
        p.brand = brand_el.get_text(strip=True)

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
    cleaned = re.sub(r"[€$£\s]", "", raw)
    if re.search(r"\d\.\d{3}", cleaned):
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
    "Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Value", "Variant SKU", "Variant Grams",
    "Variant Inventory Tracker", "Variant Inventory Qty", "Variant Inventory Policy",
    "Variant Fulfillment Service", "Variant Price", "Variant Compare At Price",
    "Variant Taxable", "Image Src", "Image Position", "Image Alt Text",
    "Source URL", "Original Price (incl. VAT)", "Net Price (excl. VAT)",
]


def product_to_shopify_row(p: Product) -> dict:
    tags = p.tags + ["source:bunkerparts.nl"]
    return {
        "Handle": p.handle,
        "Title": p.title,
        "Body (HTML)": p.description,
        "Vendor": p.brand or "Unknown",
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
    products: list[Product] = []
    seen_urls: set[str] = set()

    if use_playwright:
        log.info("Starting Playwright session (persistent browser)")
        pw_session = PlaywrightSession().__enter__()

        def fetcher(url: str) -> Optional[BeautifulSoup]:
            return pw_session.fetch(url)

        try:
            _run_scrape(fetcher, products, seen_urls)
        finally:
            pw_session.__exit__(None, None, None)
    else:
        session = make_session()

        def fetcher(url: str) -> Optional[BeautifulSoup]:
            return fetch_requests(session, url)

        _run_scrape(fetcher, products, seen_urls)

        if not products:
            log.warning("No products via requests — retrying with Playwright")
            return scrape(use_playwright=True)

    return products


def _run_scrape(
    fetcher: Callable,
    products: list[Product],
    seen_urls: set[str],
) -> None:
    cat_url = find_category_url(fetcher)
    if not cat_url:
        log.error("Could not find the exhaust category page.")
        return

    log.info("Scraping category: %s", cat_url)

    for listing_soup in paginate(fetcher, cat_url):
        product_urls = extract_product_urls(listing_soup, cat_url)
        log.info("Found %d product URLs on listing page", len(product_urls))

        for prod_url in product_urls:
            if prod_url in seen_urls:
                continue
            seen_urls.add(prod_url)

            log.info("Scraping product: %s", prod_url)
            detail_soup = fetcher(prod_url)
            if detail_soup is None:
                log.warning("Skipping (failed to load): %s", prod_url)
                continue

            product = parse_product(detail_soup, prod_url)
            if not product:
                log.warning("Could not parse product at %s", prod_url)
                continue
            if product.original_price == 0:
                log.warning("No price found for '%s' — skipping", product.title)
                continue

            products.append(product)
            log.info(
                "  %-55s  €%7.2f → export €%7.2f",
                product.title[:55],
                product.original_price,
                product.final_price,
            )


def main():
    log.info("=== Bunkerparts.nl Exhaust Scraper ===")
    log.info("VAT removal: /%.2f   Export markup: x%.2f", VAT_RATE, MARKUP)

    products = scrape(use_playwright=False)

    if not products:
        log.error("No products collected. Check logs above for details.")
        return

    export_csv(products, OUTPUT_FILE)

    print(f"\n{'='*72}")
    print(f"{'PRODUCT':<47} {'ORIG':>8} {'NET':>8} {'EXPORT':>9}")
    print(f"{'-'*72}")
    for p in products:
        print(
            f"{p.title[:46]:<47} "
            f"€{p.original_price:>7.2f} "
            f"€{p.net_price:>7.2f} "
            f"€{p.final_price:>8.2f}"
        )
    print(f"{'='*72}")
    print(f"Total products exported: {len(products)}")
    print(f"Output file: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    import sys
    if "--playwright" in sys.argv:
        log.info("Force-Playwright mode")
        products = scrape(use_playwright=True)
    else:
        products = scrape(use_playwright=False)

    if products:
        export_csv(products, OUTPUT_FILE)
        print(f"\nTotal: {len(products)} products → {OUTPUT_FILE}")
    else:
        log.error("No products collected.")
