# ADR-0003 — Multi-tenancy: shared schema + Postgres RLS

**Status:** Accepted · **Date:** 2026-06-18

## Context
Tenants are banks (co-op/RRB/PSU). Strict isolation is mandatory (S7: Tenant A
must never see Tenant B). Options: DB-per-tenant (max isolation, max ops),
schema-per-tenant (good isolation, migration pain at scale), shared-schema +
row-level security (simplest, relies on a correct predicate).

## Decision
Start with **shared database, shared schema, Postgres Row-Level Security**.
Every tenant-scoped table has a `tenant_id`; RLS policies force a
`tenant_id = current_setting('app.tenant_id')` predicate. The app sets the
tenant context per request from the authenticated principal; the **data-access
layer rejects any query without tenant context**. Defence in depth: app-layer
tenant guard + DB-layer RLS.

Provide an escape hatch: a large or compliance-demanding tenant can be promoted
to **schema-per-tenant** (or its own DB) without app changes, because all access
already goes through the tenant-aware data layer.

## Consequences
- (+) Cheapest correct isolation; one migration path; easy onboarding.
- (+) RLS is enforced by the DB even if app code has a bug.
- (−) "Noisy neighbour" risk → mitigate with per-tenant quotas/monitoring.
- (−) RLS must be tested explicitly (negative tests in CI).
