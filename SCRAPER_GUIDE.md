# Bunkerparts.nl Exhaust Scraper

Scrapes exhaust products from [bunkerparts.nl](https://bunkerparts.nl/uitlaten/),
applies non-EU export pricing, and exports a Shopify-ready CSV.

## Pricing logic

| Step | Formula |
|------|---------|
| Strip Dutch VAT (21%) | `Net Price = Original Price / 1.21` |
| Export markup (30%) | `Final Price = Net Price × 1.30` |

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # optional – only for JS-protected pages
```

## Run

```bash
# Standard mode (requests + BeautifulSoup)
python scraper.py

# Playwright mode (headless browser – use when standard mode gets blocked)
python scraper.py --playwright
```

Output: **`shopify_import.csv`** — ready for **Products → Import** in your Shopify admin.

## Shopify CSV columns

| Column | Value |
|--------|-------|
| Handle | Auto-generated from title |
| Vendor | Akrapovič |
| Variant Grams | 5000 |
| Variant Inventory Tracker | shopify |
| Variant Inventory Qty | 1 |
| Variant Inventory Policy | deny |
| Variant Fulfillment Service | manual |
| Variant Taxable | FALSE (non-EU export) |
| Tags | Breadcrumb categories + `source:bunkerparts.nl` |

Extra columns `Source URL`, `Original Price (incl. VAT)`, and `Net Price (excl. VAT)`
are appended after the standard Shopify columns for internal reference — Shopify's
importer ignores unknown columns.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| All requests return 403 | Run with `--playwright` |
| 0 products found | Check `CATEGORY_PATHS` in `scraper.py` — the shop may have changed its URL structure |
| Price shows 0.00 | The price HTML selector needs updating; inspect the product page and adjust `parse_product()` |
