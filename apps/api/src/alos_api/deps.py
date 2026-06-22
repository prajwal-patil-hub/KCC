"""Process-wide singletons and FastAPI dependencies.

In the modular monolith (ADR-0001) these in-memory stores stand in for Postgres /
Redis / Kafka. They are swapped for real drivers by changing this wiring only —
the contexts depend on the interfaces, not these concretions.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from .config import Settings, get_settings
from .context import RequestContext, current_context
from .contexts.application.service import ApplicationService
from .contexts.credit_memo.agent import CreditMemoAgent
from .contexts.credit_memo.provider import get_provider
from .contexts.disbursement.reconciliation import ReconciliationStore
from .contexts.disbursement.service import DisbursementService
from .contexts.documentation.service import DocStep, DocumentationService
from .integrations.base import CircuitBreaker
from .integrations.cbs import MockCbsAdapter
from .integrations.documents import (
    MockEsignAdapter,
    MockEstampAdapter,
    MockNeslAdapter,
)
from .integrations.kyc import MockKycAdapter
from .platform.audit import AuditStore, InMemoryAuditStore
from .platform.events import EventStore, InMemoryEventStore
from .platform.idempotency import IdempotencyStore

# --- singletons -----------------------------------------------------------

def _make_stores(settings: Settings) -> tuple[EventStore, AuditStore]:
    """Select the storage backend (ADR-0002/0003). Postgres is imported lazily so
    dev/CI without psycopg or a database still run on the in-memory stores."""
    if settings.storage == "postgres":
        from .platform.pg_audit import PostgresAuditStore
        from .platform.pg_events import PostgresEventStore

        return (
            PostgresEventStore(settings.database_url),
            PostgresAuditStore(settings.database_url),
        )
    return InMemoryEventStore(), InMemoryAuditStore()


_event_store, _audit_store = _make_stores(get_settings())
_idempotency: IdempotencyStore = IdempotencyStore()
_reconciliation: ReconciliationStore = ReconciliationStore()


def _make_bus(settings: Settings):
    from .platform.outbox import InMemoryBus, KafkaBus

    if settings.bus == "kafka":
        return KafkaBus(settings.kafka_bootstrap_servers)
    return InMemoryBus()


# Process-wide bus so an in-memory bus accumulates published messages observably.
_bus = _make_bus(get_settings())


def get_bus():
    return _bus


def get_outbox_relay(settings: Settings = Depends(get_settings)):
    from .platform.outbox import OutboxRelay

    return OutboxRelay(settings.relay_database_url, _bus)


def get_event_store() -> EventStore:
    return _event_store


def get_audit_store() -> AuditStore:
    return _audit_store


def get_idempotency_store() -> IdempotencyStore:
    return _idempotency


def get_application_service() -> ApplicationService:
    return ApplicationService(_event_store, _audit_store)


def get_reconciliation_store() -> ReconciliationStore:
    return _reconciliation


def get_credit_memo_agent(
    settings: Settings = Depends(get_settings),
) -> CreditMemoAgent:
    return CreditMemoAgent(get_provider(settings.llm_provider))


def _adapter_kwargs(settings: Settings) -> dict:
    return {
        "mock_mode": settings.integration_mode == "mock",
        "max_retries": settings.adapter_max_retries,
        "breaker": CircuitBreaker(threshold=settings.circuit_breaker_threshold),
    }


def get_documentation_service(
    settings: Settings = Depends(get_settings),
) -> DocumentationService:
    kw = _adapter_kwargs(settings)
    steps = [
        DocStep("nesl", MockNeslAdapter(**kw)),
        DocStep("estamp", MockEstampAdapter(**kw)),
        DocStep("esign", MockEsignAdapter(**kw)),
    ]
    return DocumentationService(steps, _idempotency)


def get_disbursement_service(
    settings: Settings = Depends(get_settings),
) -> DisbursementService:
    return DisbursementService(
        MockCbsAdapter(**_adapter_kwargs(settings)), _idempotency, _reconciliation
    )


def get_kyc_adapter(settings: Settings = Depends(get_settings)):
    """Feature-flagged KYC provider (ADR-0006). Default mock; ALOS_KYC_PROVIDER=
    sandbox points the same Port at a vendor sandbox over HTTP."""
    kw = _adapter_kwargs(settings)
    if settings.kyc_provider == "sandbox":
        from .integrations.kyc import SandboxKycAdapter

        kw.pop("mock_mode", None)
        return SandboxKycAdapter(
            settings.kyc_sandbox_url,
            name_match_threshold=settings.kyc_name_match_threshold,
            **kw,
        )
    return MockKycAdapter(**kw)


# --- auth dependency ------------------------------------------------------
#
# The principal is bound to the request context by ContextMiddleware (which reads
# the dev auth headers; in production this is an OIDC token validated and mapped
# to a Principal — docs/06). This dependency simply requires that binding to
# exist, returning 401 otherwise.


def require_context() -> RequestContext:
    try:
        return current_context()
    except LookupError:
        raise HTTPException(
            status_code=401, detail="Missing X-User-Id / X-Tenant-Id"
        )
