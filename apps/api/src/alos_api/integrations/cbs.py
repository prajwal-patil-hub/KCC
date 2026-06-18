"""Mock Core Banking System (CBS) adapter (ADR-0006).

Money-moving operations (disburse, post) take an idempotency key so a retry or
double-click results in exactly one effect (scenario S1). The adapter itself is
deterministic on the key: the same key returns the same reference.
"""

from __future__ import annotations

import hashlib

from .base import Adapter


def _ref(prefix: str, key: str) -> str:
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:12]}"


class MockCbsAdapter(Adapter):
    name = "cbs"

    def __init__(self, *, fail: bool = False, **kw):
        super().__init__(**kw)
        self._fail = fail

    def disburse(self, *, idempotency_key: str, amount: float, account: str) -> dict:
        def _do() -> dict:
            if self._fail:
                raise RuntimeError("CBS disbursement error")
            return {
                "reference": _ref("DISB", idempotency_key),
                "amount": amount,
                "account": account,
                "status": "SUCCESS",
            }

        return self.call("disburse", _do)

    def post(self, *, idempotency_key: str, amount: float, reference: str) -> dict:
        def _do() -> dict:
            return {
                "ledger_reference": _ref("GL", idempotency_key),
                "amount": amount,
                "disbursement_reference": reference,
                "status": "POSTED",
            }

        return self.call("post", _do)
