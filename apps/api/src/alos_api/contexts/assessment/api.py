"""Assessment context — eligibility endpoint.

Wires the pure eligibility engine (packages/eligibility-engine) into the API.
The engine decides the numbers deterministically (ADR-0005); the API only maps
JSON to the engine's value objects and records the result as an application
event so it becomes part of the auditable history.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from alos_eligibility import (
    CropPlan,
    EligibilityInput,
    LandParcel,
    Liabilities,
    compute_kcc_eligibility,
    default_policy,
)

from ...context import RequestContext
from ...deps import get_application_service, require_context
from ...platform.events import ConcurrencyError
from ...platform.tenancy import TenantIsolationError
from ..application.aggregate import InvalidTransition
from ..application.service import ApplicationService

router = APIRouter(prefix="/assessment", tags=["assessment"])


class ParcelBody(BaseModel):
    parcel_id: str
    area_hectares: float = Field(gt=0)
    verified: bool = False
    exception_override_reason: str | None = None


class CropBody(BaseModel):
    parcel_id: str
    crop: str
    season: str
    area_hectares: float = Field(gt=0)
    crop_insurance_premium: float = 0


class LiabilitiesBody(BaseModel):
    existing_kcc_outstanding: float = 0
    other_agri_loan_outstanding: float = 0
    asset_insurance_premium: float = 0


class EligibilityBody(BaseModel):
    parcels: list[ParcelBody]
    crops: list[CropBody]
    liabilities: LiabilitiesBody = LiabilitiesBody()
    prompt_repayment_history: bool = True


def _to_engine_input(body: EligibilityBody) -> EligibilityInput:
    return EligibilityInput(
        parcels=[
            LandParcel(
                p.parcel_id,
                Decimal(str(p.area_hectares)),
                verified=p.verified,
                exception_override_reason=p.exception_override_reason,
            )
            for p in body.parcels
        ],
        crops=[
            CropPlan(
                c.parcel_id,
                c.crop,
                c.season,
                Decimal(str(c.area_hectares)),
                crop_insurance_premium=Decimal(str(c.crop_insurance_premium)),
            )
            for c in body.crops
        ],
        liabilities=Liabilities(
            existing_kcc_outstanding=Decimal(str(body.liabilities.existing_kcc_outstanding)),
            other_agri_loan_outstanding=Decimal(str(body.liabilities.other_agri_loan_outstanding)),
            asset_insurance_premium=Decimal(str(body.liabilities.asset_insurance_premium)),
        ),
        prompt_repayment_history=body.prompt_repayment_history,
    )


def _result_to_dict(r) -> dict:
    b = r.breakup
    return {
        "eligible": r.eligible,
        "policy_version": r.policy_version,
        "collateral_free": r.collateral_free,
        "psl_category": r.psl_category,
        "subvention_eligible": r.subvention_eligible,
        "effective_interest_rate": str(r.effective_interest_rate),
        "reasons": r.reasons,
        "breakup": None if b is None else {
            "crop_loan_component": str(b.crop_loan_component),
            "post_harvest_component": str(b.post_harvest_component),
            "maintenance_component": str(b.maintenance_component),
            "insurance_component": str(b.insurance_component),
            "gross_limit": str(b.gross_limit),
            "liability_offset": str(b.liability_offset),
            "net_limit": str(b.net_limit),
        },
        "crop_trace": r.crop_trace,
    }


@router.post("/{application_id}/eligibility")
def compute_eligibility(
    application_id: str,
    body: EligibilityBody,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    result = compute_kcc_eligibility(_to_engine_input(body), default_policy())
    result_dict = _result_to_dict(result)
    try:
        # Record the computed result on the application's auditable history.
        svc.advance(application_id, "EligibilityComputed", result_dict)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TenantIsolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (InvalidTransition, ConcurrencyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result_dict
