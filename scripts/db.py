"""Database connection helper shared by the ingest scripts.

Reads DATABASE_URL from the environment or from a local .env file. The ingest
scripts run on your machine against the Supabase connection string; the backend
has its own connection module because it runs in Lambda and pools differently.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def connect() -> psycopg.Connection:
    _load_env_file()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set. Put it in .env (gitignored) or export it.\n"
            "Use the Supabase pooled connection string."
        )
    # prepare_threshold=None disables server-side prepared statements.
    # psycopg3 auto-prepares a query after the 5th execution, but Supabase's
    # Supavisor pooler runs in TRANSACTION mode and hands each transaction a
    # different backend, so a statement prepared on one connection is missing
    # (or already present) on the next: "prepared statement _pg3_0 already
    # exists". Only shows up once a query has run enough times, so it surfaces
    # on bulk executemany rather than in early testing.
    return psycopg.connect(url, prepare_threshold=None)
