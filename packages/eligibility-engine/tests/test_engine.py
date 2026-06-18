"""Unit tests for the deterministic KCC eligibility engine."""

from decimal import Decimal

import pytest

from alos_eligibility import (
    compute_kcc_eligibility,
    default_policy,
    LandParcel,
    CropPlan,
    Liabilities,
    EligibilityInput,
)


def _single_crop_input(**overrides):
    base = dict(
        parcels=[LandParcel("P1", Decimal("2.0"), verified=True)],
        crops=[CropPlan("P1", "wheat", "rabi", Decimal("2.0"))],
        liabilities=Liabilities(),
        prompt_repayment_history=True,
    )
    base.update(overrides)
    return EligibilityInput(**base)


def test_basic_limit_formula():
    # 2 ha wheat @ 45,000 = 90,000 crop loan
    # +10% = 9,000 ; +20% = 18,000 ; gross = 117,000
    r = compute_kcc_eligibility(_single_crop_input(), default_policy())
    assert r.eligible
    b = r.breakup
    assert b.crop_loan_component == Decimal("90000")
    assert b.post_harvest_component == Decimal("9000")
    assert b.maintenance_component == Decimal("18000")
    assert b.gross_limit == Decimal("117000")
    assert b.net_limit == Decimal("117000")


def test_insurance_is_added():
    inp = _single_crop_input(
        crops=[CropPlan("P1", "wheat", "rabi", Decimal("2.0"),
                        crop_insurance_premium=Decimal("2000"))],
        liabilities=Liabilities(asset_insurance_premium=Decimal("500")),
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert r.breakup.insurance_component == Decimal("2500")
    assert r.breakup.gross_limit == Decimal("119500")


def test_liabilities_net_off():
    inp = _single_crop_input(
        liabilities=Liabilities(existing_kcc_outstanding=Decimal("17000")),
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert r.breakup.liability_offset == Decimal("17000")
    assert r.breakup.net_limit == Decimal("100000")


def test_liabilities_exceeding_gross_floor_at_zero():
    inp = _single_crop_input(
        liabilities=Liabilities(existing_kcc_outstanding=Decimal("500000")),
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert r.breakup.net_limit == Decimal("0")
    assert not r.eligible
    assert any("liabilities exceed" in x.lower() for x in r.reasons)


def test_determinism_same_inputs_same_result():
    inp = _single_crop_input()
    policy = default_policy()
    r1 = compute_kcc_eligibility(inp, policy)
    r2 = compute_kcc_eligibility(inp, policy)
    assert r1 == r2


def test_collateral_free_flag_uses_policy_ceiling():
    # net 117,000 <= 200,000 ceiling => collateral-free
    r = compute_kcc_eligibility(_single_crop_input(), default_policy())
    assert r.collateral_free is True


def test_above_ceiling_requires_collateral():
    # sugarcane 3 ha @ 120,000 = 360,000 crop loan -> gross well above ceiling
    inp = _single_crop_input(
        parcels=[LandParcel("P1", Decimal("3.0"), verified=True)],
        crops=[CropPlan("P1", "sugarcane", "kharif", Decimal("3.0"))],
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert r.eligible
    assert r.collateral_free is False
    # also above subvention limit (300,000)
    assert r.subvention_eligible is False


def test_unverified_parcel_blocks_use():
    inp = _single_crop_input(
        parcels=[LandParcel("P1", Decimal("2.0"), verified=False)],
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert not r.eligible
    assert any("not verified" in x.lower() for x in r.reasons)


def test_exception_override_allows_unverified_parcel():
    inp = _single_crop_input(
        parcels=[LandParcel("P1", Decimal("2.0"), verified=False,
                            exception_override_reason="Officer override #123")],
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert r.eligible


def test_missing_scale_of_finance_reported():
    inp = _single_crop_input(
        crops=[CropPlan("P1", "quinoa", "rabi", Decimal("2.0"))],
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert not r.eligible
    assert any("scale of finance" in x.lower() for x in r.reasons)


def test_crop_on_unknown_parcel_reported():
    inp = _single_crop_input(
        crops=[CropPlan("PX", "wheat", "rabi", Decimal("2.0"))],
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert not r.eligible
    assert any("unusable/unknown parcel" in x.lower() for x in r.reasons)


def test_effective_interest_rate_with_and_without_prompt_repayment():
    p = default_policy()
    r_prompt = compute_kcc_eligibility(_single_crop_input(), p)
    r_no = compute_kcc_eligibility(
        _single_crop_input(prompt_repayment_history=False), p
    )
    assert r_prompt.effective_interest_rate == Decimal("0.04")  # 7% - 3%
    assert r_no.effective_interest_rate == Decimal("0.07")


def test_multi_crop_sums_components():
    inp = EligibilityInput(
        parcels=[
            LandParcel("P1", Decimal("2.0"), verified=True),
            LandParcel("P2", Decimal("1.0"), verified=True),
        ],
        crops=[
            CropPlan("P1", "wheat", "rabi", Decimal("2.0")),     # 90,000
            CropPlan("P2", "cotton", "kharif", Decimal("1.0")),  # 70,000
        ],
    )
    r = compute_kcc_eligibility(inp, default_policy())
    assert r.breakup.crop_loan_component == Decimal("160000")


def test_negative_area_rejected():
    with pytest.raises(ValueError):
        LandParcel("P1", Decimal("-1"), verified=True)


def test_crop_trace_is_populated_for_audit():
    r = compute_kcc_eligibility(_single_crop_input(), default_policy())
    assert len(r.crop_trace) == 1
    assert r.crop_trace[0]["crop"] == "wheat"
    assert r.crop_trace[0]["crop_loan_component"] == "90000"
