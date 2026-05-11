# Vault-34 — Motorcycle Exhaust Scraper & Shopify Exporter

Scrapes **all exhaust products** from [bunkerparts.nl](https://bunkerparts.nl/uitlaten/), applies non-EU export pricing, and generates a Shopify-ready CSV with structured filters for motorcycle make, model, and year.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Run
python scraper.py --playwright

# Output: shopify_import.csv
```

---

## How It Works

### 1. Scraping

The scraper targets the exhaust (`/uitlaten/`) category on bunkerparts.nl and walks every pagination page, then visits each individual product page to collect:

| Field | Source |
|---|---|
| Product title | `<h1>` on product page |
| SKU / part number | WooCommerce `.sku` element |
| Original price (incl. 21% Dutch VAT) | WooCommerce price block |
| Product description | Short description or description tab |
| Product image | WooCommerce gallery (full-size) |
| Exhaust brand | Product attributes table → fallback to title |
| Motorcycle make | Product attributes table → fallback to title regex |
| Motorcycle model | Product attributes table → fallback to title regex |
| Motorcycle year | Product attributes table → fallback to title regex |
| Source URL | Product page URL |

**Two fetch modes — automatically selected:**

| Mode | When used |
|---|---|
| `requests` + BeautifulSoup | Default — fast, no browser needed |
| Playwright (headless Chromium) | Auto-fallback if site returns 403; force with `--playwright` |

The scraper uses browser-like headers, polite request delays (1.5 s), and up to 3 retries per URL with exponential back-off.

---

### 2. Pricing Engine (Non-EU Export Logic)

| Step | Formula | Example (€649 RRP) |
|---|---|---|
| Strip Dutch VAT (21%) | `Net = Price / 1.21` | €536.36 |
| Apply export markup (50%) | `Export = Net × 1.50` | **€804.55** |

`Variant Taxable` is set to `FALSE` — products are sold to non-EU customers with no VAT applied at checkout.

---

### 3. Shopify CSV

Generated file: **`shopify_import.csv`**

Import via **Shopify Admin → Products → Import**.

#### Standard Shopify columns

| Column | Value |
|---|---|
| Handle | Auto-generated URL slug from title |
| Vendor | Exhaust brand (Akrapovič, Arrow, SC-Project, …) |
| Type | Category from breadcrumb (Slip-On Uitlaten, etc.) |
| Tags | See filter tags below |
| Published | TRUE |
| Option1 Name / Value | Title / Default Title |
| Variant Grams | 5000 (5 kg default) |
| Variant Inventory Tracker | shopify |
| Variant Inventory Qty | 1 |
| Variant Inventory Policy | deny |
| Variant Fulfillment Service | manual |
| Variant Price | Calculated export price |
| Variant Taxable | FALSE |

#### Informational columns (ignored by Shopify importer)

| Column | Purpose |
|---|---|
| Source URL | Link back to original bunkerparts.nl listing |
| Original Price (incl. VAT) | Dutch retail price for reference |
| Net Price (excl. VAT) | Price after VAT removal, before markup |
| Motorcycle Make | Honda, Yamaha, Kawasaki, … |
| Motorcycle Model | CB650R, MT-09, Z900, … |
| Motorcycle Year | 2019-2023, 2021+, … |

---

### 4. Shopify Filter Tags

Every product gets structured tags that power Shopify's native storefront collection filters:

```
make:Honda, model:CB650R, year:2019, year:2020, year:2021, year:2022, year:2023,
brand:Akrapovič, Slip-On Uitlaten, source:bunkerparts.nl
```

Year ranges (`2019-2023`) are **expanded into individual year tags** so a customer filtering on `year:2021` correctly matches any product that covers that year.

**To enable the filters in Shopify:**
1. Go to **Online Store → Navigation → Collections**
2. Open your exhaust collection → **Filters**
3. Add filter groups: `make`, `model`, `year`, `brand`
4. These map directly to the tag prefixes written by the scraper

---

## Market Competitiveness

Pricing was benchmarked against US, UK, Australian, and Japanese retail (May 2026):

| Brand | 🇺🇸 US | 🇬🇧 UK | 🇦🇺 AU | 🇯🇵 JP |
|---|---|---|---|---|
| Akrapovič (slip-on) | ✅ Competitive | ✅ Competitive | ✅ Competitive | ✅ Competitive |
| Akrapovič (full system) | ✅ Competitive | ✅ Competitive | ✅ Competitive | ✅ Competitive |
| Arrow | ✅ Best value | ✅ Best value | ✅ Best value | ✅ Best value |
| SC-Project | ⚠️ Borderline | ⚠️ Borderline | ⚠️ Borderline | ✅ Competitive |
| LeoVince | ⚠️ Above market | ⚠️ Above market | ⚠️ Above market | ⚠️ Borderline |

> Arrow and Akrapovič are the strongest export opportunity — their Dutch retail prices are below typical US/UK/AU MSRP even after the 50% markup. LeoVince is a value brand globally; consider a lower markup (30–35%) for that brand specifically.

---

## Configuration

All settings are at the top of `scraper.py`:

```python
VAT_RATE = 1.21    # Dutch VAT rate
MARKUP   = 1.50    # Export markup (50%)

REQUEST_DELAY   = 1.5   # Seconds between requests (be polite)
MAX_RETRIES     = 3     # Retries per URL before skipping
REQUEST_TIMEOUT = 20    # Seconds before a request times out
```

---

## Files

| File | Description |
|---|---|
| `scraper.py` | Main script — scraper, pricing engine, CSV exporter |
| `requirements.txt` | Python dependencies |
| `shopify_import_example.csv` | Example output with 8 sample products |
| `shopify_import.csv` | Generated after running the scraper (gitignored) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `HTTP 403` on all requests | Run with `--playwright` flag |
| `NETWORK BLOCKED` error | Sandbox/firewall is blocking outbound connections — run on a machine with open internet |
| 0 products collected | The shop may have changed its URL structure — check `CATEGORY_PATHS` in `scraper.py` |
| Price shows `0.00` | Price selector needs updating — inspect the product page and adjust `parse_product()` |
| Make/model/year blank | Product page has no attribute table — the title regex fallback will still attempt extraction |
| Playwright not found | Run `playwright install chromium` |

---

## Requirements

- Python 3.11+
- `requests`, `beautifulsoup4`, `lxml` (always required)
- `playwright` + Chromium (only needed for JS-protected pages)
