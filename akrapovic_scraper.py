"""
Akrapovič Dutch Market Scraper & Shopify Export Tool
Simulates scraping top 100 best-selling Akrapovič exhausts from Dutch retailers,
applies non-EU export pricing, and exports a Shopify-compatible CSV.
"""

import csv
import re
import random
from dataclasses import dataclass, field
from typing import Optional
from slugify import slugify  # pip install python-slugify


VAT_RATE = 1.21
MARKUP_RATE = 1.30
DEFAULT_WEIGHT_GRAMS = 5000
OUTPUT_FILE = "shopify_import.csv"

SHOPIFY_COLUMNS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags",
    "Published", "Option1 Name", "Option1 Value",
    "Variant SKU", "Variant Grams", "Variant Inventory Tracker",
    "Variant Inventory Qty", "Variant Inventory Policy",
    "Variant Fulfillment Service", "Variant Price", "Variant Taxable",
    "Image Src",
]


@dataclass
class Product:
    title: str
    sku: str
    original_price: float   # incl. 21% Dutch VAT
    source_url: str
    source_shop: str
    description: str
    image_src: str = ""
    product_type: str = "Exhaust System"
    tags: list = field(default_factory=list)

    @property
    def net_price(self) -> float:
        """Strip Dutch VAT."""
        return self.original_price / VAT_RATE

    @property
    def export_price(self) -> float:
        """Net price + 30% markup, rounded to 2dp."""
        return round(self.net_price * MARKUP_RATE, 2)

    @property
    def handle(self) -> str:
        return slugify(self.title)

    @property
    def all_tags(self) -> str:
        base = ["Akrapovic", "exhaust", "motorcycle", self.source_shop] + self.tags
        return ", ".join(dict.fromkeys(t for t in base if t))  # deduplicate, preserve order

    def to_shopify_row(self) -> dict:
        return {
            "Handle": self.handle,
            "Title": self.title,
            "Body (HTML)": self.description,
            "Vendor": "Akrapovič",
            "Type": self.product_type,
            "Tags": self.all_tags,
            "Published": "TRUE",
            "Option1 Name": "Title",
            "Option1 Value": "Default Title",
            "Variant SKU": self.sku,
            "Variant Grams": DEFAULT_WEIGHT_GRAMS,
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": 1,
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Variant Price": f"{self.export_price:.2f}",
            "Variant Taxable": "FALSE",
            "Image Src": self.image_src,
        }


# ---------------------------------------------------------------------------
# Simulated product catalogue
# Real implementation: replace each scrape_* function with HTTP requests
# using requests + BeautifulSoup (or Playwright for JS-heavy sites).
# ---------------------------------------------------------------------------

_BIKE_MODELS = [
    ("Honda CBR1000RR-R Fireblade", "CBR1000RR-R", "sport"),
    ("Honda CB650R", "CB650R", "naked"),
    ("Yamaha MT-09", "MT09", "naked"),
    ("Yamaha YZF-R1", "YZF-R1", "sport"),
    ("Yamaha YZF-R6", "YZF-R6", "sport"),
    ("Kawasaki Z900", "Z900", "naked"),
    ("Kawasaki ZX-10R", "ZX10R", "sport"),
    ("Kawasaki Z650", "Z650", "naked"),
    ("Suzuki GSX-R1000", "GSX-R1000", "sport"),
    ("Suzuki GSX-S750", "GSX-S750", "naked"),
    ("BMW S1000RR", "S1000RR", "sport"),
    ("BMW S1000R", "S1000R", "naked"),
    ("BMW R1250GS", "R1250GS", "adventure"),
    ("Ducati Panigale V4", "PanV4", "sport"),
    ("Ducati Monster 937", "Monster937", "naked"),
    ("KTM 1290 Super Duke R", "1290SDR", "naked"),
    ("KTM 890 Duke", "890Duke", "naked"),
    ("Triumph Street Triple RS", "StrTriRS", "naked"),
    ("Triumph Tiger 900", "Tiger900", "adventure"),
    ("Aprilia RSV4", "RSV4", "sport"),
]

_SYSTEM_TYPES = [
    ("Full System Titanium", "FS-TI", 1_299.0, 1_599.0),
    ("Slip-On Line Titanium", "SL-TI", 499.0, 799.0),
    ("Slip-On Line Carbon", "SL-CA", 549.0, 849.0),
    ("Evolution Full System Titanium", "EVO-TI", 1_499.0, 1_899.0),
    ("Racing Full System Titanium", "RACE-TI", 1_699.0, 2_199.0),
]

_YEARS = ["2020", "2021", "2022", "2023", "2024"]


def _build_sku(model_code: str, sys_code: str, year: str) -> str:
    return f"AKR-{model_code}-{sys_code}-{year}"


def _build_description(title: str, bike: str, sys_type: str, year: str, shop: str) -> str:
    return (
        f"<p><strong>{title}</strong></p>"
        f"<p>Factory original Akrapovič {sys_type} for the {year} {bike}. "
        "Manufactured from aerospace-grade materials with precision TIG welding. "
        "Includes all mounting hardware and conical silencer end cap. "
        "Homologated for road use (ECE approval where applicable).</p>"
        f"<p><em>Source: {shop}</em></p>"
    )


def _generate_catalogue() -> list[Product]:
    """Generate a deterministic simulated catalogue of 100+ products."""
    random.seed(42)
    products: list[Product] = []

    shops = [
        ("NR1 Motor", "https://www.nr1motor.nl/exhausts/akrapovic/"),
        ("Ten Kate Shop", "https://www.tenkate-shop.nl/akrapovic/"),
        ("Bunkerparts", "https://www.bunkerparts.nl/akrapovic-uitlaat/"),
    ]

    for bike_name, bike_code, _ in _BIKE_MODELS:
        for sys_name, sys_code, price_lo, price_hi in _SYSTEM_TYPES:
            year = random.choice(_YEARS)
            price = round(random.uniform(price_lo, price_hi), 2)
            shop_name, shop_base_url = random.choice(shops)
            sku = _build_sku(bike_code, sys_code, year)
            title = f"Akrapovič {sys_name} – {bike_name} ({year})"
            url = f"{shop_base_url}{sku.lower()}/"

            p = Product(
                title=title,
                sku=sku,
                original_price=price,
                source_url=url,
                source_shop=shop_name,
                description=_build_description(title, bike_name, sys_name, year, shop_name),
                image_src="",  # populated by real scraper
                tags=[bike_name, bike_code, year, sys_name.split()[0]],
            )
            products.append(p)

            if len(products) >= 130:  # overshoot so dedup can trim to 100
                break
        if len(products) >= 130:
            break

    return products


# ---------------------------------------------------------------------------
# Scraper stubs – replace with real HTTP scraping logic
# ---------------------------------------------------------------------------

def scrape_nr1motor(limit: int = 50) -> list[Product]:
    """
    TODO (real implementation):
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 ..."})
        for page in paginate("https://www.nr1motor.nl/exhausts/akrapovic/", limit):
            soup = BeautifulSoup(session.get(page).text, "html.parser")
            for card in soup.select(".product-card"):
                yield Product(title=card.select_one("h2").text, ...)
    """
    return _generate_catalogue()[:limit]


def scrape_tenkate(limit: int = 50) -> list[Product]:
    """Simulated Ten Kate Shop scrape."""
    catalogue = _generate_catalogue()
    # Simulate partial price overlap with slightly different prices
    for p in catalogue:
        if random.random() < 0.3:
            p.original_price = round(p.original_price * random.uniform(0.95, 1.05), 2)
            p.source_shop = "Ten Kate Shop"
            p.source_url = f"https://www.tenkate-shop.nl/akrapovic/{p.sku.lower()}/"
    return catalogue[:limit]


def scrape_bunkerparts(limit: int = 50) -> list[Product]:
    """Simulated Bunkerparts scrape."""
    catalogue = _generate_catalogue()
    for p in catalogue:
        if random.random() < 0.25:
            p.original_price = round(p.original_price * random.uniform(0.92, 1.08), 2)
            p.source_shop = "Bunkerparts"
            p.source_url = f"https://www.bunkerparts.nl/akrapovic-uitlaat/{p.sku.lower()}/"
    return catalogue[10:limit + 10]


# ---------------------------------------------------------------------------
# Deduplication: keep lowest original price per SKU
# ---------------------------------------------------------------------------

def deduplicate_best_price(products: list[Product]) -> list[Product]:
    best: dict[str, Product] = {}
    for p in products:
        if p.sku not in best or p.original_price < best[p.sku].original_price:
            best[p.sku] = p
    return list(best.values())


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_shopify_csv(products: list[Product], path: str = OUTPUT_FILE) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SHOPIFY_COLUMNS)
        writer.writeheader()
        for p in products:
            writer.writerow(p.to_shopify_row())
    print(f"Exported {len(products)} products to {path}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    print("Scraping NR1 Motor …")
    nr1_products = scrape_nr1motor(limit=50)

    print("Scraping Ten Kate Shop …")
    tenkate_products = scrape_tenkate(limit=50)

    print("Scraping Bunkerparts …")
    bunker_products = scrape_bunkerparts(limit=50)

    all_products = nr1_products + tenkate_products + bunker_products
    print(f"Total scraped (pre-dedup): {len(all_products)}")

    unique_products = deduplicate_best_price(all_products)
    print(f"Unique SKUs after best-price dedup: {len(unique_products)}")

    # Trim to top 100 (already sorted by first-seen order; adapt sort key as needed)
    top100 = unique_products[:100]
    print(f"Exporting top {len(top100)} products …")

    export_shopify_csv(top100)

    # Quick price audit
    print("\nSample pricing (first 5 rows):")
    print(f"{'Title':<55} {'Orig (€)':>10} {'Net (€)':>10} {'Export (€)':>12}")
    print("-" * 92)
    for p in top100[:5]:
        print(f"{p.title:<55} {p.original_price:>10.2f} {p.net_price:>10.2f} {p.export_price:>12.2f}")


if __name__ == "__main__":
    main()
