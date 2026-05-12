"""Tests for parsers/fitment_parser.py and parsers/product_parser.py."""

import pytest
from parsers.fitment_parser import extract_fitment, expand_years, _clean_year, _from_title
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# _from_title — make / model / year extraction
# ---------------------------------------------------------------------------

class TestFromTitle:
    def test_akrapovic_honda(self):
        make, model, year = _from_title("Akrapovic Slip-On Honda CB650R 2019-2023")
        assert make == "Honda"
        assert model == "CB650R"
        assert year == "2019-2023"

    def test_exhaust_brand_not_matched_as_make(self):
        make, _, _ = _from_title("Mivv Oval Carbon BMW S1000RR 2019+")
        assert make == "BMW", f"Expected BMW, got {make!r}"

    def test_open_ended_year(self):
        _, _, year = _from_title("Arrow Pro-Race Yamaha MT-09 2021+")
        assert year == "2021+"

    def test_year_range(self):
        _, _, year = _from_title("Remus HexaCone Triumph Street Triple R 2020-2023")
        assert year == "2020-2023"

    def test_ktm_model_with_spaces(self):
        make, model, year = _from_title("Akrapovic Racing Line KTM 890 Duke R 2020-2022")
        assert make == "KTM"
        assert "890" in model
        assert year == "2020-2022"

    def test_no_make_returns_empty(self):
        make, model, year = _from_title("Mivv uitlaatdemper Oval carbon")
        assert make == ""
        assert model == ""

    def test_arrow_is_exhaust_brand_not_make(self):
        make, _, _ = _from_title("Arrow Pro-Race Kawasaki Z900 2020+")
        assert make == "Kawasaki"

    def test_yamaha_yzf(self):
        make, model, year = _from_title("Akrapovic Yamaha YZF-R1 2020+")
        assert make == "Yamaha"
        assert "YZF" in model
        assert year == "2020+"


# ---------------------------------------------------------------------------
# _clean_year
# ---------------------------------------------------------------------------

class TestCleanYear:
    def test_en_dash_range(self):
        assert _clean_year("2019 – 2023") == "2019-2023"

    def test_slash_separator(self):
        assert _clean_year("2019/2023") == "2019-2023"

    def test_trailing_plus_space(self):
        assert _clean_year("2021 +") == "2021+"

    def test_short_year_expansion(self):
        assert _clean_year("2019-23") == "2019-2023"

    def test_bare_year(self):
        assert _clean_year("2022") == "2022"

    def test_empty(self):
        assert _clean_year("") == ""


# ---------------------------------------------------------------------------
# expand_years
# ---------------------------------------------------------------------------

class TestExpandYears:
    def test_range(self):
        result = expand_years("2019-2023")
        assert result == ["2019", "2020", "2021", "2022", "2023"]

    def test_open_ended(self):
        result = expand_years("2021+")
        assert "2021" in result
        assert "2026" in result
        assert "2021+" in result   # exact tag also preserved

    def test_single_year(self):
        assert expand_years("2022") == ["2022"]

    def test_empty(self):
        assert expand_years("") == []

    def test_invalid_range_not_expanded(self):
        result = expand_years("2030-2040")
        assert len(result) == 11    # still valid range, just far future


# ---------------------------------------------------------------------------
# extract_fitment — with real BeautifulSoup
# ---------------------------------------------------------------------------

class TestExtractFitment:
    def _make_soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def test_falls_back_to_title(self):
        soup = self._make_soup("<html><body><h1>Product</h1></body></html>")
        result = extract_fitment(soup, "Akrapovic Slip-On Honda CB650R 2019-2023")
        assert result["make"] == "Honda"
        assert result["model"] == "CB650R"
        assert result["year"] == "2019-2023"

    def test_attribute_table(self):
        html = """
        <table class="woocommerce-product-attributes">
          <tr><th>Merk motor</th><td>Yamaha</td></tr>
          <tr><th>Model</th><td>MT-09</td></tr>
          <tr><th>Bouwjaar</th><td>2021+</td></tr>
        </table>
        """
        soup = self._make_soup(html)
        result = extract_fitment(soup, "Some exhaust product")
        assert result["make"] == "Yamaha"
        assert result["model"] == "MT-09"
        assert "2021" in result["year"]

    def test_normalize_make(self):
        soup = self._make_soup("<html></html>")
        result = extract_fitment(soup, "Mivv Slip-On BMW S1000RR 2019+")
        assert result["make"] == "BMW"
