#!/usr/bin/env python3
"""
Vault-34 Exhaust Catalog Pipeline
==================================
Scrapes uitlaatstore.nl → translates → validates images → exports Shopify CSV.

IMPORTANT: Run from a home or office IP — uitlaatstore.nl blocks datacenter IPs.

Usage examples:
  python main.py --brands akrapovic,arrow,sc-project
  python main.py --all-brands
  python main.py --discover --url https://www.uitlaatstore.nl/some-product-slug
  python main.py --brands akrapovic --skip-translate   # keep Dutch descriptions
  python main.py --brands akrapovic --skip-validate    # skip image validation
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# UTF-8 output — prevents UnicodeEncodeError on Windows cp1252 consoles
# ---------------------------------------------------------------------------

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/scrape.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vault-34 exhaust catalog pipeline")

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--brands", metavar="BRAND,...",
        help="Comma-separated exhaust brand slugs (e.g. akrapovic,arrow)",
    )
    source.add_argument(
        "--all-brands", action="store_true",
        help="Scrape all brands listed in config/brands.py TOP_BRANDS",
    )
    source.add_argument(
        "--from-cache", metavar="FILE",
        help="Skip scraping; load raw products from a JSON cache file",
    )

    parser.add_argument(
        "--discover", action="store_true",
        help="Print DOM selector candidates for a product page then exit",
    )
    parser.add_argument(
        "--url", metavar="URL",
        help="Product URL to use with --discover",
    )
    parser.add_argument(
        "--skip-translate", action="store_true",
        help="Skip Claude API translation (descriptions stay in Dutch)",
    )
    parser.add_argument(
        "--skip-validate", action="store_true",
        help="Skip image URL validation (include all images as-is)",
    )
    parser.add_argument(
        "--output", metavar="FILE", default="shopify_exports/shopify_import.csv",
        help="Output CSV path (default: shopify_exports/shopify_import.csv)",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def step_discover(url: str) -> None:
    """Dump DOM selector candidates for a single product URL and exit."""
    import json as _json
    from scrapers.uitlaatstore import make_session, fetch, discover_selectors
    from parsers.product_parser import parse_product
    session = make_session()
    soup = fetch(session, url)
    if soup is None:
        log.error("Failed to fetch %s", url)
        sys.exit(1)

    # Show JSON-LD blocks present on the page
    print("\n=== JSON-LD BLOCKS ===")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            t = data.get("@type", "") if isinstance(data, dict) else ""
            print(f"  @type={t!r}  keys={list(data.keys()) if isinstance(data, dict) else '(list)'}")
            if t == "Product":
                print(f"  name={data.get('name','')!r}")
                print(f"  sku={data.get('sku','')!r}")
                offers = data.get("offers", {})
                if isinstance(offers, list): offers = offers[0]
                print(f"  price={offers.get('price','') if isinstance(offers,dict) else '?'!r}")
                print(f"  images={data.get('image',[])!r}"[:200])
        except Exception:
            pass
    print("=== END JSON-LD ===\n")

    # Show what the parser actually extracts
    print("=== PARSER OUTPUT ===")
    product = parse_product(soup, url)
    if product:
        print(f"  title:       {product['title']!r}")
        print(f"  sku:         {product['sku']!r}")
        print(f"  brand:       {product['brand']!r}")
        print(f"  price_raw:   {product['price_raw']}")
        print(f"  fitment:     {product['fitment']}")
        print(f"  images:      {len(product['images'])} found")
        for img in product['images'][:3]:
            print(f"    {img}")
        print(f"  description: {product['description_nl'][:120]!r}")
    else:
        print("  PARSER RETURNED None — missing title or price")
    print("=== END PARSER OUTPUT ===\n")

    discover_selectors(soup)
    sys.exit(0)


def step_scrape(brands: list[str]) -> list[dict]:
    """Scrape product detail pages for each brand. Returns raw product dicts."""
    from scrapers.uitlaatstore import make_session, fetch, discover_product_urls
    from parsers.product_parser import parse_product
    from config.settings import LOGS_DIR

    session = make_session()
    products: list[dict] = []
    failed_urls: list[str] = []

    for brand in brands:
        log.info("=== Scraping brand: %s ===", brand)
        checkpoint = LOGS_DIR / f"checkpoint_{brand}.json"
        urls = discover_product_urls(session, brand, checkpoint_file=checkpoint)
        log.info("  %d product URLs for %s", len(urls), brand)

        for url in urls:
            log.info("  Scraping: %s", url)
            soup = fetch(session, url)
            if soup is None:
                failed_urls.append(url)
                continue
            product = parse_product(soup, url)
            if product:
                products.append(product)
            else:
                log.warning("  Could not parse: %s", url)

    _write_log("failed_scrape.json", failed_urls)
    log.info("Scrape complete: %d products, %d failures", len(products), len(failed_urls))
    return products


def step_deduplicate(products: list[dict]) -> list[dict]:
    """Remove duplicate products by SKU, then by URL."""
    seen_skus: set[str] = set()
    seen_urls: set[str] = set()
    unique:    list[dict] = []
    dupes:     list[dict] = []

    for p in products:
        sku = p.get("sku", "").strip()
        url = p.get("url", "")
        if sku and sku in seen_skus:
            dupes.append(p)
            continue
        if url in seen_urls:
            dupes.append(p)
            continue
        if sku:
            seen_skus.add(sku)
        seen_urls.add(url)
        unique.append(p)

    if dupes:
        _write_log("duplicates.json", [{"title": d.get("title"), "sku": d.get("sku"), "url": d.get("url")} for d in dupes])
        log.info("Removed %d duplicates (see logs/duplicates.json)", len(dupes))

    return unique


def step_clean(products: list[dict]) -> list[dict]:
    """Strip competitor branding and UI artefacts from descriptions."""
    from transformers.cleaner import clean_all
    return clean_all(products)


def step_translate(products: list[dict]) -> list[dict]:
    """Translate description_nl → description_en via Claude Haiku."""
    from transformers.translator import translate_all
    return translate_all(products)


def step_validate_images(products: list[dict]) -> list[dict]:
    """Validate image URLs and filter out products with no valid images."""
    from shopify_exports.image_validator import validate_all
    importable, _missing = validate_all(products)
    return importable


def step_export(products: list[dict]) -> Path:
    """Write the Shopify CSV and image manifest."""
    from shopify_exports.csv_exporter import export
    return export(products)


def step_qa_report(products: list[dict]) -> None:
    """Write a QA report flagging data quality issues."""
    issues: list[dict] = []
    for p in products:
        flags: list[str] = []
        if not p.get("sku"):
            flags.append("missing_sku")
        if not p.get("brand"):
            flags.append("missing_brand")
        if not p.get("fitment", {}).get("make"):
            flags.append("missing_make")
        if not p.get("fitment", {}).get("model"):
            flags.append("missing_model")
        if not p.get("fitment", {}).get("year"):
            flags.append("missing_year")
        if p.get("translation_failed"):
            flags.append("translation_failed")
        if not p.get("validated_images"):
            flags.append("no_valid_images")
        if p.get("price_raw", 0) == 0:
            flags.append("zero_price")
        if flags:
            issues.append({"title": p.get("title"), "url": p.get("url"), "flags": flags})

    _write_log("qa_report.json", issues)
    log.info("QA report: %d products with issues → logs/qa_report.json", len(issues))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # Selector discovery mode
    if args.discover:
        if not args.url:
            print("--discover requires --url <product_url>", file=sys.stderr)
            sys.exit(1)
        step_discover(args.url)

    # Determine brand list
    if args.all_brands:
        from config.brands import TOP_BRANDS
        brands = TOP_BRANDS
    elif args.brands:
        brands = [b.strip() for b in args.brands.split(",") if b.strip()]
    elif args.from_cache:
        brands = []
    else:
        print("Specify --brands, --all-brands, or --from-cache", file=sys.stderr)
        sys.exit(1)

    # Load products
    if args.from_cache:
        cache_path = Path(args.from_cache)
        log.info("Loading products from cache: %s", cache_path)
        products = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        products = step_scrape(brands)

    if not products:
        log.error("No products collected. See logs/scrape.log for details.")
        sys.exit(1)

    # Save raw cache
    raw_cache = Path("logs/raw_products.json")
    raw_cache.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Raw products cached → %s", raw_cache)

    # Pipeline
    products = step_deduplicate(products)
    products = step_clean(products)

    if not args.skip_translate:
        products = step_translate(products)

    if not args.skip_validate:
        products = step_validate_images(products)

    step_qa_report(products)
    output = step_export(products)

    print(f"\n{'='*60}")
    print(f"  Done! {len(products)} products → {output}")
    print(f"  QA report:     logs/qa_report.json")
    print(f"  Image manifest: shopify_exports/image_manifest.json")
    print(f"  Next step: Shopify Admin → Products → Import → {output.name}")
    print(f"{'='*60}\n")


def _write_log(filename: str, data: object) -> None:
    from config.settings import LOGS_DIR
    path = LOGS_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
