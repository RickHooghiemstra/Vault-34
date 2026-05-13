"""
Exhaust brand configuration.

TOP_BRANDS  — brands to scrape (slug as used in uitlaatstore.nl URLs).
BRAND_NORM  — normalises variant spellings to a canonical display name.
"""

# Ordered by priority — scrape these first, in order
# Slugs must match uitlaatstore.nl/alle-merken/{slug} exactly
TOP_BRANDS: list[str] = [
    # Tier 1 — premium / high-volume
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
    "scorpion",
    "zard",
    "laser",
    "two-brothers",
    "vance-hines",
    "cobra",
    # Tier 2 — mid-range / specialist
    "hp-corse",
    "qd",
    "bodis",
    "bos",
    "hurric",
    "giannelli",
    "marving",
    "motad",
    "exan",
    "delkevic",
    "tecnigas",
    "sito",
    "storm",
    "supertrapp",
    "silvertail",
    "predator",
    "mac",
    "ix-race",
    "fmf",
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
    "two-brothers":    "Two Brothers",
    "two brothers":    "Two Brothers",
    "vance-hines":     "Vance & Hines",
    "cobra":           "Cobra",
    "hp-corse":        "HP Corse",
    "qd":              "QD Exhaust",
    "bodis":           "Bodis",
    "bos":             "Bos",
    "hurric":          "Hurric",
    "giannelli":       "Giannelli",
    "marving":         "Marving",
    "motad":           "Motad",
    "exan":            "Exan",
    "delkevic":        "Delkevic",
    "tecnigas":        "Tecnigas",
    "sito":            "Sito",
    "storm":           "Storm",
    "supertrapp":      "Supertrapp",
    "silvertail":      "Silvertail",
    "predator":        "Predator",
    "mac":             "MAC",
    "ix-race":         "IX-Race",
    "fmf":             "FMF",
    "laser":           "Laser",
}


def normalize_brand(raw: str) -> str:
    """Return canonical brand name, or title-cased original if unknown."""
    return BRAND_NORM.get(raw.strip().lower(), raw.strip().title())
