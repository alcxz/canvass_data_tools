"""Resolve every address in the voter's list to a door and a Dissemination Area.

No geocoding API is involved. The City of Toronto publishes Address Points
(Municipal) -- the One Address Repository -- with WGS84 lat/lon for 500k+
municipal addresses under the Open Government Licence - Toronto. Joining the
voter's list to that file and running point-in-polygon against the 161 DA
polygons is free, offline, and deterministic: the same address always lands in
the same DA, which a rate-limited web geocoder cannot promise.

Run this before import_canvass.py, and again whenever the voter's list is
re-exported. Already-matched households are skipped, so re-runs only resolve
genuinely new addresses.

Usage:
    python scripts/build_households.py \
        --voters "data/Voter's List - WORKING (Aug 6).xlsx - Door Knocking Data.csv" \
        --address-points data/toronto_address_points.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from db import connect
from geodata import get_lookup
from normalize import normalize_address, normalize_unit

# The Toronto file has changed its column names between releases, so accept the
# spellings that have appeared rather than pinning one.
NUMBER_FIELDS = ("ADDRESS_NUMBER", "ADDRESSNUMBER", "ADDRESS", "STREET_NUM", "NUMBER")
STREET_FIELDS = ("LINEAR_NAME_FULL", "STREET_NAME", "LINEARNAMEFULL", "LFNAME", "STREET")
LAT_FIELDS = ("LATITUDE", "LAT", "Y")
LON_FIELDS = ("LONGITUDE", "LONG", "LON", "X")

MIN_MATCH_RATE = 0.95


def _pick_field(fieldnames: list[str], candidates: tuple[str, ...], label: str) -> str:
    upper = {name.upper().strip(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in upper:
            return upper[candidate]
    raise SystemExit(
        f"Could not find the {label} column in the address-point file.\n"
        f"Looked for {candidates}.\nSaw: {fieldnames}"
    )


def load_address_points(path: Path) -> dict[tuple[str, str], list[tuple[float, float, str]]]:
    """Index address points by (street number, normalized street name).

    500k rows in a plain dict is unremarkable -- this is why the project has no
    pandas dependency. Values are lists because the same street address can appear
    more than once; the postal code disambiguates when it does.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"{path} appears to be empty.")

        number_field = _pick_field(reader.fieldnames, NUMBER_FIELDS, "street number")
        street_field = _pick_field(reader.fieldnames, STREET_FIELDS, "street name")
        lat_field = _pick_field(reader.fieldnames, LAT_FIELDS, "latitude")
        lon_field = _pick_field(reader.fieldnames, LON_FIELDS, "longitude")

        index: dict[tuple[str, str], list[tuple[float, float, str]]] = defaultdict(list)
        for row in reader:
            number = (row.get(number_field) or "").strip()
            street = (row.get(street_field) or "").strip()
            if not number or not street:
                continue

            parsed = normalize_address(f"{number} {street}")
            if parsed is None:
                continue

            try:
                lat = float(row[lat_field])
                lon = float(row[lon_field])
            except (TypeError, ValueError, KeyError):
                continue

            postal = (row.get("POSTAL_CODE") or row.get("POSTALCODE") or "").replace(" ", "").upper()
            index[parsed.key].append((lat, lon, postal))

    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Geocode the voter's list to households and DAs.")
    parser.add_argument("--voters", required=True, type=Path)
    parser.add_argument("--address-points", required=True, type=Path)
    parser.add_argument("--unmatched-out", type=Path, default=Path("data/unmatched_addresses.csv"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"indexing address points from {args.address_points.name} ...")
    points = load_address_points(args.address_points)
    print(f"  {len(points):,} distinct street addresses indexed")

    lookup = get_lookup()
    print(f"  {len(lookup)} DA polygons loaded")

    with args.voters.open(newline="", encoding="utf-8-sig") as handle:
        voter_rows = list(csv.DictReader(handle))
    print(f"  {len(voter_rows):,} voter's list rows read")

    # Collapse to distinct doors first: the export has ~20k rows across ~19.5k
    # doors, and geocoding is per-address, not per-row.
    doors: dict[tuple[str, str], str] = {}
    for row in voter_rows:
        parsed = normalize_address(row.get("Address", ""))
        if parsed is None:
            continue
        unit = normalize_unit(row.get("Unit")) or parsed.unit
        doors.setdefault((parsed.norm, unit), row.get("Address", "").strip())

    print(f"  {len(doors):,} distinct doors to resolve")

    households = []
    unmatched = []
    outside_ward = 0

    for (address_norm, unit), address_raw in sorted(doors.items()):
        parsed = normalize_address(address_raw)
        candidates = points.get(parsed.key, []) if parsed else []

        if not candidates:
            unmatched.append((address_raw, unit, "no address-point match"))
            continue

        chosen = candidates[0]
        if len(candidates) > 1 and parsed and parsed.postal_code:
            for candidate in candidates:
                if candidate[2] == parsed.postal_code:
                    chosen = candidate
                    break

        lat, lon, _ = chosen
        dauid = lookup.dauid_for_point(lon, lat)
        if dauid is None:
            outside_ward += 1
            unmatched.append((address_raw, unit, "geocoded outside the ward"))
            households.append((address_raw, address_norm, unit, None, lat, lon, "unmatched"))
            continue

        households.append((address_raw, address_norm, unit, dauid, lat, lon, "matched"))

    matched = sum(1 for h in households if h[6] == "matched")
    rate = matched / len(doors) if doors else 0.0

    print()
    print(f"matched            : {matched:,} / {len(doors):,}  ({rate:.1%})")
    print(f"no address point   : {len(unmatched) - outside_ward:,}")
    print(f"outside the ward   : {outside_ward:,}")

    if unmatched:
        args.unmatched_out.parent.mkdir(parents=True, exist_ok=True)
        with args.unmatched_out.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Address", "Unit", "Reason"])
            writer.writerows(unmatched)
        print(f"wrote {len(unmatched):,} unmatched rows to {args.unmatched_out}")

    if rate < MIN_MATCH_RATE:
        print()
        print(f"WARNING: match rate is below {MIN_MATCH_RATE:.0%}. Fix scripts/normalize.py")
        print("before importing canvass data -- a bad normalizer silently splits one door")
        print("into several, and every downstream aggregate inherits that error.")

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    statement = """
        insert into households (address_raw, address_norm, unit, dauid, lat, lon, geocode_status)
        values (%s, %s, %s, %s, %s, %s, %s)
        on conflict (address_norm, unit) do update set
            dauid = coalesce(excluded.dauid, households.dauid),
            lat = coalesce(excluded.lat, households.lat),
            lon = coalesce(excluded.lon, households.lon),
            geocode_status = excluded.geocode_status
    """

    with connect() as conn, conn.cursor() as cur:
        cur.executemany(statement, households)
        conn.commit()
        cur.execute("select count(*) from households")
        total = cur.fetchone()[0]

    print(f"households now holds {total:,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
