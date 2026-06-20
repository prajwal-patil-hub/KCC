"""Postgres-backed hash-chained audit store (docs/06), behind the AuditStore
interface. The chain is per-tenant (RLS only lets a session see its own rows), and
writes are serialised per tenant with an advisory lock so the chain stays linear.
Reuses the same hash function as the in-memory store so verification is identical.
"""

from __future__ import annotations

from .audit import GENESIS, AuditRecord, _hash, _now
from .db import get_pool, set_tenant
from ..context import current_context


class PostgresAuditStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def record(
        self, *, action: str, resource: str, reason: str | None = None
    ) -> AuditRecord:
        ctx = current_context()
        tenant = ctx.principal.tenant_id
        at = _now()
        with get_pool(self._dsn).connection() as conn:
            with conn.cursor() as cur:
                set_tenant(cur, tenant)
                # Serialise audit writes for this tenant so seq/prev_hash are linear.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (tenant,))
                cur.execute(
                    """SELECT seq, this_hash FROM audit
                       WHERE tenant_id = %s ORDER BY seq DESC LIMIT 1""",
                    (tenant,),
                )
                row = cur.fetchone()
                last_seq, prev = (row[0], row[1]) if row else (0, GENESIS)
                seq = last_seq + 1
                this_hash = _hash(
                    str(seq), tenant, ctx.principal.user_id, action, resource,
                    reason or "", at, prev,
                )
                cur.execute(
                    """INSERT INTO audit
                       (seq, tenant_id, actor_id, action, resource, reason,
                        correlation_id, prev_hash, this_hash, at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (seq, tenant, ctx.principal.user_id, action, resource, reason,
                     ctx.correlation_id, prev, this_hash, at),
                )
            conn.commit()
        return AuditRecord(
            seq=seq, tenant_id=tenant, actor_id=ctx.principal.user_id,
            action=action, resource=resource, reason=reason,
            correlation_id=ctx.correlation_id, prev_hash=prev,
            this_hash=this_hash, at=at,
        )

    def verify_chain(self) -> bool:
        """Verify the current tenant's chain (RLS scopes the read to that tenant)."""
        tenant = current_context().principal.tenant_id
        with get_pool(self._dsn).connection() as conn:
            with conn.cursor() as cur:
                set_tenant(cur, tenant)
                cur.execute(
                    """SELECT seq, tenant_id, actor_id, action, resource, reason,
                              at, prev_hash, this_hash
                       FROM audit WHERE tenant_id = %s ORDER BY seq""",
                    (tenant,),
                )
                rows = cur.fetchall()
            conn.commit()
        prev = GENESIS
        for seq, tid, actor, action, resource, reason, at, prev_hash, this_hash in rows:
            expected = _hash(
                str(seq), tid, actor, action, resource, reason or "", at, prev
            )
            if prev_hash != prev or this_hash != expected:
                return False
            prev = this_hash
        return True
