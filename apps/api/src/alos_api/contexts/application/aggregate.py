"""LoanApplication aggregate — event-sourced (ADR-0002).

The spine of the system. State is a fold over its event stream. The workflow is
an explicit ordered set of stages (ADR-0004); transitions are validated here and
maker-checker gates are enforced server-side.

This is a deliberately small, KCC-shaped slice of the full lifecycle in
docs/02; stages can be made config-driven later without changing callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...platform.events import Event
from ...platform.makerchecker import assert_distinct

# Ordered KCC workflow stages (the MVP slice).
STAGES: list[str] = [
    "LeadCreated",
    "CustomerLinked",
    "KycCompleted",
    "EligibilityComputed",
    "MakerReviewed",
    "CheckerReviewed",
    "Sanctioned",
]

# Transitions that require an independent checker (Separation of Duties).
CHECKER_GATES = {"CheckerReviewed"}


class InvalidTransition(RuntimeError):
    pass


@dataclass
class LoanApplication:
    """Folded read-state of an application. Rebuilt from events, never mutated
    directly by callers — callers issue commands on the service."""

    application_id: str
    tenant_id: str
    stage: str | None = None
    maker_user_id: str | None = None
    customer: dict = field(default_factory=dict)
    kyc: dict = field(default_factory=dict)
    eligibility: dict = field(default_factory=dict)
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
        if name == "MakerReviewed":
            self.maker_user_id = e.actor_id
        if name == "CustomerLinked":
            self.customer = e.payload
        if name == "KycCompleted":
            self.kyc = e.payload
        if name == "EligibilityComputed":
            self.eligibility = e.payload

    # --- transition rules -------------------------------------------------

    def next_stage_of(self, target: str) -> None:
        if target not in STAGES:
            raise InvalidTransition(f"Unknown stage '{target}'")
        idx = STAGES.index(target)
        expected_prev = STAGES[idx - 1] if idx > 0 else None
        if self.stage != expected_prev:
            raise InvalidTransition(
                f"Cannot move to '{target}' from '{self.stage}'; "
                f"expected previous stage '{expected_prev}'"
            )

    def guard_checker(self, target: str, actor_user_id: str) -> None:
        if target in CHECKER_GATES:
            assert_distinct(self.maker_user_id, actor_user_id)
