"""Postgres-backed event store (ADR-0002), behind the same EventStore interface
as the in-memory one. Tenant isolation is enforced by RLS in the DB (ADR-0003):
every transaction binds app.tenant_id from the request context, so a load can
only ever see the caller's tenant's events.
"""

from __future__ import annotations

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from .db import get_pool, set_tenant
from .events import ConcurrencyError, Event
from .tenancy import current_tenant


class PostgresEventStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def append(
        self, stream_id: str, expected_version: int, events: list[Event]
    ) -> None:
        tenant = current_tenant()
        with get_pool(self._dsn).connection() as conn:
            with conn.cursor() as cur:
                set_tenant(cur, tenant)
                cur.execute(
                    "SELECT coalesce(max(sequence), 0) FROM events WHERE stream_id = %s",
                    (stream_id,),
                )
                current = cur.fetchone()[0]
                if current != expected_version:
                    raise ConcurrencyError(
                        f"Stream {stream_id} at version {current}, "
                        f"expected {expected_version}"
                    )
                try:
                    for e in events:
                        cur.execute(
                            """INSERT INTO events
                               (stream_id, sequence, type, payload, tenant_id,
                                actor_id, correlation_id, schema_version, occurred_at)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (
                                e.stream_id, e.sequence, e.type, Jsonb(e.payload),
                                e.tenant_id, e.actor_id, e.correlation_id,
                                e.schema_version, e.occurred_at,
                            ),
                        )
                        # Transactional outbox: same transaction as the event, so
                        # the event and its publish-intent commit atomically.
                        cur.execute(
                            """INSERT INTO outbox
                               (stream_id, sequence, type, payload, tenant_id,
                                correlation_id, occurred_at)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (
                                e.stream_id, e.sequence, e.type, Jsonb(e.payload),
                                e.tenant_id, e.correlation_id, e.occurred_at,
                            ),
                        )
                except UniqueViolation as exc:
                    # A concurrent append took this sequence first.
                    raise ConcurrencyError(
                        f"Concurrent append to stream {stream_id}"
                    ) from exc
            conn.commit()

    def load(self, stream_id: str) -> list[Event]:
        tenant = current_tenant()
        with get_pool(self._dsn).connection() as conn:
            with conn.cursor() as cur:
                set_tenant(cur, tenant)
                cur.execute(
                    """SELECT stream_id, sequence, type, payload, tenant_id,
                              actor_id, correlation_id, schema_version, occurred_at
                       FROM events WHERE stream_id = %s ORDER BY sequence""",
                    (stream_id,),
                )
                rows = cur.fetchall()
            conn.commit()
        return [
            Event(
                stream_id=r[0], sequence=r[1], type=r[2], payload=r[3],
                tenant_id=r[4], actor_id=r[5], correlation_id=r[6],
                schema_version=r[7], occurred_at=r[8],
            )
            for r in rows
        ]
