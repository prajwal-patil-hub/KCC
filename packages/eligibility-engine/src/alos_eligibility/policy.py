"""Versioned, effective-dated KCC policy.

These values are RBI/GoI policy that changes (the collateral-free ceiling was
raised to Rs 2,00,000 effective 2025; Scale of Finance is set annually by each
District Level Technical Committee). They are therefore *data*, never constants
hard-coded into the formula (gap A6 in docs/00-gap-analysis.md).

In production this comes from the Config service, keyed by tenant + effective
date. Here we model the shape and ship a sane default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping


def _d(value: str | int | float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class ScaleOfFinance:
    """Scale of Finance (SoF) for one crop in one district for one year.

    Set by the District Level Technical Committee (DLTC). Unit: INR per hectare.
    A real table is keyed by (state, district, crop, season, year).
    """

    crop: str
    season: str  # "kharif" | "rabi" | "zaid"
    inr_per_hectare: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "inr_per_hectare", _d(self.inr_per_hectare))
        if self.inr_per_hectare < 0:
            raise ValueError("Scale of Finance cannot be negative")


@dataclass(frozen=True)
class KccPolicy:
    """A versioned snapshot of KCC policy used to compute a limit.

    The percentages below are the standard RBI KCC composition:
      * +10% of crop-loan component for post-harvest / household / consumption
      * +20% of crop-loan component for farm-asset maintenance
      * crop + asset insurance premia added on top
    Defaults are configurable per tenant and effective-dated.
    """

    policy_version: str
    effective_from: str  # ISO date; effective-dated config

    post_harvest_rate: Decimal = field(default_factory=lambda: _d("0.10"))
    maintenance_rate: Decimal = field(default_factory=lambda: _d("0.20"))

    # Collateral-free ceiling (RBI raised to Rs 2,00,000 w.e.f. 2025).
    collateral_free_ceiling: Decimal = field(default_factory=lambda: _d("200000"))

    # PSL classification carried on every KCC crop sanction.
    psl_category: str = "PSL-Agriculture"

    # Modified Interest Subvention Scheme: base rate and prompt-repayment rebate.
    base_interest_rate: Decimal = field(default_factory=lambda: _d("0.07"))
    prompt_repayment_rebate: Decimal = field(default_factory=lambda: _d("0.03"))
    # Subvention typically applies up to a notified limit (e.g. Rs 3,00,000).
    subvention_limit: Decimal = field(default_factory=lambda: _d("300000"))

    scale_of_finance: Mapping[str, ScaleOfFinance] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "post_harvest_rate",
            "maintenance_rate",
            "collateral_free_ceiling",
            "base_interest_rate",
            "prompt_repayment_rebate",
            "subvention_limit",
        ):
            object.__setattr__(self, name, _d(getattr(self, name)))

    def sof_key(self, crop: str, season: str) -> str:
        return f"{crop.strip().lower()}::{season.strip().lower()}"

    def scale_of_finance_for(self, crop: str, season: str) -> ScaleOfFinance:
        key = self.sof_key(crop, season)
        try:
            return self.scale_of_finance[key]
        except KeyError as exc:
            raise KeyError(
                f"No Scale of Finance configured for crop='{crop}', "
                f"season='{season}' in policy {self.policy_version}"
            ) from exc

    def effective_interest_rate(self, *, prompt_repayment: bool) -> Decimal:
        """Effective rate under MISS for a prompt-repaying farmer."""
        if prompt_repayment:
            return self.base_interest_rate - self.prompt_repayment_rebate
        return self.base_interest_rate


def default_policy() -> KccPolicy:
    """A reasonable default policy with a small SoF table for demos/tests."""
    sof = [
        ScaleOfFinance("wheat", "rabi", _d("45000")),
        ScaleOfFinance("paddy", "kharif", _d("55000")),
        ScaleOfFinance("cotton", "kharif", _d("70000")),
        ScaleOfFinance("sugarcane", "kharif", _d("120000")),
    ]
    policy = KccPolicy(
        policy_version="kcc-2026.1",
        effective_from="2026-04-01",
    )
    table = {policy.sof_key(s.crop, s.season): s for s in sof}
    # frozen dataclass: set the mapping post-construction
    object.__setattr__(policy, "scale_of_finance", table)
    return policy
