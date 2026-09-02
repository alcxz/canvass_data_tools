# Ward 11 Canvass Data Tool

Census and door-knocking data for Ward 11 (University–Rosedale, Toronto), joined
by Dissemination Area and shown on a map. Campaign managers see a choropleth of
the ward's 161 DAs coloured by canvass coverage; clicking a DA opens its census
profile, canvassing aggregates, and — behind a second click — the voter list.

- **Frontend** React + MapLibre GL on Vercel
- **Backend** FastAPI on AWS Lambda (Mangum + API Gateway HTTP API), deployed with SAM
- **Database** Supabase Postgres
- **Ingest** Python CLI scripts, stdlib `csv` (no pandas)

---

## ⚠️ This repository is public. No data belongs in it.

`data/` and `tests/fixtures/` are gitignored, and so are the data files currently
sitting at the repo root. **Before your first commit**, confirm the working tree
is clean of them:

```bash
git status --porcelain
```

Nothing under `data/`, `tests/fixtures/`, or matching the voter's-list or census
filenames may appear. On a public repo an accidental push of voter PII is
effectively irreversible — it is cloneable and cached by third parties within
minutes, and a force-push does not recall it.

The 197MB `lda_000b21a_e.zip` is also ignored: GitHub rejects files over 100MB,
so committing it would produce a commit that cannot be pushed. Only the extracted
112KB GeoJSON is needed, and it already lives at `frontend/public/das.geojson`.

---

## Setup

### 1. Data files

Move the exports into `data/` (gitignored):

```bash
mkdir -p data
mv "Census-Data-by-DA.xlsx - ward11_da_census_ExportTable.csv" data/
mv "Voter's List - WORKING (Aug 6).xlsx - Door Knocking Data.csv" data/
mv "Subset of Canvasses By DA for Alex's Test - Sheet1.csv" tests/fixtures/da_golden.csv
```

Then download **Address Points (Municipal) — Toronto One Address Repository**
from City of Toronto Open Data (the WGS84 lat/long variant) and save it as
`data/toronto_address_points.csv`. This replaces a geocoding API entirely: the
join is offline, free, and deterministic.

### 2. Database

```bash
psql "$DATABASE_URL" -f db/migrations/0001_init.sql
```

Then in the Supabase dashboard: **disable public signup** under Auth settings and
invite users manually.

### 3. Environment

```bash
cp .env.example .env                          # ingest scripts
cp samconfig.toml.example samconfig.toml      # backend deploy
cp frontend/.env.example frontend/.env.local  # frontend
```

Use the Supabase **pooled** connection string (Supavisor, port 6543), not the
direct one on 5432 — Lambda concurrency will exhaust direct connections.

The `service_role` key never goes in any `VITE_`-prefixed variable; those ship to
the browser. Only the anon key belongs in the frontend.

### 4. Python

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

---

## Ingest

Order matters — households must exist before canvass rows can attach to them.
Every script accepts `--dry-run` to parse and report without writing.

```bash
python scripts/import_census.py \
  --file "data/Census-Data-by-DA.xlsx - ward11_da_census_ExportTable.csv"

python scripts/build_households.py \
  --voters "data/Voter's List - WORKING (Aug 6).xlsx - Door Knocking Data.csv" \
  --address-points data/toronto_address_points.csv

python scripts/import_canvass.py \
  --file "data/Voter's List - WORKING (Aug 6).xlsx - Door Knocking Data.csv"
```

All three are idempotent — re-run them whenever the sheet is re-exported.

**Expected results for the Aug 6 export:**

| Check | Expected |
|---|---|
| `census_da` rows | 161 |
| Address match rate | ≥95% (below that, fix `scripts/normalize.py` before continuing) |
| `canvass_attempts` rows | 19,474 (from 20,163 raw rows) |
| Attempts carrying a support level | 4,029 |

`build_households.py` writes `data/unmatched_addresses.csv` for manual review.

### Why 20,163 rows become 19,474

649 (door, date) groups hold more than one row, and 322 of them record genuinely
different outcomes — one canvasser logged `No Answer` while another logged
`Answered` at the same door the same day. `import_canvass.py` picks one row per
group before inserting: a row **with** a support level beats one without (it is
absent from 79% of rows), then best outcome, then original file order. Verified
against the real export, this loses **zero** support levels.

---

## Tests

```bash
pytest
```

`tests/test_normalize.py` runs anywhere. `tests/test_da_mapping.py` is the golden
test for the geocoding path — it puts 39 hand-verified addresses through the real
pipeline and asserts each lands in the right DA. Its fixture is gitignored, so it
skips unless you have populated `tests/fixtures/` (see the README there).

---

## Run locally

```bash
# API — Mangum is a thin wrapper, so the same app serves locally
cd backend && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

## Deploy

```bash
cd backend && sam build && sam deploy    # reads samconfig.toml
```

Frontend deploys from Vercel's GitHub integration on push to `main`. **Disable
preview deployments** — a per-PR build would serve real voter data from an easily
shared URL.

---

## Notes on the data

- **DA vs DAUID.** The `DA` column in the exports is the trailing 4 digits, and
  spreadsheets strip leading zeros inconsistently (`0918` survives, `915` does
  not). `geodata.dauid_from_da_column` expands it to `3520` + 4 digits.
- **Outcomes are stored sorted.** The raw export has 23 distinct outcome strings
  that collapse to 17 once ordered — `Answered, Not Interested` and
  `Not Interested, Answered` are the same observation. Unsorted, they render as
  two pie slices that still sum to 100%, so the bug is silent.
- **Support level is sparse** (79% of attempts have none), which is why
  `canvass_latest` carries the latest *non-null* value forward rather than using
  `DISTINCT ON`. Measured on the real data, the naive version blanks 226 doors.
- **Census caveats.** Commute mode, commute time and departure-time counts come
  from the 25% long-form sample and do not sum against population; DA counts are
  randomly rounded to 5.
- **Out of scope by decision.** The census file carries ~45 more columns
  (dwelling types, 24 languages, immigrants, unemployment, commute times) and the
  voter's list carries `Knocked By`, `Notes`, and `In Contacts`. The importers
  ignore them. `Knocked By` is the likeliest future addition.
