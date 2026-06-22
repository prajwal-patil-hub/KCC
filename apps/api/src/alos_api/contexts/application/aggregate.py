"""LoanApplication aggregate — event-sourced (ADR-0002).

The spine of the system. State is a fold over its event stream. Transition
legality, the maker-checker gate, and role requirements are governed by the
config-driven WorkflowDefinition (platform/workflow.py) and enforced in the
ApplicationService — the aggregate just holds the folded read-state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...platform.events import Event

# Re-exported for backwards-compatible imports across the contexts.
from ...platform.workflow import InvalidTransition  # noqa: F401


@dataclass
class LoanApplication:
    application_id: str
    tenant_id: str
    product: str = "KCC"
    stage: str | None = None
    maker_user_id: str | None = None
    customer: dict = field(default_factory=dict)
    kyc: dict = field(default_factory=dict)
    eligibility: dict = field(default_factory=dict)
    memo: dict = field(default_factory=dict)
    documents: dict = field(default_factory=dict)
    disbursement: dict = field(default_factory=dict)
    cbs: dict = field(default_factory=dict)
    completed_stages: list[str] = field(default_factory=list)
    version: int = 0

    @classmethod
    def from_events(cls, events: list[Event]) -> "LoanApplication":
        if not events:
            raise InvalidTransition("Application has no events")
        first = events[0]
        app = cls(application_id=first.stream_id, tenant_id=first.tenant_id)
        for e in events:
            app._apply(e)
        app.version = len(events)
        return app

    def _apply(self, e: Event) -> None:
        name = e.type.split(".", 1)[-1]
        self.stage = name
        self.completed_stages.append(name)
        # The creating event carries the product (chooses the workflow).
        if isinstance(e.payload, dict) and e.payload.get("product"):
            self.product = e.payload["product"]
        if name == "MakerReviewed":
            self.maker_user_id = e.actor_id
        mapping = {
            "CustomerLinked": "customer",
            "KycCompleted": "kyc",
            "EligibilityComputed": "eligibility",
            "MemoGenerated": "memo",
            "DocumentsExecuted": "documents",
            "Disbursed": "disbursement",
            "CbsPosted": "cbs",
        }
        if name in mapping:
            setattr(self, mapping[name], e.payload)
