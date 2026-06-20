"""Request context: who is acting, for which tenant, with what correlation id.

This is the single source of the authenticated principal during a request. The
tenant guard (platform/tenancy.py) and audit writer read from here. Modelled as
a contextvar so it is available without threading it through every call.
"""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    """The authenticated actor for the current request."""

    user_id: str
    tenant_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    branch_id: str | None = None

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class RequestContext:
    principal: Principal
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


_ctx: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "alos_request_context", default=None
)


def set_context(ctx: RequestContext) -> contextvars.Token:
    return _ctx.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    # Sync FastAPI dependencies can run setup and teardown in different contexts,
    # which makes token-based reset raise. Fall back to clearing the value.
    try:
        _ctx.reset(token)
    except ValueError:
        _ctx.set(None)


def clear_context() -> None:
    """Drop any bound context (used by tests to stay isolated)."""
    _ctx.set(None)


def current_context() -> RequestContext:
    ctx = _ctx.get()
    if ctx is None:
        raise LookupError("No request context set (unauthenticated access?)")
    return ctx


def current_principal() -> Principal:
    return current_context().principal


class ContextMiddleware:
    """Pure ASGI middleware that binds the request's Principal to the contextvar.

    Runs in the request's async context, so the value is copied into the
    threadpool when sync endpoints are dispatched — unlike a yield-dependency,
    whose mutations don't propagate back across the threadpool boundary.

    Dev auth: reads X-User-Id / X-Tenant-Id / X-Roles / X-Branch-Id headers.
    In production this is replaced by OIDC token validation (docs/06); the rest
    of the app only ever sees a Principal, so nothing downstream changes.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        user = headers.get(b"x-user-id")
        tenant = headers.get(b"x-tenant-id")

        token = None
        if user and tenant:
            roles = headers.get(b"x-roles", b"").decode()
            branch = headers.get(b"x-branch-id")
            principal = Principal(
                user_id=user.decode(),
                tenant_id=tenant.decode(),
                roles=frozenset(r.strip() for r in roles.split(",") if r.strip()),
                branch_id=branch.decode() if branch else None,
            )
            token = set_context(RequestContext(principal=principal))
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_context(token)
