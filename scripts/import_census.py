"""Load the Ward 11 census extract into census_da.

The export has a two-row header: row 1 is DAUID,DA,COL0..COL62,Shape_Le_1,Shape_Area
and row 2 holds the human labels. Data starts on row 3. A plain DictReader would
silently key everything as COL0..COL62, so the header is handled explicitly.

Only the columns in Planning.md's relevant-columns list are stored. The file
carries roughly 45 more (dwelling types, 24 languages, immigrants, unemployment
rate, commute times, housing suitability) which are deliberately ignored.

Usage:
    python scripts/import_census.py --file "data/Census-Data-by-DA.xlsx - ward11_da_census_ExportTable.csv"
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from db import connect
from geodata import get_lookup

# Label in header row 2 -> column in census_da. Matching on the label rather than
# the COL<n> position means a StatCan re-export that reorders columns still works,
# and a renamed label fails loudly instead of importing the wrong numbers.
COLUMN_MAP = {
    "Population, 2021": "population",
    "Total private dwellings": "total_private_dwellings",
    "Average household size": "average_household_size",
    "Prevalence of low income": "low_income_prevalence",
    "Owner": "owner",
    "Renter": "renter",
    "Car, truck or van": "commute_car",
    "Public transit": "commute_transit",
    "Walked": "commute_walk",
    "Bicycle": "commute_bike",
    "Time leaving for work - Between 5 a.m. and 5:59 a.m.": "leave_0500",
    "Time leaving for work - Between 6 a.m. and 6:59 a.m.": "leave_0600",
    "Time leaving for work - Between 7 a.m. and 7:59 a.m.": "leave_0700",
    "Time leaving for work - Between 8 a.m. and 8:59 a.m.": "leave_0800",
    "Time leaving for work - Between 9 a.m. and 11:59 a.m.": "leave_0900",
    "Time leaving for work - Between 12 p.m. and 4:59 a.m.": "leave_1200",
}

NUMERIC_COLUMNS = {c for c in COLUMN_MAP.values()
                   if c not in {"average_household_size", "low_income_prevalence"}}

EXPECTED_ROWS = 161


def parse(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    if len(rows) < 3:
        raise SystemExit(f"{path} has {len(rows)} rows; expected a two-row header plus data.")

    labels = [label.strip() for label in rows[1]]

    missing = [label for label in COLUMN_MAP if label not in labels]
    if missing:
        raise SystemExit(
            "These expected labels are missing from header row 2:\n  "
            + "\n  ".join(missing)
            + "\n\nThe export format changed. Update COLUMN_MAP rather than guessing positions."
        )

    index_of = {label: labels.index(label) for label in COLUMN_MAP}

    records = []
    for row in rows[2:]:
        if not row or not row[0].strip():
            continue  # trailing blank row

        record = {"dauid": row[0].strip()}
        for label, column in COLUMN_MAP.items():
            raw = row[index_of[label]].strip()
            if raw == "":
                raise SystemExit(
                    f"DA {record['dauid']}: '{label}' is blank. The 2021 extract has no "
                    f"gaps, so this means the file changed. Make the column nullable "
                    f"deliberately rather than importing a silent NULL."
                )
            record[column] = int(float(raw)) if column in NUMERIC_COLUMNS else float(raw)
        records.append(record)

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the Ward 11 census extract.")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and validate without writing to the database.")
    args = parser.parse_args()

    records = parse(args.file)
    print(f"parsed {len(records)} DA rows from {args.file.name}")

    known = get_lookup().all_dauids()
    unknown = sorted({r["dauid"] for r in records} - known)
    absent = sorted(known - {r["dauid"] for r in records})
    if unknown:
        print(f"  WARNING: {len(unknown)} DAUIDs not in the boundary file: {unknown[:5]}")
    if absent:
        print(f"  WARNING: {len(absent)} boundary DAs missing from the census: {absent[:5]}")
    if len(records) != EXPECTED_ROWS:
        print(f"  WARNING: expected {EXPECTED_ROWS} rows, got {len(records)}")

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    columns = ["dauid"] + list(COLUMN_MAP.values())
    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "dauid")
    statement = (
        f"insert into census_da ({', '.join(columns)}) values ({placeholders}) "
        f"on conflict (dauid) do update set {updates}"
    )

    with connect() as conn, conn.cursor() as cur:
        cur.executemany(statement, [[r[c] for c in columns] for r in records])
        conn.commit()
        cur.execute("select count(*) from census_da")
        total = cur.fetchone()[0]

    print(f"census_da now holds {total} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
