# 05 — AI Architecture

Principle (ADR-0005): **deterministic core decides numbers; AI explains,
summarises, classifies, and flags.** AI accelerates humans; it never moves money
on its own.

## Orchestration
A graph/state-machine orchestrator runs agents as typed nodes with explicit
tool access and a shared, audited context object. Each agent run produces a
**decision record**: `{agent, model, prompt_version, inputs_hash, outputs,
confidence, citations, latency, token_cost, human_override?}`.

## Agents (one-line specs — each expands to a one-pager)

| Agent | Purpose | Key inputs | Tools | Guardrails |
|---|---|---|---|---|
| Document | Classify + OCR + extract fields + forgery signals | uploaded docs | OCR, classifier, vision | confidence threshold → maker review; never auto-verify legal docs |
| Land | Interpret fetched land records vs claim (ownership/encumbrance/mutation) | land record JSON, claim | RAG (state rules) | discrepancy → exception workflow |
| Risk | Summarise bureau/liability into risk narrative + flags | bureau, liabilities | calculators (deterministic) | numbers from code, not LLM |
| Credit-Memo | Draft the credit memo narrative around computed figures | eligibility result, all artefacts | RAG (policy/RBI) | must cite figures + policy; human approves |
| Compliance | Check application against policy/KYC/PSL completeness | full application | RAG (policy) | flags only; blocks via rules, not vibes |
| Fraud | Detect anomaly/identity/document fraud signals | cross-artefact features | anomaly models | flags → human review, never auto-reject |
| Workflow | Suggest next best action / missing items to users | workflow state | — | advisory copilot only |

**Credit-Memo agent is the MVP's first fully-built agent** (highest value,
clearest guardrails).

## Grounding (RAG)
Policy/compliance/memo agents retrieve from a versioned corpus: the **bank's own
credit policy + relevant RBI circulars + scheme docs**. Every claim cites a
source chunk. No ungrounded assertions in regulated outputs.

## PII safety (DPDP / Aadhaar)
- **Redact/tokenise PII before any model call.** Aadhaar/PAN never sent raw.
- **In-country inference path** for sensitive payloads (residency, ADR/prompt §5).
- Model I/O logged with PII redacted; logs are auditable.

## Governance & evals
- **Prompt registry** (versioned, diffable) and **model registry** (which model,
  which version, per agent).
- **Eval suite:** golden cases per agent + regression set; CI fails on eval drop.
- **Production monitoring:** confidence distribution, override rate, drift,
  cost/latency per agent; alerts on anomalies.
- **Human-in-the-loop:** below confidence threshold OR above ticket-size
  threshold → mandatory human review. Thresholds are config per tenant/product.

## AI-unavailable handling (graceful degradation) — IMPLEMENTED
AI is **additive, never load-bearing**. The Credit-Memo agent (apps/api,
`contexts/credit_memo`) proves the pattern every agent must follow:

- A provider abstraction with a `health()` check. `ALOS_LLM_PROVIDER` selects
  `none` (default) / `mock` / real. `none` = "no AI running".
- If no healthy provider **or a live call fails at runtime**, the agent returns a
  **deterministic template memo** built purely from the eligibility figures —
  the step still completes and the workflow advances.
- Explicit human escape hatches, all audited: **manual** memo (write/override)
  and **skip with a mandatory reason**.
- `GET /ai/health` returns `ai_available`, `provider`, and `fallback_options` so
  the UI can disable the AI control and surface template/manual/skip.
- Every memo result is a decision record (`mode`, `ai_available`, `confidence`,
  `model`, `prompt_version`, `inputs_hash`, `fallback_reason`).

The rule generalises: **no agent may be on the critical path such that its
absence blocks the lifecycle.** There is always a deterministic or human path.

## Cost & latency controls
- Model routing: small/cheap model for classification, larger for reasoning.
- Caching of stable retrievals; per-application token budget; async via Celery
  with a "thinking" UX rather than blocking the request.

## Explainability & override
Every AI output is shown with its citations and confidence, and is **overridable
by an authorised human with a captured reason** — the override is itself an
audited event.
