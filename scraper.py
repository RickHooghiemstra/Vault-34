#!/usr/bin/env python3
"""
Bunkerparts.nl Exhaust Scraper → Shopify CSV Exporter
======================================================
Scrapes ALL exhaust products from bunkerparts.nl, applies non-EU export
pricing, and exports a Shopify-ready CSV with structured make/model/year
tags that power Shopify's native storefront collection filters.

Pricing logic:
  Net Price   = Original Price / 1.21      (strip 21% Dutch VAT)
  Final Price = Net Price * 1.50           (add 50% export markup)

Shopify filtering:
  Tags are written as  make:Honda  model:CB650R  year:2019-2023
  Enable them in Shopify Admin → Navigation → Collections → Filters.

Usage:
  pip install -r requirements.txt
  playwright install chromium              # only needed for JS-rendered pages
  python scraper.py                        # auto-detects; falls back to Playwright
  python scraper.py --playwright           # force headless browser

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
    "/accessoires/uitlaten/",
]

OUTPUT_FILE = Path("shopify_import.csv")

VAT_RATE = 1.21
MARKUP   = 1.50

REQUEST_DELAY   = 1.5
MAX_RETRIES     = 3
REQUEST_TIMEOUT = 20

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
# Motorcycle make / model / year knowledge base
# ---------------------------------------------------------------------------

# All recognised motorcycle manufacturers — ordered longest-first so "Royal Enfield"
# is matched before "Royal", "Harley-Davidson" before "Harley", etc.
MOTO_MAKES: list[str] = [
    "Harley-Davidson", "Royal Enfield", "MV Agusta", "Husqvarna",
    "Gas Gas", "GasGas",
    "Honda", "Yamaha", "Kawasaki", "Suzuki", "BMW", "Ducati", "KTM",
    "Triumph", "Aprilia", "Benelli", "CFMoto", "Zontes", "Indian",
    "Beta", "Sherco", "TM Racing", "Husaberg", "SWM", "Moto Guzzi",
    "Piaggio", "Vespa", "Kymco", "Sym", "Peugeot",
]

# Dutch and English attribute-table labels that hold make / model / year
_MAKE_LABELS  = {"merk", "merk motor", "fabrikant", "make", "brand motor"}
_MODEL_LABELS = {"model", "model motor", "type", "uitvoering"}
_YEAR_LABELS  = {"bouwjaar", "jaar", "year", "jaargang", "bj"}


def _normalise(s: str) -> str:
    return s.strip().lower()


def extract_mmy(soup: BeautifulSoup, title: str) -> tuple[str, str, str]:
    """
    Return (make, model, year) extracted from the product page.

    Strategy (in priority order):
      1. WooCommerce product-attribute table  (most reliable)
      2. Product short-description / tab text  (sometimes listed there)
      3. Regex against the product title       (fallback)
    """
    make = model = year = ""

    # --- 1. Attribute table ---
    attr_table = soup.find("table", class_=re.compile(r"woocommerce-product-attributes|shop_attributes"))
    if attr_table:
        for row in attr_table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = _normalise(th.get_text())
            value = td.get_text(separator=" ", strip=True)
            if label in _MAKE_LABELS and not make:
                make = value
            elif label in _MODEL_LABELS and not model:
                model = value
            elif label in _YEAR_LABELS and not year:
                year = _clean_year(value)

    # --- 2. Short description / product meta ---
    if not make or not model:
        meta_area = soup.find("div", class_=re.compile(r"product_meta|product-meta"))
        if meta_area:
            for span in meta_area.find_all("span"):
                text = span.get_text(separator=" ", strip=True)
                for mk in MOTO_MAKES:
                    if re.search(rf"\b{re.escape(mk)}\b", text, re.I):
                        if not make:
                            make = mk
                        break

    # --- 3. Regex against title ---
    if not make or not model or not year:
        t_make, t_model, t_year = _parse_title(title)
        if not make:
            make = t_make
        if not model:
            model = t_model
        if not year:
            year = t_year

    return make.strip(), model.strip(), year.strip()


def _parse_title(title: str) -> tuple[str, str, str]:
    """Extract make, model, year purely from the product title string."""
    make = model = year = ""

    # Year: match  2019-2023  /  2021+  /  2022  (4-digit, at end or standalone)
    # "2021+" alternative must come BEFORE bare "20\d{2}" to avoid early match
    year_match = re.search(r"(?<!\d)(20\d{2}\+|20\d{2}[–\-/](?:20)?\d{2}|20\d{2})(?!\d)", title)
    if year_match:
        year = _clean_year(year_match.group(1))

    # Make: find first known MOTORCYCLE manufacturer name in title.
    # MOTO_MAKES intentionally excludes exhaust brand names (Akrapovič, Arrow, etc.)
    # so that "Akrapovic Slip-On Honda CB650R" correctly yields make=Honda.
    for mk in MOTO_MAKES:
        if re.search(rf"\b{re.escape(mk)}\b", title, re.I):
            make = mk
            # Model: the word(s) immediately after the make, up to the year or end
            mk_pos = title.lower().index(mk.lower())
            after = title[mk_pos + len(mk):]
            # Strip common suffix noise words and leading punctuation/spaces
            after = re.sub(r"^\s*[-–—/]\s*", "", after)
            after = re.sub(r"\b(abs|se|sp|rs|euro\s*\d|e5|e4)\b", "", after, flags=re.I)
            model_match = re.match(
                r"\s*([A-Z0-9]{1,4}[\w\-\.]{0,25}(?:\s+[A-Z0-9][\w\-\.]{0,20})?)",
                after,
            )
            if model_match:
                candidate = model_match.group(1).strip()
                # Remove any trailing year we already captured
                candidate = re.sub(r"\s*20\d{2}.*$", "", candidate).strip()
                # Remove trailing noise characters
                candidate = candidate.rstrip("-–—/., ")
                if len(candidate) >= 2:
                    model = candidate
            break

    return make, model, year


def _clean_year(raw: str) -> str:
    """Normalise year strings: '2019 - 2023' → '2019-2023', '2021 +' → '2021+'."""
    y = re.sub(r"\s*[–—]\s*", "-", raw)   # em-dash / en-dash → hyphen
    y = re.sub(r"\s*/\s*", "-", y)         # slash → hyphen
    y = re.sub(r"\s+\+", "+", y)           # '2021 +' → '2021+'
    y = re.sub(r"\s+", "", y)              # remove remaining spaces
    # Expand short year:  2019-23 → 2019-2023
    y = re.sub(r"(20\d{2})-(\d{2})$", lambda m: f"{m.group(1)}-20{m.group(2)}", y)
    return y.strip()


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
    brand: str = ""         # exhaust manufacturer (Akrapovič, Arrow, …)
    category: str = ""      # breadcrumb category
    make: str = ""          # motorcycle manufacturer (Honda, Yamaha, …)
    model: str = ""         # motorcycle model (CB650R, MT-09, …)
    year: str = ""          # year or range (2019-2023, 2021+, …)
    extra_tags: list = field(default_factory=list)

    @property
    def net_price(self) -> float:
        return self.original_price / VAT_RATE

    @property
    def final_price(self) -> float:
        return self.net_price * MARKUP

    @property
    def handle(self) -> str:
        s = self.title.lower()
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
        return s or "product"

    def shopify_tags(self) -> list[str]:
        """Build the full tag list including structured make/model/year filter tags."""
        tags: list[str] = []

        # Structured filter tags — Shopify storefront filters key on these
        if self.make:
            tags.append(f"make:{self.make}")
        if self.model:
            tags.append(f"model:{self.model}")
        if self.year:
            # Add one tag per individual year so  year:2021  matches a 2019-2023 range
            for yr in _expand_years(self.year):
                tags.append(f"year:{yr}")

        # Exhaust brand tag (Akrapovič, Arrow, …)
        if self.brand:
            tags.append(f"brand:{self.brand}")

        # Category breadcrumbs
        tags.extend(self.extra_tags)

        # Internal tracking
        tags.append("source:bunkerparts.nl")

        return tags


def _expand_years(year_str: str) -> list[str]:
    """
    '2019-2023' → ['2019','2020','2021','2022','2023']
    '2021+'     → ['2021','2022','2023','2024','2025','2026', '2021+']
    '2022'      → ['2022']
    """
    import datetime
    current_year = datetime.date.today().year

    # Range: 2019-2023
    m = re.match(r"(20\d{2})-(20\d{2})$", year_str)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if 2000 <= start <= end <= 2040:
            return [str(y) for y in range(start, end + 1)]

    # Open-ended: 2021+
    m = re.match(r"(20\d{2})\+$", year_str)
    if m:
        start = int(m.group(1))
        if 2000 <= start <= current_year:
            years = [str(y) for y in range(start, current_year + 1)]
            years.append(year_str)  # keep "2021+" tag for exact-match filtering
            return years

    return [year_str]


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
                log.warning("HTTP %s on %s — waiting %ds (attempt %d/%d)",
                            resp.status_code, url, wait, attempt, MAX_RETRIES)
                time.sleep(wait)
            else:
                log.warning("HTTP %s on %s", resp.status_code, url)
                return None
        except requests.RequestException as exc:
            log.warning("Request error on %s: %s", url, exc)
            time.sleep(attempt * 3)
    return None


# ---------------------------------------------------------------------------
# Playwright session — persistent browser for the full run
# ---------------------------------------------------------------------------

class PlaywrightSession:
    def __init__(self):
        self._pw = self._browser = self._context = self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        exec_path = next((p for p in CHROMIUM_CANDIDATES if Path(p).exists()), None)
        log.info("Playwright Chromium: %s", exec_path or "default")
        self._pw = sync_playwright().start()
        launch_kw = {"headless": True}
        if exec_path:
            launch_kw["executable_path"] = exec_path
        self._browser = self._pw.chromium.launch(**launch_kw)
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

        # Scroll to bottom to trigger lazy-loaded gallery images, then back up
        try:
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._page.wait_for_timeout(800)
            self._page.evaluate("window.scrollTo(0, 0)")
            self._page.wait_for_timeout(300)
        except Exception:
            pass

        html = self._page.content()
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")
        body_text = soup.get_text(strip=True)

        if "host not in allowlist" in body_text.lower():
            log.error(
                "\nNETWORK BLOCKED — this sandbox does not allow outbound connections.\n"
                "Run the scraper on a machine with open internet access:\n"
                "  pip install -r requirements.txt && playwright install chromium\n"
                "  python scraper.py --playwright\n"
            )
            return None

        if len(body_text) < 200 and any(
            kw in body_text.lower() for kw in ("captcha", "access denied", "challenge")
        ):
            log.warning("Bot-block detected on %s", url)
            return None

        return soup


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def _has_products(soup: BeautifulSoup) -> bool:
    return any([
        soup.find("ul", class_=re.compile(r"products")),
        soup.find("div", class_=re.compile(r"products")),
        soup.find("li", class_=re.compile(r"product")),
        soup.find("div", class_=re.compile(r"product-item")),
        soup.find("article", class_=re.compile(r"product")),
    ])


def find_category_url(fetcher: Callable) -> Optional[str]:
    for path in CATEGORY_PATHS:
        url = BASE_URL + path
        log.info("Trying category path: %s", url)
        soup = fetcher(url)
        if soup and _has_products(soup):
            log.info("Found products at %s", url)
            return url

    log.info("Discovering exhaust URL from homepage navigation")
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
    page_num = 1
    while True:
        url = (category_url if page_num == 1
               else f"{category_url.rstrip('/')}/page/{page_num}/")
        log.info("Listing page %d: %s", page_num, url)
        soup = fetcher(url)

        if soup is None:
            log.warning("Failed to fetch listing page %d, stopping", page_num)
            break

        # WooCommerce redirects to page 1 when you exceed the page count
        if page_num > 1:
            cur_el = soup.find("span", class_=re.compile(r"current"))
            if cur_el:
                try:
                    if int(cur_el.get_text(strip=True)) != page_num:
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
    urls: set[str] = set()

    # WooCommerce standard product loop
    for a in soup.select("ul.products li.product a.woocommerce-LoopProduct-link"):
        href = a.get("href", "")
        if href:
            urls.add(urljoin(base_url, href))

    # Generic fallback
    if not urls:
        for el in soup.find_all(
            ["li", "article", "div"], class_=re.compile(r"\bproduct\b")
        ):
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

def parse_product(soup: BeautifulSoup, url: str) -> Optional[Product]:
    p = Product(url=url)

    # Title
    title_el = (
        soup.find("h1", class_=re.compile(r"product[_-]title|entry-title"))
        or soup.find("h1", itemprop="name")
        or soup.find("h1")
    )
    p.title = title_el.get_text(strip=True) if title_el else _url_to_title(url)

    # SKU
    sku_el = (
        soup.find("span", class_="sku")
        or soup.find(itemprop="sku")
        or soup.find("span", class_=re.compile(r"sku"))
    )
    p.sku = sku_el.get_text(strip=True) if sku_el else urlparse(url).path.rstrip("/").split("/")[-1]

    # Price — prefer sale (ins) price over regular price
    price_el = soup.find("p", class_="price") or soup.find("span", class_="price")
    if price_el:
        ins = price_el.find("ins")
        amount_el = ((ins or price_el).find("span", class_="woocommerce-Price-amount")
                     or (ins or price_el).find("bdi"))
        if amount_el:
            p.original_price = _parse_price(amount_el.get_text(strip=True))

    # Description (keep as HTML for Shopify Body field)
    desc_el = (
        soup.find("div", class_=re.compile(r"woocommerce-product-details__short-description"))
        or soup.find("div", id="tab-description")
        or soup.find("div", class_=re.compile(r"product-description|entry-content"))
    )
    p.description = str(desc_el) if desc_el else f"<p>{p.title}</p>"

    # Primary product image — check all lazy-load attributes in priority order
    _PLACEHOLDER = "s.w.org"  # lazy-load SVG placeholder domain

    def _best_img_src(img_el) -> str:
        for attr in ("data-large_image", "data-src", "data-lazy-src", "data-original", "src"):
            val = img_el.get(attr, "")
            if val and _PLACEHOLDER not in val and not val.startswith("data:"):
                return val
        return ""

    img_wrap = soup.find(["div", "figure"], class_=re.compile(r"woocommerce-product-gallery"))
    if img_wrap:
        # Try the anchor href first (links to full-size image)
        a = img_wrap.find("a", class_=re.compile(r"woocommerce-product-gallery__trigger|zoom"))
        if not a:
            a = img_wrap.find("a", href=re.compile(r"\.(jpe?g|png|webp)", re.I))
        if a and a.get("href", "") and _PLACEHOLDER not in a["href"]:
            p.image_src = a["href"]
        if not p.image_src:
            img = img_wrap.find("img")
            if img:
                p.image_src = _best_img_src(img)
    if not p.image_src:
        img = soup.find("img", class_=re.compile(r"wp-post-image|attachment-woocommerce"))
        if img:
            p.image_src = _best_img_src(img)
    if not p.image_src:
        # Last resort: any img inside the product summary with a real URL
        summary = soup.find("div", class_=re.compile(r"summary|product-summary"))
        if summary:
            for img in summary.find_all("img"):
                src = _best_img_src(img)
                if src:
                    p.image_src = src
                    break

    # Exhaust brand (Akrapovič, Arrow, SC-Project, …)
    brand_el = (
        soup.find(itemprop="brand")
        or soup.find("span", class_=re.compile(r"brand"))
    )
    if brand_el:
        p.brand = brand_el.get_text(strip=True)

    # If brand not in structured markup, try attribute table and then title
    if not p.brand:
        p.brand = _brand_from_attributes(soup) or _brand_from_title(p.title)

    # Breadcrumb → category & extra tags
    breadcrumb_tags: list[str] = []
    breadcrumb = soup.find("nav", class_=re.compile(r"breadcrumb|woocommerce-breadcrumb"))
    if breadcrumb:
        for crumb in breadcrumb.find_all("a"):
            text = crumb.get_text(strip=True)
            if text and text.lower() not in ("home", "winkel", "shop"):
                breadcrumb_tags.append(text)
    p.extra_tags = breadcrumb_tags
    p.category = breadcrumb_tags[-1] if breadcrumb_tags else "Uitlaten"

    # Make / model / year
    p.make, p.model, p.year = extract_mmy(soup, p.title)

    return p if p.title else None


def _brand_from_attributes(soup: BeautifulSoup) -> str:
    """Read the exhaust brand from a WooCommerce attribute table."""
    attr_table = soup.find(
        "table", class_=re.compile(r"woocommerce-product-attributes|shop_attributes")
    )
    if not attr_table:
        return ""
    brand_labels = {"merk uitlaat", "uitlaat merk", "exhaust brand",
                    "merk", "fabrikant", "brand"}
    for row in attr_table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td and _normalise(th.get_text()) in brand_labels:
            return td.get_text(strip=True)
    return ""


# Known exhaust brands — used as a fallback to pull the brand from the title
_EXHAUST_BRANDS: list[str] = [
    "Akrapovič", "Akrapovic", "Arrow", "SC-Project", "Leovince",
    "LeoVince", "Yoshimura", "Remus", "Ixil", "Termignoni",
    "Rizoma", "Vance & Hines", "Two Brothers", "Austin Racing",
    "Hindle", "Graves Motorsports", "Spark", "Zard", "Mivv",
    "GPR", "Scorpion", "Laser", "QD Exhaust", "Cobra",
]


def _brand_from_title(title: str) -> str:
    for brand in _EXHAUST_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", title, re.I):
            return brand
    return ""


def _url_to_title(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").title()


def _parse_price(raw: str) -> float:
    cleaned = re.sub(r"[€$£\s\xa0]", "", raw)
    if re.search(r"\d\.\d{3}", cleaned):        # Dutch thousands separator
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
    # --- informational columns (Shopify importer ignores unknown columns) ---
    "Source URL",
    "Original Price (incl. VAT)",
    "Net Price (excl. VAT)",
    "Motorcycle Make",
    "Motorcycle Model",
    "Motorcycle Year",
]


def product_to_shopify_row(p: Product) -> dict:
    return {
        "Handle":                      p.handle,
        "Title":                       p.title,
        "Body (HTML)":                 p.description,
        "Vendor":                      p.brand or "Unknown",
        "Type":                        p.category or "Uitlaten",
        "Tags":                        ", ".join(p.shopify_tags()),
        "Published":                   "TRUE",
        "Option1 Name":                "Title",
        "Option1 Value":               "Default Title",
        "Variant SKU":                 p.sku,
        "Variant Grams":               "5000",
        "Variant Inventory Tracker":   "shopify",
        "Variant Inventory Qty":       "1",
        "Variant Inventory Policy":    "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price":               f"{p.final_price:.2f}",
        "Variant Compare At Price":    "",
        "Variant Taxable":             "FALSE",
        "Image Src":                   p.image_src,
        "Image Position":              "1",
        "Image Alt Text":              p.title,
        "Source URL":                  p.url,
        "Original Price (incl. VAT)":  f"{p.original_price:.2f}",
        "Net Price (excl. VAT)":       f"{p.net_price:.2f}",
        "Motorcycle Make":             p.make,
        "Motorcycle Model":            p.model,
        "Motorcycle Year":             p.year,
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

            log.info("Scraping: %s", prod_url)
            detail_soup = fetcher(prod_url)
            if detail_soup is None:
                log.warning("Skipping (failed to load): %s", prod_url)
                continue

            product = parse_product(detail_soup, prod_url)
            if not product:
                log.warning("Could not parse product at %s", prod_url)
                continue
            if product.original_price == 0:
                log.warning("No price for '%s' — skipping", product.title)
                continue

            products.append(product)
            log.info(
                "  %-48s  make=%-10s model=%-12s  €%7.2f → €%7.2f",
                product.title[:48],
                product.make[:10] if product.make else "-",
                product.model[:12] if product.model else "-",
                product.original_price,
                product.final_price,
            )


def scrape(use_playwright: bool = False) -> list[Product]:
    products: list[Product] = []
    seen_urls: set[str] = set()

    if use_playwright:
        with PlaywrightSession() as pw:
            _run_scrape(pw.fetch, products, seen_urls)
    else:
        session = make_session()
        _run_scrape(lambda url: fetch_requests(session, url), products, seen_urls)
        if not products:
            log.warning("No products via requests — retrying with Playwright")
            return scrape(use_playwright=True)

    return products


def main():
    log.info("=== Bunkerparts.nl Exhaust Scraper ===")
    log.info("VAT: /%.2f   Markup: ×%.2f", VAT_RATE, MARKUP)

    products = scrape(use_playwright=False)

    if not products:
        log.error("No products collected. Check logs above for details.")
        return

    export_csv(products, OUTPUT_FILE)

    print(f"\n{'='*88}")
    print(f"{'PRODUCT':<44} {'MAKE':<11} {'MODEL':<13} {'ORIG':>8} {'EXPORT':>9}")
    print(f"{'-'*88}")
    for p in products:
        print(
            f"{p.title[:43]:<44} "
            f"{(p.make or '-')[:10]:<11} "
            f"{(p.model or '-')[:12]:<13} "
            f"€{p.original_price:>7.2f} "
            f"€{p.final_price:>8.2f}"
        )
    print(f"{'='*88}")
    print(f"Total: {len(products)} products  →  {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    import sys
    use_pw = "--playwright" in sys.argv
    if use_pw:
        log.info("Force-Playwright mode")
    products = scrape(use_playwright=use_pw)
    if products:
        export_csv(products, OUTPUT_FILE)
        print(f"\nTotal: {len(products)} products → {OUTPUT_FILE}")
    else:
        log.error("No products collected.")
