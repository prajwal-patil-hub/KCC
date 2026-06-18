"""Documentation saga: NESL -> eStamp -> eSign with compensation (ADR-0004).

If any step fails, the steps already executed are compensated (voided) in
reverse order, so the application is never left in a half-executed legal state.
The whole execution is idempotent per application.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...integrations.base import IntegrationError
from ...platform.idempotency import IdempotencyStore


class SagaFailed(RuntimeError):
    def __init__(self, message: str, compensated: list[str]):
        super().__init__(message)
        self.compensated = compensated


@dataclass
class DocStep:
    name: str
    adapter: object  # _RefAdapter-like: .execute(app_id), .void(ref)


class DocumentationService:
    def __init__(self, steps: list[DocStep], idempotency: IdempotencyStore) -> None:
        self._steps = steps
        self._idem = idempotency

    def execute(self, application_id: str) -> dict:
        key = f"docs:{application_id}"
        cached = self._idem.get(key)
        if cached is not None:
            return cached  # idempotent: never run the saga twice

        executed: list[tuple[DocStep, dict]] = []
        try:
            for step in self._steps:
                result = step.adapter.execute(application_id)
                executed.append((step, result))
        except (IntegrationError, Exception) as exc:  # noqa: BLE001
            compensated = self._compensate(executed)
            raise SagaFailed(
                f"Documentation failed at step after {[s.name for s, _ in executed]}: {exc}",
                compensated,
            ) from exc

        references = {step.name: res["reference"] for step, res in executed}
        out = {"status": "executed", "references": references}
        self._idem.remember(key, out)
        return out

    def _compensate(self, executed: list[tuple[DocStep, dict]]) -> list[str]:
        compensated: list[str] = []
        for step, result in reversed(executed):
            try:
                step.adapter.void(result["reference"])
                compensated.append(step.name)
            except Exception:
                # Best-effort compensation; a real system records a recon break.
                pass
        return compensated
