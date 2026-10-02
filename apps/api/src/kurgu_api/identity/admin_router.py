"""Kullanıcı yönetimi ve denetim kaydı uçları; yalnız yönetici (`user_admin_audit`, SPEC §12.1)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from kurgu_api.core.problems import ProblemError
from kurgu_api.identity import members
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.identity.schemas import AuditPageOut, InviteIn, InviteOut, MemberOut, RolesIn
from kurgu_api.identity.service import Principal

router = APIRouter(tags=["users"], dependencies=[Depends(require(Permission.USER_ADMIN_AUDIT))])


def _tenant(principal: Principal) -> uuid.UUID:
    if principal.tenant is None:
        raise ProblemError(400, "tenant-required", "Select a tenant")
    return principal.tenant.tenant_id


@router.get("/users", response_model=list[MemberOut], operation_id="listMembers")
async def list_members(session: SessionDep) -> list[MemberOut]:
    return await members.list_members(session)


@router.put("/users/{user_id}/roles", response_model=MemberOut, operation_id="setMemberRoles")
async def set_member_roles(
    user_id: uuid.UUID, body: RolesIn, session: SessionDep, principal: PrincipalDep
) -> MemberOut:
    return await members.set_roles(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        user_id=user_id,
        roles=set(body.roles),
    )


@router.delete(
    "/users/{user_id}", status_code=204, response_class=Response, operation_id="removeMember"
)
async def remove_member(user_id: uuid.UUID, session: SessionDep, principal: PrincipalDep) -> None:
    await members.remove_member(
        session, tenant_id=_tenant(principal), actor_id=principal.user_id, user_id=user_id
    )


@router.get("/invites", response_model=list[InviteOut], operation_id="listInvites")
async def list_invites(session: SessionDep) -> list[InviteOut]:
    return await members.list_invites(session)


@router.post("/invites", response_model=InviteOut, status_code=201, operation_id="createInvite")
async def create_invite(body: InviteIn, session: SessionDep, principal: PrincipalDep) -> InviteOut:
    return await members.create_invite(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        email=body.email,
        roles=set(body.roles),
    )


@router.delete(
    "/invites/{invite_id}", status_code=204, response_class=Response, operation_id="revokeInvite"
)
async def revoke_invite(invite_id: uuid.UUID, session: SessionDep, principal: PrincipalDep) -> None:
    await members.revoke_invite(
        session, tenant_id=_tenant(principal), actor_id=principal.user_id, invite_id=invite_id
    )


@router.get("/audit", response_model=AuditPageOut, operation_id="listAudit")
async def list_audit(
    session: SessionDep,
    before: Annotated[int | None, Query(ge=1)] = None,
    action: Annotated[str | None, Query(max_length=64, pattern=r"^[a-z][a-z_.]*$")] = None,
) -> AuditPageOut:
    return await members.audit_page(session, before=before, action=action)
