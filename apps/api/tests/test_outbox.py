"""Transactional outbox (ADR-0002) against real Postgres.

Proves: the outbox row is written atomically with the event; a failed append
leaves no outbox row; the relay publishes unpublished rows, marks them, and is
idempotent; and the (BYPASSRLS) relay spans all tenants while a tenant's pending
view stays RLS-scoped.

Skipped unless ALOS_DATABASE_URL is set. The relay tests also need
ALOS_RELAY_DATABASE_URL (a BYPASSRLS role); they skip individually if it is unset.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Skip the whole module cleanly if psycopg isn't installed (e.g. the no-DB CI job).
psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("ALOS_DATABASE_URL")
RELAY_DSN = os.environ.get("ALOS_RELAY_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="ALOS_DATABASE_URL not set")

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATIONS = [MIGRATIONS_DIR / "0001_init.sql", MIGRATIONS_DIR / "0002_outbox.sql"]


@pytest.fixture
def env():
    from alos_api import context as ctxmod
    from alos_api.context import Principal, RequestContext
    from alos_api.platform import db
    from alos_api.platform.pg_events import PostgresEventStore

    for m in MIGRATIONS:
        db.apply_migration(DSN, m)
    events = PostgresEventStore(DSN)

    def as_tenant(tenant: str):
        ctxmod.set_context(RequestContext(principal=Principal("u1", tenant)))

    yield events, as_tenant
    ctxmod.clear_context()
    db.close_pools()


def _event(stream, seq, tenant):
    from alos_api.platform.events import Event
    return Event(stream_id=stream, sequence=seq, type="application.LeadCreated",
                 payload={"x": seq}, tenant_id=tenant, actor_id="u1",
                 correlation_id="c1")


def _pending(tenant: str) -> int:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
        cur.execute("SELECT count(*) FROM outbox WHERE published_at IS NULL")
        return cur.fetchone()[0]


def test_outbox_written_atomically_with_event(env):
    events, as_tenant = env
    as_tenant("bankA")
    events.append("app-1", 0, [_event("app-1", 1, "bankA")])
    assert _pending("bankA") == 1


def test_failed_append_writes_no_outbox(env):
    events, as_tenant = env
    from alos_api.platform.events import ConcurrencyError
    as_tenant("bankA")
    events.append("app-2", 0, [_event("app-2", 1, "bankA")])
    with pytest.raises(ConcurrencyError):
        events.append("app-2", 0, [_event("app-2", 1, "bankA")])  # stale version
    # the failed append rolled back; exactly one outbox row exists, not two
    assert _pending("bankA") == 1


@pytest.mark.skipif(not RELAY_DSN, reason="ALOS_RELAY_DATABASE_URL not set")
def test_relay_publishes_marks_and_is_idempotent(env):
    events, as_tenant = env
    from alos_api.platform.outbox import InMemoryBus, OutboxRelay

    as_tenant("bankA")
    events.append("app-3", 0, [_event("app-3", 1, "bankA"),
                               _event("app-3", 2, "bankA")])
    bus = InMemoryBus()
    relay = OutboxRelay(RELAY_DSN, bus)

    assert relay.run_once() == 2
    assert {m.sequence for m in bus.published} == {1, 2}
    assert bus.published[0].topic == "alos.application"
    assert _pending("bankA") == 0
    assert relay.run_once() == 0  # nothing left to publish


@pytest.mark.skipif(not RELAY_DSN, reason="ALOS_RELAY_DATABASE_URL not set")
def test_relay_spans_all_tenants(env):
    events, as_tenant = env
    from alos_api.platform.outbox import InMemoryBus, OutboxRelay

    as_tenant("bankA")
    events.append("a", 0, [_event("a", 1, "bankA")])
    as_tenant("bankB")
    events.append("b", 0, [_event("b", 1, "bankB")])

    bus = InMemoryBus()
    assert OutboxRelay(RELAY_DSN, bus).run_once() == 2
    assert {m.tenant_id for m in bus.published} == {"bankA", "bankB"}
