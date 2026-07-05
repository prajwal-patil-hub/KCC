"""Test fixtures.

The in-memory stores in deps.py are process-wide singletons, so we reset them
between tests to keep cases independent.
"""

import pytest
from fastapi.testclient import TestClient

from alos_api import deps
from alos_api.main import create_app
from alos_api.platform.audit import InMemoryAuditStore
from alos_api.platform.events import InMemoryEventStore
from alos_api.platform.idempotency import IdempotencyStore


@pytest.fixture(autouse=True)
def _reset_stores():
    from alos_api.context import clear_context

    clear_context()  # no request context leaks between tests
    deps._event_store = InMemoryEventStore()
    deps._audit_store = InMemoryAuditStore()
    deps._idempotency = IdempotencyStore()
    yield
    clear_context()


@pytest.fixture
def client():
    return TestClient(create_app())


def auth(user="maker1", tenant="bankA", roles="Maker", branch="br1"):
    return {
        "X-User-Id": user,
        "X-Tenant-Id": tenant,
        "X-Roles": roles,
        "X-Branch-Id": branch,
    }
