"""Input and output value objects for the eligibility engine.

These are pure data carriers. An EligibilityResult is fully reproducible from
its EligibilityInput plus the policy version it was computed against
(docs/02-domain-model.md: EligibilityResult invariant).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class LandParcel:
    """A land parcel offered for the KCC application."""

    parcel_id: str
    area_hectares: Decimal
    verified: bool = False
    # If not verified, an authorised exception override (with reason) is required
    # before the parcel may be used. The reason is captured for audit.
    exception_override_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_hectares", _d(self.area_hectares))
        if self.area_hectares <= 0:
            raise ValueError(f"Parcel {self.parcel_id} area must be > 0")

    @property
    def usable(self) -> bool:
        return self.verified or bool(self.exception_override_reason)


@dataclass(frozen=True)
class CropPlan:
    """A crop grown on a parcel for a season."""

    parcel_id: str
    crop: str
    season: str
    area_hectares: Decimal
    crop_insurance_premium: Decimal = field(default_factory=lambda: _d("0"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_hectares", _d(self.area_hectares))
        object.__setattr__(
            self, "crop_insurance_premium", _d(self.crop_insurance_premium)
        )
        if self.area_hectares <= 0:
            raise ValueError("Crop area must be > 0")
        if self.crop_insurance_premium < 0:
            raise ValueError("Insurance premium cannot be negative")


@dataclass(frozen=True)
class Liabilities:
    """Existing borrowings to net off against the gross limit."""

    existing_kcc_outstanding: Decimal = field(default_factory=lambda: _d("0"))
    other_agri_loan_outstanding: Decimal = field(default_factory=lambda: _d("0"))
    asset_insurance_premium: Decimal = field(default_factory=lambda: _d("0"))

    def __post_init__(self) -> None:
        for name in (
            "existing_kcc_outstanding",
            "other_agri_loan_outstanding",
            "asset_insurance_premium",
        ):
            object.__setattr__(self, name, _d(getattr(self, name)))
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

    @property
    def total_offset(self) -> Decimal:
        return self.existing_kcc_outstanding + self.other_agri_loan_outstanding


@dataclass(frozen=True)
class EligibilityInput:
    parcels: List[LandParcel]
    crops: List[CropPlan]
    liabilities: Liabilities = field(default_factory=Liabilities)
    prompt_repayment_history: bool = True


@dataclass(frozen=True)
class LimitBreakup:
    """Transparent breakdown of how the KCC limit was built."""

    crop_loan_component: Decimal
    post_harvest_component: Decimal
    maintenance_component: Decimal
    insurance_component: Decimal
    gross_limit: Decimal
    liability_offset: Decimal
    net_limit: Decimal


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: List[str]
    policy_version: str
    breakup: LimitBreakup | None
    collateral_free: bool
    psl_category: str
    subvention_eligible: bool
    effective_interest_rate: Decimal
    # Per-crop trace for auditability / the credit memo agent to cite.
    crop_trace: List[dict] = field(default_factory=list)
