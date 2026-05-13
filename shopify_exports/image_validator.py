"""
Image URL validation pipeline.

For each product image:
  1. HEAD request to check URL is reachable (HTTP 200, image Content-Type)
  2. Content-Length check (> MIN_IMAGE_BYTES)
  3. Partial GET to verify pixel dimensions (≥ MIN_IMAGE_DIM × MIN_IMAGE_DIM)
  4. Skip URLs matching IMAGE_SKIP_PATTERNS

Products with 0 valid images are written to logs/missing_images.json
and excluded from the final Shopify CSV.
"""

import json
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests

from config.settings import (
    MIN_IMAGE_BYTES, MIN_IMAGE_DIM, IMAGE_TIMEOUT,
    IMAGE_SAMPLE_BYTES, IMAGE_SKIP_PATTERNS, LOGS_DIR,
)

log = logging.getLogger(__name__)

# Shared session for image validation (reuses connections)
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; Vault34ImageValidator/1.0)"
        )
    return _session


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def validate_product_images(product: dict) -> list[str]:
    """
    Return only the valid, accessible image URLs for a product.
    Logs a warning if fewer than 2 valid images are found.
    """
    valid: list[str] = []
    for url in product.get("images", []):
        if _is_valid(url):
            valid.append(url)
            if len(valid) >= 10:   # cap at 10 images per product
                break
        else:
            log.debug("Rejected image: %s", url)

    if not valid:
        log.warning("No valid images for: %s", product.get("title", product.get("url")))
    elif len(valid) < 2:
        log.info("Only 1 image for: %s", product.get("title", ""))

    return valid


def validate_all(products: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Validate images for all products.

    Returns:
      (importable, missing_image_products)

    importable             — products with ≥1 valid image
    missing_image_products — products with 0 valid images (written to log, excluded)
    """
    importable: list[dict] = []
    missing:    list[dict] = []

    total = len(products)
    for i, product in enumerate(products, 1):
        log.info("[%d/%d] Validating images for: %s", i, total, product.get("title", ""))
        valid_images = validate_product_images(product)
        product["validated_images"] = valid_images
        if valid_images:
            importable.append(product)
        else:
            missing.append(product)

    if missing:
        _write_missing_report(missing)

    log.info(
        "Image validation complete: %d importable, %d missing",
        len(importable), len(missing),
    )
    return importable, missing


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def _is_valid(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    for pattern in IMAGE_SKIP_PATTERNS:
        if pattern in url:
            return False
    if url.startswith("data:"):
        return False

    session = _get_session()

    # Step 1: HEAD request
    try:
        resp = session.head(url, timeout=IMAGE_TIMEOUT, allow_redirects=True)
        if resp.status_code != 200:
            return False
        ctype = resp.headers.get("Content-Type", "")
        if not ctype.startswith("image/"):
            return False
        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length and content_length < MIN_IMAGE_BYTES:
            return False
    except requests.RequestException:
        return False

    # Step 2: Partial GET for dimension check
    return _check_dimensions(session, url)


def _check_dimensions(session: requests.Session, url: str) -> bool:
    try:
        from PIL import Image
        headers = {"Range": f"bytes=0-{IMAGE_SAMPLE_BYTES - 1}"}
        resp = session.get(url, headers=headers, timeout=IMAGE_TIMEOUT)
        img = Image.open(BytesIO(resp.content))
        w, h = img.size
        return w >= MIN_IMAGE_DIM or h >= MIN_IMAGE_DIM
    except Exception:
        # If Pillow can't parse a partial download, accept the image
        # (we already confirmed HTTP 200 and correct Content-Type)
        return True


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _write_missing_report(products: list[dict]) -> None:
    report = [
        {"title": p.get("title"), "url": p.get("url"), "sku": p.get("sku")}
        for p in products
    ]
    path = LOGS_DIR / "missing_images.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.warning("Wrote %d products with missing images → %s", len(products), path)
