# ADR-0006 — Integrations as adapters (ports) with mock-first development

**Status:** Accepted · **KYC sandbox adapter + contract test implemented** ·
**Date:** 2026-06-18

## Context
Integrations (Aadhaar, PAN, CKYC, NESL, eSign, eStamp, Account Aggregator,
land records, CBS, bureaus, PM-KISAN, SMS/WhatsApp) are access-gated, flaky, and
mostly unavailable in dev. Calling them directly couples business logic to
vendor quirks and makes the app un-testable offline.

## Decision
Every integration sits behind a **Port** (interface) with one or more
**Adapters** (real vendor, mock, sandbox). Each adapter provides, uniformly:
- **Mock mode** (default in dev/CI) returning realistic fixtures.
- Retries with exponential backoff + jitter; **circuit breaker**.
- **Idempotency key** on any state-changing/money call.
- Request/response **audit logging** (PII-redacted).
- A **health probe** and a pinned **interface version**.
- **Reconciliation** job for money/document side effects.

Business logic depends only on the Port. Swapping mock → sandbox → production is
a config/feature-flag change. Government-API access never blocks development.

## Consequences
- (+) Whole flow runs end-to-end with zero real access; deterministic tests.
- (+) Vendor swaps and outages are contained.
- (−) Up-front interface design per integration; contract tests required to keep
  mocks honest against real responses.
