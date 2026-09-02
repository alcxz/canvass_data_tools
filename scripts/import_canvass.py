"""Load the voter's list into canvass_attempts and voters.

Same-day conflicts are resolved here, in memory, before anything is written. The
export logs 20,163 rows across 19,474 distinct (door, date) pairs: 649 groups
have more than one row and 322 of those record genuinely different outcomes,
where one canvasser logged "No Answer" and another logged "Answered" at the same
door on the same day. Picking a winner per group is what makes
(household_id, attempted_on) a safe unique key in the schema.

The whole file is held in memory first, which at 20k rows is trivial and removes
any need for content hashing or database-side conflict handling.

Usage:
    python scripts/import_canvass.py \
        --file "data/Voter's List - WORKING (Aug 6).xlsx - Door Knocking Data.csv"
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from db import connect
from normalize import normalize_address, normalize_unit

# Outcome preference, best first. "No Answer" is the absence of information and
# always loses; anything else means somebody was actually reached.
OUTCOME_RANK = {
    "Supports Us": 0,
    "Answered": 1,
    "Not Interested": 2,
    "Not Voting": 3,
    "Language Barrier": 4,
    "Other": 5,
    "No Answer": 6,
}

# Support Label is a verified 1:1 function of Support Level, so it is not stored.
# The mapping lives in the frontend. Kept here only to validate the assumption.
SUPPORT_LABELS = {
    1: "Opposing",
    2: "Leaning Against",
    3: "Undecided",
    4: "Leaning For",
    5: "Supportive",
}


def parse_outcomes(raw: str) -> list[str]:
    """Split, dedupe and canonically SORT the comma-joined Outcome column.

    Sorting is load-bearing. The raw export holds 23 distinct outcome strings that
    collapse to 17 once ordered -- 'Answered, Not Interested' and
    'Not Interested, Answered' are the same observation written two ways. Stored
    unsorted they would render as two separate slices in the same pie chart, which
    still sums to 100% and so fails silently.
    """
    parts = {p.strip() for p in (raw or "").split(",") if p.strip()}
    return sorted(parts)


def parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_support(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = int(float(raw))
    except ValueError:
        return None
    return value if 1 <= value <= 5 else None


def rank(record: dict) -> tuple:
    """Sort key for choosing one row per (door, date). Lower is better.

    A row carrying a support level always beats one without: it is the scarcest
    and most valuable field, absent from 79% of rows. Outcome rank breaks the
    remaining ties, and the original file position makes re-runs deterministic.
    """
    outcome_rank = min((OUTCOME_RANK.get(o, 8) for o in record["outcomes"]), default=9)
    return (0 if record["support_level"] is not None else 1, outcome_rank, record["_row"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Import canvass results and voters.")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with args.file.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    print(f"read {len(rows):,} rows from {args.file.name}")

    with connect() as conn, conn.cursor() as cur:
        cur.execute("select address_norm, unit, id from households")
        household_ids = {(a, u): i for a, u, i in cur.fetchall()}
    print(f"loaded {len(household_ids):,} known households")

    grouped: dict[tuple[int, date], list[dict]] = defaultdict(list)
    voters: dict[tuple, dict] = {}
    skipped_unmatched = 0
    skipped_no_date = 0
    label_mismatches = 0

    for position, row in enumerate(rows):
        parsed = normalize_address(row.get("Address", ""))
        if parsed is None:
            skipped_unmatched += 1
            continue

        unit = normalize_unit(row.get("Unit")) or parsed.unit
        household_id = household_ids.get((parsed.norm, unit))
        if household_id is None:
            skipped_unmatched += 1
            continue

        attempted_on = parse_date(row.get("Date", ""))
        if attempted_on is None:
            skipped_no_date += 1
            continue

        support = parse_support(row.get("Support Level", ""))

        # Assumption check, not stored: Support Label must track Support Level.
        label = (row.get("Support Label") or "").strip()
        if support is not None and label and SUPPORT_LABELS.get(support) != label:
            label_mismatches += 1

        grouped[(household_id, attempted_on)].append({
            "household_id": household_id,
            "attempted_on": attempted_on,
            "outcomes": parse_outcomes(row.get("Outcome", "")),
            "support_level": support,
            "opposing_candidate": (row.get("Opposing Candidate") or "").strip() or None,
            "_row": position,
        })

        name = (row.get("Resident Name") or "").strip() or None
        email = (row.get("Resident Email") or "").strip() or None
        phone = (row.get("Resident Phone") or "").strip() or None
        if name or email or phone:
            voters[(household_id, name, email, phone)] = {
                "household_id": household_id, "name": name, "email": email, "phone": phone,
            }

    attempts = [min(candidates, key=rank) for candidates in grouped.values()]
    conflicts = sum(1 for c in grouped.values() if len(c) > 1)
    real_conflicts = sum(
        1 for c in grouped.values()
        if len({tuple(r["outcomes"]) for r in c}) > 1
    )
    support_kept = sum(1 for a in attempts if a["support_level"] is not None)
    support_available = sum(
        1 for c in grouped.values() if any(r["support_level"] is not None for r in c)
    )

    print()
    print(f"distinct (door, date) pairs : {len(attempts):,}")
    print(f"  groups with >1 source row : {conflicts:,}")
    print(f"  of those, differing outcome: {real_conflicts:,}")
    print(f"attempts with a support level: {support_kept:,} (of {support_available:,} available)")
    print(f"distinct voters             : {len(voters):,}")
    print(f"skipped, no household match : {skipped_unmatched:,}")
    print(f"skipped, unparseable date   : {skipped_no_date:,}")

    if support_kept < support_available:
        print(f"  WARNING: conflict resolution dropped {support_available - support_kept} "
              f"support levels; check rank()")
    if label_mismatches:
        print(f"  WARNING: {label_mismatches} rows where Support Label disagreed with "
              f"Support Level; the frontend mapping may be wrong")

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    attempt_sql = """
        insert into canvass_attempts
            (household_id, attempted_on, outcomes, support_level, opposing_candidate)
        values (%s, %s, %s, %s, %s)
        on conflict (household_id, attempted_on) do update set
            outcomes = excluded.outcomes,
            support_level = excluded.support_level,
            opposing_candidate = excluded.opposing_candidate
    """
    voter_sql = """
        insert into voters (household_id, name, email, phone)
        values (%s, %s, %s, %s)
        on conflict do nothing
    """

    with connect() as conn, conn.cursor() as cur:
        cur.executemany(attempt_sql, [
            (a["household_id"], a["attempted_on"], a["outcomes"],
             a["support_level"], a["opposing_candidate"])
            for a in attempts
        ])
        cur.executemany(voter_sql, [
            (v["household_id"], v["name"], v["email"], v["phone"]) for v in voters.values()
        ])
        conn.commit()
        cur.execute("select count(*) from canvass_attempts")
        attempt_total = cur.fetchone()[0]
        cur.execute("select count(*) from voters")
        voter_total = cur.fetchone()[0]

    print(f"\ncanvass_attempts now holds {attempt_total:,} rows")
    print(f"voters now holds {voter_total:,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
