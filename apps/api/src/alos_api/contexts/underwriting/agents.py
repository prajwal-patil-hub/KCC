"""Risk, Fraud and Compliance agents (docs/05).

Per ADR-0005 the scoring is DETERMINISTIC (reproducible, auditable, never a
hallucinated number); AI only adds an optional explanatory narrative, with a
deterministic fallback so the assessment works when AI is off. Every result is a
decision record and is overridable by a human; high risk / fraud flags /
compliance failures force human review.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from ..credit_memo.provider import AIUnavailable, LLMProvider

PROMPT_VERSION = "underwriting/v1"
LARGE_EXPOSURE = 1_000_000  # INR — above this, route to manual review


@dataclass
class UnderwritingResult:
    risk_score: int                 # 0..100, higher = riskier
    risk_band: str                  # Low | Medium | High
    fraud_flags: list[str]
    compliance_issues: list[str]
    compliance_passed: bool
    requires_human_review: bool
    review_reasons: list[str]
    narrative: str
    ai_used: bool
    model: str | None
    prompt_version: str
    inputs_hash: str

    def to_payload(self) -> dict:
        return asdict(self)


def _hash(app_snapshot: dict) -> str:
    blob = json.dumps(app_snapshot, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:24]


# --- deterministic assessors ---------------------------------------------

def assess_risk(eligibility: dict) -> tuple[int, str, list[str]]:
    """Deterministic risk score from the computed eligibility."""
    drivers: list[str] = []
    score = 20
    if not eligibility:
        return 60, "High", ["no eligibility computed"]
    if not eligibility.get("eligible", False):
        score += 50
        drivers.append("not eligible on policy")
    breakup = eligibility.get("breakup") or {}
    net = float(breakup.get("net_limit", 0) or 0)
    gross = float(breakup.get("gross_limit", 0) or 0)
    offset = float(breakup.get("liability_offset", 0) or 0)
    if gross and offset / gross > 0.4:
        score += 20
        drivers.append("high existing-liability ratio")
    if eligibility.get("collateral_free") is False:
        score += 15
        drivers.append("exposure above collateral-free ceiling")
    if net >= LARGE_EXPOSURE:
        score += 15
        drivers.append("large exposure")
    score = max(0, min(100, score))
    band = "Low" if score < 30 else ("Medium" if score <= 60 else "High")
    return score, band, drivers


def detect_fraud(kyc: dict, eligibility: dict) -> list[str]:
    flags: list[str] = []
    if not kyc:
        flags.append("kyc_missing")
    else:
        if not kyc.get("verified"):
            flags.append("kyc_unverified")
        if kyc.get("verified") and not kyc.get("name_match", True):
            flags.append("name_mismatch")
    net = float(((eligibility or {}).get("breakup") or {}).get("net_limit", 0) or 0)
    if net >= LARGE_EXPOSURE:
        flags.append("large_exposure_review")
    return flags


def check_compliance(kyc: dict, eligibility: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not (kyc or {}).get("verified"):
        issues.append("KYC not completed/verified")
    if not (eligibility or {}).get("psl_category"):
        issues.append("PSL classification missing")
    if (eligibility or {}).get("collateral_free") is False:
        # advisory, not a hard fail: above the collateral-free ceiling
        issues.append("Security/mortgage required (above collateral-free ceiling)")
    hard_fail = any(i.startswith("KYC") or i.startswith("PSL") for i in issues)
    return (not hard_fail), issues


# --- orchestrator ---------------------------------------------------------

class UnderwritingService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def ai_available(self) -> bool:
        try:
            return self.provider.health()
        except Exception:
            return False

    def assess(self, *, applicant_name: str, kyc: dict, eligibility: dict) -> UnderwritingResult:
        score, band, drivers = assess_risk(eligibility)
        fraud = detect_fraud(kyc, eligibility)
        passed, issues = check_compliance(kyc, eligibility)

        reasons: list[str] = []
        if band == "High":
            reasons.append("high risk band")
        if fraud:
            reasons.append("fraud signals present")
        if not passed:
            reasons.append("compliance hard-fail")
        requires_review = bool(reasons) or True  # MVP: always human-reviewed

        det = (
            f"Risk {band} (score {score}). "
            + (f"Drivers: {', '.join(drivers)}. " if drivers else "")
            + (f"Fraud signals: {', '.join(fraud)}. " if fraud else "No fraud signals. ")
            + (f"Compliance issues: {', '.join(issues)}. " if issues else "Compliant. ")
        )

        narrative, ai_used, model = det, False, None
        if self.ai_available():
            try:
                prompt = (
                    "Explain this agricultural-loan underwriting result in 2-3 "
                    f"sentences for the credit maker (do not change the figures): "
                    f"applicant={applicant_name}, risk_band={band}, score={score}, "
                    f"fraud={fraud}, compliance_issues={issues}."
                )
                ai_text, _conf = self.provider.generate(prompt)
                narrative = ai_text + "\n\n" + det
                ai_used, model = True, self.provider.name
            except (AIUnavailable, Exception):  # noqa: BLE001 - degrade, never crash
                narrative, ai_used, model = det, False, None

        return UnderwritingResult(
            risk_score=score, risk_band=band, fraud_flags=fraud,
            compliance_issues=issues, compliance_passed=passed,
            requires_human_review=requires_review, review_reasons=reasons,
            narrative=narrative, ai_used=ai_used, model=model,
            prompt_version=PROMPT_VERSION,
            inputs_hash=_hash({"name": applicant_name, "kyc": kyc, "elig": eligibility}),
        )
