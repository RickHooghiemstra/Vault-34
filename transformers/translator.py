"""
Dutch → English translation via Claude Haiku API.

Features:
  - Batches 10 descriptions per API call
  - Prompt caching on the system prompt (reduces cost ~90% on repeated runs)
  - Persistent translation cache keyed by MD5 of source text (logs/translation_cache.json)
  - Falls back to original Dutch text on API failure (flagged in QA report)
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Title translation — Dutch → English term map
# (applied before Claude API; no API cost)
# ---------------------------------------------------------------------------

# Order matters: longer / multi-word phrases must come before their components
_TITLE_TERMS: list[tuple[re.Pattern, str]] = [
    # Multi-word phrases (longest first)
    (re.compile(r"\bVolledig\s+systeem\b",       re.I), "Full System"),
    (re.compile(r"\bVolledige\s+uitlaat\b",      re.I), "Full System"),    # volledige uitlaat
    (re.compile(r"\bCompleet\s+systeem\b",       re.I), "Full System"),
    (re.compile(r"\bOptionele\s+bochtenset\b",   re.I), "Optional Header Set"),
    (re.compile(r"\bOptionele\s+collector\b",    re.I), "Optional Collector"),
    (re.compile(r"\bOptionele\s+linkpijp\b",     re.I), "Optional Link Pipe"),
    (re.compile(r"\bOptionele\s+eindkap\b",      re.I), "Optional End Cap"),
    (re.compile(r"\bOptionele\s+demper\b",       re.I), "Optional Silencer"),
    (re.compile(r"\bHitte[\s\-]?schild\b",       re.I), "Heat Shield"),
    (re.compile(r"\bKatalysator\s*converter\b",  re.I), "Catalytic Converter"),
    (re.compile(r"\bKatalysator\b",              re.I), "Cat"),
    (re.compile(r"\bUitlaatbochten\b",           re.I), "Exhaust Headers"),
    (re.compile(r"\bUitlaatpijpen?\b",           re.I), "Exhaust Pipe"),
    (re.compile(r"\bUitlaatset\b",               re.I), "Exhaust Set"),
    (re.compile(r"\bUitlaten\b",                 re.I), "Exhausts"),       # plural
    (re.compile(r"\bGeluidsdemper\b",            re.I), "Silencer"),
    (re.compile(r"\bGeluiddemper\b",             re.I), "Silencer"),
    # Single component words
    (re.compile(r"\bLinkpijp\b",                 re.I), "Link Pipe"),
    (re.compile(r"\bBochtenset\b",               re.I), "Header Set"),
    (re.compile(r"\bDempers\b",                  re.I), "Silencers"),      # plural before singular
    (re.compile(r"\bDemper\b",                   re.I), "Silencer"),
    (re.compile(r"\bEindkap\b",                  re.I), "End Cap"),
    (re.compile(r"\bCompleet\b",                 re.I), "Complete"),
    (re.compile(r"\bUitlaat\b",                  re.I), "Exhaust"),
    (re.compile(r"\bSysteme?\b",                 re.I), "System"),
    (re.compile(r"\bPijp\b",                     re.I), "Pipe"),
    (re.compile(r"\bBrug\b",                     re.I), "Bridge"),
    # Materials & finishes
    (re.compile(r"\bRVS\b"),                           "Stainless Steel"),
    (re.compile(r"\bZwart\b",                    re.I), "Black"),
    (re.compile(r"\bZilver\b",                   re.I), "Silver"),
    (re.compile(r"\bGoud\s*verguld\b",           re.I), "Gold-Plated"),
    (re.compile(r"\bVerguld\b",                  re.I), "Gold-Plated"),
    (re.compile(r"\bGoud\b",                     re.I), "Gold"),
    (re.compile(r"\bChroom\b",                   re.I), "Chrome"),
    (re.compile(r"\bMat\s+(?=black|zwart|wit|silver)", re.I), "Matte "),
    (re.compile(r"\bMat\b",                      re.I), "Matte"),
    (re.compile(r"\bGepolijst\b",                re.I), "Polished"),
    (re.compile(r"\bGeborsteld\b",               re.I), "Brushed"),
    # Descriptors
    (re.compile(r"\bOptionele?\b",               re.I), "Optional"),
    (re.compile(r"\bVolledig\b",                 re.I), "Full"),
    (re.compile(r"\bVerkort\b",                  re.I), "Short"),
    (re.compile(r"\bHoog\b",                     re.I), "High"),
    (re.compile(r"\bLaag\b",                     re.I), "Low"),
    (re.compile(r"\bOnderdeel\b",                re.I), "Part"),
    (re.compile(r"\bAccessoire\b",               re.I), "Accessory"),
    # Prepositions / grammar
    (re.compile(r"\bvoor\b",                     re.I), "for"),
    (re.compile(r"\bmet\b",                      re.I), "with"),
    (re.compile(r"\bzonder\b",                   re.I), "without"),
    (re.compile(r"\ben\b",                       re.I), "and"),
    (re.compile(r"\bof\b",                       re.I), "or"),
    (re.compile(r"\bvan\b",                      re.I), ""),   # usually redundant in EN
    (re.compile(r"\bop\b",                       re.I), ""),
    # Collapse double spaces left by removed words
    (re.compile(r"\s{2,}"),                            " "),
]


def translate_title(dutch: str) -> str:
    """Apply Dutch → English term-map substitutions to a product title."""
    title = dutch
    for pattern, replacement in _TITLE_TERMS:
        title = pattern.sub(replacement, title)
    return title.strip()

from config.settings import (
    ANTHROPIC_API_KEY,
    TRANSLATION_MODEL,
    TRANSLATION_BATCH,
    TRANSLATION_CACHE,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict[str, str] = {}


def _load_cache() -> None:
    global _cache
    if TRANSLATION_CACHE.exists():
        try:
            _cache = json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))
            log.info("Loaded %d cached translations", len(_cache))
        except (json.JSONDecodeError, OSError):
            _cache = {}


def _save_cache() -> None:
    TRANSLATION_CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a professional technical translator specialising in motorcycle exhaust systems. "
    "Translate Dutch product descriptions to English. Rules:\n"
    "- Preserve all HTML tags exactly (do not add or remove any)\n"
    "- Keep brand names, model numbers, SKUs, and technical specs verbatim (e.g. 'CB650R', '60.5mm', 'E5')\n"
    "- Keep measurements and units as-is\n"
    "- Translate naturally for an international English-speaking audience\n"
    "- Return ONLY the translated text, no explanation or commentary\n"
    "- If the input is already in English, return it unchanged"
)


def translate_batch(texts: list[str]) -> list[str]:
    """
    Translate a batch of Dutch HTML description strings to English.
    Returns translated strings in the same order.
    Falls back to original on error.
    """
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — descriptions will remain in Dutch")
        return texts

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    results: list[str] = list(texts)

    # Separate already-cached from those needing translation
    to_translate: list[tuple[int, str]] = []
    for i, text in enumerate(texts):
        key = _cache_key(text)
        if key in _cache:
            results[i] = _cache[key]
        else:
            to_translate.append((i, text))

    if not to_translate:
        return results

    # Build numbered prompt
    numbered = "\n\n".join(
        f"[{j+1}]\n{text}" for j, (_, text) in enumerate(to_translate)
    )
    user_prompt = (
        f"Translate the following {len(to_translate)} Dutch product description(s) to English. "
        f"Return each translation preceded by its number in square brackets, e.g. [1].\n\n"
        f"{numbered}"
    )

    try:
        response = client.messages.create(
            model=TRANSLATION_MODEL,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # prompt caching
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text
        translations = _parse_numbered_response(raw, len(to_translate))

        for j, (i, original) in enumerate(to_translate):
            translated = translations[j] if j < len(translations) else original
            if translated:
                results[i] = translated
                _cache[_cache_key(original)] = translated
            else:
                log.warning("Empty translation for item %d — keeping Dutch", j + 1)

        _save_cache()

    except Exception as exc:
        log.error("Translation API error: %s — keeping Dutch descriptions", exc)

    return results


def translate_all(products: list[dict]) -> list[dict]:
    """
    Translate description_nl for all products in batches.
    Adds description_en field; marks translation_failed=True on error.
    """
    _load_cache()
    texts = [p.get("description_nl", "") for p in products]

    # Process in batches
    all_translated: list[str] = []
    for start in range(0, len(texts), TRANSLATION_BATCH):
        batch = texts[start : start + TRANSLATION_BATCH]
        log.info(
            "Translating batch %d-%d of %d",
            start + 1, min(start + TRANSLATION_BATCH, len(texts)), len(texts),
        )
        all_translated.extend(translate_batch(batch))

    for product, translated in zip(products, all_translated):
        product["description_en"] = translated
        product["translation_failed"] = (translated == product.get("description_nl", ""))
        # Translate title via term map (no API cost)
        product["title_en"] = translate_title(product.get("title", ""))

    return products


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_numbered_response(text: str, expected: int) -> list[str]:
    """Extract [1] ... [2] ... blocks from the API response."""
    pattern = re.compile(r"\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)", re.S)
    matches = pattern.findall(text)
    result: dict[int, str] = {}
    for num_str, content in matches:
        num = int(num_str)
        result[num] = content.strip()
    return [result.get(i + 1, "") for i in range(expected)]
