"""Deterministic, AI-free credit-memo generator.

This is the fallback that makes "no AI running" a non-event: it builds a complete,
readable memo straight from the deterministic eligibility figures. It is pure
(no I/O, no model) and always available, so the workflow can always proceed.
"""

from __future__ import annotations


def _rupees(value: str | None) -> str:
    if value is None:
        return "-"
    try:
        return f"Rs {int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def build_template_memo(*, applicant_name: str, eligibility: dict) -> str:
    b = (eligibility or {}).get("breakup") or {}
    eligible = (eligibility or {}).get("eligible", False)
    lines: list[str] = []
    lines.append(f"CREDIT MEMO (system-generated, no AI) — {applicant_name}")
    lines.append("")
    lines.append("Eligibility decision (deterministic engine):")
    lines.append(f"  Outcome           : {'ELIGIBLE' if eligible else 'NOT ELIGIBLE'}")
    lines.append(f"  Policy version    : {(eligibility or {}).get('policy_version', '-')}")
    if b:
        lines.append("  Limit composition :")
        lines.append(f"    Crop loan       : {_rupees(b.get('crop_loan_component'))}")
        lines.append(f"    + Post-harvest  : {_rupees(b.get('post_harvest_component'))}")
        lines.append(f"    + Maintenance   : {_rupees(b.get('maintenance_component'))}")
        lines.append(f"    + Insurance     : {_rupees(b.get('insurance_component'))}")
        lines.append(f"    Gross limit     : {_rupees(b.get('gross_limit'))}")
        lines.append(f"    - Liabilities   : {_rupees(b.get('liability_offset'))}")
        lines.append(f"    NET KCC LIMIT   : {_rupees(b.get('net_limit'))}")
    cf = (eligibility or {}).get("collateral_free")
    lines.append(f"  Collateral-free   : {cf}")
    lines.append(f"  PSL category      : {(eligibility or {}).get('psl_category', '-')}")
    lines.append(f"  Subvention        : {(eligibility or {}).get('subvention_eligible')}")
    rate = (eligibility or {}).get("effective_interest_rate")
    if rate is not None:
        try:
            lines.append(f"  Effective rate    : {float(rate) * 100:.1f}%")
        except (TypeError, ValueError):
            pass
    reasons = (eligibility or {}).get("reasons") or []
    if reasons:
        lines.append("  Notes             :")
        for r in reasons:
            lines.append(f"    - {r}")
    lines.append("")
    lines.append(
        "Recommendation: "
        + (
            "Recommended for sanction subject to maker and checker review."
            if eligible
            else "Not recommended on eligibility grounds; see notes above."
        )
    )
    lines.append(
        "This memo was produced without AI assistance and should be reviewed by "
        "the credit maker."
    )
    return "\n".join(lines)
