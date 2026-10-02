"""Kimlik servis katmanı. Diğer modüller kimlik tablolarına yalnızca buradan erişir."""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.identity.models import Membership, Tenant
from kurgu_api.identity.roles import Role
from kurgu_api.identity.tokens import TokenClaims


@dataclass(frozen=True)
class MembershipView:
    tenant_id: uuid.UUID
    tenant_name: str
    roles: frozenset[Role]
    player_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str | None
    name: str | None
    mfa: bool
    memberships: tuple[MembershipView, ...]
    tenant: MembershipView | None = None
    roles: frozenset[Role] = field(default_factory=frozenset)


async def resolve_user(session: AsyncSession, claims: TokenClaims) -> uuid.UUID:
    """Kullanıcıyı (iss, sub) ile bulur ya da oluşturur.

    RLS altında kullanıcı henüz kendi kimliğini bilmediği için bu işlem
    SECURITY DEFINER bir veritabanı fonksiyonuyla yapılır (alembic 0001).
    """
    result = await session.execute(
        text("select kurgu_resolve_user(:iss, :sub, :email, :name)"),
        {"iss": claims.issuer, "sub": claims.subject, "email": claims.email, "name": claims.name},
    )
    return uuid.UUID(str(result.scalar_one()))


async def claim_invites(session: AsyncSession, user_id: uuid.UUID, claims: TokenClaims) -> int:
    """Doğrulanmış e-postaya verilmiş bekleyen davetleri üyeliğe çevirir (A-100).

    Davetler kiracı bağlamı olmadan okunamaz; iş SECURITY DEFINER fonksiyonda yapılır (alembic
    0010). E-postası doğrulanmamış token davet açamaz.
    """
    if not claims.email or not claims.email_verified:
        return 0
    result = await session.execute(
        text("select kurgu_claim_invites(:u, :e)"), {"u": user_id, "e": claims.email}
    )
    return int(result.scalar_one())


async def list_memberships(session: AsyncSession, user_id: uuid.UUID) -> tuple[MembershipView, ...]:
    """Kullanıcının tüm kiracılardaki üyelikleri. `app.user_id` ayarlı olmalıdır."""
    rows = (
        await session.execute(
            select(Membership.tenant_id, Tenant.name, Membership.role, Membership.player_id)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Membership.user_id == user_id)
            .order_by(Tenant.name)
        )
    ).all()
    grouped: dict[uuid.UUID, tuple[str, set[Role], uuid.UUID | None]] = {}
    for tenant_id, tenant_name, role, player_id in rows:
        name, roles, pid = grouped.setdefault(tenant_id, (tenant_name, set(), None))
        roles.add(Role(role))
        grouped[tenant_id] = (name, roles, pid or player_id)
    return tuple(
        MembershipView(tenant_id=tid, tenant_name=name, roles=frozenset(roles), player_id=pid)
        for tid, (name, roles, pid) in grouped.items()
    )


def select_tenant(
    memberships: tuple[MembershipView, ...], requested: uuid.UUID | None
) -> MembershipView | None:
    """İstenen kiracıyı seçer. İstek yoksa ve tek üyelik varsa onu kullanır.

    İstenen kiracıda üyelik yoksa `LookupError` fırlatır.
    """
    if requested is not None:
        for membership in memberships:
            if membership.tenant_id == requested:
                return membership
        raise LookupError(str(requested))
    if len(memberships) == 1:
        return memberships[0]
    return None


async def tenant_requires_mfa(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """Kiracı ayarı `mfa_required` (geliştirmede kiracı bazında MFA denetimi; A-90)."""
    result = await session.execute(
        text(
            "select coalesce((settings->>'mfa_required')::boolean, false)"
            " from tenants where id = :t"
        ),
        {"t": tenant_id},
    )
    return bool(result.scalar_one_or_none())
