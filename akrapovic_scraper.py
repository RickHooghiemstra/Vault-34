#!/usr/bin/env python3
"""
Akrapovič Sniper Scrape — uitlaatstore.nl
Base 34 arbitrage + Shopify 2026-ready CSV + validation XLSX
"""

import re
import time
import math
import csv
import io
import logging
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from decimal import Decimal, ROUND_DOWN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://www.uitlaatstore.nl"
CATEGORY_URL = "https://www.uitlaatstore.nl/alle-merken/akrapovic"
CONCURRENCY_DELAY = 2          # seconds between requests
MAX_PRODUCTS = 100
VAT_DIVISOR = Decimal("1.21")
MARGIN_MULTIPLIER = Decimal("1.34")
WEIGHT_DEFAULT = "5.0"

SHOPIFY_CATEGORY = (
    "Vehicles & Parts > Vehicle Parts & Accessories > "
    "Motor Vehicle Parts > Motor Vehicle Exhaust Systems"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def fetch(url: str, retries: int = 4, backoff: float = 2.0) -> BeautifulSoup | None:
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code in (403, 503):
                wait = backoff * (2 ** attempt)
                log.warning("HTTP %s for %s — backing off %.0fs", resp.status_code, url, wait)
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as exc:
            wait = backoff * (2 ** attempt)
            log.warning("Request error %s — retry in %.0fs (%s)", exc, wait, url)
            time.sleep(wait)
    log.error("Failed after %d attempts: %s", retries, url)
    return None


def normalise_year(raw: str) -> str:
    """Convert 2-digit year ranges like '24-'26 → 2024-2026."""
    def expand(m):
        y = int(m.group(0))
        return str(2000 + y) if y < 100 else m.group(0)
    return re.sub(r"\b\d{2}\b", expand, raw)


YEAR_PATTERN = re.compile(
    r"(?<!\d)"
    r"("
    r"(?:19|20)\d{2}"           # full 4-digit year
    r"|"
    r"'\d{2}"                    # shorthand '24
    r"|"
    r"\d{2}(?=\s*[-–]\s*(?:\d{2}|\d{4}))"  # range start
    r")"
    r"(?:\s*[-–]\s*"
    r"(?:(?:19|20)\d{2}|\d{2})"
    r")?",
    re.IGNORECASE,
)

BRAND_KEYWORDS = re.compile(
    r"\b(Honda|Yamaha|Kawasaki|Suzuki|Ducati|BMW|KTM|Triumph|Aprilia|Husqvarna|"
    r"Harley.Davidson|Harley|Royal Enfield|Indian|MV Agusta|Benelli|CF Moto|"
    r"Moto Guzzi|Sherco|Beta|GasGas|TM Racing|Husaberg|Buell|Zero|Energica|"
    r"Can-Am|Sea-Doo|Polaris|Arctic Cat|Ski-Doo|Segway|Lynx|Kymco|SYM|"
    r"Piaggio|Vespa|Gilera|Derbi|Peugeot|MBK|Fantic|Rieju|Montesa|Ossa|"
    r"Bultaco|Laverda|Cagiva|Italjet|Malaguti|Hyosung|Daelim|Zongshen|"
    r"Loncin|Lifan|Jianshe|Keeway|Qingqi|Xingyue|Voge|Mash|Jawa|ČZ|"
    r"AJP|Rieju|Sherco|TM|Ural|Dnepr|Vertemati|Nuda|Husaberg|"
    r"Audi|VW|Volkswagen|Mercedes|Ford|Porsche|Ferrari|Lamborghini|"
    r"Subaru|Mitsubishi|Nissan|Toyota|Lexus|Mazda|Honda|Hyundai|Kia)\b",
    re.IGNORECASE,
)


def extract_fitment(title: str, specs_text: str) -> tuple[str, str, str]:
    """Return (brand, model, years) — may be empty strings if not found."""
    combined = title + " | " + specs_text

    # brand
    brand_match = BRAND_KEYWORDS.search(combined)
    brand = brand_match.group(0).title() if brand_match else ""

    # years
    year_hits = YEAR_PATTERN.findall(combined)
    years = ""
    if year_hits:
        raw_years = " ".join(year_hits[:2])
        years = normalise_year(raw_years).strip()

    # model — text between brand and year (or end)
    model = ""
    if brand:
        after_brand = re.split(re.escape(brand), combined, maxsplit=1, flags=re.IGNORECASE)
        if len(after_brand) > 1:
            candidate = after_brand[1].strip().lstrip(" -|")
            # take first meaningful chunk up to year or pipe
            model_match = re.match(r"([A-Za-z0-9 \-/]+?)(?=\s*\d{4}|\s*'?\d{2}|\s*\||\s*$)", candidate)
            if model_match:
                model = model_match.group(1).strip(" -|")

    return brand, model, years


def parse_dutch_price(raw: str) -> Decimal | None:
    """Parse '€ 1.042,18' or '1042.18' → Decimal."""
    clean = re.sub(r"[€\s]", "", raw)
    # Dutch format: dots as thousands sep, comma as decimal
    if "," in clean:
        clean = clean.replace(".", "").replace(",", ".")
    try:
        return Decimal(clean)
    except Exception:
        return None


def base34_price(retail_incl_vat: Decimal) -> tuple[Decimal, Decimal, Decimal, str]:
    """
    Returns (ex_vat, shopify_price, profit_spread_pct, flag)
    shopify_price forced to .95 rounding.
    """
    ex_vat = (retail_incl_vat / VAT_DIVISOR).quantize(Decimal("0.01"))
    raw_shopify = ex_vat * MARGIN_MULTIPLIER
    # force-round to .95
    shopify = (raw_shopify - Decimal("0.95")).to_integral_value(ROUND_DOWN) + Decimal("0.95")

    profit_spread = ((shopify - ex_vat) / ex_vat * 100).quantize(Decimal("0.01"))

    flag = ""
    if shopify < ex_vat:
        flag = "CRITICAL_LOSS"
    elif profit_spread < 24 or profit_spread > 44:
        flag = "MANUAL_REVIEW"

    return ex_vat, shopify, profit_spread, flag


def slug(brand: str, model: str, sku: str) -> str:
    raw = f"{brand}-{model}-{sku}".lower()
    return re.sub(r"[^a-z0-9\-]", "-", raw).strip("-")


def clean_html(soup_element) -> str:
    """Return cleaned inner HTML string of a product description element."""
    if not soup_element:
        return ""
    # remove scripts/styles
    for tag in soup_element.find_all(["script", "style"]):
        tag.decompose()
    return str(soup_element).strip()


def seo_description(dutch_html: str) -> str:
    """Strip HTML, return first 150 chars of plain text."""
    text = re.sub(r"<[^>]+>", " ", dutch_html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:150]


# ---------------------------------------------------------------------------
# listing page crawl
# ---------------------------------------------------------------------------

def get_product_links(category_url: str) -> list[str]:
    """Crawl paginated listing and return product URLs (up to MAX_PRODUCTS)."""
    links: list[str] = []
    page = 1

    while len(links) < MAX_PRODUCTS:
        url = f"{category_url}?p={page}" if page > 1 else category_url
        log.info("Fetching listing page %d: %s", page, url)
        soup = fetch(url)
        if not soup:
            break

        # product cards — try multiple selectors
        cards = (
            soup.select("a.product-item-link") or
            soup.select("a.product-name") or
            soup.select(".products-grid .product-item a[href*='/product/']") or
            soup.select(".product-list a[href]") or
            soup.select("li.item.product a.product-item-link") or
            soup.select("a[data-product-id]") or
            []
        )

        # fallback: any link under a product-item that has a recognisable path
        if not cards:
            cards = [
                a for a in soup.select(".product-item a[href]")
                if "/akrapovic" in a.get("href", "") or "/product" in a.get("href", "")
            ]

        # broader fallback: any link that looks like a product detail page
        if not cards:
            cards = [
                a for a in soup.find_all("a", href=True)
                if re.search(r"/[a-z0-9\-]+-akrapovic[a-z0-9\-]*/?$", a["href"])
                or re.search(r"/akrapovic/[a-z0-9\-]+/?$", a["href"])
            ]

        new_links = []
        seen = set(links)
        for card in cards:
            href = card.get("href", "")
            if not href:
                continue
            full = urljoin(BASE_URL, href)
            if full not in seen:
                new_links.append(full)
                seen.add(full)

        if not new_links:
            log.info("No new product links on page %d — stopping.", page)
            break

        links.extend(new_links)
        log.info("Collected %d links so far.", len(links))

        # check for next page
        next_btn = soup.select_one("a.next, a[rel='next'], li.next a, .pages-item-next a")
        if not next_btn:
            break

        page += 1
        time.sleep(CONCURRENCY_DELAY)

    return links[:MAX_PRODUCTS]


# ---------------------------------------------------------------------------
# product page parser
# ---------------------------------------------------------------------------

def parse_product(url: str) -> dict | None:
    soup = fetch(url)
    if not soup:
        return None

    # --- title ---
    title_el = (
        soup.select_one("h1.page-title span") or
        soup.select_one("h1.product-title") or
        soup.select_one("h1[itemprop='name']") or
        soup.select_one("h1")
    )
    title = title_el.get_text(strip=True) if title_el else ""

    # filter: only Akrapovič products
    if "akrapovic" not in title.lower() and "akrapovič" not in title.lower():
        # check meta / breadcrumb
        brand_meta = soup.find("meta", {"itemprop": "brand"}) or soup.find("span", {"itemprop": "brand"})
        brand_val = (brand_meta.get("content", "") or brand_meta.get_text("")) if brand_meta else ""
        if "akrapovic" not in brand_val.lower() and "akrapovič" not in brand_val.lower():
            return None

    # --- SKU ---
    sku_el = (
        soup.select_one("[itemprop='sku']") or
        soup.select_one(".product-info-stock-sku .value") or
        soup.select_one("#product-attribute-specs-table tr:contains('Artikelnummer') td") or
        soup.select_one(".sku .value") or
        soup.select_one("[data-th='Artikelnummer']")
    )
    sku = sku_el.get_text(strip=True) if sku_el else ""

    # --- price ---
    price_el = (
        soup.select_one("[itemprop='price']") or
        soup.select_one(".price") or
        soup.select_one("span.price")
    )
    raw_price = ""
    if price_el:
        raw_price = price_el.get("content", "") or price_el.get_text(strip=True)

    retail_price = parse_dutch_price(raw_price) if raw_price else None

    # --- primary image ---
    img_el = (
        soup.select_one(".fotorama__img") or
        soup.select_one("[itemprop='image']") or
        soup.select_one(".product-image-photo") or
        soup.select_one("img.photo.image")
    )
    image_url = ""
    if img_el:
        image_url = img_el.get("src", "") or img_el.get("data-src", "") or img_el.get("content", "")
        if image_url and not image_url.startswith("http"):
            image_url = urljoin(BASE_URL, image_url)

    # --- description HTML ---
    desc_el = (
        soup.select_one("[itemprop='description']") or
        soup.select_one("#description") or
        soup.select_one(".product-description") or
        soup.select_one(".product.attribute.description .value") or
        soup.select_one(".description .value")
    )
    body_html = clean_html(desc_el)

    # --- specs table ---
    specs_text = ""
    specs_table = (
        soup.select_one("#product-attribute-specs-table") or
        soup.select_one(".additional-attributes") or
        soup.select_one("table.data.table.additional-attributes")
    )
    if specs_table:
        specs_text = specs_table.get_text(" ", strip=True)

    # --- weight ---
    weight = WEIGHT_DEFAULT
    weight_match = re.search(r"gewicht[:\s]+([0-9]+[.,][0-9]+)\s*kg", specs_text, re.IGNORECASE)
    if weight_match:
        weight = weight_match.group(1).replace(",", ".")

    # --- fitment ---
    brand, model, years = extract_fitment(title, specs_text)
    fitment_flag = ""
    if not brand or not years:
        fitment_flag = "MANUAL_REVIEW_FITMENT"

    # --- base34 pricing ---
    pricing_flag = fitment_flag
    ex_vat = shopify_price = profit_spread = None
    if retail_price:
        ex_vat, shopify_price, profit_spread, price_flag = base34_price(retail_price)
        if price_flag:
            pricing_flag = f"{pricing_flag},{price_flag}".strip(",")
    else:
        pricing_flag = f"{pricing_flag},MISSING_PRICE".strip(",")

    # --- SEO ---
    model_label = model or "Exhaust"
    year_label = years or "Universal"
    alt_text = f"Akrapovič {model_label} {year_label} Premium Exhaust System"
    seo_title = f"Akrapovič {model_label} ({year_label}) | Premium Performance | Global Apex"
    seo_desc = seo_description(body_html)[:150]

    handle = slug(brand or "akrapovic", model_label, sku or re.sub(r"[^a-z0-9]", "", title.lower())[:20])

    return {
        "source_url": url,
        "title": title,
        "sku": sku,
        "image_url": image_url,
        "body_html": body_html,
        "retail_incl_vat": float(retail_price) if retail_price else None,
        "retail_ex_vat": float(ex_vat) if ex_vat else None,
        "shopify_price": float(shopify_price) if shopify_price else None,
        "profit_spread_pct": float(profit_spread) if profit_spread else None,
        "brand": brand,
        "model": model,
        "years": years,
        "weight": weight,
        "flag": pricing_flag,
        # shopify fields
        "handle": handle,
        "alt_text": alt_text,
        "seo_title": seo_title,
        "seo_description": seo_desc,
    }


# ---------------------------------------------------------------------------
# CSV builder
# ---------------------------------------------------------------------------

SHOPIFY_HEADERS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
    "Tags", "Published", "Option1 Name", "Option1 Value",
    "Variant SKU", "Variant Grams", "Variant Inventory Tracker",
    "Variant Inventory Qty", "Variant Inventory Policy",
    "Variant Fulfillment Service", "Variant Price",
    "Variant Compare At Price", "Variant Requires Shipping",
    "Variant Taxable", "Image Src", "Image Position", "Image Alt Text",
    "SEO Title", "SEO Description",
    "Status", "Standard Product Type",
]


def build_shopify_row(p: dict) -> dict:
    return {
        "Handle": p["handle"],
        "Title": p["title"],
        "Body (HTML)": p["body_html"],
        "Vendor": "Akrapovič",
        "Product Category": SHOPIFY_CATEGORY,
        "Type": "Exhaust System",
        "Tags": f"akrapovic,exhaust,{p['brand'].lower()},{p['model'].lower()},{p['years']}".strip(","),
        "Published": "FALSE",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Variant SKU": p["sku"],
        "Variant Grams": str(int(float(p["weight"]) * 1000)),
        "Variant Inventory Tracker": "shopify",
        "Variant Inventory Qty": "0",
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": f"{p['shopify_price']:.2f}" if p["shopify_price"] else "",
        "Variant Compare At Price": f"{p['retail_incl_vat']:.2f}" if p["retail_incl_vat"] else "",
        "Variant Requires Shipping": "TRUE",
        "Variant Taxable": "FALSE",
        "Image Src": p["image_url"],
        "Image Position": "1",
        "Image Alt Text": p["alt_text"],
        "SEO Title": p["seo_title"],
        "SEO Description": p["seo_description"],
        "Status": "draft",
        "Standard Product Type": SHOPIFY_CATEGORY,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    log.info("=== Akrapovič Sniper Scrape — START ===")

    # 1. collect product links
    links = get_product_links(CATEGORY_URL)
    log.info("Total product URLs found: %d", len(links))

    if not links:
        log.error("No product links discovered — aborting.")
        return

    # 2. scrape each product
    products = []
    for i, url in enumerate(links, 1):
        log.info("[%d/%d] Scraping: %s", i, len(links), url)
        product = parse_product(url)
        if product:
            products.append(product)
            log.info("  OK  %-50s  SKU=%-20s  Price=€%.2f",
                     product["title"][:50],
                     product["sku"],
                     product["shopify_price"] or 0)
        else:
            log.warning("  SKIP (non-Akrapovič or parse fail)")

        if len(products) >= MAX_PRODUCTS:
            log.info("Reached %d products — stopping.", MAX_PRODUCTS)
            break

        time.sleep(CONCURRENCY_DELAY)

    log.info("Scraped %d valid Akrapovič products.", len(products))

    if not products:
        log.error("No valid products — cannot generate files.")
        return

    # 3. build DataFrames
    df = pd.DataFrame(products)

    # 4. validation XLSX
    xlsx_path = "/home/user/Vault-34/GAA_Akra_Validation_100.xlsx"
    audit_cols = [
        "title", "sku", "brand", "model", "years",
        "retail_incl_vat", "retail_ex_vat", "shopify_price",
        "profit_spread_pct", "flag", "source_url",
    ]
    df_audit = df[audit_cols].copy()
    df_audit.columns = [
        "Title", "SKU", "Brand", "Model", "Years",
        "Retail (incl. VAT €)", "Retail Ex-VAT (€)", "Shopify Price (€)",
        "Profit Spread (%)", "Flag", "Source URL",
    ]

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_audit.to_excel(writer, sheet_name="Validation", index=False)

        # summary sheet
        total = len(df_audit)
        avg_margin = df["profit_spread_pct"].dropna().mean()
        manual = df["flag"].str.contains("MANUAL_REVIEW", na=False).sum()
        critical = df["flag"].str.contains("CRITICAL_LOSS", na=False).sum()
        fitment_issues = df["flag"].str.contains("FITMENT", na=False).sum()
        missing_price = df["flag"].str.contains("MISSING_PRICE", na=False).sum()

        summary_data = {
            "Metric": [
                "Total Akrapovič SKUs processed",
                "Average Base-34 Profit Margin (%)",
                "Items flagged MANUAL_REVIEW",
                "Items flagged CRITICAL_LOSS",
                "Items flagged FITMENT issues",
                "Items with MISSING_PRICE",
                "Clean records (no flags)",
            ],
            "Value": [
                total,
                f"{avg_margin:.2f}%" if avg_margin else "N/A",
                manual,
                critical,
                fitment_issues,
                missing_price,
                total - df["flag"].astype(bool).sum(),
            ],
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

    log.info("Validation XLSX written: %s", xlsx_path)

    # 5. Shopify CSV
    csv_path = "/home/user/Vault-34/GAA_Akra_Shopify_100.csv"
    shopify_rows = [build_shopify_row(p) for p in products]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SHOPIFY_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(shopify_rows)

    log.info("Shopify CSV written: %s", csv_path)

    # 6. final report
    print("\n" + "=" * 70)
    print("FINAL REPORT — Akrapovič Base-34 Sniper Scrape")
    print("=" * 70)
    print(f"  Total Akrapovič SKUs processed   : {total}")
    print(f"  Average Base-34 Profit Margin    : {avg_margin:.2f}%" if avg_margin else "  Average Base-34 Profit Margin    : N/A")
    print(f"  Flagged MANUAL_REVIEW            : {manual}")
    print(f"  Flagged CRITICAL_LOSS            : {critical}")
    print(f"  Fitment extraction issues        : {fitment_issues}")
    print(f"  Missing price                    : {missing_price}")
    print(f"  Clean records                    : {total - df['flag'].astype(bool).sum()}")
    print("=" * 70)
    print(f"\nFiles saved:")
    print(f"  {xlsx_path}")
    print(f"  {csv_path}")


if __name__ == "__main__":
    main()
