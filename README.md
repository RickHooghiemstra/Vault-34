# Vault-34 — Motorcycle Exhaust Catalog Pipeline

> Scrape · Translate · Validate · Export  
> Production-grade Shopify catalog builder for **uitlaatstore.nl**

---

## Project Purpose

Vault-34 is a fully automated pipeline that:

1. **Scrapes** motorcycle exhaust products from [uitlaatstore.nl](https://www.uitlaatstore.nl/) by exhaust brand
2. **Translates** Dutch product descriptions to English via Claude Haiku API
3. **Validates** all product image URLs (resolution, accessibility, no placeholders)
4. **Transforms** prices (strip 21% Dutch VAT + 50% export markup)
5. **Exports** a production-ready Shopify CSV with structured fitment tags, SEO metadata, and multi-image support

The output is a clean, scalable, SEO-friendly motorcycle exhaust catalog ready for a non-EU export Shopify store.

---

## Architecture Overview

```
uitlaatstore.nl
      │
      ▼
scrapers/uitlaatstore.py       ← URL discovery + HTML fetching + checkpoints
      │
      ▼
parsers/product_parser.py      ← JSON-LD → OpenGraph → DOM selector chain
parsers/fitment_parser.py      ← Make / Model / Year extraction + normalization
      │
      ▼
transformers/translator.py     ← Dutch → English (Claude Haiku, batched, cached)
transformers/price.py          ← VAT strip + export markup
transformers/tags.py           ← Deterministic Shopify tag generation
transformers/seo.py            ← Handle, SEO title, meta description, ALT text
      │
      ▼
shopify_exports/image_validator.py  ← HEAD + partial GET dimension validation
shopify_exports/csv_exporter.py     ← Shopify-ready CSV + image manifest
      │
      ▼
shopify_exports/shopify_import.csv  ← Import in Shopify Admin → Products → Import
```

---

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> && cd Vault-34
pip install -r requirements.txt
playwright install chromium

# 2. Configure environment
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...

# 3. Run selector discovery (first time — validates the scraper can read the site)
python main.py --discover --url https://www.uitlaatstore.nl/s-k6r14-hegeht1

# 4. Scrape top brands
python main.py --brands akrapovic,arrow,sc-project

# 5. Import into Shopify
# Shopify Admin → Products → Import → shopify_exports/shopify_import.csv
```

> **IMPORTANT:** uitlaatstore.nl blocks all datacenter/cloud IPs.  
> Run from a **home or office internet connection**, or set `PROXY_URL` in `.env`.

---

## Scraping Workflow

### Brand-first URL discovery

The scraper enumerates products by brand page (`/alle-merken/{brand}`) using
offset-based pagination (`?offset=40`, `?offset=80`, …). This gives clean,
brand-scoped crawls that can be resumed independently.

| Step | Description |
|---|---|
| `discover_product_urls()` | Paginates brand listing, collects product URLs |
| Checkpoint file | `logs/checkpoint_{brand}.json` — resume interrupted scrapes |
| `fetch()` | Requests + browser headers, 2 s delay, 3 retries with back-off |
| WAF detection | Immediately aborts with clear message if blocked |

### Configurable brands

Edit `config/brands.py → TOP_BRANDS` to add or reorder brands.  
Run all brands with `--all-brands`, or target specific ones with `--brands akrapovic,arrow`.

---

## Transformation Workflow

### Pricing

| Step | Formula | Example (€649 RRP) |
|---|---|---|
| Strip Dutch VAT (21%) | `Net = Price / 1.21` | €536.36 |
| Export markup (50%) | `Export = Net × 1.50` | **€804.55** |

`Variant Taxable = FALSE` — no VAT charged to non-EU customers at checkout.

### Fitment extraction (make / model / year)

Three-layer extraction in priority order:

1. **Fitment/compatibility table** on the product page
2. **WooCommerce product attribute table** (Merk, Model, Bouwjaar rows)
3. **Title regex** — scans against `MOTO_MAKES` list (exhaust brands deliberately excluded)

Year ranges (`2019-2023`) are expanded to individual `YEAR_2021` tags.  
Open-ended years (`2021+`) expand to all years through the current year, plus the `YEAR_2021+` exact tag.

### Tagging strategy

All tags are deterministic — generated from a fixed schema, never freeform:

| Tag format | Example | Purpose |
|---|---|---|
| `BRAND_{Name}` | `BRAND_Akrapovic` | Brand collection filter |
| `MAKE_{Name}` | `MAKE_Honda` | Motorcycle make filter |
| `MODEL_{Name}` | `MODEL_CB650R` | Motorcycle model filter |
| `YEAR_{YYYY}` | `YEAR_2021` | Year filter (expanded) |
| `TYPE_{type}` | `TYPE_SlipOn` | Exhaust type filter |
| `MAT_{material}` | `MAT_Titanium` | Material filter |
| `EURO_{n}` | `EURO_5` | Euro certification |
| `HOMOLOGATED` | — | Street-legal |
| `RACE_ONLY` | — | Non-homologated |
| `CAT_{category}` | `CAT_Slip_On_Uitlaten` | Category breadcrumb |
| `source:uitlaatstore.nl` | — | Import tracking |

---

## Translation Workflow

Descriptions are translated Dutch → English using **Claude Haiku** (`claude-haiku-4-5-20251001`):

- **Batching:** 10 descriptions per API call
- **Prompt caching:** system prompt cached (reduces cost ~90% on repeated runs)
- **Result cache:** `logs/translation_cache.json` keyed by MD5 — no re-translation on re-runs
- **Fallback:** Dutch original kept on API error (flagged in QA report)
- **HTML preservation:** tags, model numbers, specs kept verbatim

Set `ANTHROPIC_API_KEY` in `.env`. Skip translation with `--skip-translate`.

---

## Image Validation

Every image URL is validated before export:

1. `HEAD` request — must return HTTP 200 with `image/*` Content-Type
2. Content-Length check — must be > 10 KB (excludes icons and placeholders)
3. Partial GET — Pillow checks pixel dimensions ≥ 800 px on either axis
4. Path filter — skips URLs containing `/logo`, `/icon`, `/banner`, `s.w.org`, `data:`

Products with **0 valid images** are written to `logs/missing_images.json` and **excluded** from the import CSV.

Skip image validation with `--skip-validate` (not recommended for production imports).

---

## Shopify Import Workflow

1. Run the pipeline: `python main.py --brands akrapovic,arrow`
2. Review `logs/qa_report.json` — check for flagged products
3. Open **Shopify Admin → Products → Import**
4. Upload `shopify_exports/shopify_import.csv`
5. After import, create smart collections (see Collection Strategy below)

### Collection Strategy

Create Shopify smart collections using `tag = {tag_value}` rules:

| Collection | Rule |
|---|---|
| Akrapovic | `tag = BRAND_Akrapovic` |
| Honda Exhausts | `tag = MAKE_Honda` |
| Slip-On Exhausts | `tag = TYPE_SlipOn` |
| Full Systems | `tag = TYPE_FullSystem` |
| Street Legal | `tag = HOMOLOGATED` |
| Race Use Only | `tag = RACE_ONLY` |
| Euro 5 Certified | `tag = EURO_5` |

---

## Configuration

All settings in `config/settings.py` (override via `.env`):

```python
VAT_RATE = 1.21        # Dutch BTW rate
MARKUP   = 1.50        # 50% export markup

REQUEST_DELAY   = 2.0  # seconds between requests
MAX_RETRIES     = 3
REQUEST_TIMEOUT = 20

PROXY_URL = ""         # optional residential proxy
```

DOM CSS selectors (tune with `--discover`):

```python
SELECTORS = {
    "title":       ["h1.product-title", "h1[itemprop='name']", "h1"],
    "price":       [".product-price .price", "[itemprop='price']", ...],
    ...
}
```

---

## Running Tests

```bash
python -m pytest tests/ -v
# 46 tests, covers: fitment parsing, price math, tag generation, SEO fields
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (translation) | Claude API key from console.anthropic.com |
| `PROXY_URL` | No | Residential proxy URL (http://user:pass@host:port) |
| `REQUEST_DELAY` | No | Override request delay in seconds (default: 2.0) |
| `MAX_RETRIES` | No | Override max retries per URL (default: 3) |

---

## Folder Structure

```
Vault-34/
├── config/           Central configuration, brand & make normalization
├── scrapers/         URL discovery + HTML fetching
├── parsers/          Product + fitment data extraction
├── transformers/     Price, tags, SEO, translation
├── shopify_exports/  CSV exporter + image validator
├── tests/            46 pytest unit tests
├── docs/             Tagging, scraping, image, QA documentation
├── logs/             Runtime logs + QA reports (gitignored)
├── images/           Image validation cache (gitignored)
├── main.py           CLI entry point
├── requirements.txt  Python dependencies
├── .env.example      Environment variable template
└── .gitignore
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `NETWORK BLOCKED` / HTTP 403 | Run from a home/office IP, or set `PROXY_URL` in `.env` |
| `ANTHROPIC_API_KEY not set` | Add API key to `.env`, or use `--skip-translate` |
| 0 product URLs for brand | Check the brand slug matches `/alle-merken/{slug}` on uitlaatstore.nl |
| Price shows `0.00` | JSON-LD / OpenGraph / DOM selectors all missed the price — run `--discover` |
| Make/model/year blank | Title regex couldn't match — check `config/makes.py MOTO_MAKES` |
| Image validation slow | Normal — each image requires a network request. Expect ~1–2 s/image |
| `Pillow not found` | `pip install Pillow` |

---

## Requirements

- Python 3.11+
- Home/office internet connection (or residential proxy)
- `ANTHROPIC_API_KEY` for English translations
