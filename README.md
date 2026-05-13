# Vault-34 — Motorcycle Exhaust Catalog Pipeline

> Scrape · Price · Translate · Validate · Export  
> Production-grade Shopify catalog builder for **uitlaatstore.nl** with competitor-aware pricing

---

## Project Purpose

Vault-34 is a fully automated pipeline that:

1. **Scrapes** motorcycle exhaust products from [uitlaatstore.nl](https://www.uitlaatstore.nl/) by exhaust brand
2. **Scrapes competitors** — fetches live prices from rival Shopify stores via `/products.json`
3. **Prices intelligently** — targets the 60th percentile of confirmed competitor prices; falls back to flat 50% markup when data is thin
4. **Translates** Dutch product descriptions to English via Claude Haiku API
5. **Validates** all product image URLs (resolution, accessibility, no placeholders) and **downloads** every image locally
6. **Exports** a production-ready Shopify CSV with structured fitment tags, SEO metadata, competitor pricing columns, and multi-image support

The output is a clean, scalable, SEO-friendly motorcycle exhaust catalog ready for a non-EU export Shopify store.

---

## Architecture Overview

```
uitlaatstore.nl                        competitors (config/competitors.yaml)
      │                                          │
      ▼                                          ▼
scrapers/uitlaatstore.py       competitor_intel/scrapers/shopify_json.py
      │                                          │
      ▼                                          ▼
parsers/product_parser.py      competitor_intel/matchers/product_matcher.py
parsers/fitment_parser.py           (SKU exact + RapidFuzz fuzzy match)
      │                                          │
      └─────────────────────┬────────────────────┘
                            ▼
                  pricing/fx.py  (ECB EUR rates, daily cache)
                  pricing/engine.py  (p60 competitor price, clamp, floor, round)
                            │
                            ▼
transformers/translator.py     ← Dutch → English (Claude Haiku, batched, cached)
transformers/tags.py           ← Deterministic Shopify tag generation (all English)
transformers/seo.py            ← Handle, SEO title, meta description, ALT text
                            │
                            ▼
shopify_exports/image_validator.py  ← HEAD + partial GET validation + full download
shopify_exports/csv_exporter.py     ← Shopify-ready CSV + image manifest
                            │
                            ▼
shopify_exports/shopify_import.csv  ← Import in Shopify Admin → Products → Import
images/{sku}/               ← All product images saved to disk
logs/pricing_report.json    ← Full per-product pricing breakdown (JSON)
logs/competitor_audit.csv   ← Flat competitor research spreadsheet
```

---

## Quick Start (Windows)

**First-time setup** (run once):
```cmd
git clone https://github.com/RickHooghiemstra/Vault-34-Scraper.git
cd Vault-34-Scraper
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
git clone https://github.com/RickHooghiemstra/Vault-34-Scraper.git
cd Vault-34-Scraper
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...

python3 main.py --discover --url https://www.uitlaatstore.nl/s-k6r14-hegeht1
python3 main.py --all-brands
```

---

## CLI Reference

```
python main.py --all-brands                          # full pipeline: scrape + price + export
python main.py --brands akrapovic,arrow              # specific brands only
python main.py --discover --url <url>                # inspect what the parser extracts
python main.py --brands akrapovic --skip-translate   # keep Dutch descriptions
python main.py --brands akrapovic --skip-validate    # skip image validation
python main.py --brands akrapovic --skip-pricing     # flat 50% markup, no competitor scrape
python main.py --pricing-only                        # re-price from cached raw_products.json
python main.py --from-cache logs/raw_products.json   # re-run full pipeline from cache
```

---

## Pipeline Steps & When They Run

| Step | Default | `--skip-pricing` | `--pricing-only` | Output |
|---|---|---|---|---|
| Scrape uitlaatstore | ✓ | ✓ | — | `logs/raw_products.json` |
| Deduplicate / clean | ✓ | ✓ | — | — |
| Translate (Dutch→EN) | ✓ | ✓ | — | `logs/translation_cache.json` |
| Validate images | ✓ | ✓ | — | `logs/missing_images.json` |
| Download images | ✓ | ✓ | ✓ | `images/{sku}/` |
| Scrape competitors | ✓ | — | ✓ | _(in-memory)_ |
| Competitor matching | ✓ | — | ✓ | _(in-memory)_ |
| Pricing engine | ✓ | — | ✓ | `logs/pricing_report.json`, `logs/competitor_audit.csv` |
| Export Shopify CSV | ✓ | ✓ | ✓ | `shopify_exports/shopify_import.csv` |

---

## Competitor Pricing

### How it works

After uitlaatstore scraping is complete, the pricing engine runs automatically:

1. **Scrapes competitors** — fetches all products from each store in `config/competitors.yaml` via their Shopify `/products.json` endpoint (no browser required, pure HTTP + pagination). 2-second delay between requests, max 3 retries. Any store returning 403/429/451 is skipped automatically.

2. **Matches products** — for each of our products, searches every competitor catalog:
   - **SKU exact match** (case-insensitive) → confidence 1.0
   - **RapidFuzz `token_sort_ratio`** on `brand + title` vs `vendor + title` → confidence 0.0–1.0
   - Only matches with confidence ≥ 0.75 are used

3. **Converts currencies** — fetches the ECB daily EUR FX XML feed; converts non-EUR prices (e.g. GBP) to EUR. Cached in `logs/fx_rates.json`, refreshed once per calendar day.

4. **Computes price**:

| Situation | Price formula | Notes |
|---|---|---|
| ≥ 2 competitor matches | 60th percentile of competitor prices | Targets competitive market position |
| Clamped to margin band | `max(net×1.35, min(net×1.80, p60))` | Protects minimum and maximum margin |
| Hard floor always applied | `max(price, net×1.20)` | Never sells below 20% margin |
| < 2 competitor matches | `net × 1.50` | Default markup; logged as fallback |
| Final rounding | Nearest €0.95 | e.g. 99.95, 149.95, 724.95 |

Where `net = uitlaatstore_price / 1.21` (strip Dutch 21% VAT).

### Adding or removing competitors

Edit `config/competitors.yaml`:

```yaml
competitors:
  - domain: www.fc-moto.de
    name: FC-Moto DE
    market: EU
    currency: EUR
    includes_vat: true

  - domain: www.holeshot.co.uk
    name: Holeshot UK
    market: GB
    currency: GBP
    includes_vat: true
```

Five starter competitors are included. The scraper skips any store that blocks access.

### Pricing output files

**`logs/pricing_report.json`** — one entry per product with the full pricing breakdown:

```json
{
  "sku": "S-H10SO3-HRC",
  "title": "Akrapovic Slip-On Honda CB650R",
  "url": "https://www.uitlaatstore.nl/...",
  "net_cost": 536.36,
  "old_price": 804.95,
  "new_price": 749.95,
  "margin_pct": 39.8,
  "method": "competitor",
  "p60": 738.50,
  "min_clamp": 724.09,
  "max_clamp": 965.45,
  "competitor_prices": [720.0, 765.0, 710.0],
  "competitor_meta": [
    {
      "name": "Motea EU",
      "domain": "www.motea.com",
      "title": "Akrapovic Slip-On Honda CB650R 2021",
      "price_eur": 720.0,
      "confidence": 0.94
    },
    {
      "name": "FC-Moto DE",
      "domain": "www.fc-moto.de",
      "title": "Akrapovic Honda CB650R Slip-On",
      "price_eur": 765.0,
      "confidence": 0.91
    }
  ]
}
```

**`logs/competitor_audit.csv`** — flat spreadsheet, one row per product-competitor match. Open in Excel or Google Sheets for a full research view, sortable by confidence, margin, or competitor:

| Column | Description |
|---|---|
| SKU | Product SKU |
| Title | Our product title |
| URL | Source URL on uitlaatstore.nl |
| Net Cost (EUR) | Ex-VAT cost (uitlaatstore price ÷ 1.21) |
| Old Price (EUR) | What the flat 50% markup would have given |
| New Price (EUR) | Final competitor-informed price |
| Margin % | `(new_price − net_cost) / net_cost × 100` |
| Pricing Method | `competitor` or `default` |
| P60 Price (EUR) | 60th percentile of competitor prices (blank if < 2 matches) |
| Min Clamp (EUR) | Lower bound `net × 1.35` |
| Max Clamp (EUR) | Upper bound `net × 1.80` |
| Competitor Name | Display name from competitors.yaml |
| Competitor Domain | Store domain |
| Competitor Matched Title | Title of the matched product on that store |
| Competitor Price (EUR) | Ex-VAT EUR price from that store |
| Match Confidence | 0.75–1.0 (1.0 = SKU exact match) |

Products with no competitor matches appear as a single row with empty competitor columns and `method = default`.

The **Shopify CSV** also includes two summary columns: **Competitor Price (EUR)** (average of all matched prices) and **Margin %**.

### Pricing-only mode

Re-price an existing catalog without re-scraping uitlaatstore:

```bash
python main.py --pricing-only
```

Reads `logs/raw_products.json` (from a previous full run), fetches fresh competitor prices and FX rates, and exports a new CSV + audit files.

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

Top brands list lives in `config/brands.py → TOP_BRANDS`.

---

## Transformation Workflow

### Pricing

| Step | Formula | Example (€649 retail price) |
|---|---|---|
| Strip Dutch VAT (21%) | `Net = Price / 1.21` | €536.36 |
| Competitor p60 target | from matched competitor prices | e.g. €738.50 |
| Clamp to margin band | `[net × 1.35, net × 1.80]` | €724.09 – €965.45 |
| Hard floor | `max(price, net × 1.20)` | ≥ €643.63 |
| Round to €0.95 | nearest .95 | **€749.95** |

With `--skip-pricing`, the formula is simply `net × 1.50` rounded to €0.95.

### Fitment extraction (make / model / year)

Three-layer extraction in priority order:

1. **Fitment/compatibility table** on the product page
2. **WooCommerce product attribute table** (Merk, Model, Bouwjaar rows)
3. **Title regex** — scans against `MOTO_MAKES` list (exhaust brands deliberately excluded)

Year ranges (`2019-2023`) are expanded to individual `YEAR_2021` tags.  
Open-ended years (`2021+`) expand to all years through the current year, plus the `YEAR_2021+` exact tag.

### Tagging strategy

All tags are deterministic — generated from a fixed schema, always in English:

| Tag format | Example | Purpose |
|---|---|---|
| `BRAND_{Name}` | `BRAND_Akrapovic` | Brand collection filter |
| `MAKE_{Name}` | `MAKE_Honda` | Motorcycle make filter |
| `MODEL_{Name}` | `MODEL_CB650R` | Motorcycle model filter |
| `YEAR_{YYYY}` | `YEAR_2021` | Year filter (expanded from ranges) |
| `TYPE_{type}` | `TYPE_SlipOn` | Exhaust type filter |
| `MAT_{material}` | `MAT_Titanium` | Material filter |
| `EURO_{n}` | `EURO_5` | Euro certification |
| `HOMOLOGATED` | — | Street-legal |
| `RACE_ONLY` | — | Non-homologated |
| `CAT_{type}` | `CAT_SlipOn` | Category (derived from TYPE_, always English) |
| `source:uitlaatstore.nl` | — | Import tracking |

---

## Translation Workflow

Descriptions are translated Dutch → English using **Claude Haiku** (`claude-haiku-4-5-20251001`):

- **Batching:** 10 descriptions per API call
- **Prompt caching:** system prompt cached (reduces cost ~90% on repeated runs)
- **Result cache:** `logs/translation_cache.json` keyed by MD5 — no re-translation on re-runs
- **Fallback:** Dutch original kept on API error (flagged in QA report)
- **HTML preservation:** tags, model numbers, specs kept verbatim
- **Titles:** always translated via built-in Dutch → English term map (no API cost)

Set `ANTHROPIC_API_KEY` in `.env`. Skip translation with `--skip-translate`.

---

## Image Validation & Download

Every image URL is validated before export:

1. `HEAD` request — must return HTTP 200 with `image/*` Content-Type
2. Content-Length check — must be > 10 KB (excludes icons and placeholders)
3. Partial GET — Pillow checks pixel dimensions ≥ 800 px on either axis
4. Path filter — skips URLs containing `/logo`, `/icon`, `/banner`, `s.w.org`, `data:`

After validation, **all valid images are downloaded** to `images/{sku}/01.jpg`, `02.jpg`, … providing a permanent local copy of the full catalog imagery. Files already on disk are skipped (acts as a cache).

Magento cache URLs (`/media/catalog/product/cache/{hash}/...`) are automatically
stripped to their full-resolution originals before validation.

Products with **0 valid images** are written to `logs/missing_images.json` and **excluded** from the import CSV.

Skip validation with `--skip-validate` (images are still downloaded from the unvalidated URL list).

---

## Shopify Import Workflow

1. Run the pipeline: `run.bat` or `python main.py --all-brands`
2. Review `logs/qa_report.json` — check for flagged products
3. Review `logs/competitor_audit.csv` — verify pricing decisions
4. Open **Shopify Admin → Products → Import**
5. Upload `shopify_exports/shopify_import.csv`
6. Smart collections auto-populate from tags

### Output files

| File | When created | Description |
|---|---|---|
| `shopify_exports/shopify_import.csv` | Every run | Upload this to Shopify |
| `shopify_exports/image_manifest.json` | Every run | All image URLs per SKU |
| `images/{sku}/` | Every run | Downloaded product images (local copy) |
| `logs/pricing_report.json` | When pricing runs | Full per-product pricing breakdown (JSON) |
| `logs/competitor_audit.csv` | When pricing runs | Flat competitor research spreadsheet |
| `logs/fx_rates.json` | When pricing runs | ECB FX rates cache (refreshed daily) |
| `logs/qa_report.json` | Every run | Per-product quality flags |
| `logs/missing_images.json` | When images fail | Products excluded (no valid images) |
| `logs/failed_scrape.json` | Every scrape | URLs that failed after all retries |
| `logs/duplicates.json` | Every scrape | Deduplicated products |
| `logs/raw_products.json` | Every scrape | Raw scraped data (used by `--pricing-only`) |
| `logs/translation_cache.json` | When translating | MD5-keyed translation cache |

---

## Configuration

All settings in `config/settings.py` (override via `.env`):

```python
VAT_RATE = 1.21        # Dutch BTW rate
MARKUP   = 1.50        # fallback markup when < 2 competitor prices

REQUEST_DELAY   = 2.0  # seconds between requests
MAX_RETRIES     = 3
REQUEST_TIMEOUT = 20

PROXY_URL = ""         # optional residential proxy
```

Competitor stores: `config/competitors.yaml` — see Competitor Pricing section above.

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

Run `python main.py --discover --url <product_url>` to verify selectors.

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
Vault-34-Scraper/
├── config/
│   ├── settings.py          Central configuration
│   ├── brands.py            Exhaust brand list + normalization
│   ├── makes.py             Motorcycle make list + normalization
│   └── competitors.yaml     Competitor Shopify stores for price research
├── scrapers/
│   └── uitlaatstore.py      URL discovery + HTML fetching + checkpoints
├── parsers/
│   ├── product_parser.py    JSON-LD → OpenGraph → DOM extraction
│   └── fitment_parser.py    Make / Model / Year extraction
├── transformers/
│   ├── price.py             VAT strip + markup
│   ├── translator.py        Dutch → English (Claude Haiku, cached)
│   ├── tags.py              Deterministic Shopify tag generation
│   ├── seo.py               Handle, SEO title, meta description, ALT text
│   └── cleaner.py           Strip competitor branding from descriptions
├── competitor_intel/
│   ├── scrapers/
│   │   └── shopify_json.py  Scrape rival Shopify stores via /products.json
│   └── matchers/
│       └── product_matcher.py  SKU exact + RapidFuzz fuzzy matching (≥0.75)
├── pricing/
│   ├── engine.py            p60 pricing, clamp [net×1.35, net×1.80], floor net×1.20
│   └── fx.py                ECB EUR FX rates (daily cache)
├── shopify_exports/
│   ├── csv_exporter.py      Shopify CSV + image manifest
│   └── image_validator.py   Validate + download all product images
├── tests/                   46 pytest unit tests
├── docs/                    Tagging, scraping, image, QA documentation
├── logs/                    Runtime logs + reports (gitignored)
├── images/                  Downloaded product images — images/{sku}/ (gitignored)
├── main.py                  CLI entry point
├── run.bat                  Windows one-click scrape script
├── requirements.txt         Python dependencies
└── .env.example             Environment variable template
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `NETWORK BLOCKED` / HTTP 403 on uitlaatstore | Run from a home/office IP, or set `PROXY_URL` in `.env` |
| Competitor returns 403/429 | Expected — skipped automatically, pipeline continues |
| ECB FX fetch fails | Stale cache is used; run again later for fresh rates |
| `ANTHROPIC_API_KEY not set` | Add key to `.env`, or use `--skip-translate` |
| All products use `method: default` | Competitor SKUs don't match — check fuzzy match confidence in `competitor_audit.csv` |
| `--pricing-only` fails | Run a full scrape first to generate `logs/raw_products.json` |
| Price shows `0.00` | Run `--discover` to inspect what the page returns for price |
| Make/model/year blank | Title regex couldn't match — check `config/makes.py` |
| Image validation slow | Normal — each image requires a HEAD + partial GET (~1–2 s/image) |
| `UnicodeEncodeError` on Windows | Run `run.bat` — it sets `chcp 65001` + `PYTHONIOENCODING=utf-8` |

---

## Requirements

- Python 3.11+
- Home/office internet connection (or residential proxy)
- `ANTHROPIC_API_KEY` for English description translations
- `pip install -r requirements.txt` — requests, httpx, rapidfuzz, PyYAML, beautifulsoup4, lxml, anthropic, Pillow, python-dotenv
