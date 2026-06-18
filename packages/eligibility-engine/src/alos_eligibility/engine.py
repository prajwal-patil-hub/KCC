"""The deterministic KCC eligibility & limit calculator.

Formula (RBI KCC, see prompts/ALOS_Master_Prompt_v2.md sec 3):

    crop_loan      = sum over crops of  SoF(crop, season) * area_sown
    post_harvest   = post_harvest_rate * crop_loan        (default 10%)
    maintenance    = maintenance_rate  * crop_loan        (default 20%)
    insurance      = crop insurance premia + asset insurance premium
    gross_limit    = crop_loan + post_harvest + maintenance + insurance
    net_limit      = gross_limit - existing agri/KCC liabilities

This module is pure: same inputs + same policy version => same result, forever.
Rounding is done once, at the end, half-up to whole rupees.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .models import (
    EligibilityInput,
    EligibilityResult,
    LimitBreakup,
)
from .policy import KccPolicy


def _round_rupees(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def compute_kcc_eligibility(
    inp: EligibilityInput, policy: KccPolicy
) -> EligibilityResult:
    reasons: list[str] = []

    usable_parcel_ids = {p.parcel_id for p in inp.parcels if p.usable}
    unusable = [p.parcel_id for p in inp.parcels if not p.usable]
    if unusable:
        reasons.append(
            "Parcels not verified and without exception override: "
            + ", ".join(unusable)
        )

    if not inp.crops:
        reasons.append("No crop plan provided.")

    crop_loan = Decimal("0")
    insurance = Decimal("0")
    crop_trace: list[dict] = []

    for crop in inp.crops:
        if crop.parcel_id not in usable_parcel_ids:
            reasons.append(
                f"Crop '{crop.crop}' references unusable/unknown parcel "
                f"'{crop.parcel_id}'."
            )
            continue
        try:
            sof = policy.scale_of_finance_for(crop.crop, crop.season)
        except KeyError as exc:
            reasons.append(str(exc))
            continue

        component = sof.inr_per_hectare * crop.area_hectares
        crop_loan += component
        insurance += crop.crop_insurance_premium
        crop_trace.append(
            {
                "parcel_id": crop.parcel_id,
                "crop": crop.crop,
                "season": crop.season,
                "area_hectares": str(crop.area_hectares),
                "sof_inr_per_hectare": str(sof.inr_per_hectare),
                "crop_loan_component": str(_round_rupees(component)),
            }
        )

    # If nothing usable computed, fail early with the gathered reasons.
    if crop_loan <= 0:
        if "No crop plan provided." not in reasons and not crop_trace:
            reasons.append("No fundable crop component could be computed.")
        return EligibilityResult(
            eligible=False,
            reasons=reasons,
            policy_version=policy.policy_version,
            breakup=None,
            collateral_free=False,
            psl_category=policy.psl_category,
            subvention_eligible=False,
            effective_interest_rate=policy.effective_interest_rate(
                prompt_repayment=inp.prompt_repayment_history
            ),
            crop_trace=crop_trace,
        )

    post_harvest = policy.post_harvest_rate * crop_loan
    maintenance = policy.maintenance_rate * crop_loan
    insurance += inp.liabilities.asset_insurance_premium

    gross_limit = crop_loan + post_harvest + maintenance + insurance
    liability_offset = inp.liabilities.total_offset
    net_limit = gross_limit - liability_offset
    if net_limit < 0:
        net_limit = Decimal("0")
        reasons.append(
            "Existing liabilities exceed the computed gross limit; "
            "net eligibility is zero."
        )

    breakup = LimitBreakup(
        crop_loan_component=_round_rupees(crop_loan),
        post_harvest_component=_round_rupees(post_harvest),
        maintenance_component=_round_rupees(maintenance),
        insurance_component=_round_rupees(insurance),
        gross_limit=_round_rupees(gross_limit),
        liability_offset=_round_rupees(liability_offset),
        net_limit=_round_rupees(net_limit),
    )

    eligible = breakup.net_limit > 0
    collateral_free = breakup.net_limit <= policy.collateral_free_ceiling
    subvention_eligible = (
        eligible and breakup.net_limit <= policy.subvention_limit
    )

    return EligibilityResult(
        eligible=eligible,
        reasons=reasons or ["Eligible: KCC limit computed successfully."],
        policy_version=policy.policy_version,
        breakup=breakup,
        collateral_free=collateral_free,
        psl_category=policy.psl_category,
        subvention_eligible=subvention_eligible,
        effective_interest_rate=policy.effective_interest_rate(
            prompt_repayment=inp.prompt_repayment_history
        ),
        crop_trace=crop_trace,
    )
