"""Kulüp üyeliği yönetimi: üyeler, roller, davetler ve denetim kaydı (SPEC §12.1, A-100).

Kimlik (parola, MFA) IdP'dedir; Kurgu yalnız kulüp üyeliğini ve rolleri yönetir. Yönetici bir
e-posta adresine davet verir; kişi o adresle (IdP'de doğrulanmış) ilk girişinde üye olur.
Kulübün son yöneticisi rolünü bırakamaz ve çıkarılamaz.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.audit import write_audit
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.roles import Role
from kurgu_api.identity.schemas import AuditEntryOut, AuditPageOut, InviteOut, MemberOut

INVITE_DAYS = 14
AUDIT_PAGE = 50

MEMBERS_SQL = """
select u.id, u.email, u.display_name, u.last_seen_at,
       array_agg(m.role order by m.role) as roles,
       max(m.player_id::text) as player_id,
       max(sp.name) as player_name
  from memberships m
  join users u on u.id = m.user_id
  left join squad_players sp on sp.id = m.player_id and sp.tenant_id = m.tenant_id
 where m.tenant_id = kurgu_current_tenant() {where}
 group by u.id
 order by lower(coalesce(u.display_name, u.email, '')), u.id
"""


def _member(row: Any) -> MemberOut:
    return MemberOut(
        user_id=row.id,
        email=row.email,
        name=row.display_name,
        roles=sorted(Role(r) for r in row.roles),
        last_seen_at=row.last_seen_at,
        squad_player_id=uuid.UUID(row.player_id) if row.player_id else None,
        squad_player_name=row.player_name,
    )


async def list_members(session: AsyncSession) -> list[MemberOut]:
    rows = (await session.execute(text(MEMBERS_SQL.format(where="")))).all()
    return [_member(r) for r in rows]


async def get_member(session: AsyncSession, user_id: uuid.UUID) -> MemberOut:
    row = (
        await session.execute(text(MEMBERS_SQL.format(where="and u.id = :u")), {"u": user_id})
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "User is not a member of this club")
    return _member(row)


async def _lock_admins(session: AsyncSession) -> set[uuid.UUID]:
    """Kulübün yönetici satırlarını kilitler; eşzamanlı iki işlem son yöneticiyi düşüremez."""
    rows = await session.execute(
        text(
            "select user_id from memberships"
            " where tenant_id = kurgu_current_tenant() and role = 'admin' for update"
        )
    )
    return {r.user_id for r in rows}


async def set_roles(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: set[Role],
) -> MemberOut:
    """Üyenin bu kulüpteki rollerini verilen kümeye eşitler.

    Kalan satırlara dokunulmaz; böylece oyuncu rolünün kadro bağlantısı (`player_id`) korunur.
    """
    admins = await _lock_admins(session)
    before = await get_member(session, user_id)
    current = set(before.roles)
    if Role.ADMIN in current and Role.ADMIN not in roles and admins == {user_id}:
        raise ProblemError(409, "last-admin", "The club must keep at least one admin")
    removed = current - roles
    added = roles - current
    if removed:
        await session.execute(
            text(
                "delete from memberships where tenant_id = kurgu_current_tenant()"
                " and user_id = :u and role = any(:roles)"
            ),
            {"u": user_id, "roles": [r.value for r in removed]},
        )
    for role in sorted(added):
        await session.execute(
            text(
                "insert into memberships (user_id, tenant_id, role)"
                " values (:u, kurgu_current_tenant(), :r)"
            ),
            {"u": user_id, "r": role.value},
        )
    if removed or added:
        await write_audit(
            session,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="member.roles",
            entity="users",
            entity_id=user_id,
            before={"roles": [r.value for r in sorted(current)]},
            after={"roles": [r.value for r in sorted(roles)]},
        )
    return await get_member(session, user_id)


async def remove_member(
    session: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    admins = await _lock_admins(session)
    before = await get_member(session, user_id)
    if admins == {user_id}:
        raise ProblemError(409, "last-admin", "The club must keep at least one admin")
    await session.execute(
        text("delete from memberships where tenant_id = kurgu_current_tenant() and user_id = :u"),
        {"u": user_id},
    )
    await write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="member.removed",
        entity="users",
        entity_id=user_id,
        before={"roles": [r.value for r in before.roles]},
        after={},
    )


INVITES_SQL = """
select i.id, i.email, i.roles, i.created_at, i.expires_at, u.display_name as invited_by_name
  from membership_invites i
  left join users u on u.id = i.invited_by
 where i.accepted_at is null and i.revoked_at is null and i.expires_at > now() {where}
 order by i.created_at desc
"""


def _invite(row: Any) -> InviteOut:
    return InviteOut(
        id=row.id,
        email=row.email,
        roles=sorted(Role(r) for r in row.roles),
        invited_by_name=row.invited_by_name,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


async def list_invites(session: AsyncSession) -> list[InviteOut]:
    rows = (await session.execute(text(INVITES_SQL.format(where="")))).all()
    return [_invite(r) for r in rows]


async def create_invite(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    email: str,
    roles: set[Role],
    now: dt.datetime | None = None,
) -> InviteOut:
    email = email.strip().lower()
    member = (
        await session.execute(
            text(
                "select 1 from memberships m join users u on u.id = m.user_id"
                " where m.tenant_id = kurgu_current_tenant() and lower(u.email) = :e limit 1"
            ),
            {"e": email},
        )
    ).first()
    if member is not None:
        raise ProblemError(409, "already-member", "This e-mail already belongs to a member")
    # Süresi dolmuş bekleyen davet benzersizlik dizinini tutmasın diye kapatılır.
    await session.execute(
        text(
            "update membership_invites set revoked_at = now() where tenant_id ="
            " kurgu_current_tenant() and email = :e and accepted_at is null"
            " and revoked_at is null and expires_at <= now()"
        ),
        {"e": email},
    )
    start = now or dt.datetime.now(dt.UTC)
    invite_id = (
        await session.execute(
            text(
                "insert into membership_invites (tenant_id, email, roles, invited_by, expires_at)"
                " values (kurgu_current_tenant(), :e, cast(:roles as varchar[]), :by, :exp)"
                " on conflict do nothing returning id"
            ),
            {
                "e": email,
                "roles": [r.value for r in sorted(roles)],
                "by": actor_id,
                "exp": start + dt.timedelta(days=INVITE_DAYS),
            },
        )
    ).scalar_one_or_none()
    if invite_id is None:
        raise ProblemError(409, "invite-exists", "A pending invite exists for this e-mail")
    await write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="invite.created",
        entity="membership_invites",
        entity_id=invite_id,
        after={"email": email, "roles": [r.value for r in sorted(roles)]},
    )
    row = (
        await session.execute(text(INVITES_SQL.format(where="and i.id = :i")), {"i": invite_id})
    ).one()
    return _invite(row)


async def revoke_invite(
    session: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, invite_id: uuid.UUID
) -> None:
    email = (
        await session.execute(
            text(
                "update membership_invites set revoked_at = now()"
                " where id = :i and accepted_at is null and revoked_at is null returning email"
            ),
            {"i": invite_id},
        )
    ).scalar_one_or_none()
    if email is None:
        raise ProblemError(404, "not-found", "No pending invite with this id")
    await write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="invite.revoked",
        entity="membership_invites",
        entity_id=invite_id,
        after={"email": email},
    )


async def audit_page(
    session: AsyncSession, *, before: int | None, action: str | None, limit: int = AUDIT_PAGE
) -> AuditPageOut:
    """Denetim kaydı, yeniden eskiye. `action` ön ekle süzer (ör. `privacy.` ya da `member.`).

    Yapan kişi kulüpten ayrıldıysa kullanıcı kaydı RLS ile görünmez; adı boş döner.
    """
    rows = (
        await session.execute(
            text(
                "select a.id, a.at, a.actor_id, coalesce(u.display_name, u.email) as actor_name,"
                " a.action, a.entity, a.entity_id, a.before, a.after"
                " from audit_log a left join users u on u.id = a.actor_id"
                " where a.tenant_id = kurgu_current_tenant()"
                " and (cast(:before as bigint) is null or a.id < :before)"
                " and (cast(:action as text) is null or a.action like :action || '%')"
                " order by a.id desc limit :limit"
            ),
            {"before": before, "action": action, "limit": limit + 1},
        )
    ).all()
    items = [
        AuditEntryOut(
            id=r.id,
            at=r.at,
            actor_id=r.actor_id,
            actor_name=r.actor_name,
            action=r.action,
            entity=r.entity,
            entity_id=r.entity_id,
            before=r.before,
            after=r.after,
        )
        for r in rows[:limit]
    ]
    return AuditPageOut(items=items, next_before=items[-1].id if len(rows) > limit else None)
