"""Deterministic dairy (allied activity) eligibility.

Sits alongside the KCC crop rule in the same engine package — adding a product
adds a module, it does not change the KCC math (ADR-0001 module boundaries,
ADR-0005 deterministic core). Same shape of output (a limit breakup + flags) so
the rest of the platform — memo agent, disbursement — consumes it unchanged.

Limit = number of milch animals x unit cost/animal
        + feed & maintenance (rate x base)
        + insurance, netted against existing liabilities.
Unit cost per animal type is versioned policy (like Scale of Finance for crops).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Mapping


def _d(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _round(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DairyPolicy:
    policy_version: str
    effective_from: str
    feed_maintenance_rate: Decimal = field(default_factory=lambda: _d("0.15"))
    collateral_free_ceiling: Decimal = field(default_factory=lambda: _d("200000"))
    psl_category: str = "PSL-Agriculture-AlliedActivities"
    # unit cost (INR) per animal type, set annually by the technical committee
    unit_cost_per_animal: Mapping[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for n in ("feed_maintenance_rate", "collateral_free_ceiling"):
            object.__setattr__(self, n, _d(getattr(self, n)))

    def unit_cost(self, animal_type: str) -> Decimal:
        key = animal_type.strip().lower()
        if key not in self.unit_cost_per_animal:
            raise KeyError(
                f"No unit cost configured for animal '{animal_type}' "
                f"in dairy policy {self.policy_version}"
            )
        return _d(self.unit_cost_per_animal[key])


@dataclass(frozen=True)
class CattleUnit:
    animal_type: str
    count: int
    insurance_premium: Decimal = field(default_factory=lambda: _d("0"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "insurance_premium", _d(self.insurance_premium))
        if self.count <= 0:
            raise ValueError("Cattle count must be > 0")


@dataclass(frozen=True)
class DairyEligibilityInput:
    cattle: List[CattleUnit]
    existing_liabilities: Decimal = field(default_factory=lambda: _d("0"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "existing_liabilities", _d(self.existing_liabilities))


@dataclass(frozen=True)
class DairyEligibilityResult:
    eligible: bool
    reasons: List[str]
    policy_version: str
    breakup: dict | None
    collateral_free: bool
    psl_category: str
    animal_trace: List[dict] = field(default_factory=list)


def default_dairy_policy() -> DairyPolicy:
    policy = DairyPolicy(policy_version="dairy-2026.1", effective_from="2026-04-01")
    object.__setattr__(
        policy, "unit_cost_per_animal",
        {"buffalo": _d("70000"), "cow": _d("60000"), "goat": _d("8000")},
    )
    return policy


def compute_dairy_eligibility(
    inp: DairyEligibilityInput, policy: DairyPolicy
) -> DairyEligibilityResult:
    reasons: list[str] = []
    base = Decimal("0")
    insurance = Decimal("0")
    trace: list[dict] = []

    if not inp.cattle:
        reasons.append("No cattle provided.")

    for unit in inp.cattle:
        try:
            cost = policy.unit_cost(unit.animal_type)
        except KeyError as exc:
            reasons.append(str(exc))
            continue
        component = cost * unit.count
        base += component
        insurance += unit.insurance_premium
        trace.append({
            "animal_type": unit.animal_type, "count": unit.count,
            "unit_cost": str(cost), "component": str(_round(component)),
        })

    if base <= 0:
        return DairyEligibilityResult(
            eligible=False, reasons=reasons or ["No fundable cattle component."],
            policy_version=policy.policy_version, breakup=None,
            collateral_free=False, psl_category=policy.psl_category,
            animal_trace=trace,
        )

    feed = policy.feed_maintenance_rate * base
    gross = base + feed + insurance
    net = gross - inp.existing_liabilities
    if net < 0:
        net = Decimal("0")
        reasons.append("Existing liabilities exceed the computed limit; net is zero.")

    breakup = {
        "base_component": str(_round(base)),
        "feed_maintenance_component": str(_round(feed)),
        "insurance_component": str(_round(insurance)),
        "gross_limit": str(_round(gross)),
        "liability_offset": str(_round(inp.existing_liabilities)),
        "net_limit": str(_round(net)),
    }
    return DairyEligibilityResult(
        eligible=net > 0,
        reasons=reasons or ["Eligible: dairy limit computed successfully."],
        policy_version=policy.policy_version, breakup=breakup,
        collateral_free=net <= policy.collateral_free_ceiling,
        psl_category=policy.psl_category, animal_trace=trace,
    )
