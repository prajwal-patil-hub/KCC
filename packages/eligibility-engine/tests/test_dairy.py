"""Unit tests for the deterministic dairy eligibility rule."""

from decimal import Decimal

import pytest

from alos_eligibility import (
    CattleUnit,
    DairyEligibilityInput,
    compute_dairy_eligibility,
    default_dairy_policy,
)


def test_basic_dairy_limit():
    # 2 buffalo @ 70,000 = 140,000 base; +15% feed = 21,000; gross 161,000
    inp = DairyEligibilityInput(cattle=[CattleUnit("buffalo", 2)])
    r = compute_dairy_eligibility(inp, default_dairy_policy())
    assert r.eligible
    assert r.breakup["base_component"] == "140000"
    assert r.breakup["feed_maintenance_component"] == "21000"
    assert r.breakup["gross_limit"] == "161000"
    assert r.breakup["net_limit"] == "161000"
    assert r.psl_category == "PSL-Agriculture-AlliedActivities"
    assert r.collateral_free is True


def test_mixed_herd_and_liabilities():
    inp = DairyEligibilityInput(
        cattle=[CattleUnit("cow", 1), CattleUnit("goat", 5)],  # 60000 + 40000
        existing_liabilities=Decimal("10000"),
    )
    r = compute_dairy_eligibility(inp, default_dairy_policy())
    assert r.breakup["base_component"] == "100000"
    assert r.breakup["liability_offset"] == "10000"
    # gross = 100000 + 15000 = 115000 ; net = 105000
    assert r.breakup["net_limit"] == "105000"


def test_unknown_animal_reported():
    inp = DairyEligibilityInput(cattle=[CattleUnit("llama", 1)])
    r = compute_dairy_eligibility(inp, default_dairy_policy())
    assert not r.eligible
    assert any("unit cost" in x.lower() for x in r.reasons)


def test_determinism():
    inp = DairyEligibilityInput(cattle=[CattleUnit("buffalo", 3)])
    p = default_dairy_policy()
    assert compute_dairy_eligibility(inp, p) == compute_dairy_eligibility(inp, p)


def test_above_ceiling_needs_collateral():
    # 4 buffalo @ 70,000 = 280,000 -> above 200,000 ceiling
    inp = DairyEligibilityInput(cattle=[CattleUnit("buffalo", 4)])
    r = compute_dairy_eligibility(inp, default_dairy_policy())
    assert r.eligible and r.collateral_free is False


def test_invalid_count_rejected():
    with pytest.raises(ValueError):
        CattleUnit("cow", 0)
