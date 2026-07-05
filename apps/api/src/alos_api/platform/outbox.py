"""Transactional outbox: message bus + relay (ADR-0002).

The outbox row is written atomically with the event by PostgresEventStore. This
module is the *publish* half: a pluggable MessageBus and a relay that drains
unpublished rows and marks them published. The relay uses a BYPASSRLS connection
because it is infrastructure spanning all tenants, not a tenant itself.

Buses:
  * InMemoryBus — collects messages (dev/tests).
  * KafkaBus    — shaped for a real broker; constructed only when configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OutboxMessage:
    id: int
    stream_id: str
    sequence: int
    type: str
    payload: dict
    tenant_id: str
    correlation_id: str
    occurred_at: str

    @property
    def topic(self) -> str:
        # e.g. "application.LeadCreated" -> topic "alos.application"
        return "alos." + self.type.split(".", 1)[0]


class MessageBus(Protocol):
    def publish(self, message: OutboxMessage) -> None: ...


class InMemoryBus:
    def __init__(self) -> None:
        self.published: list[OutboxMessage] = []

    def publish(self, message: OutboxMessage) -> None:
        self.published.append(message)


class KafkaBus:
    """Placeholder for a real Kafka producer (kept behind config). The relay only
    depends on the MessageBus interface, so swapping this in is a wiring change."""

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers

    def publish(self, message: OutboxMessage) -> None:  # pragma: no cover
        raise NotImplementedError(
            "KafkaBus requires a broker + producer; not wired in this environment"
        )


class OutboxRelay:
    def __init__(self, relay_dsn: str, bus: MessageBus) -> None:
        self._dsn = relay_dsn
        self._bus = bus

    def run_once(self, batch: int = 100) -> int:
        """Publish up to `batch` unpublished rows; returns the count published.
        FOR UPDATE SKIP LOCKED makes it safe to run multiple relays concurrently."""
        import psycopg  # lazy: the in-memory path must not require psycopg

        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, stream_id, sequence, type, payload, tenant_id,
                              correlation_id, occurred_at
                       FROM outbox WHERE published_at IS NULL
                       ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""",
                    (batch,),
                )
                rows = cur.fetchall()
                if not rows:
                    conn.commit()
                    return 0
                for r in rows:
                    self._bus.publish(OutboxMessage(*r))
                cur.execute(
                    "UPDATE outbox SET published_at = now() WHERE id = ANY(%s)",
                    ([r[0] for r in rows],),
                )
            conn.commit()
        return len(rows)
