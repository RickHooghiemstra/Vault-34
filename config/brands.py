"""
Exhaust brand configuration.

TOP_BRANDS  — brands to scrape (slug as used in uitlaatstore.nl URLs).
BRAND_NORM  — normalises variant spellings to a canonical display name.
"""

# Ordered by priority — scrape these first, in order
TOP_BRANDS: list[str] = [
    "akrapovic",
    "arrow",
    "sc-project",
    "mivv",
    "yoshimura",
    "leovince",
    "remus",
    "gpr",
    "termignoni",
    "ixil",
    "spark",
    "zard",
    "scorpion",
    "laser",
    "racefit",
    "austin-racing",
]

# Canonical display names for tag generation and Shopify Vendor field
BRAND_NORM: dict[str, str] = {
    "akrapovic":       "Akrapovic",
    "akrapovič":       "Akrapovic",
    "arrow":           "Arrow",
    "sc-project":      "SC-Project",
    "sc project":      "SC-Project",
    "mivv":            "Mivv",
    "yoshimura":       "Yoshimura",
    "leovince":        "LeoVince",
    "leo vince":       "LeoVince",
    "remus":           "Remus",
    "gpr":             "GPR",
    "termignoni":      "Termignoni",
    "ixil":            "Ixil",
    "spark":           "Spark",
    "zard":            "Zard",
    "scorpion":        "Scorpion",
    "laser":           "Laser",
    "racefit":         "Racefit",
    "austin-racing":   "Austin Racing",
    "austin racing":   "Austin Racing",
    "two brothers":    "Two Brothers",
    "hindle":          "Hindle",
    "cobra":           "Cobra",
    "vance & hines":   "Vance & Hines",
    "vance and hines": "Vance & Hines",
    "graves":          "Graves Motorsports",
    "qd exhaust":      "QD Exhaust",
    "hp corse":        "HP Corse",
    "hpcorse":         "HP Corse",
    "takkoni":         "Takkoni",
    "brocks":          "Brocks",
    "rizoma":          "Rizoma",
}


def normalize_brand(raw: str) -> str:
    """Return canonical brand name, or title-cased original if unknown."""
    return BRAND_NORM.get(raw.strip().lower(), raw.strip().title())
