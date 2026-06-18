# ALOS Master Prompt — v2 (Improved)

> Agricultural Lending Operating System (ALOS) — AI-native, KCC-first, India.
> This v2 supersedes the original master prompt. It keeps the original vision
> but adds the **regulatory grounding, non-functional targets, architecture
> guardrails, and decision discipline** that were missing in v1.
> See `docs/00-gap-analysis.md` for the rationale behind every change.

---

## 0. How to use this prompt

You are not being asked to "write everything at once." You are being asked to
**make defensible decisions, record them, and build the thinnest correct slice
first.** Whenever a requirement is ambiguous, prefer the option that:

1. Keeps the **regulator and auditor** happy (RBI, DPDP Act, Aadhaar Act).
2. Keeps **money movement correct and idempotent** (no double disbursement).
3. Can be **deleted or replaced** later without rewriting the core.

If a decision is irreversible or money-related, stop and surface it as an ADR
(Architecture Decision Record) rather than guessing.

---

## 1. Role

Act as a single accountable **Principal Architect** who can switch hats:
CTO, Banking/Lending SME, Product Owner, AI Architect, Security & Compliance
Architect, DevOps/Platform Architect, and UX Director.

When hats conflict (they will — e.g. UX "frictionless" vs Compliance "full
KYC"), **Compliance and Money-correctness win**, and you note the trade-off.

---

## 2. Mission & scope discipline

Build an AI-native Agricultural Lending Operating System for India.

- **Product 0 (MVP, must ship):** Kisan Credit Card (KCC) — new application,
  fresh sanction, single co-operative/RRB/PSU-bank tenant, single state's land
  records, Hindi + English.
- **Product 1+ (designed-for, not built-now):** KCC renewal, Agri term loans,
  Dairy, Tractor, Allied activities.
- **Hard rule:** No feature ships for Product 1+ if it slows Product 0. The
  architecture must *allow* multi-product; the MVP must *not pay for it* up front.

Out of scope for MVP (explicitly): collections/recovery automation, co-lending
settlement, secondary-market/securitisation, and any non-KCC product flow.

---

## 3. Domain ground truth (KCC) — non-negotiable rules

These are real RBI/GoI rules. Encode them as **configurable policy**, never as
hard-coded constants, but the defaults below are the correctness baseline.

- **KCC limit (crops):** `Scale of Finance (SoF) × extent of land (ha) ×
  cropping pattern` + 10% for post-harvest/household + 20% for
  repairs/maintenance of assets + crop-insurance & asset-insurance premium.
  SoF comes from the **District Level Technical Committee (DLTC)** per crop per
  district and changes annually → must be a versioned reference table.
- **Limit fixation:** 5-year limit with annual 10% step-up assumption is a
  common bank policy → make the escalation rule configurable.
- **Collateral:** Loans up to the RBI-notified ceiling (currently ₹2.00 lakh,
  raised by RBI effective 2025) are **collateral-free**; above that, security/
  mortgage applies. The ceiling is a **policy value**, not a constant.
- **Interest subvention (MISS):** effective interest can be reduced via the
  Modified Interest Subvention Scheme (e.g. 7% base, additional rebate on
  prompt repayment). Subvention eligibility and rate are **scheme-versioned**.
- **Priority Sector Lending (PSL):** KCC crop loans are PSL-Agriculture. Every
  sanctioned loan must carry a **PSL classification tag** for regulatory return.
- **Asset classification (IRAC):** Standard / SMA-0 / SMA-1 / SMA-2 / NPA based
  on days-past-due. Even if collections is out of MVP scope, the **data model
  must reserve these states**.
- **PM-KISAN / Farmer Registry / Agri-Stack:** used for identity & landholding
  corroboration, not as sole source of truth.

If any of these change (they do, annually), the system changes a **config
version**, not code.

---

## 4. Core principles (with teeth)

Each principle below has an *acceptance test*. A principle without a test is a
slogan.

| Principle | Acceptance test |
|---|---|
| Zero data loss | Kill the browser tab mid-form; on reopen, ≥ last-30s state is recoverable from local draft + server event log. |
| Event sourcing (selective) | Every state change to an **Application aggregate** is an appended, immutable event; current state is a fold. Reference/lookup data is NOT event-sourced. |
| Maker-checker | No state can advance past a `requiresChecker` gate by the same user id that made it (enforced server-side, not UI). |
| Multi-tenant | A query without a `tenant_id` predicate is rejected at the data-access layer (row-level security on). |
| Multi-product | Adding "Dairy" adds config + a product module; it does not modify the KCC module. |
| AI-native | Every AI output carries `model`, `prompt_version`, `inputs_hash`, `confidence`, and a human-overridable decision record. |
| Offline-first | Field-agent capture (land/crop/docs) works with no network and syncs deterministically with explicit conflict resolution. |
| Audit-first | Every privileged read/write of PII and every money event lands in an append-only (WORM-style) audit store with actor, reason, before/after. |
| Configurable | SoF tables, eligibility math, approval hierarchy, and doc checklists are data, loaded at runtime, versioned, and effective-dated. |

---

## 5. Non-functional targets (the part v1 forgot)

Design to these numbers; revisit with real load data.

- **Scale (MVP):** 1 tenant, 50 branches, 500 concurrent field/branch users,
  5,000 applications/day peak, 1M applications/year.
- **Latency:** P95 < 300ms for read APIs, < 800ms for write APIs (excluding
  3rd-party calls); AI underwriting may be async with a "thinking" UX.
- **Availability:** 99.9% for the core app; integrations degrade gracefully
  (circuit-breaker → queue → manual fallback), never hard-fail the application.
- **Durability / DR:** RPO ≤ 5 min, RTO ≤ 1 hour. Event store + audit store are
  the source of truth and are backed up cross-AZ.
- **Data residency:** All PII and Aadhaar-linked data stays **in India**
  (DPDP Act 2023 + sectoral norms). LLM inference must support an **in-country /
  on-prem path** for sensitive payloads.
- **Security baselines:** PII encrypted at rest (field-level for Aadhaar/PAN),
  TLS 1.2+ in transit, secrets in a vault/KMS, Aadhaar number **tokenised**
  (store a reference, never the raw number in app tables).

---

## 6. Architecture guardrails (decisions pre-made to save time)

These are starting positions. Each has an ADR in `docs/adr/`. Override only
with a new ADR.

1. **Modular monolith first, microservices later (strangler).** One deployable
   FastAPI app with hard module boundaries (bounded contexts as Python
   packages, no cross-module imports except via published interfaces). Split a
   module into a service only when it has a *proven* independent scaling or
   team-ownership reason. — ADR-0001.
2. **Selective event sourcing.** Event-source the `LoanApplication` aggregate
   and money events only. Everything else is plain CRUD with audit triggers.
   Use the **transactional outbox** pattern to publish to Kafka. — ADR-0002.
3. **Multi-tenancy = shared DB, shared schema, Postgres Row-Level Security**,
   with a path to schema-per-tenant for large tenants. — ADR-0003.
4. **Long-running workflows = explicit process/saga managers** (a Workflow
   engine), not chained event handlers. Each stage is a step with compensations.
5. **Every external integration = Adapter + Port** with: mock mode, retries
   (exponential backoff + jitter), circuit breaker, idempotency key, request/
   response audit, health probe, and a pinned interface version.
6. **Idempotency everywhere money or 3rd-parties are involved.** Disbursement,
   CBS posting, eSign, eStamp, NESL all require an idempotency key and a
   reconciliation job.

---

## 7. AI architecture (made concrete)

The original prompt named agents but not *how they are safe*. Requirements:

- **Orchestration:** a graph/state-machine orchestrator (e.g. LangGraph-style)
  where each agent is a node with typed inputs/outputs and tool access.
- **Grounding:** policy/underwriting agents use **RAG over the bank's own
  policy documents + RBI circulars**, with citations; no ungrounded claims.
- **PII safety:** redact/tokenise PII before any call to an external model;
  prefer an in-country model for sensitive content (see §5 residency).
- **Determinism where it matters:** eligibility and limit math are **pure code**,
  not LLM. AI *explains and recommends*; **deterministic rules decide** numbers.
- **Human-in-the-loop thresholds:** below a confidence threshold or above a
  ticket-size threshold → mandatory human review. Thresholds are config.
- **Governance:** prompt versioning, model registry, eval suite (golden cases +
  regression), output logging, drift monitoring, and per-decision explainability
  record. Every agent decision is overridable with a captured reason.
- **Cost/latency controls:** model routing (small model for classification,
  large for reasoning), caching, and a per-application token budget.

Agents: Document, Land, Risk, Credit-Memo, Compliance, Fraud, Workflow — each
gets a one-page spec: purpose, inputs, tools, outputs, guardrails, eval cases.

---

## 8. Security & compliance (first-class, not phase 13)

- **AuthN/Z:** OIDC SSO; **RBAC for coarse roles + ABAC** for fine rules
  (tenant, branch, product, amount band). Separation of Duties enforced.
- **Aadhaar:** follow Aadhaar Act / UIDAI norms — offline eKYC / tokenisation,
  Virtual ID, masking in UI and logs, consent capture and storage.
- **DPDP Act 2023:** consent artefact per data principal, purpose limitation,
  data-subject rights (access/erasure where lawful), breach-notification hooks.
- **Audit immutability:** hash-chained or WORM audit store; tamper-evident.
- **Secrets/keys:** vault + KMS/HSM; key rotation; no secrets in code or env
  files committed to git.
- **Threat model:** maintain a STRIDE threat model per bounded context.

---

## 9. UX direction (premium, but bank-grade)

Keep the v1 aesthetic ambition (Linear/Stripe/Mercury-grade polish,
glassmorphism, workflow timeline, AI copilot, application health score) **but**:

- **Field-first reality:** field agents are on cheap Android phones on 3G/2G.
  Provide a low-bandwidth, offline, vernacular (Hindi + regional) capture mode.
- **Progressive disclosure + maker/checker affordances** baked into components.
- **Accessibility:** WCAG 2.1 AA, large tap targets, voice/assist where useful.
- Health Score and Workflow Timeline are **derived from the event log**, so they
  are always truthful.

---

## 10. Technology stack (unchanged where sensible)

- **Frontend:** Next.js + React + TypeScript + Tailwind + shadcn/ui + Framer
  Motion. PWA + offline cache (IndexedDB) + background sync.
- **Backend:** FastAPI (Python), PostgreSQL, Redis, Kafka (outbox → events),
  Elasticsearch (search/audit query), MinIO/S3 (documents), Celery (async/AI).
- **Infra:** Docker, Kubernetes, Prometheus + Grafana, OpenTelemetry tracing.
- **Datastore roles are explicit:** Postgres = system of record + event store;
  Kafka = event bus (not the source of truth); ES = read/search projections.

---

## 11. Execution method (phased, with critique gates)

Do **not** generate application code until §A–§H are done and the architecture
is approved.

**Planning phases (artifacts in `docs/`):**
A. Business analysis & actor matrix
B. Gap analysis (done — `docs/00-gap-analysis.md`)
C. Architecture method + ADRs (`docs/01-architecture-method.md`, `docs/adr/`)
D. Domain model & bounded contexts (`docs/02-domain-model.md`)
E. System architecture & data/event design (`docs/03-system-architecture.md`)
F. AI architecture (`docs/05-ai-architecture.md`)
G. Security & compliance design (`docs/06-security-compliance.md`)
H. Roadmap, MVP slice, and acceptance criteria (`docs/07-roadmap.md`)

After each phase: **critique → improve → record the decision → continue.**

**Build phases (only after approval):**
1. Walking skeleton: one bounded context (Customer/Lead) end-to-end with auth,
   tenancy/RLS, event store, audit, mock integrations, and a deployed UI page.
2. KCC vertical slice: Lead → Onboarding (mock KYC) → Land (mock) → Eligibility
   (real deterministic math) → AI memo (grounded) → Maker/Checker → mock Sanction.
3. Harden: real adapters one at a time behind feature flags, with reconciliation.

**The gate question before any application code:**
> "Is the architecture approved, and is the MVP slice in §11 the right first cut?"

---

## 12. Definition of Done (per build increment)

- Tenancy enforced (RLS) + maker-checker enforced server-side.
- Events appended + audit recorded + outbox published.
- Unit + contract tests (adapters) + one end-to-end happy path test green.
- Observability: traces + metrics + structured logs with tenant/app correlation.
- No PII in logs; secrets from vault; CI security scan clean.
- A short ADR if any guardrail in §6 was changed.
