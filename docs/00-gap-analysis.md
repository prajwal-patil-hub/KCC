# 00 — Gap Analysis: what v1 was missing & what to implement

This document critiques the original `ALOS_Master_Claude_Prompt.md`, lists the
gaps, and maps each gap to a concrete, implementable decision. It answers the
brief: *"what's missing, what can be implemented."*

## How to read this
Each gap has: **Why it matters → Decision/what to implement → Where it lives.**
Severity: 🔴 blocker (correctness/legal/money), 🟠 important, 🟡 nice-to-have.

---

## A. Regulatory & domain grounding (the biggest gap)

The v1 prompt listed a workflow but **no actual lending rules**. A lending OS
that doesn't encode the rules is a CRM with extra steps.

| # | Gap | Sev | Decision / what to implement | Where |
|---|---|---|---|---|
| A1 | No KCC limit formula | 🔴 | Implement deterministic limit engine: `SoF × area × cropping pattern + 10% post-harvest + 20% maintenance + insurance`. SoF as versioned, district×crop reference table sourced from DLTC. | Eligibility context |
| A2 | No collateral-free ceiling | 🔴 | Make the collateral-free limit a **policy value** (RBI raised it to ₹2L in 2025). Above ceiling → security workflow. | Policy config |
| A3 | No interest subvention (MISS) | 🟠 | Scheme-versioned subvention rules; effective rate derived, not stored raw. | Policy config |
| A4 | No PSL tagging | 🟠 | Every sanction carries a PSL-Agri classification tag for regulatory returns. | Loan aggregate |
| A5 | No IRAC / asset classification states | 🟠 | Reserve Standard/SMA-0/1/2/NPA in the loan lifecycle model even if collections is out of MVP scope. | Domain model |
| A6 | No annual config versioning | 🔴 | SoF, ceilings, subvention, doc checklists are **effective-dated, versioned config**, never constants. | Config service |

## B. Non-functional requirements (unquantified in v1)

| # | Gap | Sev | Decision | Where |
|---|---|---|---|---|
| B1 | No scale/latency/availability targets | 🟠 | Defined in prompt v2 §5 (500 concurrent, 5k apps/day, P95 budgets, 99.9%). | Prompt v2 |
| B2 | No RPO/RTO/DR | 🔴 | RPO ≤ 5 min, RTO ≤ 1 h; event+audit store = source of truth, cross-AZ backup. | Architecture |
| B3 | No data residency stance | 🔴 | All PII in India; LLM in-country path for sensitive payloads (DPDP Act). | Security doc |
| B4 | Offline-first stated, no conflict strategy | 🔴 | Define sync protocol + conflict resolution (per-field LWW with vector clocks for capture data; server authoritative for money). | Architecture |

## C. Architecture rigor

| # | Gap | Sev | Decision | Where |
|---|---|---|---|---|
| C1 | "Microservices" assumed from day 1 | 🟠 | **Modular monolith first**, strangler to services on proven need. | ADR-0001 |
| C2 | Event sourcing everywhere = over-engineering | 🟠 | **Selective** event sourcing (application + money only) + outbox. | ADR-0002 |
| C3 | No tenancy model chosen | 🔴 | Shared schema + Postgres RLS, path to schema-per-tenant. | ADR-0003 |
| C4 | No saga/process-manager for long workflows | 🔴 | Explicit workflow engine with compensations, not event-handler chains. | Architecture |
| C5 | No idempotency/reconciliation for money | 🔴 | Idempotency keys + reconciliation jobs for disbursement/CBS/eSign/NESL. | Integrations |
| C6 | No clear MVP slice | 🔴 | Thin KCC vertical slice defined. | Roadmap |
| C7 | No build-vs-buy for integrations | 🟡 | Decide per integration (e.g. KYC aggregator vs direct). | Integrations |

## D. AI architecture

| # | Gap | Sev | Decision | Where |
|---|---|---|---|---|
| D1 | Agents named, not specified | 🟠 | One-page spec per agent: inputs/tools/outputs/guardrails/evals. | AI doc |
| D2 | No PII redaction before LLM | 🔴 | Tokenise/redact PII pre-call; in-country model for sensitive data. | AI doc |
| D3 | LLM doing math = hallucination risk | 🔴 | **Numbers are deterministic code**; AI only explains/recommends. | AI doc |
| D4 | No eval/governance/versioning | 🟠 | Prompt versions, model registry, golden+regression evals, drift monitor. | AI doc |
| D5 | No human-in-the-loop thresholds | 🟠 | Confidence + ticket-size thresholds force human review; configurable. | AI doc |
| D6 | No grounding/citations | 🟠 | RAG over bank policy + RBI circulars with citations. | AI doc |

## E. Security & compliance (was "phase 13", too late)

| # | Gap | Sev | Decision | Where |
|---|---|---|---|---|
| E1 | No Aadhaar handling rules | 🔴 | Tokenise Aadhaar, mask in UI/logs, Virtual ID, consent capture (Aadhaar Act/UIDAI). | Security doc |
| E2 | No DPDP Act 2023 mapping | 🔴 | Consent artefacts, purpose limitation, data-subject rights, breach hooks. | Security doc |
| E3 | RBAC only, no ABAC | 🟠 | RBAC (roles) + ABAC (tenant/branch/product/amount) + SoD. | Security doc |
| E4 | No secrets/key management | 🔴 | Vault + KMS/HSM, rotation, no secrets in git. | Security doc |
| E5 | Audit "store" not immutable | 🔴 | Hash-chained / WORM, tamper-evident audit. | Security doc |
| E6 | No threat model | 🟠 | STRIDE per bounded context. | Security doc |

## F. UX realities

| # | Gap | Sev | Decision | Where |
|---|---|---|---|---|
| F1 | Premium UI ignored field reality | 🟠 | Low-bandwidth, offline, vernacular field-capture mode on cheap Android. | Prompt v2 §9 |
| F2 | No localization | 🟠 | Hindi + regional language; i18n from day 1. | Frontend |
| F3 | No accessibility target | 🟡 | WCAG 2.1 AA. | Frontend |
| F4 | Health score/timeline source unclear | 🟡 | Derived from event log so they can't lie. | Architecture |

## G. Things v1 didn't mention at all

- **Reconciliation & double-entry ledger** for disbursement and CBS posting. 🔴
- **Business Correspondent (BC) / agent network model** common in agri lending. 🟡
- **Co-lending** design hook (future). 🟡
- **Regulatory reporting** (PSL returns, CRILC, etc.) data capture. 🟠
- **Notification orchestration** (SMS/WhatsApp/email) as an outbound adapter
  with templates, DLT compliance (TRAI), and delivery audit. 🟠
- **Sandbox/staging strategy for government APIs** that are hard to access —
  mock mode is the default dev experience, real adapters behind flags. 🔴

---

## What we will actually implement first (the answer to "what can be implemented")

Ranked by value-to-effort for the **KCC MVP**:

1. **Deterministic Eligibility/Limit engine** (A1–A3, D3). Pure, testable, no
   external deps. Highest certainty, highest demo value. → build first.
2. **Application aggregate with selective event sourcing + audit** (C2, E5).
   The spine everything hangs off.
3. **Tenancy + RLS + auth + maker/checker gate** (C3, E3). Correctness skeleton.
4. **Integration adapter framework with mock mode** (C5, G-sandbox). Lets the
   whole flow run with zero real government access.
5. **One AI agent done right — Credit-Memo agent, grounded + governed** (D1–D6).
6. **Field capture PWA (offline, vernacular) for Land/Crop** (B4, F1).

Everything else is designed-for but deferred. See `docs/07-roadmap.md`.
