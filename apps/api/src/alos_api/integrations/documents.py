"""Mock documentation adapters: NESL, eStamp, eSign (ADR-0006).

Each is a thin Adapter (retry + circuit breaker + audited). They expose a
`void(reference)` compensation so the documentation saga can roll back a partial
execution. `fail` lets tests force a step to fail and exercise compensation.
"""

from __future__ import annotations

import uuid

from .base import Adapter


class _RefAdapter(Adapter):
    def __init__(self, *, fail: bool = False, **kw):
        super().__init__(**kw)
        self._fail = fail

    def _ref(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"

    def execute(self, application_id: str) -> dict:
        def _do() -> dict:
            if self._fail:
                raise RuntimeError(f"{self.name} provider error")
            return {"reference": self._ref(self.name.upper()), "status": "done"}

        return self.call("execute", _do)

    def void(self, reference: str) -> dict:
        """Compensation — undo a previously successful step."""
        return self.call("void", lambda: {"reference": reference, "status": "voided"})


class MockNeslAdapter(_RefAdapter):
    name = "nesl"


class MockEstampAdapter(_RefAdapter):
    name = "estamp"


class MockEsignAdapter(_RefAdapter):
    name = "esign"
