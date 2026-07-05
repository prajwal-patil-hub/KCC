"""Postgres connection helpers + per-transaction tenant binding.

The single most important function here is `set_tenant`: it sets the
`app.tenant_id` GUC that the RLS policies read (ADR-0003). Every DB operation
opens a transaction, sets the tenant from the request context, does its work, and
commits — so RLS is enforced by Postgres on every query, independent of any
application-layer check.

A tiny connection pool keeps this cheap. Real deployments would tune the pool
and likely use async; the interface the stores depend on does not change.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

_pools: dict[str, ConnectionPool] = {}


def get_pool(dsn: str) -> ConnectionPool:
    pool = _pools.get(dsn)
    if pool is None:
        pool = ConnectionPool(dsn, min_size=1, max_size=8, open=True)
        _pools[dsn] = pool
    return pool


def set_tenant(cur: psycopg.Cursor, tenant_id: str) -> None:
    """Bind the RLS tenant for the current transaction (is_local=true)."""
    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))


def apply_migration(dsn: str, sql_path: str | Path) -> None:
    sql = Path(sql_path).read_text()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql)


def close_pools() -> None:
    for pool in _pools.values():
        pool.close()
    _pools.clear()
