"""
Strip competitor branding and UI artifacts from scraped product descriptions.

Removes sentences that:
  - Mention uitlaatstore.nl (competitor name)
  - Reference the competitor's UI ("button on this page", "via de knop")
  - Contain "cheapest" / "goedkoopst" cross-promotions
  - Are generic dealer boasts ("X has been a Y dealer for years")
"""

import re
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentence-level patterns (match whole sentence up to . ! ?)
# Works on both plain text and HTML (tags are preserved, only text sentences removed)
# ---------------------------------------------------------------------------

# Any sentence mentioning the competitor by name
_RE_UITLAATSTORE = re.compile(
    r'[^<.!?]*uitlaatstore[^<.!?]*[.!?]?',
    re.I,
)

# UI references to competitor's on-page widgets
_RE_UI_WIDGET = re.compile(
    r'[^<.!?]*(button on this page|via de knop|via de button|ask them|stel.*vraag'
    r'|contact.*knop|via.*chat|stuur.*bericht)[^<.!?]*[.!?]?',
    re.I,
)

# "Cheapest X at..." promotional lines
_RE_CHEAPEST = re.compile(
    r'[^<.!?]*(cheapest|goedkoopst|laagste prijs)[^<.!?]*[.!?]?',
    re.I,
)

# "X has been a Y dealer for N years" boast lines
_RE_DEALER_BOAST = re.compile(
    r'[^<.!?]*(has been a \w+ dealer|is al \w+ jaar|jarenlange ervaring'
    r'|years? of experience|jaren\s+(dealer|partner))[^<.!?]*[.!?]?',
    re.I,
)

_PATTERNS = [
    _RE_UITLAATSTORE,
    _RE_UI_WIDGET,
    _RE_CHEAPEST,
    _RE_DEALER_BOAST,
]

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def clean_description(html: str) -> str:
    """
    Remove competitor-branded and UI-specific sentences from a description string.
    Preserves all HTML tags; only strips matching text content.
    """
    if not html:
        return html

    original_len = len(html)
    for pattern in _PATTERNS:
        html = pattern.sub("", html)

    # Collapse artefact whitespace left behind
    html = re.sub(r"[ \t]{2,}", " ", html)
    html = re.sub(r"(<br\s*/?>|\n){3,}", "<br>", html, flags=re.I)
    html = html.strip()

    if len(html) < original_len:
        log.debug("Cleaned %d chars of competitor text", original_len - len(html))

    return html


def clean_all(products: list[dict]) -> list[dict]:
    """Apply description cleaning to all products in the pipeline."""
    cleaned = 0
    for p in products:
        before_nl = p.get("description_nl", "")
        before_en = p.get("description_en", "")

        p["description_nl"] = clean_description(before_nl)
        if before_en:
            p["description_en"] = clean_description(before_en)

        if p["description_nl"] != before_nl or p.get("description_en", "") != before_en:
            cleaned += 1

    log.info("Competitor text stripped from %d/%d product descriptions", cleaned, len(products))
    return products
