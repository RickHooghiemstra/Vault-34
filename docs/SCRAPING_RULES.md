# Scraping Rules

## Network Requirements

uitlaatstore.nl enforces WAF-level IP blocking on all datacenter ranges.

**Required:** Run from a home or office residential IP.  
**Optional:** Set `PROXY_URL` in `.env` for a residential proxy service.

Never attempt to bypass the WAF with datacenter IPs — the site returns `x-deny-reason: host_not_allowed` and the scraper will abort with a clear error message.

## Rate Limiting

- Default delay: **2.0 seconds** between requests
- Retries: **3 attempts** per URL with exponential back-off (5 s, 10 s, 15 s)
- Respect `429 Too Many Requests` — increase `REQUEST_DELAY` if you see them

## Pagination

uitlaatstore.nl uses offset-based pagination: `?offset=40`, `?offset=80`, …  
Each page contains up to **40 products**.

The scraper detects end-of-results when:
- A page returns fewer than 40 product URLs, OR
- All URLs on a page were already seen

## Checkpointing

URL discovery results are saved to `logs/checkpoint_{brand}.json`.  
If the scraper is interrupted, re-running will load from the checkpoint and skip re-discovery.

Delete the checkpoint file to force a fresh discovery.

## Product Page Parser

Extraction uses a **priority chain**:

1. **JSON-LD** (`<script type="application/ld+json">` with `@type: Product`)  
   Extracts: name, sku, brand, offers.price, description, image, gtin
2. **OpenGraph** (`og:title`, `og:description`, `og:image`, `og:price:amount`)
3. **DOM selectors** (configurable in `config/settings.py → SELECTORS`)

Run `python main.py --discover --url <url>` to dump selector candidates and tune the DOM fallback.

## Selector Discovery

When JSON-LD is absent or incomplete, the `--discover` mode prints all candidate elements:

```bash
python main.py --discover --url https://www.uitlaatstore.nl/s-k6r14-hegeht1
```

Update `config/settings.py → SELECTORS` with the correct CSS selectors.

## What Is Skipped

- Pages returning HTTP 4xx/5xx after all retries
- Products with no title or price (logged to `logs/failed_scrape.json`)
- Duplicate products by SKU or URL (logged to `logs/duplicates.json`)
- Category pages, navigation pages, blog posts
