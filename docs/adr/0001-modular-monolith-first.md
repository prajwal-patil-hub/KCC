# ADR-0001 — Modular monolith first, microservices via strangler

**Status:** Accepted · **Date:** 2026-06-18

## Context
v1 assumed microservices from day 1. We have a small team, flaky external deps,
and an unproven domain decomposition. Premature microservices buy network
failure modes, distributed transactions, and ops overhead we can't yet justify.

## Decision
Ship a **single deployable FastAPI application** organised as a modular monolith.
Each bounded context (Customer, Lead, Land, Crop, Eligibility, Underwriting,
Documentation, Disbursement, Notification, Config, Audit) is a Python package
with a **published interface**; cross-context calls go only through those
interfaces — no reaching into another module's models or tables.

Extract a module into its own service **only** when it has a proven reason:
independent scaling, independent deploy cadence, or separate team ownership
(strangler-fig migration). The module boundaries are drawn now so extraction is
mechanical later.

## Consequences
- (+) Simple local dev, one transaction boundary, easy refactors, fast MVP.
- (+) Clear seams mean future extraction is low-risk.
- (−) Requires discipline (enforce boundaries via import-linting in CI).
- (−) One process scales as a unit until we split (acceptable at MVP scale).
