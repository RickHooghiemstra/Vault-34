# Tagging Rules

All Shopify tags are generated deterministically by `transformers/tags.py`.
Never add freeform tags manually — always extend the tag builder.

## Tag Schema

| Group | Format | Example | Shopify Filter Key |
|---|---|---|---|
| Brand | `BRAND_{Name}` | `BRAND_Akrapovic` | `BRAND_` prefix |
| Make | `MAKE_{Name}` | `MAKE_Honda` | `MAKE_` prefix |
| Model | `MODEL_{Name}` | `MODEL_CB650R` | `MODEL_` prefix |
| Year | `YEAR_{YYYY}` | `YEAR_2021` | `YEAR_` prefix |
| Type | `TYPE_{type}` | `TYPE_SlipOn` | `TYPE_` prefix |
| Material | `MAT_{material}` | `MAT_Titanium` | `MAT_` prefix |
| Euro cert | `EURO_{n}` | `EURO_5` | `EURO_` prefix |
| Homologation | `HOMOLOGATED` or `RACE_ONLY` | — | exact match |
| Category | `CAT_{category}` | `CAT_FullSystem` | `CAT_` prefix |
| Source | `source:uitlaatstore.nl` | — | tracking only |

## Exhaust Types

| Keyword matched | Tag generated |
|---|---|
| slip-on, slipon, demper, outlet | `TYPE_SlipOn` |
| uitlaatsysteem, racing line, evolution line, full system | `TYPE_FullSystem` |
| decat | `TYPE_Decat` |
| linkpipe, link pipe, collector | `TYPE_LinkPipe` |
| uitlaatbochtenset | `TYPE_HeaderSet` |
| db-killer | `TYPE_DbKiller` |
| hitteschild | `TYPE_HeatShield` |
| kat, katvervanger | `TYPE_CatReplacer` |

## Year Expansion

Year ranges are expanded so filters work correctly:

- `2019-2023` → `YEAR_2019, YEAR_2020, YEAR_2021, YEAR_2022, YEAR_2023`
- `2021+` → `YEAR_2021, YEAR_2022, YEAR_2023, YEAR_2024, YEAR_2025, YEAR_2026, YEAR_2021+`
- `2022` → `YEAR_2022`

## Enabling Filters in Shopify

1. Shopify Admin → **Online Store → Navigation → Collections**
2. Open your exhaust collection → **Filters**
3. Add filter groups using tag prefix matching:
   - Filter "Brand" → tag starts with `BRAND_`
   - Filter "Motorcycle Make" → tag starts with `MAKE_`
   - Filter "Model" → tag starts with `MODEL_`
   - Filter "Year" → tag starts with `YEAR_`
   - Filter "Type" → tag starts with `TYPE_`
