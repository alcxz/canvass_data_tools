# Ward 11 Canvass Data Tool

Hi there! This was created as a project to help visualize canvassing data for
a campaign for Ward 11 (University-Rosedale) Councillor which I was 
door-knocking for. This app features a map with an overlay of all the 
Dissemination Areas (DAs) of Ward 11 and some colourings in each of the DAs
that represent some of the data that we've collected (support, how much of
the neighbourhood has been canvassed, etc.). In addition to the map, users
can click on a specific DA and see our canvassing data (number of doors
knocked, number of people who are supportive/unsupportive, number of doors
that answered, etc.). While this is codebase is specific to Ward 11, I hope
you may be able to repurpose it for your own campaign. 

The code in this repo was created in help with Claude Code.

---

## Stack

- **Frontend** React + MapLibre GL on Vercel
- **Backend** FastAPI on AWS Lambda (Mangum + a Function URL)
- **Database** Supabase Postgres
- **Ingest** Python CLI scripts, stdlib `csv` (no pandas)

---

## ⚠️ This repository is public but no data belongs in it.

Our data is stored in `data/` and `tests/fixtures/` locally. You can take a look
at `Planning.md` to see which columns we utilized. If you wish to utilize some
of the scripts that upload the data to a database, I recommend also keeping your
downloaded csvs (if you use them) in the `data/` directory and repurposing the
scripts in `scripts/`. 

Make sure that the data is not committed. **Before you commit**, make sure your
data files are not added to the your staged changes and are git ignored:

```bash
git status --porcelain
```

An extracted 112KB GeoJSON is used for the boundaries of the DAs within Ward 11, 
and it lives at `frontend/public/das.geojson`. It was extracted from the GovCan
website: https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21

---

## Setup

### 1. Data files

Move the exports into `data/` (gitignored):

```bash
mkdir -p data
```

Then download your data into the `data/` directory.

After, download **Address Points (Municipal) — Toronto One Address Repository**
from City of Toronto Open Data (the WGS84 lat/long variant) and save it as
`data/toronto_address_points.csv`. This is used to take the address of each
knocked door, and match it to its latitude and longitude so those can be
matched to a DA.

### 2. Environment

```bash
cp .env.example .env                          # ingest scripts & local backend
cp frontend/.env.example frontend/.env.local  # frontend
```

Make sure to set the environment variables to your own database link.

I used the Supabase **pooled** connection string (Supavisor, port 6543), not the
direct one on 5432 as AWS Lambda concurrency will exhaust direct connections.
See 3. for more instructions on setting up the database.

The only genuine secret in this project is `DATABASE_URL`. Everything in
`frontend/.env.local` is public by design, including the anon key. This is
because only users with emails that have been invited can use the app. This
authorization is granted on the database end through Supabase.

### 3. Database

To set up a Supabase database, go to supabase.com, and create a new project. I
only turned on the enable automatic RLS security option. Once in the console for
your project, go to Authentication -> Sign In/Providers -> Turn off "Allow new
users to sign up". This makes it so access to the app (yes the auth is mainly
done through the database settings since we can query this for an access token)
is invite only. To invite your users, go to Authentication -> Users -> Click the
green "Add User" button -> Send invitation -> Fill out the new user's email.

Once that's set up, get the project string and password, and set those according
to the form in .env.example into the "DATABASE_URL" env variable in .env.

Run the following to then set up the tables in the database:

```bash
psql "$DATABASE_URL" -f db/schema.sql
```

`db/schema.sql` is the complete current schema for a **fresh** database. You may
need to update an existing database in which case you should look at all the 
migration scripts in `db/migrations` and find which ones you have not run yet.

### 4. Ingest Scripts

Set up the virtual environment to be able to run the python scripts:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

---

## Tests

```bash
pytest
```

`tests/test_normalize.py` validates some of my scripts. 
`tests/test_da_mapping.py` is used to validate the mapping of an address to a
DA.

By running this before the ingest, we can catch any errors before we run
scripts that will insert data into the database.

---

## Ingest

The commands below are examples of scripts to extract the data out of the 
downloaded files and insert it into the database. These scripts can be
repurposed to your specific campaign and the data columns you have.

Note: Order matters — households must exist before canvass rows can attach to 
them. Every script accepts `--dry-run` to parse and report without writing.

The listed files are also the names of the ones I utilized.

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

---

## Install dependencies

```bash
# Ingest scripts and tests
source .venv/bin/activate
pip install -r requirements-dev.txt

# Setting up a venv for local backend testing
pip install -r backend/requirements-dev.txt

# Frontend — also generates package-lock.json, which should be committed
cd frontend && npm install
```

Deployment does **not** use your local installs. Vercel runs `npm install` itself
from `package.json`, and `scripts/deploy_backend.sh` builds the Lambda package
fresh from `backend/requirements.txt`.

`backend/requirements.txt` does not have uvicorn which is not needed on lambda.

## Run locally

```bash
# API — Mangum is a thin wrapper, so the same app serves locally
cd backend && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
```

## Deploy

### Backend

First run the deploy script:

```bash
./scripts/deploy_backend.sh          # build and deploy code
./scripts/deploy_backend.sh --env    # also push environment variables
./scripts/deploy_backend.sh --url    # print the Function URL
```

First run creates the IAM role, the function, its Function URL and a 7-day log
retention policy. Every run after that uploads code directly to Lambda.

The package is uploaded straight to Lambda via `update-function-code` (50MB 
zipped limit; the current build is 14MB). Dependencies are downloaded as 
prebuilt `manylinux` aarch64 wheels rather than compiled locally, which is why
no Linux container is needed.

This code does not have a rollback feature.

Config comes from `.env` (`DATABASE_URL`, `SUPABASE_URL`, `ALLOWED_ORIGINS`), so
no secret is typed on the command line.

### Frontend

Vercel deploys from the GitHub integration on push to `main`. I have **Disable preview deployments** on in case the voter's list is visable.

After the first backend deploy, set `VITE_API_URL` to the Function URL in both
`frontend/.env.local` and Vercel. `VITE_` variables are inlined at build time, so
**redeploy the frontend** after changing it — updating the value in Vercel alone
does nothing to the already-built site.

Then put your Vercel origin in `ALLOWED_ORIGINS` and run
`./scripts/deploy_backend.sh --env`. Skipping this shows up as a CORS error in
the browser rather than anything obviously wrong with either deploy.

---

## Notes on the data

- **DA vs DAUID.** The `DA` column in the exports is the trailing 4 digits, and
  spreadsheets strip leading zeros inconsistently (`0918` survives, `915` does
  not). `geodata.dauid_from_da_column` expands it to `3520` + 4 digits.
- **Census caveats.** Commute mode, commute time and departure-time counts come
  from the 25% long-form sample and do not sum against population; DA counts are
  randomly rounded to 5.

Example:
<img width="1920" height="958" alt="Screenshot 2026-09-03 at 3 53 46 AM" src="https://github.com/user-attachments/assets/1dca9460-8aca-48fe-b651-45a136b101d9" />
