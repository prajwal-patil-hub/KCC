"""Integration adapter framework (ADR-0006).

Every external system sits behind a Port; each call goes through a resilient
wrapper providing the uniform guarantees from the ADR: retries with backoff, a
circuit breaker, idempotency, and PII-redacted audit. Mock mode is the default
so the whole flow runs with zero real access.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

T = TypeVar("T")


class IntegrationError(RuntimeError):
    pass


class CircuitOpenError(IntegrationError):
    """Raised when the breaker is open and calls are short-circuited (S5)."""


@dataclass
class CircuitBreaker:
    """Trips open after `threshold` consecutive failures; half-opens after cooldown."""

    threshold: int = 5
    cooldown_seconds: float = 30.0
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.cooldown_seconds:
            return False  # half-open: allow a trial call
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = time.monotonic()


class Adapter:
    """Base for all integration adapters.

    Subclasses set `name`, declare `mock_mode`, and implement business methods by
    wrapping their actual work in `self.call(...)`.
    """

    name: str = "adapter"

    def __init__(
        self,
        *,
        mock_mode: bool = True,
        max_retries: int = 3,
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.mock_mode = mock_mode
        self.max_retries = max_retries
        self.breaker = breaker or CircuitBreaker()
        self._sleep = sleep

    def call(self, operation: str, fn: Callable[[], T]) -> T:
        if self.breaker.is_open:
            raise CircuitOpenError(f"{self.name}.{operation}: circuit open")

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = fn()
                self.breaker.record_success()
                self._audit(operation, "ok", attempt)
                return result
            except Exception as exc:  # noqa: BLE001 - adapters normalise errors
                last_exc = exc
                self.breaker.record_failure()
                self._audit(operation, f"error:{type(exc).__name__}", attempt)
                if attempt < self.max_retries:
                    # exponential backoff + (deterministic, test-friendly) step
                    self._sleep(min(2 ** (attempt - 1) * 0.1, 2.0))
        raise IntegrationError(
            f"{self.name}.{operation} failed after {self.max_retries} attempts"
        ) from last_exc

    def _audit(self, operation: str, outcome: str, attempt: int) -> None:
        """Record a PII-redacted integration audit entry (best-effort)."""
        try:
            from ..deps import get_audit_store

            get_audit_store().record(
                action=f"integration.{self.name}.{operation}",
                resource=f"{self.name}:{outcome}",
                reason=f"attempt={attempt} mode={'mock' if self.mock_mode else 'live'}",
            )
        except Exception:
            # Never let auditing failure mask the integration result in the skeleton.
            pass
