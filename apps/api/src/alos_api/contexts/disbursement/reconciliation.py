"""Reconciliation store + job (docs/06 money controls).

Records each disbursement and its CBS posting, then a reconcile() job verifies
that every disbursement has a matching ledger posting for the same amount. Any
mismatch is a "break" surfaced for manual action — money is never silently lost.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class ReconEntry:
    application_id: str
    disbursement_reference: str | None = None
    ledger_reference: str | None = None
    disbursed_amount: float | None = None
    posted_amount: float | None = None


class ReconciliationStore:
    def __init__(self) -> None:
        self._entries: dict[str, ReconEntry] = {}
        self._lock = threading.RLock()

    def record_disbursement(self, application_id: str, reference: str, amount: float):
        with self._lock:
            e = self._entries.setdefault(application_id, ReconEntry(application_id))
            e.disbursement_reference = reference
            e.disbursed_amount = amount

    def record_posting(self, application_id: str, ledger_reference: str, amount: float):
        with self._lock:
            e = self._entries.setdefault(application_id, ReconEntry(application_id))
            e.ledger_reference = ledger_reference
            e.posted_amount = amount

    def reconcile(self) -> dict:
        with self._lock:
            breaks = []
            matched = 0
            for e in self._entries.values():
                ok = (
                    e.disbursement_reference is not None
                    and e.ledger_reference is not None
                    and e.disbursed_amount == e.posted_amount
                )
                if ok:
                    matched += 1
                else:
                    breaks.append(
                        {
                            "application_id": e.application_id,
                            "disbursed_amount": e.disbursed_amount,
                            "posted_amount": e.posted_amount,
                            "has_disbursement": e.disbursement_reference is not None,
                            "has_posting": e.ledger_reference is not None,
                        }
                    )
            return {
                "total": len(self._entries),
                "matched": matched,
                "breaks": breaks,
                "clean": not breaks,
            }
