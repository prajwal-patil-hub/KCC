# ALOS — Agricultural Lending Operating System

AI-native lending OS for India, **KCC (Kisan Credit Card) first**, designed for
multi-product / multi-tenant / multi-state growth.

> **Status:** Architecture & planning, with the first build increment started
> (the deterministic eligibility engine). This branch is the planning baseline.

## Why v2
The original brief (`prompts/ALOS_Master_Claude_Prompt.md`) had the vision but
was missing the regulatory rules, non-functional targets, architecture
guardrails, AI safety, and a shippable MVP slice. The improved prompt and the
reasoning behind every change live here:

- **Improved prompt:** [`prompts/ALOS_Master_Prompt_v2.md`](prompts/ALOS_Master_Prompt_v2.md)
- **What was missing / what to build:** [`docs/00-gap-analysis.md`](docs/00-gap-analysis.md)

## Read in this order
1. [`docs/00-gap-analysis.md`](docs/00-gap-analysis.md) — critique of v1, ranked gaps, what to implement first.
2. [`docs/01-architecture-method.md`](docs/01-architecture-method.md) — **how we find the best architecture** (drivers → scenarios → reversibility → ADRs).
3. [`docs/adr/`](docs/adr/) — the Type-1 decisions (monolith-first, selective ES, RLS tenancy, workflow engine, deterministic-core, mock-first adapters).
4. [`docs/02-domain-model.md`](docs/02-domain-model.md) — bounded contexts, aggregates, KCC ubiquitous language.
5. [`docs/03-system-architecture.md`](docs/03-system-architecture.md) — containers, data/event design, offline sync, resilience.
6. [`docs/05-ai-architecture.md`](docs/05-ai-architecture.md) — agents, grounding, PII safety, governance.
7. [`docs/06-security-compliance.md`](docs/06-security-compliance.md) — Aadhaar, DPDP, audit immutability, money controls.
8. [`docs/07-roadmap.md`](docs/07-roadmap.md) — MVP slice, milestones, acceptance criteria.

## The four guardrails that matter most
1. **Deterministic core decides money; AI explains.** (ADR-0005)
2. **Selective event sourcing + outbox** — audit & zero-loss where it counts. (ADR-0002)
3. **Tenant isolation via Postgres RLS.** (ADR-0003)
4. **Every integration behind a mock-first adapter** so the whole flow runs offline. (ADR-0006)

## Build started: eligibility engine
The first component — a pure, framework-free KCC limit/eligibility calculator —
is in [`packages/eligibility-engine/`](packages/eligibility-engine/). It encodes
the RBI KCC formula as configurable, versioned policy and is fully unit-tested.

```bash
cd packages/eligibility-engine
python -m pytest -q
python -m alos_eligibility.demo   # prints a worked KCC example
```
