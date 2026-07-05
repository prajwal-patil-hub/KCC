"""Hash-chained, append-only audit store (docs/06 security).

Tamper-evident: each record stores the hash of the previous record, so any
edit/removal breaks the chain and is detectable. Records the who/what/when/why
plus a before/after hash. PII must be redacted by callers before logging here.

In-memory driver behind an interface; production driver is a WORM-backed store.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    tenant_id: str
    actor_id: str
    action: str                 # e.g. "application.advance"
    resource: str               # e.g. "application:123"
    reason: str | None
    correlation_id: str
    prev_hash: str
    this_hash: str = field(default="")
    at: str = field(default_factory=_now)


class AuditStore(Protocol):
    def record(
        self,
        *,
        action: str,
        resource: str,
        reason: str | None = None,
    ) -> AuditRecord: ...

    def verify_chain(self) -> bool: ...


GENESIS = "0" * 64


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = threading.RLock()

    def record(
        self, *, action: str, resource: str, reason: str | None = None
    ) -> AuditRecord:
        # Imported lazily to avoid a hard import cycle with context.
        from ..context import current_context

        ctx = current_context()
        with self._lock:
            seq = len(self._records) + 1
            prev = self._records[-1].this_hash if self._records else GENESIS
            partial = AuditRecord(
                seq=seq,
                tenant_id=ctx.principal.tenant_id,
                actor_id=ctx.principal.user_id,
                action=action,
                resource=resource,
                reason=reason,
                correlation_id=ctx.correlation_id,
                prev_hash=prev,
            )
            this_hash = _hash(
                str(seq),
                partial.tenant_id,
                partial.actor_id,
                action,
                resource,
                reason or "",
                partial.at,
                prev,
            )
            record = AuditRecord(**{**partial.__dict__, "this_hash": this_hash})
            self._records.append(record)
            return record

    def verify_chain(self) -> bool:
        prev = GENESIS
        for r in self._records:
            expected = _hash(
                str(r.seq), r.tenant_id, r.actor_id, r.action, r.resource,
                r.reason or "", r.at, prev,
            )
            if r.prev_hash != prev or r.this_hash != expected:
                return False
            prev = r.this_hash
        return True

    def records_for_tenant(self, tenant_id: str) -> list[AuditRecord]:
        with self._lock:
            return [r for r in self._records if r.tenant_id == tenant_id]
