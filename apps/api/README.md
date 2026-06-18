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
