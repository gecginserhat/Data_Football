"""`GET /me`: oturumdaki kullanıcı, üyelikleri ve aktif kiracıdaki rolleri (SPEC §11)."""

from fastapi import APIRouter

from kurgu_api.identity.deps import PrincipalDep
from kurgu_api.identity.roles import permissions_for
from kurgu_api.identity.schemas import ActiveTenantOut, MembershipOut, MeOut

router = APIRouter(tags=["identity"])


@router.get("/me", response_model=MeOut, operation_id="getMe")
async def get_me(principal: PrincipalDep) -> MeOut:
    active = None
    if principal.tenant is not None:
        active = ActiveTenantOut(
            tenant_id=principal.tenant.tenant_id,
            tenant_name=principal.tenant.tenant_name,
            roles=sorted(principal.roles),
            permissions=permissions_for(principal.roles),
            squad_player_id=principal.tenant.player_id,
        )
    return MeOut(
        user_id=principal.user_id,
        email=principal.email,
        name=principal.name,
        memberships=[
            MembershipOut(tenant_id=m.tenant_id, tenant_name=m.tenant_name, roles=sorted(m.roles))
            for m in principal.memberships
        ],
        active_tenant=active,
    )
