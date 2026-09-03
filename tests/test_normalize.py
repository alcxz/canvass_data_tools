"""Unit tests for address normalization.

This module's failure mode is silent: a normalizer that treats "123 Main St" and
"123 Main Street" as different addresses splits one door into two, and every
count downstream inherits the error without anything looking broken.
"""

import pytest

from normalize import normalize_address, normalize_unit


class TestGoogleFormat:
    """The voter's list format: full Google-formatted strings with postal codes."""

    def test_parses_street_and_postal_code(self):
        parsed = normalize_address("18 Page Street, Toronto, Ontario M6G 1J2, Canada")
        assert parsed.number == "18"
        assert parsed.street == "PAGE STREET"
        assert parsed.postal_code == "M6G1J2"

    def test_lowercase_postal_code(self):
        # The export mixes "M5S 2H8" and "M5s 2j6".
        parsed = normalize_address("736 Spadina Avenue, Toronto, Ontario M5s 2j6, Canada")
        assert parsed.postal_code == "M5S2J6"

    def test_directional_is_kept(self):
        parsed = normalize_address("77 Gerrard Street West, Toronto, Ontario M5g 2a1, Canada")
        assert parsed.street == "GERRARD STREET WEST"

    def test_missing_postal_code(self):
        # 7 of the 39 golden rows have no postal code.
        parsed = normalize_address("5 Tacoma Avenue, Toronto, Ontario")
        assert parsed.number == "5"
        assert parsed.street == "TACOMA AVENUE"
        assert parsed.postal_code is None


class TestAbbreviationFallback:
    """Defensive handling for rows that are not Google-formatted."""

    @pytest.mark.parametrize("raw", [
        "123 Main St",
        "123 Main Street",
        "123 MAIN ST.",
        "123 main street",
    ])
    def test_street_type_variants_agree(self, raw):
        assert normalize_address(raw).key == ("123", "MAIN STREET")

    @pytest.mark.parametrize("raw", [
        "123 Bloor St W",
        "123 Bloor Street West",
        "123 BLOOR ST. W.",
    ])
    def test_directional_variants_agree(self, raw):
        assert normalize_address(raw).key == ("123", "BLOOR STREET WEST")

    @pytest.mark.parametrize("raw", [
        "151 St. George Street",
        "151 Saint George Street",
        "151 St George St",
    ])
    def test_saint_george_variants_agree(self, raw):
        # Leading "St" is Saint, not Street -- the golden fixture has two of these.
        assert normalize_address(raw).key == ("151", "SAINT GEORGE STREET")

    def test_avenue_and_boulevard(self):
        assert normalize_address("385 Montrose Ave").key == ("385", "MONTROSE AVENUE")
        assert normalize_address("311 Palmerston Blvd").key == ("311", "PALMERSTON BOULEVARD")


class TestEmbeddedUnits:
    @pytest.mark.parametrize("raw", [
        "Apt 4 - 123 Main St",
        "#4-123 Main St",
        "Unit 4, 123 Main Street",
        "123 Main St #4",
        "123 Main Street Apt 4",
    ])
    def test_unit_is_extracted_and_address_agrees(self, raw):
        parsed = normalize_address(raw)
        assert parsed.key == ("123", "MAIN STREET")
        assert parsed.unit == "4"


class TestRangeVersusUnit:
    """"<number>-<number>" is ambiguous, and guessing wrong merges distinct doors.

    A range ascends; a unit does not. Getting this backwards puts two units in one
    household, whose attempts then collide on (household_id, attempted_on) and
    overwrite each other.
    """

    @pytest.mark.parametrize("raw,number", [
        ("123-125 Bloor Street West", "123"),
        ("1128-1132 Dundas Street West", "1128"),   # real row in the export
        ("730-732 Crawford Street", "730"),
    ])
    def test_ascending_pair_is_an_address_range(self, raw, number):
        parsed = normalize_address(raw)
        assert parsed.number == number
        assert parsed.unit == ""

    @pytest.mark.parametrize("raw,unit", [
        ("730-1 Crawford Street", "1"),             # real row in the export
        ("730 -2 Crawford Street", "2"),            # real row, space before the dash
        ("100-4 Main Street", "4"),
    ])
    def test_descending_pair_is_a_unit(self, raw, unit):
        parsed = normalize_address(raw)
        assert parsed.key == (raw.split("-")[0].strip().split()[0], parsed.street)
        assert parsed.unit == unit

    def test_explicit_marker_still_wins(self):
        # "Apt 4 - 123" must stay a unit even though 4 < 123 would also say so.
        assert normalize_address("Apt 4 - 123 Main St").unit == "4"


class TestEdgeCases:
    def test_address_range_takes_first_number(self):
        assert normalize_address("123-125 Bloor Street West").number == "123"

    def test_lettered_street_number(self):
        assert normalize_address("12A Page Street").number == "12A"

    @pytest.mark.parametrize("raw", ["", "   ", None, "Toronto, Ontario", "no number here"])
    def test_unparseable_returns_none(self, raw):
        assert normalize_address(raw) is None

    def test_street_named_west_is_not_mangled(self):
        # Only a *trailing* directional is expanded.
        assert normalize_address("10 West Lodge Avenue").street == "WEST LODGE AVENUE"


class TestNormalizeUnit:
    @pytest.mark.parametrize("raw,expected", [
        ("119", "119"),
        ("Apt 4", "4"),
        ("#1102", "1102"),
        ("Lower", "LOWER"),      # row 39 of the golden fixture
        ("-3", "3"),             # real row: "-3" and "3" must be the same door
        ("", ""),
        (None, ""),
    ])
    def test_units(self, raw, expected):
        assert normalize_unit(raw) == expected

    def test_blank_is_empty_string_never_none(self):
        # The schema stores '' so UNIQUE constraints actually fire.
        assert normalize_unit(None) == ""
        assert normalize_unit("") == ""
