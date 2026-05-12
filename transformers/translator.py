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
            _cache = json.loads(TRANSLATION_CACHE.read_text())
            log.info("Loaded %d cached translations", len(_cache))
        except (json.JSONDecodeError, OSError):
            _cache = {}


def _save_cache() -> None:
    TRANSLATION_CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2))


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
