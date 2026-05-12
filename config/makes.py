"""
Motorcycle make normalization.

MOTO_MAKES  — ordered longest-first so "Royal Enfield" is matched before "Royal".
              Does NOT include exhaust brand names.
MAKE_NORM   — maps raw extracted strings to canonical display names.
"""

# Recognised motorcycle manufacturers — intentionally excludes exhaust brands
MOTO_MAKES: list[str] = [
    "Harley-Davidson",
    "Royal Enfield",
    "MV Agusta",
    "Husqvarna",
    "Gas Gas",
    "GasGas",
    "Moto Guzzi",
    "TM Racing",
    "Husaberg",
    "SWM",
    "Honda",
    "Yamaha",
    "Kawasaki",
    "Suzuki",
    "BMW",
    "Ducati",
    "KTM",
    "Triumph",
    "Aprilia",
    "Benelli",
    "CFMoto",
    "Zontes",
    "Indian",
    "Beta",
    "Sherco",
    "Piaggio",
    "Vespa",
    "Kymco",
    "Sym",
    "Peugeot",
    "Brixton",
    "Norton",
    "Zero",
    "Energica",
]

MAKE_NORM: dict[str, str] = {
    "harley":         "Harley-Davidson",
    "hd":             "Harley-Davidson",
    "harley davidson": "Harley-Davidson",
    "royal enfield":  "Royal Enfield",
    "mv agusta":      "MV Agusta",
    "mva":            "MV Agusta",
    "bmw":            "BMW",
    "ktm":            "KTM",
    "gasgas":         "GasGas",
    "gas gas":        "GasGas",
    "moto guzzi":     "Moto Guzzi",
    "husqvarna":      "Husqvarna",
    "husaberg":       "Husaberg",
}


def normalize_make(raw: str) -> str:
    """Return canonical make name."""
    key = raw.strip().lower()
    if key in MAKE_NORM:
        return MAKE_NORM[key]
    # Check if raw matches any known make (case-insensitive)
    for make in MOTO_MAKES:
        if make.lower() == key:
            return make
    return raw.strip().title()
