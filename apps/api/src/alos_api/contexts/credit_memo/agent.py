"""Credit-Memo agent.

Produces a credit memo for an application. AI is *additive*: if a healthy
provider exists it narrates the memo (with confidence + citations); otherwise the
agent automatically returns the deterministic template memo. Either way a memo is
produced and the workflow proceeds — AI being down is never a dead end.

Every result is a decision record (model, prompt_version, inputs_hash, mode,
confidence) and is always overridable by a human (ADR-0005 / docs/05).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from .provider import AIUnavailable, LLMProvider
from .template import build_template_memo

PROMPT_VERSION = "credit-memo/v1"

# Citations are illustrative of the RAG grounding described in docs/05; in
# production these are retrieved policy/RBI chunks.
DEFAULT_CITATIONS = [
    "Bank credit policy — KCC limit composition",
    "RBI Master Direction — Kisan Credit Card scheme",
]


@dataclass
class MemoResult:
    mode: str                # "ai" | "template" | "manual" | "skipped"
    ai_available: bool
    narrative: str | None
    confidence: float | None
    model: str | None
    prompt_version: str | None
    inputs_hash: str
    citations: list[str] = field(default_factory=list)
    requires_human_review: bool = True
    fallback_reason: str | None = None  # why we fell back from AI, if we did
    note: str | None = None             # skip/override reason

    def to_payload(self) -> dict:
        return asdict(self)


def _inputs_hash(applicant_name: str, eligibility: dict) -> str:
    blob = json.dumps(
        {"applicant": applicant_name, "eligibility": eligibility},
        sort_keys=True, default=str,
    )
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:24]


def _build_prompt(applicant_name: str, eligibility: dict) -> str:
    # PII is not included here; figures + applicant name only (docs/05 PII safety).
    return (
        f"Write a concise agricultural credit memo for applicant {applicant_name}. "
        f"Do NOT change any numbers. Eligibility figures (authoritative): "
        f"{json.dumps(eligibility, default=str)}. Explain the decision, flag risks, "
        f"and cite policy."
    )


class CreditMemoAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def ai_available(self) -> bool:
        try:
            return self.provider.health()
        except Exception:
            return False

    def generate(self, *, applicant_name: str, eligibility: dict) -> MemoResult:
        ih = _inputs_hash(applicant_name, eligibility)
        template = build_template_memo(
            applicant_name=applicant_name, eligibility=eligibility
        )

        if not self.ai_available():
            return MemoResult(
                mode="template",
                ai_available=False,
                narrative=template,
                confidence=None,
                model=None,
                prompt_version=PROMPT_VERSION,
                inputs_hash=ih,
                citations=[],
                fallback_reason="AI provider not available; used template memo.",
            )

        # AI is healthy — try it, but fall back to the template on any failure.
        try:
            prompt = _build_prompt(applicant_name, eligibility)
            narrative, confidence = self.provider.generate(prompt)
            # AI narrative is presented alongside the deterministic figures.
            combined = narrative + "\n\n---\n" + template
            return MemoResult(
                mode="ai",
                ai_available=True,
                narrative=combined,
                confidence=confidence,
                model=self.provider.name,
                prompt_version=PROMPT_VERSION,
                inputs_hash=ih,
                citations=list(DEFAULT_CITATIONS),
                # Low confidence forces human review (it is already required in MVP).
                requires_human_review=True,
            )
        except (AIUnavailable, Exception) as exc:  # noqa: BLE001 - degrade, never crash
            return MemoResult(
                mode="template",
                ai_available=False,
                narrative=template,
                confidence=None,
                model=None,
                prompt_version=PROMPT_VERSION,
                inputs_hash=ih,
                citations=[],
                fallback_reason=f"AI call failed ({type(exc).__name__}); used template memo.",
            )

    def manual(self, *, applicant_name: str, eligibility: dict, text: str) -> MemoResult:
        return MemoResult(
            mode="manual",
            ai_available=self.ai_available(),
            narrative=text,
            confidence=None,
            model=None,
            prompt_version=PROMPT_VERSION,
            inputs_hash=_inputs_hash(applicant_name, eligibility),
            note="Memo written/overridden by a human.",
        )

    def skip(self, *, applicant_name: str, eligibility: dict, reason: str) -> MemoResult:
        return MemoResult(
            mode="skipped",
            ai_available=self.ai_available(),
            narrative=None,
            confidence=None,
            model=None,
            prompt_version=PROMPT_VERSION,
            inputs_hash=_inputs_hash(applicant_name, eligibility),
            note=reason,
        )
