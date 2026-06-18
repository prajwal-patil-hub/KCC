"""Application service — orchestrates commands on the LoanApplication aggregate.

Each command runs the canonical write path (docs/03): validate invariants +
tenant context, append event(s), and write an audit record. (Outbox publication
is a no-op stub in the skeleton; the seam is here.)
"""

from __future__ import annotations

import uuid

from ...context import current_context
from ...platform.audit import AuditStore
from ...platform.events import Event, EventStore
from ...platform.tenancy import assert_tenant, current_tenant
from .aggregate import LoanApplication


class ApplicationService:
    def __init__(self, events: EventStore, audit: AuditStore) -> None:
        self._events = events
        self._audit = audit

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

    def create_lead(self, payload: dict) -> LoanApplication:
        application_id = str(uuid.uuid4())
        self._emit(application_id, 0, "application.LeadCreated", payload)
        return self._load(application_id)

    def advance(
        self, application_id: str, target: str, payload: dict | None = None
    ) -> LoanApplication:
        app = self._load(application_id)
        actor = current_context().principal.user_id
        app.next_stage_of(target)              # transition legality
        app.guard_checker(target, actor)       # maker != checker on gated steps
        self._emit(application_id, app.version, f"application.{target}", payload or {})
        return self._load(application_id)

    def get(self, application_id: str) -> LoanApplication:
        return self._load(application_id)

    def history(self, application_id: str) -> list[Event]:
        app = self._load(application_id)  # also enforces tenant
        return self._events.load(app.application_id)
