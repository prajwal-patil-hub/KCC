# CONTEXT — ALOS

Orientation doc. Read this first when picking up the project (human or agent).
It captures *what this is, why, the decisions already made, and the current
state* so you don't have to reconstruct it.

## What we are building
ALOS — an **AI-native Agricultural Lending Operating System for India**.
First product: **Kisan Credit Card (KCC)** loans. Designed to extend to KCC
renewal, Agri term loans, Dairy, Tractor, and Allied lending without rewriting
the core. Tenants are banks (co-operative banks, RRBs, PSU banks).

## Why it exists (problem)
Agri lending in India is rule-heavy (RBI/GoI policy that changes annually and
varies by state/district), document-heavy, and field-driven (agents on poor
connectivity and low-end phones). Existing systems are slow, hard to audit, and
not configurable. ALOS aims to make the lending lifecycle fast, auditable,
configurable, and AI-assisted — without ever letting AI move money on its own.

## Who uses it (actors)
Field Agent (capture) · Maker · Checker · Credit Officer · Branch Manager ·
Regional Manager · Sanction Authority · Compliance/Auditor · Admin. Separation
of Duties is enforced: the maker of a step can never be its checker.

## The lifecycle (one line)
Lead → Onboarding/KYC → Land → Crop → Bureau → **Eligibility (deterministic)** →
AI Underwriting/Memo → Maker → Checker → Approval hierarchy → Sanction →
Documentation (NESL/eStamp/eSign) → Disbursement → CBS posting → Monitoring →
Renewal → Closure.

## Decisions already made (don't re-litigate without an ADR)
| # | Decision | ADR |
|---|---|---|
| 1 | Modular monolith first; strangle to services only on proven need | adr/0001 |
| 2 | Selective event sourcing (application + money) + transactional outbox | adr/0002 |
| 3 | Multi-tenancy via shared schema + Postgres Row-Level Security | adr/0003 |
| 4 | Explicit workflow/saga engine with compensations (config-driven) | adr/0004 |
| 5 | **Deterministic core decides numbers; AI only explains/recommends** | adr/0005 |
| 6 | Every integration behind a mock-first adapter (port) | adr/0006 |

The four that matter most: **AI never moves money**, **event-source what needs
auditing**, **RLS for tenant isolation**, **mocks so the whole flow runs offline**.

## Domain rules that must stay configurable (not constants)
- KCC limit = `SoF × area × cropping pattern + 10% post-harvest + 20% maintenance
  + insurance`, netted against existing liabilities.
- Collateral-free ceiling (RBI raised to ₹2,00,000 in 2025) — a policy value.
- Interest subvention (MISS), PSL-Agriculture tagging, IRAC asset classes.
- Scale of Finance (SoF) is set annually per district per crop by the DLTC.
All of the above change via a **config version bump**, never code.

## Compliance constraints (hard)
- **DPDP Act 2023** — consent, purpose limitation, data-subject rights, India
  data residency.
- **Aadhaar Act / UIDAI** — tokenise Aadhaar (never store raw), mask in UI/logs,
  capture consent.
- Append-only / WORM audit; dual control + idempotency + reconciliation on money.

## Tech stack
Next.js/React/TS/Tailwind/shadcn/Framer (web + offline PWA) · FastAPI/Python ·
PostgreSQL (SoR + event store + outbox) · Redis · Kafka (bus) · Elasticsearch
(read/search) · MinIO/S3 (docs) · Celery (async/AI) · Docker/K8s ·
Prometheus/Grafana/OpenTelemetry.

## Current state of the repo (2026-06-18)
- **Planning complete** for the first cut: improved prompt + gap analysis +
  architecture method + 6 ADRs + domain/system/AI/security docs + roadmap.
- **`packages/eligibility-engine`** — pure, dependency-free, fully unit-tested
  (15 tests) deterministic KCC limit calculator.
- **`apps/api` — Milestone 0 walking skeleton DONE (7 tests green).** FastAPI
  modular monolith proving the spine: ASGI context/auth middleware, tenant
  isolation guard, event-sourced `LoanApplication`, server-side maker-checker,
  hash-chained audit, mock-first integration adapters (KYC with tokenised
  Aadhaar), and the eligibility engine wired into the Assessment context. A full
  KCC lead→sanction flow runs end-to-end on mocks.
- **Credit-Memo agent DONE (16 API tests green).** AI is optional by design:
  with a healthy provider it narrates the memo; otherwise it auto-falls-back to a
  deterministic template memo, plus manual/skip options — the workflow never
  blocks on AI. `GET /ai/health` drives the UI. Provider via `ALOS_LLM_PROVIDER`
  (none|mock|real). New `MemoGenerated` workflow stage.
- **Workflow/saga engine DONE (ADR-0004)** — `platform/workflow.py`: the KCC
  lifecycle is a config-driven, versioned `WorkflowDefinition`; the service
  enforces transition legality, maker-checker, and per-stage role requirements.
- **Documentation → Disbursement → CBS DONE** — NESL/eStamp/eSign saga with
  compensation on partial failure; idempotent money events (double-disburse →
  one effect, same reference); reconciliation store + `/reconciliation/report`.
- **Full lifecycle workspace site DONE (`apps/web`)** — served at `/app`;
  glassmorphism UI with a derived workflow timeline, health-score ring, and
  stage-aware actions (memo with AI fallback, maker/checker/sanction, docs,
  disburse, CBS, reconciliation). Verified end-to-end over HTTP.
- **Postgres event + audit stores with RLS DONE (Milestone 2, ADR-0003)** —
  `platform/pg_events.py`, `platform/pg_audit.py`, `migrations/0001_init.sql`.
  Selected via `ALOS_STORAGE=postgres`; tenant isolation enforced by Postgres
  Row-Level Security (FORCE RLS, non-superuser app role). Verified against a real
  database: RLS hides other tenants' rows, WITH CHECK blocks cross-tenant insert,
  optimistic concurrency holds, per-tenant hash-chained audit verifies, and the
  full lead→CBS lifecycle runs over HTTP on the Postgres backend.
- **26 tests green** (API 21 in-memory + 5 Postgres RLS; engine 15 separately).
- **Not yet built:** Redis/Kafka drivers (idempotency + outbox), real (non-mock)
  integrations behind feature flags, additional AI agents (Land/Risk/Fraud/
  Compliance), renewal + 2nd product, and the production Next.js + offline field
  PWA. See roadmap M2 (remainder)–M3.

## Where things live
```
prompts/   ALOS_Master_Prompt_v2.md (use this), v1_original (reference)
docs/      00 gap-analysis · 01 architecture-method · 02 domain · 03 system
           05 AI · 06 security · 07 roadmap · adr/ (the decisions)
DESIGN.md  consolidated technical design (single-page architecture)
packages/eligibility-engine/   the first built component
.github/workflows/ci.yml        runs the engine tests
```

## What to do next (proposed)
Milestones 0 and 1 are done (full KCC lead→CBS lifecycle on mocks, end-to-end).
Next, Milestone 2: swap an in-memory store for a real driver (Postgres event
store + RLS) behind the existing interfaces, then replace one mock integration
(e.g. KYC) with a real/sandbox adapter behind a feature flag, with contract
tests. Then renewal + a 2nd product (config-only) to prove the multi-product
seam. Full plan in `docs/07-roadmap.md`.

## Working agreement
- Decisions that are hard to reverse or touch money → write an ADR first.
- Every increment meets the Definition of Done in `prompts/ALOS_Master_Prompt_v2.md` §12.
- Keep the eligibility engine pure (no I/O, no framework imports).
