"""Aggregate queries. All the arithmetic happens in Postgres, not in Python."""

from __future__ import annotations

from db import query

CENSUS_COLUMNS = [
    "population", "total_private_dwellings", "average_household_size",
    "low_income_prevalence", "owner", "renter",
    "commute_car", "commute_transit", "commute_walk", "commute_bike",
    "leave_0500", "leave_0600", "leave_0700", "leave_0800", "leave_0900", "leave_1200",
]

# One row per DA. Feeds the choropleth, so it must stay small -- 161 rows.
# doors_total is every known door in the DA; doors_knocked is those with at least
# one attempt. Coverage is measured against census dwellings rather than known
# doors, because the voter's list only contains addresses somebody has visited.
DA_SUMMARY = """
    select
        c.dauid,
        c.total_private_dwellings,
        count(h.id)                                      as doors_total,
        count(cl.household_id)                           as doors_knocked,
        coalesce(sum(cl.attempts), 0)                    as attempts,
        count(cl.support_level)                          as doors_with_support,
        round(avg(cl.support_level)::numeric, 2)         as avg_support,
        case
            when c.total_private_dwellings > 0
            then round(100.0 * count(cl.household_id) / c.total_private_dwellings, 1)
        end                                              as coverage_pct
    from census_da c
    left join households h on h.dauid = c.dauid
    left join canvass_latest cl on cl.household_id = h.id
    group by c.dauid, c.total_private_dwellings
    order by c.dauid
"""

DA_CENSUS = f"select dauid, {', '.join(CENSUS_COLUMNS)} from census_da where dauid = %s"

# Support distribution for one DA, including the doors with no support level
# recorded -- which is most of them, so the null bucket is not optional.
DA_SUPPORT = """
    select cl.support_level, count(*) as doors
    from households h
    join canvass_latest cl on cl.household_id = h.id
    where h.dauid = %s
    group by cl.support_level
    order by cl.support_level nulls last
"""

# Combination view: one row per attempt, so these sum to exactly 100%.
# array_to_string is safe because outcomes is stored canonically sorted.
DA_OUTCOME_COMBINATIONS = """
    select array_to_string(a.outcomes, '+') as combination, count(*) as attempts
    from households h
    join canvass_attempts a on a.household_id = h.id
    where h.dauid = %s
    group by 1
    order by attempts desc
"""

# Atomic view: one attempt can contribute to several rows, so this does NOT sum
# to 100%. Answers "how many attempts ever reached someone?", which the
# combination view cannot.
DA_OUTCOME_ATOMS = """
    select unnest(a.outcomes) as outcome, count(*) as attempts
    from households h
    join canvass_attempts a on a.household_id = h.id
    where h.dauid = %s
    group by 1
    order by attempts desc
"""

DA_VOTERS = """
    select
        v.id, v.name, v.email, v.phone,
        h.address_raw as address, h.unit,
        cl.support_level, cl.last_attempted_on
    from households h
    join voters v on v.household_id = h.id
    left join canvass_latest cl on cl.household_id = h.id
    where h.dauid = %s
    order by h.address_raw, h.unit, v.name nulls last
"""


def da_summary() -> list[dict]:
    return query(DA_SUMMARY)


def da_detail(dauid: str) -> dict | None:
    census = query(DA_CENSUS, (dauid,))
    if not census:
        return None

    support = query(DA_SUPPORT, (dauid,))
    return {
        "dauid": dauid,
        "census": census[0],
        "support_levels": support,
        "outcome_combinations": query(DA_OUTCOME_COMBINATIONS, (dauid,)),
        "outcome_atoms": query(DA_OUTCOME_ATOMS, (dauid,)),
        "doors_knocked": sum(row["doors"] for row in support),
    }


def da_voters(dauid: str) -> list[dict]:
    return query(DA_VOTERS, (dauid,))
