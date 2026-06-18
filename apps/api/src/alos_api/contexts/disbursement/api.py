"""Disbursement + CBS posting + reconciliation routes.

Money events are idempotent: a repeat /disburse returns the same reference and
does NOT emit a second Disbursed event (scenario S1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...context import RequestContext
from ...deps import (
    get_application_service,
    get_disbursement_service,
    get_reconciliation_store,
    require_context,
)
from ...platform.events import ConcurrencyError
from ...platform.tenancy import TenantIsolationError
from ...platform.workflow import InvalidTransition, RoleNotPermitted
from ..application.service import ApplicationService
from .reconciliation import ReconciliationStore
from .service import DisbursementService

router = APIRouter(tags=["disbursement"])


def _net_limit(app) -> float:
    breakup = (app.eligibility or {}).get("breakup") or {}
    try:
        return float(breakup.get("net_limit", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _load(svc: ApplicationService, application_id: str):
    try:
        return svc.get(application_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TenantIsolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _advance(svc: ApplicationService, application_id: str, target: str, payload: dict):
    try:
        return svc.advance(application_id, target, payload)
    except (InvalidTransition, ConcurrencyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RoleNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/applications/{application_id}/disburse")
def disburse(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    disb: DisbursementService = Depends(get_disbursement_service),
):
    app = _load(svc, application_id)
    amount = _net_limit(app)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="No sanctioned amount to disburse")
    account = (app.customer or {}).get("customer_id") or application_id

    result, is_new = disb.disburse(
        application_id=application_id, amount=amount, account=account
    )
    if is_new:
        _advance(svc, application_id, "Disbursed", {**result, "idempotent_replay": False})
    # Idempotent replay: no second money event, return the same reference.
    app = svc.get(application_id)
    return {"stage": app.stage, "disbursement": app.disbursement,
            "idempotent_replay": not is_new, "reference": result["reference"]}


@router.post("/applications/{application_id}/cbs-post")
def cbs_post(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    disb: DisbursementService = Depends(get_disbursement_service),
):
    app = _load(svc, application_id)
    disbursement = app.disbursement or {}
    if not disbursement.get("reference"):
        raise HTTPException(status_code=409, detail="Nothing disbursed to post")
    result, is_new = disb.post_to_cbs(
        application_id=application_id,
        amount=float(disbursement.get("amount", 0)),
        disbursement_reference=disbursement["reference"],
    )
    if is_new:
        _advance(svc, application_id, "CbsPosted", result)
    app = svc.get(application_id)
    return {"stage": app.stage, "cbs": app.cbs, "idempotent_replay": not is_new}


@router.get("/reconciliation/report")
def reconciliation_report(
    ctx: RequestContext = Depends(require_context),
    recon: ReconciliationStore = Depends(get_reconciliation_store),
):
    return recon.reconcile()
