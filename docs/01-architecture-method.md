# 01 — How to find the *best* architecture (the method)

"Best" is not a vibe. It's the architecture that best satisfies the **ranked
quality attributes** under our constraints, with the **cheapest reversibility**
on the decisions we're least sure about. This doc is the repeatable method; the
ADRs in `docs/adr/` are its output.

## Step 1 — Rank the quality attributes (drivers)

For a lending OS, ranked:

1. **Correctness of money & decisions** (a wrong disbursement is unrecoverable).
2. **Auditability / regulatory defensibility** (RBI, DPDP, Aadhaar).
3. **Data durability** (zero data loss).
4. **Security & privacy** of PII.
5. **Evolvability** (multi-product, multi-state, annual rule changes).
6. **Availability** (degrade gracefully, never hard-fail an application).
7. **Performance** (important, but bounded by 3rd-party latency anyway).
8. **Cost / time-to-market**.

Anything that trades down 1–4 to buy 7–8 is rejected by default.

## Step 2 — Capture constraints

- India data residency; government APIs are flaky and access-gated.
- Field users on poor connectivity and low-end devices.
- Rules change annually and vary by state/district.
- Small initial team → operational simplicity matters.

## Step 3 — Use scenarios to stress each candidate (ATAM-lite)

Write concrete scenarios and check each architecture option against them:

- **S1 (correctness):** Two clicks of "Disburse" 200ms apart must result in
  exactly one transfer. → forces idempotency keys + outbox + reconciliation.
- **S2 (audit):** An auditor asks "who changed this limit and why, and what did
  the AI see?" → forces event sourcing on the application + AI decision records.
- **S3 (evolvability):** DLTC publishes new Scale-of-Finance for next season. →
  forces versioned, effective-dated config, not constants.
- **S4 (residency/privacy):** Underwriting needs an LLM but data can't leave
  India. → forces PII redaction + in-country inference path.
- **S5 (availability):** Land-records API is down for 3 hours. → forces
  circuit-breaker → queue → manual-fallback, never block the whole app.
- **S6 (offline):** Agent captures land in a no-network village. → forces local
  draft store + deterministic sync + conflict resolution.
- **S7 (multi-tenant isolation):** Tenant A must never see Tenant B's rows. →
  forces RLS / enforced tenant predicate at the data layer.

A "best" architecture is the one where every scenario has a designed answer and
the *expensive-to-change* answers are the ones we're most confident in.

## Step 4 — Decide reversibility, then commit

- **Type-1 (hard to reverse):** tenancy model, event-store choice, money/ledger
  design, PII tokenisation. → decide carefully now, write an ADR.
- **Type-2 (easy to reverse):** which LLM, UI library specifics, queue tuning.
  → pick a sane default, move on, revisit with data.

## Step 5 — Record as ADRs and re-evaluate at gates

Every Type-1 decision becomes an ADR (context → options → decision →
consequences). Re-open an ADR only with evidence (a failed scenario, real load).

---

## Candidate comparison summary (the actual choices)

| Concern | Options considered | Chosen | Why (vs the ranked drivers) |
|---|---|---|---|
| Deployment shape | Microservices now / **Modular monolith** / monolith forever | Modular monolith → strangler | Ops simplicity + evolvability without distributed-systems tax up front. ADR-0001 |
| State model | Full CQRS+ES / **Selective ES** / pure CRUD | Selective ES + outbox | Audit & zero-loss where it matters; CRUD elsewhere to stay simple. ADR-0002 |
| Tenancy | DB-per-tenant / schema-per-tenant / **shared+RLS** | Shared schema + RLS | Cheapest isolation that passes S7; escalate big tenants to schema. ADR-0003 |
| Workflow | Event-handler chains / **explicit saga/process engine** | Explicit workflow engine | Long-running, compensable, auditable stages (S1/S2). ADR-0004 |
| Numbers/decisions | LLM decides / **deterministic core + LLM explains** | Deterministic core | Correctness (driver #1); LLM can't be trusted with money math. ADR-0005 |
| Integrations | Direct calls / **adapter+port with mock mode** | Adapter + port | S5 + government-API access reality; testable offline. ADR-0006 |

ADRs follow.
