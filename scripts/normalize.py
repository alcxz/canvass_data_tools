"""Address normalization shared by every ingest script and by the tests.

The voter's list stores Google-formatted addresses:

    "18 Page Street, Toronto, Ontario M6G 1J2, Canada"

so the primary parse is simply "split on commas and take field 0". Street types
are already expanded there and directionals spelled out. The abbreviation
handling below is a defensive fallback -- the full export is not guaranteed to be
as uniform as the sample, and the Toronto address-point file uses its own
conventions that have to be normalized to the same shape.

The failure mode of this module is silent duplicate doors, which is why it is
tested directly rather than only through the loaders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches "M6G 1J2" / "M6G1J2" / "m6g 1j2".
POSTAL_RE = re.compile(r"^[A-Z]\d[A-Z]\s*\d[A-Z]\d$", re.IGNORECASE)

# Comma fields that carry no addressing information.
_NOISE_FIELDS = {"TORONTO", "ONTARIO", "ON", "CANADA", "CA"}

# Trailing street types. Google spells these out; the address-point file may not.
_STREET_TYPES = {
    "ST": "STREET", "STR": "STREET",
    "AVE": "AVENUE", "AV": "AVENUE",
    "RD": "ROAD",
    "BLVD": "BOULEVARD", "BLV": "BOULEVARD",
    "DR": "DRIVE",
    "CRES": "CRESCENT", "CR": "CRESCENT",
    "CT": "COURT",
    "PL": "PLACE",
    "SQ": "SQUARE",
    "TER": "TERRACE",
    "PKWY": "PARKWAY", "PKY": "PARKWAY",
    "LN": "LANE",
    "GDNS": "GARDENS", "GDN": "GARDENS",
    "HTS": "HEIGHTS",
    "CIR": "CIRCLE",
    "TRL": "TRAIL",
    "WAY": "WAY",
    "MEWS": "MEWS",
    "PATH": "PATH",
    "GATE": "GATE",
    "PARK": "PARK",
}

# Trailing directionals.
_DIRECTIONALS = {
    "W": "WEST", "E": "EAST", "N": "NORTH", "S": "SOUTH",
    "NW": "NORTHWEST", "NE": "NORTHEAST",
    "SW": "SOUTHWEST", "SE": "SOUTHEAST",
}

# Unit prefixes seen in free-text addresses.
_UNIT_WORDS = r"(?:APT|APARTMENT|UNIT|SUITE|STE|#|NO\.?|RM|ROOM|PH)"

# "Apt 4 - 123 Main St" / "#4-123 Main St" / "Unit 4, 123 Main St"
_LEADING_UNIT_RE = re.compile(
    rf"^\s*{_UNIT_WORDS}?\s*([A-Z0-9][A-Z0-9\-]*)\s*[-,]\s*(?=\d)", re.IGNORECASE
)
# "123 Main St #4" / "123 Main St Apt 4"
_TRAILING_UNIT_RE = re.compile(rf"\s+{_UNIT_WORDS}\s*([A-Z0-9][A-Z0-9\-]*)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Address:
    """A normalized address.

    ``key`` is what joins the voter's list to the Toronto address points, and what
    deduplicates households. ``unit`` is only populated when one was embedded in
    the address string; the voter's list carries units in their own column.
    """

    number: str
    street: str
    postal_code: str | None = None
    unit: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.number, self.street)

    @property
    def norm(self) -> str:
        return f"{self.number} {self.street}".strip()


def _strip_punctuation(text: str) -> str:
    text = text.replace(".", " ").replace("'", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _expand_tokens(tokens: list[str]) -> list[str]:
    """Expand a trailing directional and street type, plus a leading 'St.' -> Saint.

    Order matters: the directional is checked first because it sits outermost, as
    in "Gerrard Street West". Only trailing positions are touched, so a street
    genuinely named "West Lodge" keeps its name.
    """
    if not tokens:
        return tokens

    # Leading "ST" is Saint (as in "Saint George Street"), never Street.
    if len(tokens) > 1 and tokens[0] == "ST":
        tokens = ["SAINT"] + tokens[1:]

    if len(tokens) > 1 and tokens[-1] in _DIRECTIONALS:
        tokens = tokens[:-1] + [_DIRECTIONALS[tokens[-1]]]
        if len(tokens) > 2 and tokens[-2] in _STREET_TYPES:
            tokens = tokens[:-2] + [_STREET_TYPES[tokens[-2]], tokens[-1]]
        return tokens

    if len(tokens) > 1 and tokens[-1] in _STREET_TYPES:
        tokens = tokens[:-1] + [_STREET_TYPES[tokens[-1]]]

    return tokens


def normalize_address(raw: str) -> Address | None:
    """Normalize a free-text address. Returns None if no street number is found."""
    if not raw or not raw.strip():
        return None

    fields = [f.strip() for f in raw.split(",") if f.strip()]
    if not fields:
        return None

    postal_code = None
    street_field = None

    for field in fields:
        upper = _strip_punctuation(field).upper()
        if not upper:
            continue

        # "Ontario M6G 1J2" arrives as one field; peel the postal code off the end.
        parts = upper.split()
        if len(parts) >= 2 and POSTAL_RE.match(" ".join(parts[-2:])):
            postal_code = "".join(parts[-2:])
            upper = " ".join(parts[:-2]).strip()
        elif POSTAL_RE.match(upper):
            postal_code = upper.replace(" ", "")
            continue

        if not upper or upper in _NOISE_FIELDS:
            continue
        if street_field is None:
            street_field = upper

    if street_field is None:
        return None

    unit = ""

    match = _LEADING_UNIT_RE.match(street_field)
    if match:
        unit = match.group(1)
        street_field = street_field[match.end():].strip()

    match = _TRAILING_UNIT_RE.search(street_field)
    if match:
        unit = match.group(1)
        street_field = street_field[: match.start()].strip()

    # Street number, optionally a range ("123-125") -- take the first number.
    number_match = re.match(r"^(\d+)(?:\s*-\s*\d+)?\s*([A-Z]?)\s+(.*)$", street_field)
    if not number_match:
        return None

    number = number_match.group(1)
    suffix = number_match.group(2)
    remainder = number_match.group(3).strip()
    if suffix:
        number = f"{number}{suffix}"

    street = " ".join(_expand_tokens(remainder.split()))
    if not street:
        return None

    return Address(number=number, street=street, postal_code=postal_code, unit=unit)


def normalize_unit(raw: str | None) -> str:
    """Normalize the voter's list Unit column.

    Never returns None: the schema stores '' rather than NULL so that UNIQUE
    constraints actually fire for the 5,120 rows with no unit.
    """
    if raw is None:
        return ""
    unit = _strip_punctuation(str(raw)).upper()
    unit = re.sub(rf"^{_UNIT_WORDS}\s*", "", unit, flags=re.IGNORECASE).strip()
    return unit
