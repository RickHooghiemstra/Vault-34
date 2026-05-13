# Image Processing

## Validation Pipeline

Every image URL extracted from a product page goes through three checks:

### 1. URL Filter

URLs are immediately rejected if they contain:
- `/logo`, `/icon`, `/banner`, `/placeholder`
- `s.w.org` (WordPress lazy-load SVG placeholder)
- `data:` (inline base64 images)
- Non-HTTPS URLs

### 2. HTTP HEAD Check

- Must return HTTP 200
- `Content-Type` must start with `image/`
- `Content-Length` (if present) must be > 10 KB

### 3. Dimension Check

A partial GET downloads the first 64 KB of the image file.  
Pillow parses the header bytes to read width and height.  
**Minimum: 800 px on either axis.**

If Pillow cannot parse the partial download, the image is accepted (HTTP 200 + correct Content-Type is sufficient confidence).

## Multi-Image Products

The scraper collects **all** image URLs from a product page (up to 10 per product).

The Shopify CSV exports them in multi-row format:
- Row 1: all product data + `Image Src` = first image, `Image Position` = 1
- Row 2+: `Handle` only + `Image Src` + `Image Position` (Shopify multi-image format)

## Missing Images

Products with 0 valid images after validation are:
1. Written to `logs/missing_images.json`
2. **Excluded** from the Shopify import CSV

Review `missing_images.json` and manually source images if needed before import.

## Extraction Sources

Image URLs are extracted from (in priority order):
1. JSON-LD `image` array
2. OpenGraph `og:image`
3. DOM: `data-large_image`, `data-src`, `data-lazy-src`, `data-original`, `src` attributes
4. Any `<img>` inside product gallery containers

Lazy-load placeholders (`data:` URIs and SVG emoji) are automatically skipped.
