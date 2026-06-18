"""Worked KCC example. Run: python -m alos_eligibility.demo"""

from decimal import Decimal

from .policy import default_policy
from .models import LandParcel, CropPlan, Liabilities, EligibilityInput
from .engine import compute_kcc_eligibility


def main() -> None:
    policy = default_policy()
    inp = EligibilityInput(
        parcels=[
            LandParcel("P1", area_hectares=Decimal("2.0"), verified=True),
            LandParcel("P2", area_hectares=Decimal("1.5"), verified=True),
        ],
        crops=[
            # 2.0 ha wheat (rabi) @ 45,000/ha = 90,000
            CropPlan("P1", "wheat", "rabi", Decimal("2.0"),
                     crop_insurance_premium=Decimal("1500")),
            # 1.5 ha paddy (kharif) @ 55,000/ha = 82,500
            CropPlan("P2", "paddy", "kharif", Decimal("1.5"),
                     crop_insurance_premium=Decimal("1200")),
        ],
        liabilities=Liabilities(existing_kcc_outstanding=Decimal("20000")),
        prompt_repayment_history=True,
    )

    r = compute_kcc_eligibility(inp, policy)
    b = r.breakup

    print(f"Policy version      : {r.policy_version}")
    print(f"Eligible            : {r.eligible}")
    print(f"Crop loan component : Rs {b.crop_loan_component:,}")
    print(f"  + post-harvest 10%: Rs {b.post_harvest_component:,}")
    print(f"  + maintenance  20%: Rs {b.maintenance_component:,}")
    print(f"  + insurance       : Rs {b.insurance_component:,}")
    print(f"Gross limit         : Rs {b.gross_limit:,}")
    print(f"  - liabilities     : Rs {b.liability_offset:,}")
    print(f"NET KCC LIMIT       : Rs {b.net_limit:,}")
    print(f"Collateral-free     : {r.collateral_free} "
          f"(ceiling Rs {policy.collateral_free_ceiling:,})")
    print(f"PSL category        : {r.psl_category}")
    print(f"Subvention eligible : {r.subvention_eligible}")
    print(f"Effective rate      : {r.effective_interest_rate * 100:.1f}%")
    print("Reasons             :")
    for reason in r.reasons:
        print(f"  - {reason}")


if __name__ == "__main__":
    main()
