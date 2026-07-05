# alos-api — KCC walking skeleton (Milestone 0)

FastAPI **modular monolith** (ADR-0001) proving the cross-cutting spine before
features are piled on:

- **Auth + tenant binding** via `ContextMiddleware` (dev: `X-User-Id` /
  `X-Tenant-Id` headers → a `Principal`; prod: OIDC, same downstream shape).
- **Tenant isolation** (ADR-0003) — app-layer guard mirroring Postgres RLS;
  cross-tenant access → 403.
- **Event-sourced `LoanApplication`** (ADR-0002) — append-only stream, state is
  a fold, optimistic concurrency.
- **Server-side maker-checker** — a checker gate cannot be cleared by the maker.
- **Hash-chained audit** (docs/06) — tamper-evident; `/audit/verify`.
- **Mock-first integration adapters** (ADR-0006) — KYC adapter with retry +
  circuit breaker; returns only a **tokenised/masked Aadhaar**, never the raw number.
- **Eligibility engine wired in** (ADR-0005) — the pure
  `packages/eligibility-engine` computes the KCC limit; the API records the
  result as an application event.
- **Credit-Memo agent with AI-optional design** — AI narrates the memo when a
  provider is healthy; otherwise the agent automatically returns a deterministic
  **template memo**, so the workflow never blocks. Plus **manual** and **skip
  (with audited reason)** options. `GET /ai/health` exposes status + fallbacks.

## AI is optional by design
`ALOS_LLM_PROVIDER` selects the provider: `none` (default — "no AI running"),
`mock` (demo/test), or a real provider. When AI is unavailable *or a live call
fails*, `POST /applications/{id}/memo/generate` falls back to the template memo
and reports `mode: "template"`, `ai_available: false`, and a `fallback_reason`.
Other ways to complete the step: `POST .../memo/manual` (human writes/overrides)
and `POST .../memo/skip` (requires a reason; recorded in the audit chain).

- **Config-driven workflow/saga engine** (ADR-0004) — `platform/workflow.py`.
  The KCC lifecycle is a versioned `WorkflowDefinition`; the service enforces
  transition legality, maker-checker, and per-stage role requirements. Adding a
  product/approval-chain = new definition, not new code.
- **Documentation → Disbursement → CBS** — NESL/eStamp/eSign **saga with
  compensation** (partial failure rolls back), **idempotent money events** (a
  repeat `/disburse` returns the same reference and emits no second event), and a
  **reconciliation** store (`GET /reconciliation/report`).

## Full KCC lifecycle (all mocked)
```
Lead → CustomerLinked → KycCompleted → EligibilityComputed → MemoGenerated
   → MakerReviewed → CheckerReviewed → Sanctioned → DocumentsExecuted
   → Disbursed → CbsPosted
```
`GET /applications/{id}/timeline` returns the stages + an **application health
score**, both derived from the event log so they can't drift from reality.

## Real integrations behind feature flags (ADR-0006)
KYC can point at a vendor sandbox over real HTTP while everything else stays
mocked:
```bash
# terminal 1 — a stand-in vendor sandbox
PYTHONPATH=src uvicorn scripts.kyc_sandbox:app --port 9099
# terminal 2 — the API with the flag flipped
ALOS_KYC_PROVIDER=sandbox ALOS_KYC_SANDBOX_URL=http://127.0.0.1:9099 \
  PYTHONPATH=src uvicorn alos_api.main:app
```
`integrations/kyc.py` has both `MockKycAdapter` and `SandboxKycAdapter` behind one
Port; `parse_vendor_kyc` is the single schema boundary. The **contract test**
(`tests/test_kyc_contract.py`) pins the vendor response shape and asserts the
mock obeys the same `KycResult` contract, so the mock can't drift from reality.

## Demonstrator site
A self-contained UI (`apps/web`) is served at **`/app`**. It renders the derived
workflow timeline + health ring and offers stage-aware actions: the memo step
(AI / template / manual / skip), maker → checker → sanction, document execution,
disbursement, CBS posting, and the reconciliation report. Run uvicorn and open
`http://localhost:8000/app/`.

## Run

```bash
cd apps/api
pip install -e ../../packages/eligibility-engine
pip install fastapi uvicorn "pydantic>=2" pydantic-settings httpx pytest
PYTHONPATH=src python -m pytest -q          # tests (7)
PYTHONPATH=src uvicorn alos_api.main:app    # serve; docs at /docs
```

## Try the KCC flow (mock everything)

```bash
H='-H X-User-Id:maker1 -H X-Tenant-Id:bankA -H X-Roles:Maker'
# create lead
curl -s $H -X POST localhost:8000/applications \
  -d '{"applicant_name":"Ramesh","mobile":"9999999999"}' -H content-type:application/json
# ... link-customer, /kyc, /assessment/{id}/eligibility,
#     advance/MakerReviewed, advance/CheckerReviewed (different user), advance/Sanctioned
```

## Boundaries (so the monolith stays modular)
Contexts live under `src/alos_api/contexts/<context>` and depend on the platform
kernel (`platform/`) and integration **ports** only — never on another context's
internals. This is what makes a future service extraction mechanical.

## What this is NOT yet
No real DB (in-memory stores stand in for Postgres/Redis/Kafka behind
interfaces), no real integrations (all mock), no AI agent yet, no web UI. Those
are Milestones 1–2 in `docs/07-roadmap.md`.
