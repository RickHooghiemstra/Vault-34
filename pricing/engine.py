"""
Competitor-aware pricing engine.

For each product:
  net_cost = uitlaatstore_price / 1.21

  If ≥ 2 confirmed competitor prices:
    target = competitor_p60 (60th percentile, ex-VAT EUR)
    clamped = clamp(target, net_cost × 1.35, net_cost × 1.80)
    price   = max(clamped, net_cost × 1.20)   ← hard floor
  Else:
    price = net_cost × 1.50                    ← default markup (logs a warning)
    price = max(price, net_cost × 1.20)        ← hard floor still applies

  Round to nearest €0.95 (e.g. 99.95, 149.95).
"""

import csv
import json
import logging
import math
from pathlib import Path
from typing import Optional

from competitor_intel.matchers.product_matcher import match_all_competitors
from config.settings import VAT_RATE, LOGS_DIR
from pricing.fx import get_rates, to_eur

log = logging.getLogger(__name__)

# ── Pricing constants ────────────────────────────────────────────────────────
_DEFAULT_MARKUP  = 1.50
_MIN_MARGIN_MULT = 1.35   # lower clamp: net × 1.35
_MAX_MARGIN_MULT = 1.80   # upper clamp: net × 1.80
_HARD_FLOOR_MULT = 1.20   # absolute floor: net × 1.20
_P60             = 0.60   # percentile target

PRICING_REPORT_FILE = LOGS_DIR / "pricing_report.json"
AUDIT_CSV_FILE      = LOGS_DIR / "competitor_audit.csv"

_AUDIT_COLUMNS = [
    "SKU",
    "Title",
    "URL",
    "Net Cost (EUR)",
    "Old Price (EUR)",
    "New Price (EUR)",
    "Margin %",
    "Pricing Method",
    "P60 Price (EUR)",
    "Min Clamp (EUR)",
    "Max Clamp (EUR)",
    "Competitor Name",
    "Competitor Domain",
    "Competitor Matched Title",
    "Competitor Price (EUR)",
    "Match Confidence",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile. *values* must be non-empty."""
    s = sorted(values)
    n = len(s)
    idx = p * (n - 1)
    lo  = int(idx)
    hi  = lo + 1
    if hi >= n:
        return s[-1]
    return s[lo] + (idx - lo) * (s[hi] - s[lo])


def _round_to_95(price: float) -> float:
    """Round to nearest value ending in .95 (99.95, 149.95, …)."""
    # Equivalent to: round(price + 0.05) - 0.05 using floor
    return math.floor(price + 0.55) - 0.05


# ── Core pricing function ────────────────────────────────────────────────────

def compute_price(
    product: dict,
    competitor_data: dict[str, list[dict]],
    fx_rates: dict[str, float],
) -> tuple[float, dict]:
    """
    Compute the final export price for *product*.

    Returns (price_float, metadata_dict).
    metadata_dict keys:
      net_cost, old_price, new_price, margin_pct, method,
      competitor_prices (list[float]), competitor_meta (list[dict])
    """
    price_raw = float(product.get("price_raw") or 0.0)
    net_cost  = price_raw / VAT_RATE
    old_price = _round_to_95(net_cost * _DEFAULT_MARKUP)
    hard_floor = net_cost * _HARD_FLOOR_MULT

    # ── Collect competitor prices ────────────────────────────────────────────
    matches = match_all_competitors(product, competitor_data)

    competitor_prices: list[float] = []
    competitor_meta:   list[dict]  = []

    for comp_prod, confidence in matches:
        # Convert to EUR if needed
        currency  = comp_prod.get("currency", "EUR")
        price_eur = comp_prod.get("price_eur", 0.0)

        if currency != "EUR":
            # price_eur was computed ex-VAT in scraper; just apply FX
            price_eur = to_eur(price_eur, currency, fx_rates)

        if price_eur <= 0:
            continue

        competitor_prices.append(price_eur)
        competitor_meta.append({
            "domain":     comp_prod.get("domain"),
            "name":       comp_prod.get("name"),
            "title":      comp_prod.get("title"),
            "price_eur":  round(price_eur, 2),
            "confidence": confidence,
        })

    # ── Determine price ──────────────────────────────────────────────────────
    min_clamp = round(net_cost * _MIN_MARGIN_MULT, 2)
    max_clamp = round(net_cost * _MAX_MARGIN_MULT, 2)

    if len(competitor_prices) >= 2:
        p60     = _percentile(competitor_prices, _P60)
        clamped = max(net_cost * _MIN_MARGIN_MULT, min(net_cost * _MAX_MARGIN_MULT, p60))
        raw_price = max(hard_floor, clamped)
        method  = "competitor"
    else:
        p60       = None
        raw_price = max(hard_floor, net_cost * _DEFAULT_MARKUP)
        method    = "default"
        if not competitor_prices:
            log.info(
                "Pricing fallback (no competitor data): %r",
                (product.get("title") or "?")[:60],
            )
        else:
            log.info(
                "Pricing fallback (only 1 competitor price): %r",
                (product.get("title") or "?")[:60],
            )

    final_price = _round_to_95(raw_price)

    margin_pct = (
        (final_price - net_cost) / net_cost * 100
        if net_cost > 0 else 0.0
    )

    return final_price, {
        "net_cost":          round(net_cost, 2),
        "old_price":         old_price,
        "new_price":         final_price,
        "margin_pct":        round(margin_pct, 1),
        "method":            method,
        "p60":               round(p60, 2) if p60 is not None else None,
        "min_clamp":         min_clamp,
        "max_clamp":         max_clamp,
        "competitor_prices": [round(p, 2) for p in competitor_prices],
        "competitor_meta":   competitor_meta,
    }


# ── Audit CSV ────────────────────────────────────────────────────────────────

def _write_audit_csv(report: list[dict]) -> None:
    """
    Write logs/competitor_audit.csv — one row per product-competitor match.
    Products with no matches get a single row with empty competitor columns.
    """
    try:
        with AUDIT_CSV_FILE.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_AUDIT_COLUMNS, extrasaction="ignore")
            writer.writeheader()

            for entry in report:
                base = {
                    "SKU":              entry.get("sku", ""),
                    "Title":            entry.get("title", ""),
                    "URL":              entry.get("url", ""),
                    "Net Cost (EUR)":   entry.get("net_cost", ""),
                    "Old Price (EUR)":  entry.get("old_price", ""),
                    "New Price (EUR)":  entry.get("new_price", ""),
                    "Margin %":         entry.get("margin_pct", ""),
                    "Pricing Method":   entry.get("method", ""),
                    "P60 Price (EUR)":  entry.get("p60", "") if entry.get("p60") is not None else "",
                    "Min Clamp (EUR)":  entry.get("min_clamp", ""),
                    "Max Clamp (EUR)":  entry.get("max_clamp", ""),
                }

                metas = entry.get("competitor_meta", [])
                if metas:
                    for meta in metas:
                        writer.writerow({
                            **base,
                            "Competitor Name":         meta.get("name", ""),
                            "Competitor Domain":        meta.get("domain", ""),
                            "Competitor Matched Title": meta.get("title", ""),
                            "Competitor Price (EUR)":   meta.get("price_eur", ""),
                            "Match Confidence":         meta.get("confidence", ""),
                        })
                else:
                    writer.writerow(base)

        log.info("Competitor audit CSV → %s", AUDIT_CSV_FILE)
    except OSError as exc:
        log.warning("Could not write competitor audit CSV: %s", exc)


# ── Batch entry point ────────────────────────────────────────────────────────

def apply_pricing(
    products: list[dict],
    competitor_data: dict[str, list[dict]],
) -> tuple[list[dict], list[dict]]:
    """
    Apply competitor-aware pricing to every product in *products*.

    Attaches ``export_price_computed`` and ``pricing_meta`` to each dict.
    Returns (updated_products, pricing_report_rows).
    """
    fx_rates = get_rates()
    report: list[dict] = []

    for product in products:
        price, meta = compute_price(product, competitor_data, fx_rates)
        product["export_price_computed"] = price
        product["pricing_meta"]          = meta
        report.append({
            "sku":   product.get("sku"),
            "title": product.get("title"),
            "url":   product.get("url"),
            **meta,
        })

    # Persist JSON report + audit CSV
    try:
        PRICING_REPORT_FILE.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Pricing report → %s", PRICING_REPORT_FILE)
    except OSError as exc:
        log.warning("Could not write pricing report: %s", exc)

    _write_audit_csv(report)

    competitor_count = sum(1 for r in report if r["method"] == "competitor")
    default_count    = len(report) - competitor_count
    log.info(
        "Pricing complete: %d competitor-based, %d default (flat %.0f%%)",
        competitor_count, default_count, (_DEFAULT_MARKUP - 1) * 100,
    )

    return products, report
