# DESIGN — ALOS (consolidated technical design)

Single-page design that ties the `docs/` set together. For depth, follow the
links. For *why* a choice was made, see the referenced ADR.

---

## 1. Design goals (ranked)
1. Money & decision **correctness** (a wrong disbursement is unrecoverable).
2. **Auditability** / regulatory defensibility (RBI, DPDP, Aadhaar).
3. **Zero data loss** (durability).
4. **PII security & privacy**.
5. **Evolvability** (multi-product / multi-state / annual rule changes).
6. **Availability** (degrade gracefully, never hard-fail an application).
7. Performance, then 8. cost/time-to-market.

A choice that trades down 1–4 to buy 6–8 is rejected by default. The method for
reaching these choices is in [`docs/01-architecture-method.md`](docs/01-architecture-method.md).

## 2. System shape (modular monolith — [ADR-0001](docs/adr/0001-modular-monolith-first.md))
One deployable FastAPI app; bounded contexts are Python packages with published
interfaces and no cross-module reach-in. Contexts:

```
Platform:   Identity/Access · Tenancy · Config · Audit · Event Store · Notification
Acquisition: Lead · Customer · KYC
Assessment:  Land · Crop · Bureau/Liability · Eligibility(pure)
Decision:    Underwriting(AI+rules) · Credit Memo · Approval · Documentation ·
             Disbursement/CBS · Servicing/Renewal(future)
```
Likely first service extractions when scaling: Document/AI, Notification, Land.
Full context map + aggregates: [`docs/02-domain-model.md`](docs/02-domain-model.md).

## 3. Container & data view
```
Web (Next.js) + Field PWA (offline IndexedDB+sync)
        │ HTTPS / OIDC
   API/BFF (FastAPI)  ── authN, tenant resolution, tracing, rate limit
        │ in-process ports
   ALOS monolith ── Eligibility engine (pure) · Workflow saga engine ·
                    Integration ports (mock/sandbox/prod) · AI orchestrator ·
                    Event-store + Audit writers
        │
 Postgres(SoR+event store+outbox, RLS) · Redis(cache/locks/idempotency) ·
 Kafka(bus via outbox) · Elasticsearch(read/search/audit) · MinIO/S3(docs,WORM) ·
 Celery(AI/OCR/land/recon)
        │ adapters (retry · circuit-breaker · idempotent · audited)
 External: Aadhaar·PAN·CKYC·AA/Sahamati·DigiLocker·NESL·eStamp·eSign·
           Land records·CBS·Bureaus·PM-KISAN·SMS/WhatsApp/Email
```
**Store roles:** Postgres is the source of truth (incl. event store); Kafka is a
bus, not truth; ES holds read/search projections; MinIO holds documents.
Detail + diagram: [`docs/03-system-architecture.md`](docs/03-system-architecture.md).

## 4. State & events ([ADR-0002](docs/adr/0002-selective-event-sourcing.md))
- Event-source **only** `LoanApplication` + **money events**; everything else is
  CRUD with audit triggers.
- Canonical write = one DB transaction appending **event + outbox row + audit
  row**; outbox relay publishes to Kafka; consumers update ES idempotently.
- Events: past-tense, context-prefixed, versioned with upcasters; periodic
  snapshots. Every event carries `tenant_id, application_id, actor_id,
  correlation_id, occurred_at, schema_version`.

## 5. Workflow ([ADR-0004](docs/adr/0004-workflow-engine.md))
Lifecycle is an explicit, **config-driven** saga: each stage has entry guards,
an action (often an adapter call), success/failure transitions, a
**compensation**, and a maker/checker gate flag. Adding a product or changing
the approval chain is configuration. The Workflow Timeline UI is **derived from
real workflow state** so it can't lie.

## 6. Eligibility (deterministic core — [ADR-0005](docs/adr/0005-deterministic-decisions-ai-explains.md))
```
crop_loan    = Σ SoF(crop,season) × area_sown
post_harvest = 10% × crop_loan ; maintenance = 20% × crop_loan
insurance    = crop premia + asset premium
gross_limit  = crop_loan + post_harvest + maintenance + insurance
net_limit    = gross_limit − existing agri/KCC liabilities
```
Pure, reproducible, fully unit-tested. Outputs: limit breakup, collateral-free
flag, PSL tag, subvention eligibility, effective interest rate, per-crop audit
trace. Built in [`packages/eligibility-engine`](packages/eligibility-engine).
**AI explains these numbers; it never computes them.**

## 7. AI architecture ([`docs/05-ai-architecture.md`](docs/05-ai-architecture.md))
- Graph orchestrator; agents are typed nodes (Document, Land, Risk, Credit-Memo,
  Compliance, Fraud, Workflow). Each run emits a decision record with
  `model, prompt_version, inputs_hash, confidence, citations, cost`.
- **Grounding:** RAG over bank policy + RBI circulars, with citations.
- **PII safety:** redact/tokenise before any model call; in-country inference for
  sensitive payloads.
- **Governance:** prompt + model registry, golden+regression evals in CI, drift
  monitoring, human-in-the-loop thresholds (confidence + ticket size), and a
  human override captured as an audited event.
- Credit-Memo agent is the first one built.

## 8. Multi-tenancy ([ADR-0003](docs/adr/0003-multi-tenancy-rls.md))
Shared schema + Postgres **Row-Level Security**: every tenant-scoped table has
`tenant_id`; queries without tenant context are rejected (app guard + DB RLS).
Large tenants can be promoted to schema-per-tenant with no app change. Negative
isolation tests run in CI.

## 9. Security & compliance ([`docs/06-security-compliance.md`](docs/06-security-compliance.md))
OIDC SSO · RBAC (roles) + ABAC (tenant/branch/product/amount) + SoD ·
Aadhaar tokenisation + masking + consent · DPDP consent/rights/residency ·
field-level PII encryption · vault + KMS/HSM · hash-chained/WORM audit ·
idempotency + dual control + reconciliation on all money movement ·
STRIDE threat model per context.

## 10. Offline-first & resilience
Field PWA captures to IndexedDB as client-id'd commands with vector clocks;
background sync replays them, **server is authoritative**; per-field LWW for
capture data, never client-authoritative for money. Each adapter has retry +
circuit breaker + bulkhead; an outage queues + drops to a manual-fallback stage
rather than hard-failing the application.

## 11. Integrations ([ADR-0006](docs/adr/0006-integration-adapters-mock-first.md))
Every external system sits behind a Port with mock / sandbox / prod adapters.
Uniform: mock mode (default in dev/CI), retry+backoff+jitter, circuit breaker,
idempotency key, PII-redacted audit, health probe, pinned version, reconciliation
for money/doc effects. The full flow runs end-to-end with **zero real access**.

## 12. Build sequence ([`docs/07-roadmap.md`](docs/07-roadmap.md))
- **M0** walking skeleton: one context end-to-end (auth, RLS, event store, audit,
  outbox, mock adapters).
- **M1** KCC vertical slice on mocks: Land/Crop → eligibility (built) → AI memo →
  maker/checker/approval → mock sanction/disbursement/CBS (idempotent + recon).
- **M2** real adapters one-at-a-time behind flags + hardening.
- **M3** renewal + 2nd product as config (prove the seam).
- **M4** scale: promote a tenant to schema; extract first service.

## 13. Definition of Done (per increment)
Tenancy (RLS) + maker-checker enforced server-side · event + audit + outbox
written · unit + adapter-contract + one e2e happy-path test green · OTel traces +
business/technical metrics + PII-free structured logs · secrets from vault · CI
security scan clean · an ADR if any guardrail changed.
