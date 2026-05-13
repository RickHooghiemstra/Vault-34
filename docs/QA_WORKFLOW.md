# QA Workflow

## Pre-Import Checklist

Run the pipeline and check these files before importing to Shopify:

### 1. `logs/qa_report.json`

Lists all products with data quality flags:

| Flag | Meaning | Action |
|---|---|---|
| `missing_sku` | No SKU extracted | Check product page — may need DOM selector update |
| `missing_brand` | Brand not identified | Update `config/brands.py BRAND_NORM` |
| `missing_make` | Motorcycle make blank | Title regex failed — check `config/makes.py` |
| `missing_model` | Model blank | Normal for generic products (e.g. universal parts) |
| `missing_year` | Year blank | Normal for universal/bracket products |
| `translation_failed` | Dutch description kept | Claude API error — retry or translate manually |
| `no_valid_images` | Product excluded from import | Source images manually |
| `zero_price` | Price not extracted | Critical — selector needs fixing |

### 2. `logs/missing_images.json`

Products with 0 valid images, excluded from import.  
For each: check the source URL, find alternative image sources, then add manually in Shopify Admin.

### 3. `logs/duplicates.json`

Products deduplicated by SKU or URL. Review if any look like genuine separate products.

### 4. `logs/failed_scrape.json`

URLs that failed after all retries. May indicate temporary downtime — retry these.

### 5. `shopify_exports/image_manifest.json`

All validated image URLs per product SKU. Use this to audit image counts.

## Import Validation

After importing the CSV to Shopify:

1. **Check product count** — should match `Done! N products` from the pipeline output
2. **Browse 5–10 random products** — verify title, images, price, and tags display correctly
3. **Test collection filters** — search by `MAKE_Honda`, `TYPE_SlipOn`, etc.
4. **Check a fitment example** — product with `YEAR_2021` should appear when filtering by year 2021

## Running Tests

```bash
python -m pytest tests/ -v
```

All 46 tests must pass before a production scrape run.
