"""
SEO field generation: handle, SEO title, meta description, image ALT text.
"""

import re
import unicodedata


def generate_handle(title: str, sku: str = "", existing: set | None = None) -> str:
    """
    Create a URL-safe Shopify handle from the product title.
    Appends SKU suffix if the handle collides with an existing one.
    """
    handle = _slugify(title)
    if existing is not None and handle in existing:
        handle = f"{handle}-{_slugify(sku)}" if sku else f"{handle}-dup"
    return handle or "product"


def seo_title(brand: str, product_type: str, make: str, model: str, year: str) -> str:
    """
    Format: '{Brand} {ProductType} for {Make} {Model} {Year} | Vault-34'
    Skips empty parts gracefully.
    Max 70 chars recommended for Google.
    """
    parts: list[str] = []
    if brand:
        parts.append(brand)
    if product_type:
        parts.append(product_type)
    bike_parts: list[str] = []
    if make:
        bike_parts.append(make)
    if model:
        bike_parts.append(model)
    if year:
        bike_parts.append(year)
    if bike_parts:
        parts.append("for " + " ".join(bike_parts))
    base = " ".join(parts)
    full = f"{base} | Vault-34"
    return full[:70] if len(full) > 70 else full


def meta_description(title: str, brand: str, make: str, model: str) -> str:
    """150-char meta description."""
    bike = f"{make} {model}".strip() or "your motorcycle"
    desc = f"Buy the {title} at Vault-34. Free international shipping. Premium {brand} exhaust for {bike}."
    return desc[:150]


def alt_text(brand: str, product_type: str, make: str, model: str) -> str:
    """ALT text format: '{Brand} {ProductType} for {Make} {Model}'."""
    parts = [brand, product_type]
    if make or model:
        parts.append("for")
        if make:
            parts.append(make)
        if model:
            parts.append(model)
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
