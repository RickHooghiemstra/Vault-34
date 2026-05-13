"""Tests for transformers: price, tags, seo."""

import pytest
from transformers.price import net_price, export_price, format_price
from transformers.tags import build_tags, _slug
from transformers.seo import generate_handle, seo_title, meta_description, alt_text


# ---------------------------------------------------------------------------
# Price transformer
# ---------------------------------------------------------------------------

class TestPrice:
    def test_net_price(self):
        assert abs(net_price(121.0) - 100.0) < 0.01

    def test_export_price(self):
        assert abs(export_price(121.0) - 150.0) < 0.01

    def test_known_example(self):
        # €649 RRP → net €536.36 → export €804.55
        assert abs(net_price(649.0) - 536.36) < 0.01
        assert abs(export_price(649.0) - 804.55) < 0.01

    def test_format_price(self):
        assert format_price(100.0) == "100.00"
        assert format_price(804.5537) == "804.55"


# ---------------------------------------------------------------------------
# Tag builder
# ---------------------------------------------------------------------------

def _make_product(**overrides) -> dict:
    base = {
        "title":        "Akrapovic Slip-On Honda CB650R 2019-2023",
        "brand":        "Akrapovic",
        "product_type": "Slip-On Uitlaten",
        "description_nl": "Titanium slip-on uitlaatdemper voor de Honda CB650R.",
        "fitment": {"make": "Honda", "model": "CB650R", "year": "2019-2023"},
        "breadcrumbs":  ["Uitlaten", "Slip-On Uitlaten"],
    }
    base.update(overrides)
    return base


class TestTags:
    def test_brand_tag(self):
        tags = build_tags(_make_product())
        assert "BRAND_Akrapovic" in tags

    def test_make_tag(self):
        tags = build_tags(_make_product())
        assert "MAKE_Honda" in tags

    def test_model_tag(self):
        tags = build_tags(_make_product())
        assert "MODEL_CB650R" in tags

    def test_year_expansion(self):
        tags = build_tags(_make_product())
        for yr in range(2019, 2024):
            assert f"YEAR_{yr}" in tags, f"YEAR_{yr} missing from tags"

    def test_type_slipon(self):
        tags = build_tags(_make_product())
        assert "TYPE_SlipOn" in tags

    def test_source_tag(self):
        tags = build_tags(_make_product())
        assert "source:uitlaatstore.nl" in tags

    def test_material_titanium(self):
        p = _make_product(title="Akrapovic Titanium Slip-On Honda CB650R 2019-2023")
        tags = build_tags(p)
        assert "MAT_Titanium" in tags

    def test_full_system_type(self):
        p = _make_product(
            title="Akrapovic Racing Line Uitlaatsysteem Yamaha MT-09 2021+",
            description_nl="Volledig uitlaatsysteem van titanium voor de Yamaha MT-09.",
        )
        tags = build_tags(p)
        assert "TYPE_FullSystem" in tags

    def test_no_duplicate_tags(self):
        tags = build_tags(_make_product())
        assert len(tags) == len(set(tags)), "Duplicate tags found"

    def test_open_ended_year_includes_exact_tag(self):
        p = _make_product(fitment={"make": "Yamaha", "model": "MT-09", "year": "2021+"})
        tags = build_tags(p)
        assert "YEAR_2021+" in tags
        assert "YEAR_2021" in tags

    def test_no_make_no_make_tag(self):
        p = _make_product(fitment={"make": "", "model": "", "year": ""})
        tags = build_tags(p)
        assert not any(t.startswith("MAKE_") for t in tags)


class TestSlug:
    def test_removes_spaces(self):
        assert _slug("SC-Project") == "SC_Project"

    def test_underscore_normalization(self):
        assert "__" not in _slug("Slip-On Line")


# ---------------------------------------------------------------------------
# SEO transformer
# ---------------------------------------------------------------------------

class TestSEO:
    def test_handle_basic(self):
        h = generate_handle("Akrapovic Slip-On Honda CB650R 2019-2023")
        assert h == "akrapovic-slip-on-honda-cb650r-2019-2023"

    def test_handle_deduplication(self):
        existing = {"akrapovic-slip-on-honda-cb650r-2019-2023"}
        h = generate_handle("Akrapovic Slip-On Honda CB650R 2019-2023", "SKU123", existing)
        assert h != "akrapovic-slip-on-honda-cb650r-2019-2023"
        assert "sku123" in h

    def test_seo_title_max_length(self):
        title = seo_title("Akrapovic", "Slip-On Uitlaten", "Honda", "CBR1000RR-R Fireblade", "2020+")
        assert len(title) <= 70

    def test_seo_title_contains_brand(self):
        title = seo_title("Arrow", "Slip-On", "Yamaha", "MT-09", "2021+")
        assert "Arrow" in title
        assert "Yamaha" in title

    def test_meta_description_max_length(self):
        desc = meta_description(
            "Akrapovic Slip-On Line (Titanium) Honda CB650R 2019-2023",
            "Akrapovic", "Honda", "CB650R"
        )
        assert len(desc) <= 150

    def test_alt_text_format(self):
        alt = alt_text("Akrapovic", "Slip-On", "Honda", "CB650R")
        assert alt == "Akrapovic Slip-On for Honda CB650R"

    def test_handle_unicode_stripped(self):
        h = generate_handle("Akrapovič Slip-On")
        assert "akrapovic" in h
        assert "č" not in h
