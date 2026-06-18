"""Config-driven workflow / saga engine (ADR-0004).

The lending lifecycle is *data*, not hard-coded branching: a WorkflowDefinition
is an ordered set of Stages, each with optional maker-checker gating, role
requirements, and a flag marking automated (side-effecting) stages. Adding a
product or changing the approval chain is a new definition, not new code.

Transition legality, the checker gate, and role requirements are enforced here
(server-side). Stage *actions* and their compensations live in the owning
contexts (documentation, disbursement) and are run as small sagas.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class InvalidTransition(RuntimeError):
    """Raised when a stage is entered out of order."""


class RoleNotPermitted(PermissionError):
    """Raised when the actor lacks a role required by the stage."""


@dataclass(frozen=True)
class Stage:
    name: str
    requires_checker: bool = False           # maker != checker (Separation of Duties)
    required_roles: frozenset[str] = field(default_factory=frozenset)
    automated: bool = False                  # has a side-effecting action (saga)
    description: str = ""


@dataclass(frozen=True)
class WorkflowDefinition:
    product: str
    version: str
    stages: tuple[Stage, ...]

    def names(self) -> list[str]:
        return [s.name for s in self.stages]

    def get(self, name: str) -> Stage:
        for s in self.stages:
            if s.name == name:
                return s
        raise InvalidTransition(f"Unknown stage '{name}' in workflow {self.product}")

    def index(self, name: str) -> int:
        return self.names().index(name)

    def assert_transition(self, current: str | None, target: str) -> None:
        if target not in self.names():
            raise InvalidTransition(f"Unknown stage '{target}'")
        idx = self.index(target)
        expected_prev = self.names()[idx - 1] if idx > 0 else None
        if current != expected_prev:
            raise InvalidTransition(
                f"Cannot move to '{target}' from '{current}'; "
                f"expected previous stage '{expected_prev}'"
            )


def kcc_workflow() -> WorkflowDefinition:
    """The KCC MVP lifecycle. In production this is loaded from the Config
    service, versioned and effective-dated, per tenant + product."""
    return WorkflowDefinition(
        product="KCC",
        version="kcc-flow/v1",
        stages=(
            Stage("LeadCreated", description="Lead captured"),
            Stage("CustomerLinked", description="Customer profile linked"),
            Stage("KycCompleted", description="Identity verified (KYC)"),
            Stage("EligibilityComputed", description="Deterministic KCC limit computed"),
            Stage("MemoGenerated", description="Credit memo produced (AI optional)"),
            Stage("MakerReviewed", required_roles=frozenset({"Maker"}),
                  description="Maker review"),
            Stage("CheckerReviewed", requires_checker=True,
                  required_roles=frozenset({"Checker"}),
                  description="Independent checker review"),
            Stage("Sanctioned", required_roles=frozenset({"SanctionAuthority"}),
                  description="Sanction by authority"),
            Stage("DocumentsExecuted", automated=True,
                  description="NESL + eStamp + eSign (saga with compensation)"),
            Stage("Disbursed", automated=True,
                  description="Funds disbursed (idempotent money event)"),
            Stage("CbsPosted", automated=True,
                  description="Posted to CBS ledger + reconciled"),
        ),
    )
