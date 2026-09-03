"""Golden test: does an address land in the right Dissemination Area?

This is the primary correctness gate for the geocoding path. It runs the real
pipeline -- normalize -> address-point lookup -> point-in-polygon -- against a
hand-verified fixture of 39 Ward 11 addresses with known DAs.

Local only. The fixture is derived from campaign data and is gitignored, so this
skips on a fresh clone. See tests/fixtures/README.md.

Two assertions are kept separate because they fail for different reasons and want
different fixes:
  (a) the address resolved to a lat/lon at all  -> normalize.py, or address-point coverage
  (b) that lat/lon landed in the right polygon  -> geodata.py / point-in-polygon
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from build_households import load_address_points, resolve_point
from geodata import dauid_from_da_column, get_lookup
from normalize import normalize_address

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = FIXTURES / "da_golden.csv"
POINTS_SUBSET = FIXTURES / "address_points_subset.csv"
POINTS_FULL = Path(__file__).resolve().parent.parent / "data" / "toronto_address_points.csv"


def _require(path: Path, what: str):
    if not path.exists():
        pytest.skip(
            f"missing {path.relative_to(Path(__file__).resolve().parent.parent)} ({what}). "
            f"See tests/fixtures/README.md -- data files are gitignored."
        )


@pytest.fixture(scope="module")
def golden_rows():
    _require(GOLDEN, "the golden DA fixture")
    with GOLDEN.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def address_points():
    path = POINTS_SUBSET if POINTS_SUBSET.exists() else POINTS_FULL
    _require(path, "Toronto address points")
    return load_address_points(path)


@pytest.fixture(scope="module")
def resolved(golden_rows, address_points):
    """Run the real pipeline once; both assertions read from this."""
    lookup = get_lookup()
    results = []

    for row in golden_rows:
        expected = dauid_from_da_column(row["DA"])
        parsed = normalize_address(row["Address"])

        # Same resolver the importer uses, so the test cannot pass against logic
        # that build_households.py does not actually run.
        lat, _lon, actual = resolve_point(parsed, address_points, lookup)

        results.append({
            "address": row["Address"], "unit": row.get("Unit", ""),
            "expected": expected, "actual": actual, "geocoded": lat is not None,
        })

    return results


def test_fixture_dauids_all_exist_in_boundary_file(golden_rows):
    """Guards the fixture itself, so a failure below is our bug, not bad test data."""
    known = get_lookup().all_dauids()
    missing = [
        (r["Address"], r["DA"], dauid_from_da_column(r["DA"]))
        for r in golden_rows
        if dauid_from_da_column(r["DA"]) not in known
    ]
    assert not missing, f"{len(missing)} fixture DAs are not in the boundary file: {missing[:5]}"


def test_every_address_geocodes(resolved):
    """(a) Normalization and address-point coverage."""
    failures = [r for r in resolved if not r["geocoded"]]
    assert not failures, (
        f"{len(failures)}/{len(resolved)} addresses did not resolve to a lat/lon:\n"
        + "\n".join(f"  {r['address']}" for r in failures[:10])
    )


def test_every_address_lands_in_the_right_da(resolved):
    """(b) Point-in-polygon."""
    mismatches = [r for r in resolved if r["geocoded"] and r["actual"] != r["expected"]]
    assert not mismatches, (
        f"{len(mismatches)}/{len(resolved)} addresses landed in the wrong DA:\n"
        + "\n".join(
            f"  {r['address']:60} expected {r['expected']} got {r['actual']}"
            for r in mismatches[:10]
        )
    )


def test_da_column_expansion():
    """Sheets drops leading zeros inconsistently: '0918' survives but '915' does not."""
    assert dauid_from_da_column("0918") == "35200918"
    assert dauid_from_da_column("915") == "35200915"
    assert dauid_from_da_column("4156") == "35204156"
    assert dauid_from_da_column("35200746") == "35200746"
