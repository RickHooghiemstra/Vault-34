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

## Quick Start (Windows)

**First-time setup** (run once):
```cmd
git clone https://github.com/RickHooghiemstra/Vault-34.git
cd Vault-34
git checkout claude/scrape-motorcycle-exhausts-FHcwH
setup.bat
```

`setup.bat` installs all dependencies and creates `.env` from the example template.  
Open `.env` and set your `ANTHROPIC_API_KEY=sk-ant-...` (get one at [console.anthropic.com](https://console.anthropic.com/)).

**Every subsequent run:**
```cmd
run.bat
```

`run.bat` pulls the latest code from GitHub and runs the full scrape automatically.

> **IMPORTANT:** uitlaatstore.nl blocks all datacenter/cloud IPs.  
> Run from a **home or office internet connection**, or set `PROXY_URL` in `.env`.

> **No API key?** Run `python main.py --all-brands --skip-translate` — titles are still translated via the built-in term map, only descriptions stay in Dutch.

---

## Quick Start (macOS / Linux)

```bash
git clone https://github.com/RickHooghiemstra/Vault-34.git
cd Vault-34
git checkout claude/scrape-motorcycle-exhausts-FHcwH
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...

python3 main.py --discover --url https://www.uitlaatstore.nl/s-k6r14-hegeht1
python3 main.py --all-brands
```

---

## CLI Reference

```
python main.py --all-brands                    # scrape all 16 top brands
python main.py --brands akrapovic,arrow        # scrape specific brands
python main.py --discover --url <url>          # inspect what the parser extracts
python main.py --brands akrapovic --skip-translate   # keep Dutch descriptions
python main.py --brands akrapovic --skip-validate    # skip image validation
python main.py --from-cache logs/raw_products.json   # re-run pipeline from cache
```

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
| `fetch()` | Requests with browser headers, 2 s delay, 3 retries with back-off |
| WAF detection | Immediately aborts with clear message if blocked |

### Resuming an interrupted scrape

Just run `run.bat` (or `python main.py --all-brands`) again. Checkpoint files are saved per brand after URL discovery. If a brand's checkpoint exists, URL discovery is skipped and scraping resumes from that list.

To force a fresh discovery, delete `logs/checkpoint_{brand}.json`.

### Configurable brands

Top brands list lives in `config/brands.py → TOP_BRANDS`:

```
akrapovic, arrow, sc-project, mivv, yoshimura, leovince,
remus, gpr, termignoni, ixil, spark, zard, scorpion,
laser, racefit, austin-racing
```

---

## Transformation Workflow

### Pricing

| Step | Formula | Example (€1.014 sale price) |
|---|---|---|
| Strip Dutch VAT (21%) | `Net = Price / 1.21` | €838.02 |
| Export markup (50%) | `Export = Net × 1.50` | **€1.257,03** |

The scraper always extracts the **current selling price** (sale price when on offer, regular price otherwise). `Variant Taxable = FALSE` — no VAT charged to non-EU customers at checkout.

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

Magento cache URLs (`/media/catalog/product/cache/{hash}/...`) are automatically
stripped to their full-resolution originals before validation.

Products with **0 valid images** are written to `logs/missing_images.json` and **excluded** from the import CSV.

Skip image validation with `--skip-validate` (not recommended for production imports).

---

## Shopify Import Workflow

1. Run the pipeline: `run.bat` or `python main.py --all-brands`
2. Review `logs/qa_report.json` — check for flagged products
3. Open **Shopify Admin → Products → Import**
4. Upload `shopify_exports/shopify_import.csv`
5. Smart collections are already created in Shopify and auto-populate from tags

### Output files

| File | Description |
|---|---|
| `shopify_exports/shopify_import.csv` | Upload this to Shopify |
| `shopify_exports/image_manifest.json` | All validated image URLs per SKU |
| `logs/qa_report.json` | Per-product quality flags |
| `logs/missing_images.json` | Products excluded (no valid images) |
| `logs/failed_scrape.json` | URLs that failed after all retries |
| `logs/duplicates.json` | Deduplicated products |
| `logs/raw_products.json` | Raw scraped data before transformation |

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

DOM CSS selectors (confirmed working against uitlaatstore.nl Magento 2 structure):

```python
SELECTORS = {
    "title":       ["h1", "[itemprop='name']"],
    "price":       ["[data-price-type='finalPrice'] .price", ".price-final_price .price", ".price"],
    "sku":         ["[itemprop='sku']", ".sku"],
    "description": ["[class*='description'] .value", "[class*='description']"],
    "images":      ["img[src*='/media/catalog/product/']"],
}
```

Run `python main.py --discover --url <product_url>` to verify selectors and inspect what the parser extracts.

---

## Running Tests

```bash
python -m pytest tests/ -v
# 46 tests: fitment parsing, price math, tag generation, SEO fields
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
├── run.bat           Windows one-click scrape script
├── requirements.txt  Python dependencies
├── .env.example      Environment variable template
└── .gitignore
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `NETWORK BLOCKED` / HTTP 403 | Run from a home/office IP, or set `PROXY_URL` in `.env` |
| Binary garbage in page output | Brotli encoding issue — already fixed (Accept-Encoding: gzip, deflate) |
| `UnicodeEncodeError` on Windows | Fixed — `run.bat` sets `chcp 65001` + `PYTHONIOENCODING=utf-8` |
| `ANTHROPIC_API_KEY not set` | Add API key to `.env`, or use `--skip-translate` |
| `logs/` directory not found | Created automatically on first run |
| 0 product URLs for brand | Check the brand slug matches `/alle-merken/{slug}` on uitlaatstore.nl |
| Price shows `0.00` | Run `--discover` to inspect what the page returns for price |
| Make/model/year blank | Title regex couldn't match — check `config/makes.py MOTO_MAKES` |
| Image validation slow | Normal — each image requires a network request (~1–2 s/image) |
| `python` not found on Windows | Use the full path: `C:\Users\timme\AppData\Local\Python\bin\python3.exe` |

---

## Requirements

- Python 3.11+ (Windows: `C:\Users\timme\AppData\Local\Python\bin\python3.exe`)
- Home/office internet connection (or residential proxy)
- `ANTHROPIC_API_KEY` for English description translations (titles always translated via built-in term map)
