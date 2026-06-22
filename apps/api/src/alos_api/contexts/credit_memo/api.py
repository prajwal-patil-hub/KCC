"""Credit-Memo HTTP routes.

The memo step is designed so it can ALWAYS be completed:
  * /generate  — AI memo if available, else automatic deterministic template memo
  * /manual    — human writes (or overrides) the memo
  * /skip      — skip the step with a recorded reason (audited)
  * /ai/health — lets the UI show AI status and surface the right controls
All four advance the application to the MemoGenerated stage, so a missing/broken
AI never blocks the workflow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...context import RequestContext
from ...deps import (
    get_application_service,
    get_credit_memo_agent,
    get_underwriting_service,
    require_context,
)
from ...platform.events import ConcurrencyError
from ...platform.tenancy import TenantIsolationError
from ..application.aggregate import InvalidTransition
from ..application.service import ApplicationService
from ..underwriting.agents import UnderwritingService
from .agent import CreditMemoAgent

router = APIRouter(tags=["credit-memo"])


class ManualMemoBody(BaseModel):
    text: str = Field(min_length=1)


class SkipMemoBody(BaseModel):
    reason: str = Field(min_length=3, description="Why the memo step is skipped")


@router.get("/ai/health")
def ai_health(
    ctx: RequestContext = Depends(require_context),
    agent: CreditMemoAgent = Depends(get_credit_memo_agent),
):
    available = agent.ai_available()
    return {
        "ai_available": available,
        "provider": agent.provider.name,
        # Tell the UI what to do when AI is down.
        "fallback_options": (
            [] if available else ["template", "manual", "skip"]
        ),
        "message": (
            "AI underwriting is available."
            if available
            else "AI is not running — use a template memo, write one manually, "
            "or skip the step with a reason."
        ),
    }


def _record(svc: ApplicationService, application_id: str, payload: dict):
    try:
        app = svc.advance(application_id, "MemoGenerated", payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TenantIsolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (InvalidTransition, ConcurrencyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"stage": app.stage, "memo": app.memo}


def _load_app(svc: ApplicationService, application_id: str):
    try:
        return svc.get(application_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TenantIsolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _applicant_name(app) -> str:
    return (app.customer or {}).get("applicant_name") \
        or (app.customer or {}).get("customer_id") or "Applicant"


def _applicant_and_eligibility(svc: ApplicationService, application_id: str):
    app = _load_app(svc, application_id)
    return _applicant_name(app), app.eligibility


@router.get("/applications/{application_id}/underwriting")
def underwriting_preview(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    uw: UnderwritingService = Depends(get_underwriting_service),
):
    """Advisory Risk/Fraud/Compliance assessment of the current state (no event).
    Lets the maker see the risk picture before generating the memo."""
    app = _load_app(svc, application_id)
    return uw.assess(applicant_name=_applicant_name(app), kyc=app.kyc,
                     eligibility=app.eligibility).to_payload()


@router.post("/applications/{application_id}/memo/generate")
def generate_memo(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    agent: CreditMemoAgent = Depends(get_credit_memo_agent),
    uw: UnderwritingService = Depends(get_underwriting_service),
):
    app = _load_app(svc, application_id)
    name = _applicant_name(app)
    # Underwriting (Risk + Fraud + Compliance) feeds the memo (docs/05).
    underwriting = uw.assess(applicant_name=name, kyc=app.kyc, eligibility=app.eligibility)
    result = agent.generate(applicant_name=name, eligibility=app.eligibility)
    payload = {**result.to_payload(), "underwriting": underwriting.to_payload()}
    return _record(svc, application_id, payload)


@router.post("/applications/{application_id}/memo/manual")
def manual_memo(
    application_id: str,
    body: ManualMemoBody,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    agent: CreditMemoAgent = Depends(get_credit_memo_agent),
):
    name, eligibility = _applicant_and_eligibility(svc, application_id)
    result = agent.manual(applicant_name=name, eligibility=eligibility, text=body.text)
    return _record(svc, application_id, result.to_payload())


@router.post("/applications/{application_id}/memo/skip")
def skip_memo(
    application_id: str,
    body: SkipMemoBody,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    agent: CreditMemoAgent = Depends(get_credit_memo_agent),
):
    name, eligibility = _applicant_and_eligibility(svc, application_id)
    result = agent.skip(applicant_name=name, eligibility=eligibility, reason=body.reason)
    payload = result.to_payload()
    payload["_reason"] = body.reason  # surfaced into the audit record
    return _record(svc, application_id, payload)
