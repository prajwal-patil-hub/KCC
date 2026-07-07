"""Application context HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import Settings, get_settings
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
from ...platform.workflow import InvalidTransition, RoleNotPermitted
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
        "product": app.product,
        "stage": app.stage,
        "maker_user_id": app.maker_user_id,
        "version": app.version,
        "customer": app.customer,
        "kyc": app.kyc,
        "eligibility": app.eligibility,
        "memo": app.memo,
    }


@router.post("", status_code=201)
def create_lead(
    body: CreateLeadBody,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    app = svc.create_lead(body.model_dump())
    return _view(app)


@router.post("/{application_id}/renew", status_code=201)
def renew(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    """Open a KCC-RENEWAL application against a live (disbursed) loan. The renewal
    is a separate product/workflow (config-only) that revalidates and recomputes."""
    def _do():
        source = svc.get(application_id)
        if source.stage != "CbsPosted":
            raise HTTPException(
                status_code=409,
                detail="Renewal requires a live loan (stage CbsPosted)",
            )
        renewal = svc.create("KCC-RENEWAL", {
            "original_application_id": application_id,
            "applicant_name": (source.customer or {}).get("applicant_name")
            or (source.customer or {}).get("customer_id"),
            "customer": source.customer,
            "prior_net_limit": (source.eligibility or {}).get("breakup", {}).get("net_limit"),
        })
        return _view(renewal)

    return _guarded(_do)


class BypassBody(BaseModel):
    reason: str | None = None


@router.post("/{application_id}/bypass")
def bypass(
    application_id: str,
    body: BypassBody | None = None,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    settings: Settings = Depends(get_settings),
):
    """TEST-ONLY: force-advance past the current (stuck) stage. Enabled only when
    ALOS_TEST_BYPASS is on; returns 403 otherwise so it can never fire in prod."""
    if not settings.test_bypass:
        raise HTTPException(
            status_code=403,
            detail="Bypass is disabled. Set ALOS_TEST_BYPASS=1 to enable (non-prod only).",
        )
    reason = (body.reason if body else None) or "test bypass"
    return _guarded(lambda: _view(svc.bypass(application_id, reason)))


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


@router.get("/{application_id}/timeline")
def get_timeline(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
):
    """Workflow timeline + application health score, both DERIVED from the event
    log so they cannot drift from reality (ADR-0004 / docs/03)."""

    def _do():
        app = svc.get(application_id)
        workflow = svc.workflow_for(app)
        done = set(app.completed_stages)
        stages = workflow.stages
        timeline = []
        current_reached = True
        for s in stages:
            status = "done" if s.name in done else ("current" if current_reached else "pending")
            if status == "current":
                current_reached = False
            # 'current' = the first not-yet-done stage
            timeline.append({
                "name": s.name,
                "description": s.description,
                "requires_checker": s.requires_checker,
                "automated": s.automated,
                "status": "done" if s.name in done else "pending",
            })
        completed = sum(1 for t in timeline if t["status"] == "done")
        total = len(timeline)
        # Health score: progress through the workflow, lightly penalised if the
        # memo step was skipped (a known risk signal).
        memo_skipped = (app.memo or {}).get("mode") == "skipped"
        health = round(100 * completed / total) - (10 if memo_skipped else 0)
        return {
            "application_id": application_id,
            "product": workflow.product,
            "workflow_version": workflow.version,
            "current_stage": app.stage,
            "completed": completed,
            "total": total,
            "health_score": max(0, health),
            "flags": (["memo_skipped"] if memo_skipped else []),
            "timeline": timeline,
        }

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
    except RoleNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (InvalidTransition, ConcurrencyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
