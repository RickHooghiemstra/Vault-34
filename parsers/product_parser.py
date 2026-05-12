"""
Product detail page parser.

Extraction priority chain (highest to lowest confidence):
  1. JSON-LD structured data  (schema.org/Product)
  2. OpenGraph meta tags
  3. DOM selectors (configurable in config/settings.py)

Returns a raw product dict — no pricing or tag logic here.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from config.settings import BASE_URL, SELECTORS, IMAGE_SKIP_PATTERNS
from config.brands import normalize_brand
from parsers.fitment_parser import extract_fitment

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def parse_product(soup: BeautifulSoup, url: str) -> Optional[dict]:
    """
    Parse a product detail page into a raw product dict.

    Returns None if the page does not look like a valid product.
    """
    p: dict = {
        "url":             url,
        "title":           "",
        "sku":             "",
        "brand":           "",
        "price_raw":       0.0,
        "description_nl":  "",
        "images":          [],
        "breadcrumbs":     [],
        "fitment":         {"make": "", "model": "", "year": ""},
        "product_type":    "",
        "gtin":            "",
        "availability":    "",
        "weight_grams":    5000,
        "json_ld":         {},
        "_price_candidates": [],   # collects all prices; min taken at end
    }

    # --- Strategy 1: JSON-LD ---
    _apply_json_ld(soup, p)

    # --- Strategy 2: OpenGraph ---
    _apply_opengraph(soup, p)

    # --- Strategy 3: DOM selectors ---
    _apply_dom(soup, url, p)

    # Final price: take the minimum of all candidates (sale price < list price)
    candidates = [v for v in p.pop("_price_candidates") if v > 0]
    if candidates:
        p["price_raw"] = min(candidates)

    # Breadcrumbs
    p["breadcrumbs"] = _extract_breadcrumbs(soup)
    if p["breadcrumbs"]:
        p["product_type"] = p["breadcrumbs"][-1]

    # Fitment (make / model / year)
    p["fitment"] = extract_fitment(soup, p["title"])

    # Validate — must have at minimum a title and a price
    if not p["title"] or p["price_raw"] == 0.0:
        log.debug("Skipping %s — missing title or price", url)
        return None

    # Normalise brand
    p["brand"] = normalize_brand(p["brand"]) if p["brand"] else ""

    # Deduplicate and validate images
    p["images"] = _deduplicate_images(p["images"])

    return p


# ---------------------------------------------------------------------------
# Strategy 1 — JSON-LD
# ---------------------------------------------------------------------------

def _apply_json_ld(soup: BeautifulSoup, p: dict) -> None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both single object and @graph arrays
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict) and node.get("@graph"):
                nodes.extend(node["@graph"])
            if not isinstance(node, dict):
                continue
            t = node.get("@type", "")
            types = [t] if isinstance(t, str) else t
            if "Product" not in types:
                continue

            p["json_ld"] = node
            _set_if_empty(p, "title",  node.get("name", ""))
            _set_if_empty(p, "sku",    node.get("sku", "") or node.get("mpn", ""))
            _set_if_empty(p, "gtin",   node.get("gtin", "") or node.get("gtin13", ""))
            _set_if_empty(p, "description_nl", _strip_html(node.get("description", "")))

            # Brand
            brand_node = node.get("brand", {})
            if isinstance(brand_node, dict):
                _set_if_empty(p, "brand", brand_node.get("name", ""))
            elif isinstance(brand_node, str):
                _set_if_empty(p, "brand", brand_node)

            # Price
            offers = node.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                raw_price = offers.get("price", offers.get("lowPrice", ""))
                _set_price_if_empty(p, raw_price)
                avail = offers.get("availability", "")
                _set_if_empty(p, "availability", avail.split("/")[-1] if "/" in avail else avail)

            # Images
            imgs = node.get("image", [])
            if isinstance(imgs, str):
                imgs = [imgs]
            for img in imgs:
                url_val = img.get("url", img) if isinstance(img, dict) else img
                if isinstance(url_val, str):
                    url_val = _strip_magento_cache(url_val)
                    if _is_valid_image_url(url_val):
                        p["images"].append(url_val)

            return   # First Product node wins


# ---------------------------------------------------------------------------
# Strategy 2 — OpenGraph
# ---------------------------------------------------------------------------

def _apply_opengraph(soup: BeautifulSoup, p: dict) -> None:
    og: dict[str, str] = {}
    for meta in soup.find_all("meta", attrs={"property": True}):
        prop = meta.get("property", "")
        content = meta.get("content", "")
        if prop.startswith("og:") and content:
            og[prop] = content

    _set_if_empty(p, "title", og.get("og:title", ""))
    _set_if_empty(p, "description_nl", _strip_html(og.get("og:description", "")))

    img = og.get("og:image", "")
    if img and _is_valid_image_url(img) and img not in p["images"]:
        p["images"].append(img)

    price_str = og.get("og:price:amount", "") or og.get("product:price:amount", "")
    _set_price_if_empty(p, price_str)


# ---------------------------------------------------------------------------
# Strategy 3 — DOM selectors
# ---------------------------------------------------------------------------

def _apply_dom(soup: BeautifulSoup, page_url: str, p: dict) -> None:
    base = urlparse(page_url)

    def first_text(selectors: list[str]) -> str:
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return ""

    _set_if_empty(p, "title",          first_text(SELECTORS["title"]))
    _set_if_empty(p, "sku",            first_text(SELECTORS["sku"]))
    _set_if_empty(p, "brand",          first_text(SELECTORS["brand"]))

    desc_text = first_text(SELECTORS["description"])
    desc_html = ""
    for sel in SELECTORS["description"]:
        el = soup.select_one(sel)
        if el:
            desc_html = str(el)
            break
    _set_if_empty(p, "description_nl", desc_html or desc_text)

    # Price: collect all candidates, excluding explicit old-price wrappers
    seen_price_els: set[int] = set()
    for sel in SELECTORS["price"]:
        for el in soup.select(sel):
            if id(el) in seen_price_els:
                continue
            seen_price_els.add(id(el))
            if el.find_parent(class_="old-price") or el.find_parent(attrs={"data-price-type": "oldPrice"}):
                continue
            val = _parse_price(el.get_text(strip=True))
            if val > 0:
                p["_price_candidates"].append(val)

    # Images from DOM
    for sel in SELECTORS["images"]:
        for img in soup.select(sel):
            src = (
                img.get("data-large_image")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
                or img.get("src", "")
            )
            if src:
                full = urljoin(f"{base.scheme}://{base.netloc}", src)
                full = _strip_magento_cache(full)
                if _is_valid_image_url(full) and full not in p["images"]:
                    p["images"].append(full)

    # Fallback title from slug
    if not p["title"]:
        slug = urlparse(page_url).path.rstrip("/").split("/")[-1]
        p["title"] = slug.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_breadcrumbs(soup: BeautifulSoup) -> list[str]:
    crumbs: list[str] = []
    for sel in SELECTORS["breadcrumb"]:
        items = soup.select(sel)
        if items:
            for a in items:
                text = a.get_text(strip=True)
                if text and text.lower() not in ("home", "winkel", "shop", ""):
                    crumbs.append(text)
            break
    return crumbs


def _set_if_empty(p: dict, key: str, value: str) -> None:
    if not p.get(key) and value:
        p[key] = value.strip()


def _set_price_if_empty(p: dict, raw: object) -> None:
    """Collect price candidate; final min() taken in parse_product."""
    if isinstance(raw, float) and raw > 0:
        p["_price_candidates"].append(raw)
        return
    price = _parse_price(str(raw) if raw else "")
    if price:
        p["_price_candidates"].append(price)


def _parse_price(raw: str) -> float:
    cleaned = re.sub(r"[€$£\s\xa0]", "", raw)
    # Dutch thousands separator: 1.299,00 → remove dots, replace comma
    if re.search(r"\d\.\d{3}", cleaned):
        cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(re.sub(r"[^\d.]", "", cleaned))
    except ValueError:
        return 0.0


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _is_valid_image_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    if url.startswith("data:"):
        return False
    for pattern in IMAGE_SKIP_PATTERNS:
        if pattern in url:
            return False
    # Magento cache URLs embed the extension mid-path (e.g. /cache/.../photo.jpg/...)
    return bool(re.search(r"\.(jpe?g|png|webp|gif)", url, re.I))


_MAGENTO_CACHE_RE = re.compile(r"/cache/[a-f0-9]{32}/")


def _strip_magento_cache(url: str) -> str:
    """Convert a Magento cache URL to the original full-resolution path."""
    return _MAGENTO_CACHE_RE.sub("/", url)


def _deduplicate_images(images: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in images:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result
