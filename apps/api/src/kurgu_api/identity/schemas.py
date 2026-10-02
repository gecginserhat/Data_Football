"""Kimlik uçlarının yanıt şemaları."""

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field

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


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str | None
    name: str | None
    roles: list[Role]
    last_seen_at: dt.datetime | None
    squad_player_id: uuid.UUID | None = None
    squad_player_name: str | None = None


class RolesIn(BaseModel):
    roles: list[Role] = Field(min_length=1, max_length=len(Role))


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    roles: list[Role] = Field(min_length=1, max_length=len(Role))


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    roles: list[Role]
    invited_by_name: str | None
    created_at: dt.datetime
    expires_at: dt.datetime


class AuditEntryOut(BaseModel):
    id: int
    at: dt.datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: str
    entity: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    next_before: int | None
    """Sonraki sayfa için `before` değeri; son sayfada `None`."""
