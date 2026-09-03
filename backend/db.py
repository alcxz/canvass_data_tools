"""Postgres connection for Lambda.

The one Lambda-specific gotcha that matters: every concurrent invocation opens
its own connection, and Supabase's direct connection limit is small. Use the
Supavisor pooled connection string (port 6543) rather than the direct one on
5432, or the API falls over under concurrency.

The connection is held at module scope so warm invocations reuse it, and checked
for liveness before each request because Lambda can freeze a container for long
enough that the far end has gone away.
"""

from __future__ import annotations

import os
import threading

import psycopg
from psycopg.rows import dict_row
from psycopg.types.numeric import FloatLoader

_lock = threading.Lock()
_connection: psycopg.Connection | None = None

# prepare_threshold=None disables server-side prepared statements.
# psycopg3 auto-prepares a query after the 5th execution, but Supabase's
# Supavisor pooler runs in TRANSACTION mode and hands each transaction a
# different backend, so a statement prepared on one connection is missing
# (or already present) on the next: "prepared statement _pg3_0 already
# exists". Only shows up once a query has run enough times, so it surfaces
# on bulk executemany rather than in early testing.


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(_database_url(), row_factory=dict_row, prepare_threshold=None)
    # psycopg returns Postgres `numeric` as Decimal, and FastAPI (via pydantic)
    # serialises Decimal to a JSON *string*, so average_household_size,
    # avg_support and coverage_pct arrive in the browser as "2.5" rather than
    # 2.5. Load numerics as floats instead: nothing here is money, and the
    # values are already rounded in SQL.
    conn.adapters.register_loader("numeric", FloatLoader)
    return conn


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set on the function.")
    if ":5432" in url:
        # Loud, because the symptom otherwise appears only under load.
        print("WARNING: DATABASE_URL uses port 5432 (direct). Use the Supavisor "
              "pooled string on 6543 -- Lambda concurrency will exhaust direct "
              "connections.")
    return url


def get_connection() -> psycopg.Connection:
    global _connection
    with _lock:
        if _connection is None or _connection.closed:
            _connection = _connect()
            return _connection

        try:
            with _connection.cursor() as cur:
                cur.execute("select 1")
        except psycopg.Error:
            try:
                _connection.close()
            except psycopg.Error:
                pass
            _connection = _connect()

        return _connection


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(sql: str, params: tuple = ()) -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()
