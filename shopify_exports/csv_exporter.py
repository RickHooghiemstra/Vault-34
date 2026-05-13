"""
Shopify CSV exporter.

Generates shopify_exports/shopify_import.csv ready for:
  Shopify Admin → Products → Import

Multi-image products are written as multiple rows (one per image)
with the product data repeated — exactly as Shopify's importer expects.
"""

import csv
import json
import logging
from pathlib import Path

from config.settings import (
    EXPORTS_DIR, VARIANT_GRAMS, VARIANT_TAXABLE, PRODUCT_PUBLISHED,
    INVENTORY_TRACKER, INVENTORY_QTY, INVENTORY_POLICY, FULFILLMENT,
)
from transformers.price import export_price, net_price, format_price
from transformers.tags import build_tags
from transformers.seo import generate_handle, seo_title, meta_description, alt_text
from transformers.translator import translate_title

log = logging.getLogger(__name__)

OUTPUT_CSV      = EXPORTS_DIR / "shopify_import.csv"
IMAGE_MANIFEST  = EXPORTS_DIR / "image_manifest.json"

# ---------------------------------------------------------------------------
# Product type resolver — derives a clean English product type from TYPE_ tags
# ---------------------------------------------------------------------------

_TYPE_TAG_TO_PRODUCT_TYPE: dict[str, str] = {
    "TYPE_SlipOn":      "Slip-On Exhaust",
    "TYPE_FullSystem":  "Full System Exhaust",
    "TYPE_Decat":       "Decat Pipe",
    "TYPE_LinkPipe":    "Link Pipe",
    "TYPE_HeaderSet":   "Header Set",
    "TYPE_DbKiller":    "Db Killer",
    "TYPE_HeatShield":  "Heat Shield",
    "TYPE_CatReplacer": "Cat Replacer",
}


def _resolve_product_type(tags: list[str]) -> str:
    """Return a clean English product type based on TYPE_ tags, or a sensible fallback."""
    for tag in tags:
        if tag in _TYPE_TAG_TO_PRODUCT_TYPE:
            return _TYPE_TAG_TO_PRODUCT_TYPE[tag]
    return "Motorcycle Exhaust"

# ---------------------------------------------------------------------------
# Shopify CSV column order
# ---------------------------------------------------------------------------

_COLUMNS = [
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
    # Informational (Shopify importer ignores unknown columns)
    "Source URL",
    "Original Price (incl. VAT)",
    "Net Price (excl. VAT)",
    "Motorcycle Make",
    "Motorcycle Model",
    "Motorcycle Year",
    "SEO Title",
    "Meta Description",
]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def export(products: list[dict]) -> Path:
    """
    Write all products to the Shopify CSV and image manifest.
    Returns the path to the generated CSV.
    """
    rows: list[dict] = []
    manifest: dict[str, list[str]] = {}
    used_handles: set[str] = set()

    for product in products:
        product_rows, img_urls = _product_to_rows(product, used_handles)
        rows.extend(product_rows)
        if img_urls:
            manifest[product.get("sku", product.get("url", ""))] = img_urls

    # Write CSV
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info("Exported %d products (%d rows) → %s", len(products), len(rows), OUTPUT_CSV)

    # Write image manifest
    IMAGE_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Image manifest → %s", IMAGE_MANIFEST)

    return OUTPUT_CSV


# ---------------------------------------------------------------------------
# Row building
# ---------------------------------------------------------------------------

def _product_to_rows(product: dict, used_handles: set[str]) -> tuple[list[dict], list[str]]:
    fitment = product.get("fitment", {})
    make    = fitment.get("make", "")
    model   = fitment.get("model", "")
    year    = fitment.get("year", "")
    brand   = product.get("brand", "")
    # Use pre-translated title if available; otherwise apply term-map on the fly
    title   = product.get("title_en") or translate_title(product.get("title", ""))

    handle      = generate_handle(title, product.get("sku", ""), used_handles)
    used_handles.add(handle)

    tags_list   = build_tags(product)
    tags_str    = ", ".join(tags_list)

    price       = format_price(export_price(product.get("price_raw", 0.0)))
    net         = format_price(net_price(product.get("price_raw", 0.0)))
    orig        = format_price(product.get("price_raw", 0.0))

    # Derive English product type from TYPE_ tags (never exposes raw Dutch breadcrumbs)
    product_type = _resolve_product_type(tags_list)
    description  = product.get("description_en") or product.get("description_nl", "")

    seo_t   = seo_title(brand, product_type, make, model, year)
    meta_d  = meta_description(title, brand, make, model)
    alt     = alt_text(brand, product_type, make, model)

    images = product.get("validated_images") or product.get("images", [])

    base_row = {
        "Handle":                     handle,
        "Title":                      title,
        "Body (HTML)":                description,
        "Vendor":                     brand or "Unknown",
        "Type":                       product_type,
        "Tags":                       tags_str,
        "Published":                  PRODUCT_PUBLISHED,
        "Option1 Name":               "Title",
        "Option1 Value":              "Default Title",
        "Variant SKU":                product.get("sku", ""),
        "Variant Grams":              str(VARIANT_GRAMS),
        "Variant Inventory Tracker":  INVENTORY_TRACKER,
        "Variant Inventory Qty":      str(INVENTORY_QTY),
        "Variant Inventory Policy":   INVENTORY_POLICY,
        "Variant Fulfillment Service": FULFILLMENT,
        "Variant Price":              price,
        "Variant Compare At Price":   "",
        "Variant Taxable":            VARIANT_TAXABLE,
        "Image Src":                  images[0] if images else "",
        "Image Position":             "1",
        "Image Alt Text":             alt,
        "Source URL":                 product.get("url", ""),
        "Original Price (incl. VAT)": orig,
        "Net Price (excl. VAT)":      net,
        "Motorcycle Make":            make,
        "Motorcycle Model":           model,
        "Motorcycle Year":            year,
        "SEO Title":                  seo_t,
        "Meta Description":           meta_d,
    }

    rows = [base_row]

    # Additional image rows (Shopify multi-image format)
    for pos, img_url in enumerate(images[1:], start=2):
        rows.append({
            "Handle":          handle,
            "Image Src":       img_url,
            "Image Position":  str(pos),
            "Image Alt Text":  alt,
        })

    return rows, images
