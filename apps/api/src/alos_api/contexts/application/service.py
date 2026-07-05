"""Application service — orchestrates commands on the LoanApplication aggregate.

Each command runs the canonical write path (docs/03): validate invariants +
tenant context, append event(s), and write an audit record. Transition legality,
maker-checker, and role requirements come from the injected WorkflowDefinition
(ADR-0004). (Outbox publication is a no-op stub in the skeleton; the seam is here.)
"""

from __future__ import annotations

import uuid

from ...context import current_context
from ...platform.audit import AuditStore
from ...platform.events import Event, EventStore
from ...platform.makerchecker import assert_distinct
from ...platform.tenancy import assert_tenant
from ...platform.workflow import (
    RoleNotPermitted,
    WorkflowDefinition,
    get_workflow,
)
from .aggregate import LoanApplication


class ApplicationService:
    def __init__(self, events: EventStore, audit: AuditStore) -> None:
        self._events = events
        self._audit = audit

    def workflow_for(self, app: LoanApplication) -> WorkflowDefinition:
        """Resolve the workflow from the application's product (config-driven,
        multi-product — ADR-0004). No product-specific branching in this service."""
        return get_workflow(app.product)

    # --- helpers ----------------------------------------------------------

    def _load(self, application_id: str) -> LoanApplication:
        stream = self._events.load(application_id)
        if not stream:
            raise KeyError(f"Application {application_id} not found")
        app = LoanApplication.from_events(stream)
        assert_tenant(app.tenant_id)  # tenant isolation (ADR-0003)
        return app

    def _emit(
        self, application_id: str, expected_version: int, etype: str, payload: dict
    ) -> Event:
        ctx = current_context()
        event = Event(
            stream_id=application_id,
            sequence=expected_version + 1,
            type=etype,
            payload=payload,
            tenant_id=ctx.principal.tenant_id,
            actor_id=ctx.principal.user_id,
            correlation_id=ctx.correlation_id,
        )
        self._events.append(application_id, expected_version, [event])
        self._audit.record(
            action=etype, resource=f"application:{application_id}",
            reason=payload.get("_reason"),
        )
        # Outbox publish seam (no-op in skeleton): publish(event)
        return event

    # --- commands ---------------------------------------------------------

    def create(self, product: str, payload: dict) -> LoanApplication:
        """Create an application for any registered product; emit that product's
        first workflow stage (LeadCreated for KCC/Dairy, RenewalInitiated for
        renewal). The product is recorded on the creating event."""
        workflow = get_workflow(product)
        first = workflow.names()[0]
        application_id = str(uuid.uuid4())
        workflow.assert_transition(None, first)
        self._emit(
            application_id, 0, f"application.{first}", {**payload, "product": product}
        )
        return self._load(application_id)

    def create_lead(self, payload: dict) -> LoanApplication:
        return self.create(payload.get("product", "KCC"), payload)

    def advance(
        self, application_id: str, target: str, payload: dict | None = None
    ) -> LoanApplication:
        app = self._load(application_id)
        workflow = self.workflow_for(app)
        principal = current_context().principal
        stage = workflow.get(target)

        # 1) transition legality
        workflow.assert_transition(app.stage, target)
        # 2) Separation of Duties (before role, so SoD violations surface as 409)
        if stage.requires_checker:
            assert_distinct(app.maker_user_id, principal.user_id)
        # 3) role requirement (ABAC-lite)
        if stage.required_roles and not (stage.required_roles & principal.roles):
            raise RoleNotPermitted(
                f"Stage '{target}' requires one of {sorted(stage.required_roles)}"
            )

        self._emit(application_id, app.version, f"application.{target}", payload or {})
        return self._load(application_id)

    def get(self, application_id: str) -> LoanApplication:
        return self._load(application_id)

    def history(self, application_id: str) -> list[Event]:
        app = self._load(application_id)  # also enforces tenant
        return self._events.load(app.application_id)
