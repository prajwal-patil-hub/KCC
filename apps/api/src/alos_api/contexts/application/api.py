"""Application context HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...context import RequestContext
from ...deps import (
    get_application_service,
    get_kyc_adapter,
    require_context,
)
from ...integrations.kyc import MockKycAdapter
from ...platform.events import ConcurrencyError
from ...platform.makerchecker import MakerCheckerViolation
from ...platform.tenancy import TenantIsolationError
from .aggregate import InvalidTransition
from .service import ApplicationService

router = APIRouter(prefix="/applications", tags=["applications"])


class CreateLeadBody(BaseModel):
    applicant_name: str
    mobile: str
    product: str = "KCC"


class LinkCustomerBody(BaseModel):
    customer_id: str
    farmer_class: str | None = None


class KycBody(BaseModel):
    aadhaar_number: str
    name: str


class AdvanceBody(BaseModel):
    reason: str | None = None


def _view(app) -> dict:
    return {
        "application_id": app.application_id,
        "tenant_id": app.tenant_id,
        "stage": app.stage,
        "maker_user_id": app.maker_user_id,
        "version": app.version,
        "customer": app.customer,
        "kyc": app.kyc,
        "eligibility": app.eligibility,
    }


@router.post("", status_code=201)
def create_lead(
    body: CreateLeadBody,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    app = svc.create_lead(body.model_dump())
    return _view(app)


@router.post("/{application_id}/link-customer")
def link_customer(
    application_id: str,
    body: LinkCustomerBody,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    return _guarded(lambda: _view(
        svc.advance(application_id, "CustomerLinked", body.model_dump())
    ))


@router.post("/{application_id}/kyc")
def complete_kyc(
    application_id: str,
    body: KycBody,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    kyc: MockKycAdapter = Depends(get_kyc_adapter),
):
    result = kyc.verify(aadhaar_number=body.aadhaar_number, name=body.name)
    if not result.verified:
        raise HTTPException(status_code=422, detail="KYC verification failed")
    # Note: only tokenised/masked Aadhaar is persisted (docs/06).
    payload = {
        "verified": result.verified,
        "name_match": result.name_match,
        "aadhaar_token": result.aadhaar_token,
        "masked_aadhaar": result.masked_aadhaar,
        "source": result.source,
    }
    return _guarded(lambda: _view(svc.advance(application_id, "KycCompleted", payload)))


@router.post("/{application_id}/advance/{target}")
def advance(
    application_id: str,
    target: str,
    body: AdvanceBody | None = None,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    payload = {"_reason": body.reason} if body and body.reason else {}
    return _guarded(lambda: _view(svc.advance(application_id, target, payload)))


@router.get("/{application_id}")
def get_application(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    return _guarded(lambda: _view(svc.get(application_id)))


@router.get("/{application_id}/history")
def get_history(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    def _do():
        return [
            {
                "sequence": e.sequence,
                "type": e.type,
                "actor_id": e.actor_id,
                "occurred_at": e.occurred_at,
                "payload": e.payload,
            }
            for e in svc.history(application_id)
        ]

    return _guarded(_do)


def _guarded(fn):
    """Translate domain errors into HTTP status codes."""
    try:
        return fn()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TenantIsolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except MakerCheckerViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (InvalidTransition, ConcurrencyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
