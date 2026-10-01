"""Kimlik uçlarının yanıt şemaları."""

import uuid

from pydantic import BaseModel

from kurgu_api.identity.roles import Permission, Role, Scope


class MembershipOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    roles: list[Role]


class ActiveTenantOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    roles: list[Role]
    permissions: dict[Permission, Scope]
    squad_player_id: uuid.UUID | None = None
    """Oyuncu hesabının bağlı olduğu kadro kaydı (A-79)."""


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str | None
    name: str | None
    memberships: list[MembershipOut]
    active_tenant: ActiveTenantOut | None
