"""Documentation routes — runs the NESL/eStamp/eSign saga, then records the
DocumentsExecuted stage. A saga failure compensates and does NOT advance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...context import RequestContext
from ...deps import (
    get_application_service,
    get_documentation_service,
    require_context,
)
from ...platform.events import ConcurrencyError
from ...platform.tenancy import TenantIsolationError
from ...platform.workflow import InvalidTransition, RoleNotPermitted
from ..application.service import ApplicationService
from .service import DocumentationService, SagaFailed

router = APIRouter(tags=["documentation"])


@router.post("/applications/{application_id}/documents/execute")
def execute_documents(
    application_id: str,
    ctx: RequestContext = Depends(require_context),
    svc: ApplicationService = Depends(get_application_service),
    docs: DocumentationService = Depends(get_documentation_service),
):
    # Confirm the application exists / tenant before doing external work.
    try:
        svc.get(application_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TenantIsolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    try:
        result = docs.execute(application_id)
    except SagaFailed as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": str(exc), "compensated": exc.compensated},
        )

    try:
        app = svc.advance(application_id, "DocumentsExecuted", result)
    except (InvalidTransition, ConcurrencyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RoleNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"stage": app.stage, "documents": app.documents}
