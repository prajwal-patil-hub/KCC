"""Append-only event store (ADR-0002).

Selective event sourcing: only aggregates whose history is the product (the
LoanApplication, money events) are stored here. The store is append-only — events
are never mutated or deleted. Current state is a fold over the event stream.

This in-memory implementation is the dev/test driver behind an interface; the
production driver is Postgres (append-only table + transactional outbox). The
interface is what the rest of the app depends on.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    """An immutable domain event.

    Every event carries the correlation fields required by docs/03 so the audit
    trail and projections can be reconstructed deterministically.
    """

    stream_id: str          # e.g. application id
    sequence: int           # per-stream monotonic, starts at 1
    type: str               # past-tense, context-prefixed e.g. "application.LeadCreated"
    payload: dict
    tenant_id: str
    actor_id: str
    correlation_id: str
    schema_version: int = 1
    occurred_at: str = field(default_factory=_now)


class ConcurrencyError(RuntimeError):
    """Raised when the expected stream version does not match (optimistic lock)."""


class EventStore(Protocol):
    def append(
        self, stream_id: str, expected_version: int, events: list[Event]
    ) -> None: ...

    def load(self, stream_id: str) -> list[Event]: ...


class InMemoryEventStore:
    """Thread-safe in-memory append-only event store with optimistic locking."""

    def __init__(self) -> None:
        self._streams: dict[str, list[Event]] = {}
        self._lock = threading.RLock()

    def append(
        self, stream_id: str, expected_version: int, events: list[Event]
    ) -> None:
        with self._lock:
            current = self._streams.get(stream_id, [])
            if len(current) != expected_version:
                raise ConcurrencyError(
                    f"Stream {stream_id} at version {len(current)}, "
                    f"expected {expected_version}"
                )
            self._streams.setdefault(stream_id, []).extend(events)

    def load(self, stream_id: str) -> list[Event]:
        with self._lock:
            return list(self._streams.get(stream_id, []))
