# 03 — System Architecture & Data/Event Design

## C4 — Container view (logical)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Clients                                                               │
│  • Next.js web app (branch/credit users)  • PWA field-capture (agents) │
│    offline IndexedDB + background sync                                  │
└───────────────┬───────────────────────────────────────────────────────┘
                │ HTTPS (OIDC tokens)
        ┌───────▼────────┐
        │  API Gateway / │  rate-limit, authN, tenant resolution, tracing
        │  BFF (FastAPI) │
        └───────┬────────┘
                │ in-process module calls (ports)
 ┌──────────────▼──────────────────────────────────────────────────────┐
 │  ALOS Modular Monolith (FastAPI)                                      │
 │  Acquisition · Assessment · Decision · Platform contexts             │
 │  ── Eligibility engine (pure)  ── Workflow engine (saga)             │
 │  ── Integration ports (mock/sandbox/prod adapters)                   │
 │  ── AI orchestrator (agents) ── Audit + Event Store writers          │
 └───┬──────────┬─────────┬──────────┬───────────┬──────────┬──────────┘
     │          │         │          │           │          │
 ┌───▼───┐ ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌────▼────┐ ┌───▼─────┐
 │Postgres│ │ Redis │ │ Kafka  │ │ Elastic│ │ MinIO/  │ │ Celery  │
 │SoR +   │ │cache/ │ │outbox→ │ │search/ │ │ S3 docs │ │ workers │
 │event   │ │locks  │ │events  │ │audit Q │ │         │ │ (AI/IO) │
 │store   │ │       │ │        │ │        │ │         │ │         │
 └────────┘ └───────┘ └────────┘ └────────┘ └─────────┘ └─────────┘
                │ adapters (retry/CB/idempotent/audited)
   External: Aadhaar·PAN·CKYC·AA/Sahamati·DigiLocker·NESL·eStamp·eSign·
             Land records·CBS·Bureaus·PM-KISAN/Farmer Registry·SMS/WA/Email
```

## Data architecture & store roles
- **Postgres** = system of record + event store + outbox. RLS for tenancy
  (ADR-0003). Field-level encryption for PII; Aadhaar stored as token reference.
- **Kafka** = event bus fed by the outbox relay. *Not* the source of truth.
- **Elasticsearch** = read/search projections + fast audit querying.
- **MinIO/S3** = documents (KYC, land, signed docs); object-locked (WORM) for
  executed legal docs.
- **Redis** = cache, distributed locks, idempotency-key store, rate limits.
- **Celery** = async/long jobs: AI agents, OCR, land fetch, reconciliation.

## Write path (the canonical transaction)
1. Command hits a context service (e.g. `Eligibility.compute`).
2. Validate invariants + tenant context (RLS set).
3. In **one DB transaction**: append domain event(s) + write outbox row +
   write audit row (actor, reason, before/after hash).
4. Commit. Outbox relay → Kafka. Consumers update ES projections idempotently.
5. Money/3rd-party effects go through an adapter with an **idempotency key** and
   a **reconciliation** record.

## Event design
- Events are versioned (`v1`, `v2`) with **upcasters** on read.
- Naming: past-tense, context-prefixed (`Land.LandVerified`).
- Snapshots per aggregate every N events for fast load.
- Every event carries `tenant_id, application_id, actor_id, correlation_id,
  occurred_at, schema_version`.

## Offline-first & sync (field PWA)
- Capture (land/crop/docs) writes to **IndexedDB** as draft commands with a
  client-generated id + vector clock.
- Background sync replays commands when online; server is **authoritative**.
- Conflict policy: per-field last-writer-wins for capture data using vector
  clocks; **money/decision data is never client-authoritative**.
- Documents queue as resumable uploads to MinIO.

## Resilience patterns
- Circuit breaker + retry/backoff + bulkheads per adapter.
- Graceful degradation: integration down → queue + manual fallback stage in the
  workflow; the application never hard-fails (S5).
- Idempotency keys + reconciliation jobs for all money/document side effects.

## Observability
- OpenTelemetry traces correlated by `correlation_id` across web → API → worker.
- Metrics: technical (latency, error, queue depth) **and business** (TAT per
  stage, approval rate, exception rate) on Grafana.
- Logs structured, PII-redacted, tenant/application-correlated.

## Environments
- `dev`/`CI`: all integrations in **mock mode** (ADR-0006); deterministic.
- `staging`: sandbox adapters where available, behind feature flags.
- `prod`: real adapters per-tenant, flagged, with reconciliation dashboards.
