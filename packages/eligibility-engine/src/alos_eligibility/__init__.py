"""ALOS deterministic eligibility engine.

Pure, framework-free KCC limit & eligibility math. No I/O, no LLM, no money is
moved here — this is the reproducible source of truth for numbers (see
docs/adr/0005-deterministic-decisions-ai-explains.md).

All amounts are in INR. Areas are in hectares.
"""

from .policy import KccPolicy, ScaleOfFinance, default_policy
from .models import (
    LandParcel,
    CropPlan,
    Liabilities,
    EligibilityInput,
    EligibilityResult,
    LimitBreakup,
)
from .engine import compute_kcc_eligibility

__all__ = [
    "KccPolicy",
    "ScaleOfFinance",
    "default_policy",
    "LandParcel",
    "CropPlan",
    "Liabilities",
    "EligibilityInput",
    "EligibilityResult",
    "LimitBreakup",
    "compute_kcc_eligibility",
]

__version__ = "0.1.0"
