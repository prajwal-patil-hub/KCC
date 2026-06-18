# ADR-0004 — Explicit workflow/saga engine for the lending lifecycle

**Status:** Accepted · **Date:** 2026-06-18

## Context
The KCC lifecycle (Lead → … → Disbursement → Renewal) is long-running, spans
external systems, and needs compensations (e.g. eStamp succeeded but eSign
failed → roll back / retry). Chaining Kafka event-handlers makes the flow
implicit, hard to audit, and hard to recover.

## Decision
Model the lifecycle as an **explicit, configurable workflow** of stages. Each
stage has: entry guards, the action (often an adapter call), success/failure
transitions, a **compensation** for partial failure, and a maker/checker gate
flag. The workflow definition is **data** (versioned, per product/tenant), so
adding Dairy or changing the approval chain is config, not code.

The engine persists workflow state alongside the `LoanApplication` events, so
the **Workflow Timeline UI is derived from real state**. Use a saga/process-
manager pattern; consider a durable engine (e.g. Temporal-style) if/when needed,
but a DB-backed state machine suffices for MVP.

## Consequences
- (+) Auditable, recoverable, configurable workflows; truthful timeline UI.
- (+) Approval hierarchy and stage gates become configuration.
- (−) Need a compensation for every externally-visible side effect.
- (−) Engine is core infrastructure — must be well-tested.
