# 07 — Roadmap, MVP Slice & Acceptance Criteria

Strategy: prove the **spine** with a walking skeleton, then a **thin KCC vertical
slice** that runs end-to-end on mocks, then harden with real adapters one at a
time behind feature flags.

## Milestone 0 — Foundations (walking skeleton)
**Goal:** one bounded context end-to-end, proving every cross-cutting concern.
- Monorepo + FastAPI app + Next.js app, dockerised, CI green.
- Auth (OIDC), tenancy + **RLS**, event store, append-only audit, outbox→Kafka.
- Integration **port framework** with mock adapters.
- Customer/Lead context: create lead → create customer (mock KYC) → see it in UI.
- **DoD:** tenant isolation test passes; an event + audit row is written; trace
  visible end-to-end; no PII in logs.

## Milestone 1 — KCC vertical slice (mock everything external)
**Goal:** a full KCC application from lead to mock sanction, decisions correct.
1. Land capture (offline PWA) + mock land verification.
2. Crop capture linked to **Scale-of-Finance** reference table (versioned).
3. **Deterministic Eligibility/Limit engine** (KCC formula, collateral-free
   ceiling, PSL tag, subvention eligibility) — fully unit-tested.
4. **Credit-Memo AI agent** (grounded, governed, overridable) drafting the memo
   around the computed figures.
5. **Workflow engine** driving Maker → Checker → approval hierarchy with gates.
6. Mock Documentation (NESL/eStamp/eSign) → mock Disbursement → mock CBS posting,
   all **idempotent** with a reconciliation stub.
- **DoD:** double "Disburse" → exactly one money event; maker can't check own
  work; limit recomputes identically from stored inputs+config versions; AI memo
  cites figures; workflow timeline derived from events.

## Milestone 2 — Harden & real adapters (flagged)
- Replace mocks one integration at a time (KYC → land records → NESL/eSign/
  eStamp → CBS → bureau) behind feature flags, with contract tests + recon
  dashboards.
- Security hardening: STRIDE reviews, secret scanning, pen-test prep.
- Observability: business KPI dashboards (TAT per stage, approval rate).

## Milestone 3 — Renewal + 2nd product proof
- KCC **renewal** flow (revalidation + recompute).
- Add a 2nd product (e.g. Dairy/Tractor) **as config + module** to prove the
  multi-product seam (no edits to KCC module).

## Milestone 4 — Scale & extract
- Promote a large tenant to schema-per-tenant if needed.
- Strangle the first service out (likely Document/AI or Notification).

---

## Acceptance criteria that define "good" (system-level)
- **Correctness:** every monetary action idempotent + reconciled; eligibility
  reproducible.
- **Auditability:** any decision answerable as "who/what/when/why + what the AI
  saw" from the stores.
- **Isolation:** RLS negative tests pass in CI.
- **Resilience:** an integration outage never hard-fails an application.
- **Privacy:** Aadhaar tokenised; PII encrypted; no PII in logs/LLM calls.
- **Evolvability:** annual SoF/ceiling/subvention change = config version bump,
  zero code change.

## Suggested repo layout (target)
```
/apps
  /api        FastAPI modular monolith (bounded-context packages)
  /web        Next.js web app
  /field-pwa  offline capture PWA
/packages
  /eligibility-engine   pure, framework-free limit/eligibility math
  /contracts            shared types / event & API schemas
/infra        docker-compose (dev), k8s manifests, otel/grafana
/docs         this folder
/prompts      master prompt(s)
```

## Immediate next build step (proposed)
Start Milestone 1.3 first — the **deterministic eligibility engine** as a pure,
dependency-free package with a full unit-test suite. It is the highest-certainty,
highest-value, zero-external-dependency component and anchors everything else.
```
```
