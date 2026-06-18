"""Maker-checker enforcement (core principle, server-side).

The rule: a transition guarded as `requiresChecker` cannot be performed by the
same user id that made the prior maker action. Enforced here, never relying on
the UI. Separation of Duties is a correctness property, not a convenience.
"""

from __future__ import annotations


class MakerCheckerViolation(PermissionError):
    """Raised when the checker is the same person as the maker."""


def assert_distinct(maker_user_id: str | None, checker_user_id: str) -> None:
    if maker_user_id is not None and maker_user_id == checker_user_id:
        raise MakerCheckerViolation(
            "Checker must be a different user than the maker (Separation of Duties)"
        )
