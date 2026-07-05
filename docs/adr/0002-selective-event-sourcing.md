# ADR-0002 — Selective event sourcing + transactional outbox

**Status:** Accepted · **Implemented** (Postgres event store + outbox + relay,
verified) · **Date:** 2026-06-18

## Context
"Event sourcing" everywhere (v1) is over-engineering: reference data and config
don't need it and it slows every CRUD path. But audit, zero-data-loss, and the
"who/what/when/why" of a loan application demand an immutable history.

## Decision
Event-source **only** the aggregates where history is the product:
- `LoanApplication` (every state transition is an appended event).
- **Money events** (sanction, disbursement, posting, reversal).

Everything else (customers' editable profile, lookups, config) is **CRUD with
audit triggers**. Current application state is a **fold** of its events; we keep
periodic **snapshots** for fast load. Events are versioned with **upcasters** for
schema evolution.

Publish to Kafka via the **transactional outbox**: write event + outbox row in
one DB transaction; a relay ships outbox rows to Kafka. Kafka is the bus, **not**
the source of truth — Postgres is.

## Consequences
- (+) Full audit/replay where it matters; simple CRUD elsewhere.
- (+) No dual-write inconsistency (outbox guarantees at-least-once publish).
- (−) Consumers must be idempotent (they must be anyway).
- (−) Event schema discipline + upcasters required.
