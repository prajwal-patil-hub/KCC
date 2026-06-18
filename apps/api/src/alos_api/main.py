"""ALOS API — FastAPI app factory (modular monolith, ADR-0001).

Each bounded context contributes a router; they share the platform kernel
(events, audit, tenancy, maker-checker) via dependencies in deps.py.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .config import get_settings
from .context import ContextMiddleware, RequestContext
from .contexts.application.api import router as application_router
from .contexts.assessment.api import router as assessment_router
from .contexts.credit_memo.api import router as credit_memo_router
from .contexts.disbursement.api import router as disbursement_router
from .contexts.documentation.api import router as documentation_router
from .deps import get_audit_store, require_context


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="Agricultural Lending Operating System — KCC MVP walking skeleton",
    )
    app.add_middleware(ContextMiddleware)

    @app.get("/health", tags=["platform"])
    def health() -> dict:
        return {
            "status": "ok",
            "environment": settings.environment,
            "integration_mode": settings.integration_mode,
        }

    @app.get("/audit/verify", tags=["platform"])
    def audit_verify(
        ctx: RequestContext = Depends(require_context),
    ) -> dict:
        """Tamper-evidence check on the hash-chained audit store (docs/06)."""
        store = get_audit_store()
        return {"chain_intact": store.verify_chain()}

    app.include_router(application_router)
    app.include_router(assessment_router)
    app.include_router(credit_memo_router)
    app.include_router(documentation_router)
    app.include_router(disbursement_router)

    # Serve the demonstrator site (apps/web) at /app if present.
    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    web_dir = Path(__file__).resolve().parents[3] / "web"
    if web_dir.is_dir():
        app.mount("/app", StaticFiles(directory=str(web_dir), html=True), name="web")


app = create_app()
