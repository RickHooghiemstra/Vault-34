# Competitor Intelligence

## Overview

The competitor scraper fetches live prices from rival stores and feeds them into the pricing engine. It supports **Shopify** and **WooCommerce** stores out of the box, with auto-detection when the store type is unknown.

## Supported Platforms

| Platform | Endpoint | Notes |
|---|---|---|
| Shopify | `/products.json?limit=250&page=N` | Pagination via page number |
| WooCommerce | `/wp-json/wc/store/v1/products?per_page=100&page=N` | Block Store API, no auth required |

Stores that don't respond to either API are skipped automatically.

## Config File

Edit `config/competitors.yaml` to add, remove, or tune competitors:

```yaml
competitors:
  - domain: www.example.com
    name: Example Store
    market: DE           # NL | DE | FR | GB | US | JP | AU | EU | …
    currency: EUR        # ISO 4217
    includes_vat: true   # true if prices shown include VAT/GST/consumption tax
    type: auto           # shopify | woocommerce | auto (default: auto)
```

### `type` field

| Value | Behaviour |
|---|---|
| `shopify` | Always use Shopify `/products.json` — fastest, no probing |
| `woocommerce` | Always use WooCommerce Store API |
| `auto` (default) | Probe Shopify first; if empty, probe WooCommerce; skip if neither works |

Use explicit `type` for known stores to avoid the probe overhead (~2–3 s per auto store).

### VAT / tax flags

| Market | Rate | `includes_vat` |
|---|---|---|
| NL | 21% | true |
| DE | 19% | true |
| FR | 20% | true |
| GB | 20% | true |
| AU | 10% GST | true |
| JP | 10% consumption tax | true |
| US | — (sales tax not in list price) | false |

The scraper divides all `includes_vat: true` prices by 1.21 to produce `price_eur` (ex-VAT). The pricing engine's FX module then converts non-EUR prices to EUR using daily ECB rates.

## Current Competitor List

| Market | Store | Type | Currency |
|---|---|---|---|
| NL | motea.com | Shopify | EUR |
| NL | thunderbike.nl | Auto | EUR |
| NL | motoscoot.nl | Auto | EUR |
| DE | fc-moto.de | Shopify | EUR |
| DE | louis.de | Shopify | EUR |
| DE | polo-motorrad.de | Shopify | EUR |
| FR | motoblouz.com | Auto | EUR |
| FR | dafy-moto.com | Auto | EUR |
| FR | speedway.fr | Auto | EUR |
| GB | holeshot.co.uk | Shopify | GBP |
| GB | sportsbikeshop.co.uk | Auto | GBP |
| GB | wemoto.com | Auto | GBP |
| US | revzilla.com | Auto | USD |
| US | cyclegear.com | Auto | USD |
| US | jpcycles.com | Auto | USD |
| JP | webike.net | Auto | JPY |
| JP | nankai-buhin.com | Auto | JPY |
| JP | daytona.co.jp | Auto | JPY |
| AU | mcas.com.au | Auto | AUD |
| AU | bikebiz.com.au | Auto | AUD |
| AU | mymoto.com.au | Auto | AUD |

## Output

Each scraped product variant produces a dict:

```python
{
    "domain":       "www.fc-moto.de",
    "name":         "FC-Moto DE",
    "market":       "DE",
    "currency":     "EUR",
    "includes_vat": True,
    "sku":          "S-H10SO3-HRC",
    "title":        "Akrapovic Slip-On Honda CB650R",
    "vendor":       "Akrapovic",
    "price_raw":    749.0,   # original listed price (may include VAT)
    "price_eur":    617.36,  # ex-VAT (price_raw / 1.21 when includes_vat=True)
    "tags":         ["akrapovic", "honda", "cb650r"],
}
```

`price_eur` is pre-FX (assumed EUR); the pricing engine converts GBP/USD/JPY/AUD to EUR using ECB daily rates.

## Scraper Architecture

```
config/competitors.yaml
        │
        ▼
competitor_intel/scrapers/auto_scraper.py   ← dispatcher (scrape_all_competitors)
        │
        ├── type: shopify   → competitor_intel/scrapers/shopify_json.py
        │                      GET /products.json?limit=250&page=N
        │
        └── type: woocommerce / auto probe
                            → competitor_intel/scrapers/woocommerce_json.py
                               GET /wp-json/wc/store/v1/products?per_page=100&page=N
```

## Extending to New Platforms

To add support for a new e-commerce platform (e.g. Magento, BigCommerce):

1. Create `competitor_intel/scrapers/magento_json.py` with a `scrape_competitor(competitor) -> list[dict]` function returning the standard product dict structure above.
2. Add an `is_magento(domain)` probe function.
3. Register it in `auto_scraper.py`'s `_scrape_one()` function.
4. Add `type: magento` support to the YAML config.
