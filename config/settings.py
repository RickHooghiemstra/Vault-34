"""
Central configuration for the Vault-34 scraper pipeline.
All tuneable values live here; never hardcode them in scraper/transformer files.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR      = Path(__file__).parent.parent
LOGS_DIR      = ROOT_DIR / "logs"
IMAGES_DIR    = ROOT_DIR / "images"
EXPORTS_DIR   = ROOT_DIR / "shopify_exports"

LOGS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Target site
# ---------------------------------------------------------------------------

BASE_URL = "https://www.uitlaatstore.nl"
BRAND_LISTING_PATH = "/alle-merken/{brand}"   # {brand} replaced at runtime
PAGE_SIZE = 40                                 # items per offset page

# ---------------------------------------------------------------------------
# Scraper behaviour
# ---------------------------------------------------------------------------

REQUEST_DELAY   = float(os.getenv("REQUEST_DELAY", "2.0"))   # seconds between requests
MAX_RETRIES     = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = 20                                          # seconds per request

# Residential proxy (optional — leave blank for direct home/office IP)
PROXY_URL = os.getenv("PROXY_URL", "") or None

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

VAT_RATE = 1.21   # Dutch BTW rate — divided out to get net price
MARKUP   = 1.35   # 35% export markup (sharpened 10% from original 1.50 to improve competitiveness)

# compareAtPrice ("was" price) — mirrors the promotional strategy applied in-store
COMPARE_AT_MARKUP   = 1.50   # "was" price = net × this (original markup, shown as RRP anchor)
COMPARE_AT_FRACTION = 0.30   # fraction of products displaying the sale badge
COMPARE_AT_SEED     = 42     # random seed — keeps the 30% selection stable across re-runs

# ---------------------------------------------------------------------------
# Claude API (translation)
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
TRANSLATION_MODEL   = "claude-haiku-4-5-20251001"
TRANSLATION_BATCH   = 10       # descriptions per API call
TRANSLATION_CACHE   = LOGS_DIR / "translation_cache.json"

# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

MIN_IMAGE_BYTES    = 10_000     # images smaller than this are likely thumbnails
MIN_IMAGE_DIM      = 800        # minimum width or height in pixels
IMAGE_TIMEOUT      = 5          # seconds for HEAD/GET requests
IMAGE_SAMPLE_BYTES = 65_536     # bytes to download for dimension check (partial GET)

# URL path fragments that indicate non-product images — skip these
IMAGE_SKIP_PATTERNS = ["/logo", "/icon", "/banner", "/placeholder", "s.w.org", "data:"]

# ---------------------------------------------------------------------------
# DOM selector fallbacks (used only when JSON-LD / OpenGraph are absent)
# Tune these by running:  python main.py --discover --url <product_url>
# ---------------------------------------------------------------------------

SELECTORS = {
    # Confirmed working against uitlaatstore.nl via --discover
    "title":       ["h1", "[itemprop='name']"],
    "price":       [
        "[data-price-type='finalPrice'] .price",  # Magento 2 final price
        ".price-final_price .price",              # Magento 2 alt
        ".special-price .price",                  # sale price wrapper
        ".price ins .amount",                     # WooCommerce sale
        ".price ins",
        ".price",                                 # last resort: first price on page
    ],
    "sku":         ["[itemprop='sku']", ".sku"],
    "description": ["[class*='description'] .value", "[class*='description']"],
    "brand":       ["[itemprop='brand'] [itemprop='name']", "[itemprop='brand']"],
    "images":      ["img[src*='/media/catalog/product/']", "img[data-src*='/media/catalog/product/']"],
    "breadcrumb":  ["nav a", ".breadcrumb a", ".breadcrumbs a"],
    "fitment":     [".product-fitment", ".compatibility-table", ".fitment"],
}

# ---------------------------------------------------------------------------
# Shopify CSV defaults
# ---------------------------------------------------------------------------

VARIANT_GRAMS      = 5000
VARIANT_TAXABLE    = "TRUE"     # Shopify applies VAT by customer location (configure tax regions in Shopify Admin → Taxes & duties)
PRODUCT_PUBLISHED  = "TRUE"
INVENTORY_TRACKER  = "shopify"
INVENTORY_QTY      = 1
INVENTORY_POLICY   = "deny"
FULFILLMENT        = "manual"
