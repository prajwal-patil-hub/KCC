"""LLM provider abstraction for the Credit-Memo agent.

The whole point of this module: the rest of the app asks `get_provider()` for a
provider and checks `.health()`. If no AI is configured or the model is down,
health is False and the agent falls back to a deterministic template memo — the
workflow never blocks on AI (the user's requirement; consistent with ADR-0005,
where AI only explains and never decides).

Providers:
  * NullProvider  — no AI configured (default). health() -> False.
  * MockLLMProvider — simulates "AI running" for demos/tests. health() -> True.
  * (real OpenAI/Anthropic adapters slot in here behind config, unimplemented.)
"""

from __future__ import annotations

from typing import Protocol


class AIUnavailable(RuntimeError):
    """Raised when a generation is attempted but no healthy provider exists."""


class LLMProvider(Protocol):
    name: str

    def health(self) -> bool: ...

    def generate(self, prompt: str) -> tuple[str, float]:
        """Return (narrative, confidence in 0..1). May raise on transient failure."""
        ...


class NullProvider:
    """Used when ALOS_LLM_PROVIDER=none — i.e. 'I don't have AI running'."""

    name = "none"

    def health(self) -> bool:
        return False

    def generate(self, prompt: str) -> tuple[str, float]:
        raise AIUnavailable("No AI provider configured (ALOS_LLM_PROVIDER=none)")


class MockLLMProvider:
    """Deterministic stand-in for a real LLM so the AI path is demoable/testable.

    `fail` lets tests simulate a model outage at call time (so we can prove the
    runtime fallback to the template memo, not just the not-configured case).
    """

    name = "mock"

    def __init__(self, healthy: bool = True, fail: bool = False) -> None:
        self._healthy = healthy
        self._fail = fail

    def health(self) -> bool:
        return self._healthy

    def generate(self, prompt: str) -> tuple[str, float]:
        if self._fail:
            raise RuntimeError("simulated model timeout")
        narrative = (
            "AI underwriting summary:\n"
            "Based on the verified land and crop plan, the computed KCC limit and "
            "the applicant's repayment profile, the application presents an "
            "acceptable agricultural credit risk. The deterministic eligibility "
            "figures below were not altered by the model; this narrative explains "
            "them and highlights points for the maker's attention.\n"
            "Points to verify: continued cultivation of the stated crops, validity "
            "of land records, and absence of overlapping KCC limits."
        )
        return narrative, 0.82


def get_provider(provider_name: str) -> LLMProvider:
    name = (provider_name or "none").strip().lower()
    if name == "mock":
        return MockLLMProvider()
    if name == "none":
        return NullProvider()
    # Real providers (openai/anthropic) would be constructed here from secrets.
    # Until implemented, fail safe to NullProvider so we degrade, never crash.
    return NullProvider()
