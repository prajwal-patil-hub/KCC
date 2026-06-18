"""Disbursement + CBS posting — idempotent money events (ADR-0002, docs/06).

The correctness guarantee (scenario S1): two disburse calls for the same
application produce exactly one money movement and one Disbursed event. The
idempotency key gates the side effect; the second call returns the cached result
without emitting a new event.
"""

from __future__ import annotations

from ...integrations.cbs import MockCbsAdapter
from ...platform.idempotency import IdempotencyStore
from .reconciliation import ReconciliationStore


class DisbursementService:
    def __init__(
        self,
        cbs: MockCbsAdapter,
        idempotency: IdempotencyStore,
        recon: ReconciliationStore,
    ) -> None:
        self._cbs = cbs
        self._idem = idempotency
        self._recon = recon

    def disburse(self, *, application_id: str, amount: float, account: str) -> tuple[dict, bool]:
        """Returns (result, is_new). is_new=False means it was already disbursed."""
        key = f"disburse:{application_id}"
        cached = self._idem.get(key)
        if cached is not None:
            return cached, False
        result = self._cbs.disburse(idempotency_key=key, amount=amount, account=account)
        self._idem.remember(key, result)
        self._recon.record_disbursement(application_id, result["reference"], amount)
        return result, True

    def post_to_cbs(self, *, application_id: str, amount: float, disbursement_reference: str):
        key = f"cbspost:{application_id}"
        cached = self._idem.get(key)
        if cached is not None:
            return cached, False
        result = self._cbs.post(
            idempotency_key=key, amount=amount, reference=disbursement_reference
        )
        self._idem.remember(key, result)
        self._recon.record_posting(application_id, result["ledger_reference"], amount)
        return result, True
