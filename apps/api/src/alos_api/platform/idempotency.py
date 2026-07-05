"""Idempotency key store (ADR-0006 / docs/06).

Any state-changing external call or money movement must carry an idempotency key
so a retry or double-click results in exactly one effect (scenario S1). The store
returns the cached result for a key it has already seen.

In-memory driver; production driver is Redis with a TTL.
"""

from __future__ import annotations

import threading
from typing import Any


class IdempotencyStore:
    def __init__(self) -> None:
        self._seen: dict[str, Any] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._seen.get(key)

    def remember(self, key: str, result: Any) -> None:
        with self._lock:
            self._seen[key] = result

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._seen
