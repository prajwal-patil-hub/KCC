# ADR-0005 — Deterministic core decides; AI explains and recommends

**Status:** Accepted · **Date:** 2026-06-18

## Context
v1 implied "AI Underwriting" could produce decisions. LLMs hallucinate and are
non-reproducible — unacceptable for limit/eligibility math and for regulatory
defensibility (driver #1: money correctness; #2: auditability).

## Decision
- **Numbers and rule outcomes are computed by deterministic, unit-tested code:**
  KCC limit, eligibility, subvention, PSL tag, policy validation.
- **AI is advisory:** it summarises documents, flags risks/fraud signals, drafts
  the credit memo narrative, and explains the deterministic result in plain
  language — always with citations to policy and to the computed figures.
- A decision record stores both: the deterministic outputs **and** the AI
  commentary, with model/prompt versions and a human-override field.
- Below a confidence threshold or above a ticket-size threshold → mandatory
  human review (thresholds are config).

## Consequences
- (+) Reproducible, auditable, defensible numbers; AI adds speed not risk.
- (+) Clear failure isolation: a bad model never moves money.
- (−) Must keep the rules engine and AI prompts in sync on terminology.
