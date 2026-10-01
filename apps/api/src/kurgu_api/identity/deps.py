"""FastAPI bağımlılıkları: kimlik doğrulama, kiracı bağlamı ve izin kontrolü."""

import uuid
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.config import get_settings
from kurgu_api.core.db import get_session, set_request_context
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity import service
from kurgu_api.identity.roles import MFA_REQUIRED_ROLES, Permission, Scope, scope_for
from kurgu_api.identity.service import Principal
from kurgu_api.identity.tokens import InvalidTokenError, JwksTokenVerifier, TokenVerifier

TENANT_HEADER = "X-Kurgu-Tenant"

_bearer = HTTPBearer(auto_error=False)
_WWW_AUTH = {"WWW-Authenticate": "Bearer"}


@lru_cache
def get_token_verifier() -> TokenVerifier:
    return JwksTokenVerifier(get_settings())


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_principal(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    tenant_header: Annotated[str | None, Header(alias=TENANT_HEADER)] = None,
) -> Principal:
    """Token'ı doğrular, kullanıcıyı çözer ve RLS bağlamını işleme yazar."""
    if credentials is None:
        raise ProblemError(401, "unauthorized", "Missing bearer token", headers=_WWW_AUTH)
    try:
        claims = await verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise ProblemError(401, "invalid-token", "Invalid token", headers=_WWW_AUTH) from exc

    requested: uuid.UUID | None = None
    if tenant_header:
        try:
            requested = uuid.UUID(tenant_header)
        except ValueError as exc:
            raise ProblemError(400, "invalid-tenant", f"Invalid {TENANT_HEADER}") from exc

    user_id = await service.resolve_user(session, claims)
    await set_request_context(session, user_id=user_id, tenant_id=None)
    memberships = await service.list_memberships(session, user_id)
    try:
        tenant = service.select_tenant(memberships, requested)
    except LookupError as exc:
        raise ProblemError(403, "not-a-member", "No membership in the requested tenant") from exc
    await set_request_context(
        session, user_id=user_id, tenant_id=tenant.tenant_id if tenant else None
    )

    roles = tenant.roles if tenant else frozenset()
    settings = get_settings()
    if settings.kurgu_require_mfa and roles & MFA_REQUIRED_ROLES and not claims.mfa:
        raise ProblemError(403, "mfa-required", "Multi-factor authentication is required")

    return Principal(
        user_id=user_id,
        email=claims.email,
        name=claims.name,
        mfa=claims.mfa,
        memberships=memberships,
        tenant=tenant,
        roles=roles,
    )


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require(permission: Permission) -> Callable[[Principal], Awaitable[Scope]]:
    """Uçta izin şartı koşar; izin kapsamını (`all`/`summary`/`own`) döner."""

    async def _dependency(principal: PrincipalDep) -> Scope:
        if principal.tenant is None:
            raise ProblemError(400, "tenant-required", f"Select a tenant with {TENANT_HEADER}")
        scope = scope_for(principal.roles, permission)
        if scope is None:
            raise ProblemError(403, "forbidden", f"Missing permission: {permission.value}")
        return scope

    return _dependency
