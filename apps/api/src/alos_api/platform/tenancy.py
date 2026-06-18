"""Tenant isolation guard (ADR-0003).

In production, isolation is enforced by Postgres Row-Level Security at the DB
layer. This module is the *application-layer* half of the defence in depth: any
data access must be scoped to the current principal's tenant, and a mismatch
raises rather than leaks. The in-memory repositories call `assert_tenant` so the
skeleton exhibits the same guarantee that RLS gives in prod.
"""

from __future__ import annotations

from ..context import current_principal


class TenantIsolationError(PermissionError):
    """Raised when a resource is accessed outside the caller's tenant."""


def current_tenant() -> str:
    return current_principal().tenant_id


def assert_tenant(resource_tenant_id: str) -> None:
    """Reject cross-tenant access. The DB-layer equivalent is the RLS policy:

        CREATE POLICY tenant_isolation ON <table>
          USING (tenant_id = current_setting('app.tenant_id')::uuid);
    """
    if resource_tenant_id != current_tenant():
        raise TenantIsolationError("Cross-tenant access denied")
