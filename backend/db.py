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

_lock = threading.Lock()
_connection: psycopg.Connection | None = None


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
            _connection = psycopg.connect(_database_url(), row_factory=dict_row)
            return _connection

        try:
            with _connection.cursor() as cur:
                cur.execute("select 1")
        except psycopg.Error:
            try:
                _connection.close()
            except psycopg.Error:
                pass
            _connection = psycopg.connect(_database_url(), row_factory=dict_row)

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
