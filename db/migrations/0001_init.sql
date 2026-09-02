-- Ward 11 Canvass Data Tool — initial schema
--
-- Column scope is deliberately limited to the "Relevant Columns" list in Planning.md.
-- The source files carry considerably more (≈45 extra census columns; Knocked By,
-- Notes and In Contacts on the voter's list). Those are ignored by the importers.

begin;

-- ---------------------------------------------------------------------------
-- census_da: one row per Dissemination Area. 161 rows for Ward 11.
--
-- Every column is NOT NULL: the 2021 extract was checked cell by cell and has no
-- blanks, no StatCan suppression markers (x, F, ..) and no non-numeric values.
-- A frozen extract that won't change is better served by a loud import failure
-- than by silent nulls.
--
-- No dguid column: the field labelled "GEO UID" in the export is the DAUID. The
-- boundary file's true DGUID ('2021S051235200746') is a pure function of the
-- DAUID -- '2021S0512' || dauid -- so storing it only creates a column that can
-- disagree with itself.
-- ---------------------------------------------------------------------------
create table census_da (
    dauid                     text     primary key,
    population                integer  not null,
    total_private_dwellings   integer  not null,
    average_household_size    numeric  not null,
    low_income_prevalence     numeric  not null,
    owner                     integer  not null,
    renter                    integer  not null,
    commute_car               integer  not null,
    commute_transit           integer  not null,
    commute_walk              integer  not null,
    commute_bike              integer  not null,
    leave_0500                integer  not null,
    leave_0600                integer  not null,
    leave_0700                integer  not null,
    leave_0800                integer  not null,
    leave_0900                integer  not null,
    leave_1200                integer  not null
);

comment on column census_da.commute_car is
    'Commute mode and time-leaving counts come from the 25% long-form sample and '
    'do not sum against population. DA counts are randomly rounded to 5.';

-- ---------------------------------------------------------------------------
-- households: one row per physical door. The join key for everything else.
--
-- Address strings are never used as foreign keys; address_norm exists only to
-- deduplicate the import. unit is NOT NULL DEFAULT '' because a nullable column
-- in a UNIQUE constraint never conflicts in Postgres, which would let every
-- no-unit house re-insert on each import (5,120 such rows in the current export).
-- ---------------------------------------------------------------------------
create table households (
    id             bigserial primary key,
    address_raw    text not null,
    address_norm   text not null,
    unit           text not null default '',
    dauid          text references census_da (dauid),
    lat            double precision,
    lon            double precision,
    geocode_status text not null default 'pending'
                   check (geocode_status in ('pending', 'matched', 'unmatched')),
    created_at     timestamptz not null default now(),
    unique (address_norm, unit)
);

create index households_dauid_idx on households (dauid);

-- ---------------------------------------------------------------------------
-- canvass_attempts: append-only log, one row per door per day.
--
-- Same-day conflicts (649 groups in the current export, 322 with genuinely
-- different outcomes) are resolved in scripts/import_canvass.py BEFORE insert,
-- which is what makes (household_id, attempted_on) a safe key here.
--
-- outcomes is a canonically sorted, deduplicated array. Sorting matters: the raw
-- export has 23 distinct outcome strings that collapse to 17 once ordered, e.g.
-- 'Answered, Not Interested' and 'Not Interested, Answered' are the same
-- observation. Left unsorted they would render as two separate pie slices.
-- ---------------------------------------------------------------------------
create table canvass_attempts (
    id                 bigserial primary key,
    household_id       bigint not null references households (id) on delete cascade,
    attempted_on       date not null,
    outcomes           text[] not null default '{}',
    support_level      smallint check (support_level between 1 and 5),
    opposing_candidate text,
    created_at         timestamptz not null default now(),
    unique (household_id, attempted_on)
);

create index canvass_attempts_household_idx on canvass_attempts (household_id);
create index canvass_attempts_outcomes_idx  on canvass_attempts using gin (outcomes);

comment on column canvass_attempts.support_level is
    '1 Opposing, 2 Leaning Against, 3 Undecided, 4 Leaning For, 5 Supportive. '
    'NULL means not captured -- true of 79% of source rows. The label mapping '
    'lives in the frontend; the redundant "Support Label" column is not stored.';

-- ---------------------------------------------------------------------------
-- voters: PII. Only ever returned from the authenticated /voters endpoint.
--
-- name is nullable (blank on 96% of source rows). UNIQUE NULLS NOT DISTINCT
-- (Postgres 15+) treats nulls as equal, so re-imports deduplicate correctly --
-- a plain UNIQUE would let every partially-blank row insert again each run.
-- ---------------------------------------------------------------------------
create table voters (
    id           bigserial primary key,
    household_id bigint not null references households (id) on delete cascade,
    name         text,
    email        text,
    phone        text,
    created_at   timestamptz not null default now(),
    unique nulls not distinct (household_id, name, email, phone),
    constraint voters_not_entirely_blank
        check (name is not null or email is not null or phone is not null)
);

create index voters_household_idx on voters (household_id);

-- ---------------------------------------------------------------------------
-- canvass_latest: current state per door.
--
-- Aggregates rather than DISTINCT ON so the latest NON-NULL support level wins.
-- Support level is absent from 79% of attempts, so the most recent attempt at a
-- door usually has none even when an earlier one did: measured at 226 doors,
-- 5.6% of every door that ever recorded a support level. DISTINCT ON would show
-- those as blank.
-- ---------------------------------------------------------------------------
create view canvass_latest as
select
    household_id,
    max(attempted_on) as last_attempted_on,
    count(*)          as attempts,
    (array_agg(support_level order by attempted_on desc, id desc)
        filter (where support_level is not null))[1] as support_level
from canvass_attempts
group by household_id;

-- ---------------------------------------------------------------------------
-- voter_access_log: audit trail for PII reads. The Ontario Municipal Elections
-- Act restricts what a municipal voters' list may be used for.
-- ---------------------------------------------------------------------------
create table voter_access_log (
    id          bigserial primary key,
    user_id     text not null,
    user_email  text,
    dauid       text,
    row_count   integer,
    accessed_at timestamptz not null default now()
);

create index voter_access_log_accessed_idx on voter_access_log (accessed_at desc);

commit;
