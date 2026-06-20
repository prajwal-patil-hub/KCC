"""Postgres event/audit stores with Row-Level Security.

These run only when ALOS_DATABASE_URL points at a Postgres reachable via a
non-superuser, non-BYPASSRLS role (otherwise RLS would be skipped and the test
would be meaningless). Skipped automatically when unset.

What we prove:
  * append/load round-trips through Postgres
  * RLS hides another tenant's events even from a raw query
  * WITH CHECK blocks inserting a row for a different tenant
  * optimistic concurrency (UNIQUE stream_id+sequence) is enforced
  * the per-tenant audit hash chain verifies
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

DSN = os.environ.get("ALOS_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="ALOS_DATABASE_URL not set")

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATIONS = [MIGRATIONS_DIR / "0001_init.sql", MIGRATIONS_DIR / "0002_outbox.sql"]


@pytest.fixture
def pg(monkeypatch):
    from alos_api import context as ctxmod
    from alos_api.context import Principal, RequestContext
    from alos_api.platform import db
    from alos_api.platform.pg_audit import PostgresAuditStore
    from alos_api.platform.pg_events import PostgresEventStore

    for m in MIGRATIONS:  # fresh schema each test
        db.apply_migration(DSN, m)
    events = PostgresEventStore(DSN)
    audit = PostgresAuditStore(DSN)

    def as_tenant(tenant: str, user: str = "u1"):
        ctx = RequestContext(principal=Principal(user_id=user, tenant_id=tenant))
        ctxmod.set_context(ctx)
        return ctx

    yield events, audit, as_tenant
    ctxmod.clear_context()
    db.close_pools()


def _event(stream, seq, tenant, etype="application.LeadCreated", payload=None):
    from alos_api.platform.events import Event
    return Event(
        stream_id=stream, sequence=seq, type=etype, payload=payload or {"x": seq},
        tenant_id=tenant, actor_id="u1", correlation_id="corr-1",
    )


def test_append_and_load_roundtrip(pg):
    events, _, as_tenant = pg
    as_tenant("bankA")
    events.append("app-1", 0, [_event("app-1", 1, "bankA")])
    events.append("app-1", 1, [_event("app-1", 2, "bankA")])
    loaded = events.load("app-1")
    assert [e.sequence for e in loaded] == [1, 2]
    assert loaded[0].payload == {"x": 1}


def test_rls_hides_other_tenants_events(pg):
    events, _, as_tenant = pg
    as_tenant("bankA")
    events.append("app-A", 0, [_event("app-A", 1, "bankA")])

    # Switch to bankB: the same stream id returns nothing (RLS filters it out).
    as_tenant("bankB")
    assert events.load("app-A") == []

    # Even a raw query under bankB's GUC sees zero of bankA's rows.
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', 'bankB', false)")
        cur.execute("SELECT count(*) FROM events")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT set_config('app.tenant_id', 'bankA', false)")
        cur.execute("SELECT count(*) FROM events")
        assert cur.fetchone()[0] == 1


def test_with_check_blocks_cross_tenant_insert(pg):
    events, _, as_tenant = pg
    as_tenant("bankB")
    # Context is bankB, but the event claims bankA -> WITH CHECK must reject it.
    with pytest.raises(Exception):
        events.append("app-x", 0, [_event("app-x", 1, "bankA")])


def test_optimistic_concurrency(pg):
    events, _, as_tenant = pg
    as_tenant("bankA")
    events.append("app-2", 0, [_event("app-2", 1, "bankA")])
    from alos_api.platform.events import ConcurrencyError
    with pytest.raises(ConcurrencyError):
        events.append("app-2", 0, [_event("app-2", 1, "bankA")])  # stale version


def test_audit_chain_verifies_per_tenant(pg):
    _, audit, as_tenant = pg
    as_tenant("bankA")
    audit.record(action="application.LeadCreated", resource="application:1")
    audit.record(action="application.Sanctioned", resource="application:1",
                 reason="approved")
    assert audit.verify_chain() is True

    # A different tenant has an independent (empty) chain that also verifies.
    as_tenant("bankB")
    assert audit.verify_chain() is True
