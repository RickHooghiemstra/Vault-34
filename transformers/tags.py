"""
Deterministic Shopify tag generation.

Tag groups and formats:
  BRAND_{Name}        e.g. BRAND_Akrapovic
  MAKE_{Name}         e.g. MAKE_Honda
  MODEL_{Name}        e.g. MODEL_CBR600RR   (spaces → underscores)
  YEAR_{YYYY}         e.g. YEAR_2021        (expanded from ranges)
  TYPE_{ExhaustType}  e.g. TYPE_SlipOn
  MAT_{Material}      e.g. MAT_Titanium
  EURO_{n}            e.g. EURO_5
  HOMOLOGATED         street-legal products
  RACE_ONLY           non-homologated / race use only
  CAT_{Category}      e.g. CAT_FullSystem
  source:uitlaatstore.nl
"""

import re
from parsers.fitment_parser import expand_years

# ---------------------------------------------------------------------------
# Exhaust type keywords → TYPE tag
# ---------------------------------------------------------------------------

_TYPE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bslip[-\s]?on\b",                  re.I), "SlipOn"),
    (re.compile(r"\bslipon\b",                         re.I), "SlipOn"),
    (re.compile(r"\bfull\s*system\b",                  re.I), "FullSystem"),
    (re.compile(r"\bcomplete\b.*\buitlaatsysteem\b",   re.I), "FullSystem"),
    (re.compile(r"\bracing\s*line\b",                  re.I), "FullSystem"),
    (re.compile(r"\bevolution\s*line\b",               re.I), "FullSystem"),
    (re.compile(r"\buitlaatsysteem\b",                 re.I), "FullSystem"),
    (re.compile(r"\bvolledig\s*systeem\b",             re.I), "FullSystem"),   # Dutch
    (re.compile(r"\bvolledige\s*uitlaat\b",            re.I), "FullSystem"),   # Dutch
    (re.compile(r"\bdecat\b",                          re.I), "Decat"),
    (re.compile(r"\bde[-\s]?cat\b",                    re.I), "Decat"),
    (re.compile(r"\blink\s*pipe\b",                    re.I), "LinkPipe"),
    (re.compile(r"\blinkpipe\b",                       re.I), "LinkPipe"),
    (re.compile(r"\blinkpijp\b",                       re.I), "LinkPipe"),     # Dutch
    (re.compile(r"\bcollector\b",                      re.I), "LinkPipe"),
    (re.compile(r"\buitlaatbochtenset\b",              re.I), "HeaderSet"),
    (re.compile(r"\bbochtenset\b",                     re.I), "HeaderSet"),    # Dutch
    (re.compile(r"\bheader\s*set\b",                   re.I), "HeaderSet"),
    (re.compile(r"\bdb[-\s]?killer\b",                 re.I), "DbKiller"),
    (re.compile(r"\bhitteschild\b",                    re.I), "HeatShield"),
    (re.compile(r"\bheat\s*shield\b",                  re.I), "HeatShield"),
    (re.compile(r"\bkat(?:vervanger)?\b",              re.I), "CatReplacer"),
    (re.compile(r"\bdempers?\b",                       re.I), "SlipOn"),       # Dutch (singular + plural)
]

# ---------------------------------------------------------------------------
# Material keywords → MAT tag
# ---------------------------------------------------------------------------

_MAT_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btitanium\b",          re.I), "Titanium"),
    (re.compile(r"\bcarbon\b",            re.I), "Carbon"),
    (re.compile(r"\brvs\b|stainless",     re.I), "StainlessSteel"),
    (re.compile(r"\bstaal\b",             re.I), "Steel"),
    (re.compile(r"\bzwart\b|black",       re.I), "BlackEdition"),
    (re.compile(r"\bgoud\b|gold",         re.I), "Gold"),
]

# ---------------------------------------------------------------------------
# Euro certification
# ---------------------------------------------------------------------------

_EURO_RE = re.compile(r"\beuro\s*([3-5])\b", re.I)

# ---------------------------------------------------------------------------
# CAT_ tag denylist — breadcrumb values that are NOT product categories
# (navigation pages, static pages, store sections, etc.)
# ---------------------------------------------------------------------------

_CAT_DENYLIST: frozenset[str] = frozenset({
    "home", "winkel", "shop", "contact", "verzending", "retour",
    "garantie", "over ons", "faq", "vacatures", "sponsoring",
    "privacy", "algemene voorwaarden", "tax free", "outlet",
    "alle merken", "alle producten", "producten", "merken",
    "onderhoud", "olie", "blog", "nieuws", "service", "sitemap",
    "veelgestelde vragen", "tax free shopping", "outlet aanbiedingen",
})

# ---------------------------------------------------------------------------
# Homologation keywords
# ---------------------------------------------------------------------------

_HOMOLOGATED_RE  = re.compile(r"\be-keur\b|\bhomologat|\bstraat\b|\bstreet\b|\bece\b", re.I)
_RACE_ONLY_RE    = re.compile(r"\brace\b|\bnot\s+road\b|\btrack\b|\bnot\s+for\s+road\b", re.I)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def build_tags(product: dict) -> list[str]:
    """
    Build the full deterministic tag list for a product.

    product must have keys: brand, fitment {make, model, year},
    title, product_type, breadcrumbs, description_nl.
    """
    tags: list[str] = []
    title = product.get("title", "")
    desc  = product.get("description_nl", "")
    text  = f"{title} {desc}"

    # Brand
    brand = product.get("brand", "")
    if brand:
        tags.append(f"BRAND_{_slug(brand)}")

    # Make / Model / Year
    fitment = product.get("fitment", {})
    make  = fitment.get("make", "")
    model = fitment.get("model", "")
    year  = fitment.get("year", "")

    if make:
        tags.append(f"MAKE_{_slug(make)}")
    if model:
        tags.append(f"MODEL_{_slug(model)}")
    for yr in expand_years(year):
        tags.append(f"YEAR_{yr}")

    # Exhaust type
    for pattern, type_tag in _TYPE_MAP:
        if pattern.search(text):
            tag = f"TYPE_{type_tag}"
            if tag not in tags:
                tags.append(tag)
            break

    # Material
    for pattern, mat_tag in _MAT_MAP:
        if pattern.search(text):
            tag = f"MAT_{mat_tag}"
            if tag not in tags:
                tags.append(tag)

    # Euro certification
    euro_m = _EURO_RE.search(text)
    if euro_m:
        tags.append(f"EURO_{euro_m.group(1)}")

    # Homologation
    if _HOMOLOGATED_RE.search(text):
        tags.append("HOMOLOGATED")
    elif _RACE_ONLY_RE.search(text):
        tags.append("RACE_ONLY")

    # Category from breadcrumbs — only for exhaust-relevant values
    product_type = product.get("product_type", "")
    if product_type and product_type.lower() not in _CAT_DENYLIST:
        tags.append(f"CAT_{_slug(product_type)}")

    return tags


def _slug(text: str) -> str:
    """Convert display name to a clean tag slug: 'Slip-On Line' → 'SlipOnLine'."""
    # Title-case, remove spaces/hyphens between words
    s = re.sub(r"[^\w]", "_", text.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s
