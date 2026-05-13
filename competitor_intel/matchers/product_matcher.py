"""
Match competitor products to our catalog.

Priority:
  1. SKU exact match (case-insensitive, stripped) → confidence 1.0
  2. RapidFuzz token_sort_ratio on vendor+title vs brand+title → confidence 0.0–1.0

Only matches with confidence ≥ 0.75 are returned.
"""

import logging
from typing import Optional

from rapidfuzz import fuzz

log = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.75


def _combined_text(vendor: str, title: str) -> str:
    return f"{vendor} {title}".lower().strip()


def match_product(
    our_product: dict,
    competitor_products: list[dict],
) -> Optional[tuple[dict, float]]:
    """
    Find the best matching competitor product for *our_product*.

    Returns (competitor_dict, confidence) where confidence ∈ [0, 1],
    or None if no match meets MIN_CONFIDENCE (0.75).
    """
    our_sku   = (our_product.get("sku") or "").strip().upper()
    our_brand = (our_product.get("brand") or "").strip()
    our_title = (our_product.get("title") or "").strip()
    our_text  = _combined_text(our_brand, our_title)

    best_prod:  Optional[dict] = None
    best_score: float          = 0.0

    for comp in competitor_products:
        comp_sku  = (comp.get("sku") or "").strip().upper()
        comp_text = _combined_text(comp.get("vendor", ""), comp.get("title", ""))

        # SKU exact match — short-circuit immediately
        if our_sku and comp_sku and our_sku == comp_sku:
            return comp, 1.0

        # Fuzzy title match
        score = fuzz.token_sort_ratio(our_text, comp_text) / 100.0
        if score > best_score:
            best_score = score
            best_prod  = comp

    if best_score >= MIN_CONFIDENCE and best_prod is not None:
        return best_prod, round(best_score, 4)

    return None


def match_all_competitors(
    our_product: dict,
    competitor_data: dict[str, list[dict]],
) -> list[tuple[dict, float]]:
    """
    Run match_product against every competitor's catalog.
    Returns a list of (competitor_dict, confidence) tuples, one per
    competitor site that produced a confident match (≥ 0.75).
    At most one match per competitor domain.
    """
    matches: list[tuple[dict, float]] = []
    for domain, products in competitor_data.items():
        result = match_product(our_product, products)
        if result is not None:
            matched_prod, confidence = result
            log.debug(
                "Matched %r → %r @ %s (conf=%.2f)",
                our_product.get("title", "?")[:40],
                matched_prod.get("title", "?")[:40],
                domain,
                confidence,
            )
            matches.append((matched_prod, confidence))
    return matches
