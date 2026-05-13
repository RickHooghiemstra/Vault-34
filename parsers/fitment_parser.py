"""
Motorcycle fitment (make / model / year) extraction.

Priority:
  1. Structured fitment table on the product page
  2. Product attributes table (WooCommerce-style or custom)
  3. Regex against product title + breadcrumbs
"""

import re
import datetime
from typing import Optional
from bs4 import BeautifulSoup

from config.makes import MOTO_MAKES, normalize_make

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def extract_fitment(soup: BeautifulSoup, title: str) -> dict:
    """Return {'make': str, 'model': str, 'year': str}."""
    make = model = year = ""

    # 1. Structured compatibility / fitment table
    make, model, year = _from_fitment_table(soup)

    # 2. WooCommerce product attribute table
    if not make or not model:
        t_make, t_model, t_year = _from_attribute_table(soup)
        if not make:
            make = t_make
        if not model:
            model = t_model
        if not year:
            year = t_year

    # 3. Regex against title
    if not make or not model or not year:
        r_make, r_model, r_year = _from_title(title)
        if not make:
            make = r_make
        if not model:
            model = r_model
        if not year:
            year = r_year

    return {
        "make":  normalize_make(make) if make else "",
        "model": model.strip(),
        "year":  _clean_year(year),
    }


# ---------------------------------------------------------------------------
# Strategy 1 — fitment / compatibility table
# ---------------------------------------------------------------------------

_FITMENT_TABLE_PATTERNS = re.compile(
    r"fitment|compatibility|geschikt|passend|motor|motorfiets", re.I
)
_MAKE_LABELS  = {"merk", "merk motor", "fabrikant", "make", "brand motor", "motortype"}
_MODEL_LABELS = {"model", "model motor", "type", "uitvoering", "motormodel"}
_YEAR_LABELS  = {"bouwjaar", "jaar", "year", "jaargang", "bj", "bouwjaren"}


def _from_fitment_table(soup: BeautifulSoup) -> tuple[str, str, str]:
    make = model = year = ""
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if caption and _FITMENT_TABLE_PATTERNS.search(caption.get_text()):
            for row in table.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
                if len(cells) >= 2:
                    label, value = cells[0].lower(), cells[1]
                    if label in _MAKE_LABELS and not make:
                        make = value
                    elif label in _MODEL_LABELS and not model:
                        model = value
                    elif label in _YEAR_LABELS and not year:
                        year = value
    return make, model, year


# ---------------------------------------------------------------------------
# Strategy 2 — attribute table
# ---------------------------------------------------------------------------

def _from_attribute_table(soup: BeautifulSoup) -> tuple[str, str, str]:
    make = model = year = ""
    attr_table = soup.find(
        "table",
        class_=re.compile(r"woocommerce-product-attributes|shop_attributes|product-attributes"),
    )
    if not attr_table:
        return make, model, year
    for row in attr_table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label = th.get_text(strip=True).lower()
        value = td.get_text(separator=" ", strip=True)
        if label in _MAKE_LABELS and not make:
            make = value
        elif label in _MODEL_LABELS and not model:
            model = value
        elif label in _YEAR_LABELS and not year:
            year = value
    return make, model, year


# ---------------------------------------------------------------------------
# Strategy 3 — title regex
# ---------------------------------------------------------------------------

def _from_title(title: str) -> tuple[str, str, str]:
    make = model = year = ""

    # Year — try "2021+" before bare "2021" to avoid early match
    year_m = re.search(
        r"(?<!\d)(20\d{2}\+|20\d{2}[–\-/](?:20)?\d{2}|20\d{2})(?!\d)", title
    )
    if year_m:
        year = year_m.group(1)

    # Make — scan MOTO_MAKES (exhaust brands are deliberately excluded)
    for mk in MOTO_MAKES:
        if re.search(rf"\b{re.escape(mk)}\b", title, re.I):
            make = mk
            mk_pos = title.lower().index(mk.lower())
            after = title[mk_pos + len(mk):]
            after = re.sub(r"^\s*[-–—/]\s*", "", after)
            after = re.sub(r"\b(abs|se|sp|rs|euro\s*\d|e5|e4)\b", "", after, flags=re.I)
            model_m = re.match(
                r"\s*([A-Z0-9]{1,4}[\w\-\.]{0,25}(?:\s+[A-Z0-9][\w\-\.]{0,20})?)",
                after,
            )
            if model_m:
                candidate = model_m.group(1).strip()
                candidate = re.sub(r"\s*20\d{2}.*$", "", candidate).rstrip("-–—/., ")
                if len(candidate) >= 2:
                    model = candidate
            break

    return make, model, year


# ---------------------------------------------------------------------------
# Year helpers
# ---------------------------------------------------------------------------

def _clean_year(raw: str) -> str:
    """'2019 - 2023' → '2019-2023',  '2021 +' → '2021+'."""
    if not raw:
        return ""
    y = re.sub(r"\s*[–—]\s*", "-", raw)
    y = re.sub(r"\s*/\s*", "-", y)
    y = re.sub(r"\s+\+", "+", y)
    y = re.sub(r"\s+", "", y)
    y = re.sub(r"(20\d{2})-(\d{2})$", lambda m: f"{m.group(1)}-20{m.group(2)}", y)
    return y.strip()


def expand_years(year_str: str) -> list[str]:
    """
    '2019-2023' → ['2019','2020','2021','2022','2023']
    '2021+'     → ['2021','2022','2023','2024','2025','2026', '2021+']
    '2022'      → ['2022']
    """
    current = datetime.date.today().year

    m = re.match(r"(20\d{2})-(20\d{2})$", year_str)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if 2000 <= start <= end <= 2040:
            return [str(y) for y in range(start, end + 1)]

    m = re.match(r"(20\d{2})\+$", year_str)
    if m:
        start = int(m.group(1))
        if 2000 <= start <= current:
            years = [str(y) for y in range(start, current + 1)]
            years.append(year_str)
            return years

    return [year_str] if year_str else []
