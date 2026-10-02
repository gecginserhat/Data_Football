"""Kullanıcı yönetimi: üyeler, roller, davetler ve denetim kaydı (SPEC §12.1, A-100)."""

import uuid
from typing import Any

import asyncpg

from .conftest import Seeded, TokenFactory, add_member


async def _admin(
    make_token: TokenFactory, superuser: asyncpg.Connection, tenant: uuid.UUID
) -> tuple[uuid.UUID, dict[str, str]]:
    subject = f"admin-{uuid.uuid4()}"
    user = await add_member(superuser, subject, tenant, "admin")
    token = make_token(subject, email=f"{subject}@kurgu.test")
    return user, {"Authorization": f"Bearer {token}", "X-Kurgu-Tenant": str(tenant)}


async def test_only_admins_manage_users(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    subject = f"coach-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, "head_coach")
    headers = {
        "Authorization": f"Bearer {make_token(subject)}",
        "X-Kurgu-Tenant": str(tenants.tenant_a),
    }
    for method, path in (
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/invites"),
        ("GET", "/api/v1/audit"),
        ("DELETE", f"/api/v1/users/{uuid.uuid4()}"),
    ):
        response = await client.request(method, path, headers=headers)
        assert response.status_code == 403, path
        assert response.headers["content-type"] == "application/problem+json"


async def test_admin_lists_only_own_club_members(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    admin, headers = await _admin(make_token, superuser, tenants.tenant_a)
    analyst = await add_member(
        superuser, f"analyst-{uuid.uuid4()}", tenants.tenant_a, "analyst", "viewer"
    )
    other = await add_member(superuser, f"other-{uuid.uuid4()}", tenants.tenant_b, "admin")

    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200
    by_id = {m["user_id"]: m for m in response.json()}
    assert set(by_id) == {str(admin), str(analyst)}
    assert by_id[str(analyst)]["roles"] == ["analyst", "viewer"]
    assert str(other) not in by_id


async def test_roles_change_keeps_player_link_and_is_audited(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    _, headers = await _admin(make_token, superuser, tenants.tenant_a)
    player = await superuser.fetchval(
        "insert into squad_players (tenant_id, name, shirt_number, position, height_cm)"
        " values ($1, 'Bağlı Oyuncu', 9, 'FWD', 182) returning id",
        tenants.tenant_a,
    )
    user = await add_member(superuser, f"p-{uuid.uuid4()}", tenants.tenant_a, "player")
    await superuser.execute(
        "update memberships set player_id = $1 where user_id = $2", player, user
    )

    response = await client.put(
        f"/api/v1/users/{user}/roles", headers=headers, json={"roles": ["player", "viewer"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["roles"] == ["player", "viewer"]
    assert body["squad_player_id"] == str(player)
    assert body["squad_player_name"] == "Bağlı Oyuncu"

    audit = await superuser.fetchrow(
        "select before, after from audit_log where tenant_id = $1 and action = 'member.roles'",
        tenants.tenant_a,
    )
    assert audit is not None
    assert '"player"' in audit["before"]
    assert '"viewer"' in audit["after"]

    empty = await client.put(f"/api/v1/users/{user}/roles", headers=headers, json={"roles": []})
    assert empty.status_code == 422
    bad = await client.put(
        f"/api/v1/users/{user}/roles", headers=headers, json={"roles": ["owner"]}
    )
    assert bad.status_code == 422


async def test_last_admin_cannot_be_demoted_or_removed(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    admin, headers = await _admin(make_token, superuser, tenants.tenant_a)
    demote = await client.put(
        f"/api/v1/users/{admin}/roles", headers=headers, json={"roles": ["analyst"]}
    )
    assert demote.status_code == 409
    assert demote.json()["type"].endswith("/last-admin")
    remove = await client.delete(f"/api/v1/users/{admin}", headers=headers)
    assert remove.status_code == 409

    # İkinci bir yönetici varsa ilk yönetici kendini çıkarabilir.
    await add_member(superuser, f"admin2-{uuid.uuid4()}", tenants.tenant_a, "admin")
    assert (await client.delete(f"/api/v1/users/{admin}", headers=headers)).status_code == 204
    left = await superuser.fetchval(
        "select count(*) from memberships where user_id = $1 and tenant_id = $2",
        admin,
        tenants.tenant_a,
    )
    assert left == 0


async def test_members_of_another_club_are_not_found(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    _, headers = await _admin(make_token, superuser, tenants.tenant_a)
    other = await add_member(superuser, f"b-{uuid.uuid4()}", tenants.tenant_b, "analyst")
    response = await client.put(
        f"/api/v1/users/{other}/roles", headers=headers, json={"roles": ["viewer"]}
    )
    assert response.status_code == 404
    assert (await client.delete(f"/api/v1/users/{other}", headers=headers)).status_code == 404
    roles = await superuser.fetch("select role from memberships where user_id = $1", other)
    assert [r["role"] for r in roles] == ["analyst"]


async def test_invite_becomes_membership_on_verified_sign_in(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    _, headers = await _admin(make_token, superuser, tenants.tenant_a)
    email = f"yeni-{uuid.uuid4().hex[:8]}@kulup.org"
    created = await client.post(
        "/api/v1/invites", headers=headers, json={"email": email.upper(), "roles": ["sp_coach"]}
    )
    assert created.status_code == 201, created.text
    invite = created.json()
    assert invite["email"] == email
    assert invite["roles"] == ["sp_coach"]

    again = await client.post(
        "/api/v1/invites", headers=headers, json={"email": email, "roles": ["viewer"]}
    )
    assert again.status_code == 409
    assert again.json()["type"].endswith("/invite-exists")

    subject = f"new-{uuid.uuid4()}"
    # Doğrulanmamış e-posta daveti açmaz.
    unverified = make_token(subject, email=email, email_verified=False)
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {unverified}"})
    assert me.json()["memberships"] == []

    verified = make_token(subject, email=email, email_verified=True)
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {verified}"})
    assert [m["tenant_id"] for m in me.json()["memberships"]] == [str(tenants.tenant_a)]
    assert me.json()["memberships"][0]["roles"] == ["sp_coach"]

    pending = await client.get("/api/v1/invites", headers=headers)
    assert pending.json() == []
    actions = await superuser.fetch(
        "select action from audit_log where tenant_id = $1 and action like 'invite.%' order by id",
        tenants.tenant_a,
    )
    assert [a["action"] for a in actions] == ["invite.created", "invite.accepted"]

    member = await client.post(
        "/api/v1/invites", headers=headers, json={"email": email, "roles": ["viewer"]}
    )
    assert member.status_code == 409
    assert member.json()["type"].endswith("/already-member")


async def test_revoked_or_expired_invites_are_not_claimed(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    _, headers = await _admin(make_token, superuser, tenants.tenant_a)
    revoked = f"r-{uuid.uuid4().hex[:8]}@kulup.org"
    invite = (
        await client.post(
            "/api/v1/invites", headers=headers, json={"email": revoked, "roles": ["viewer"]}
        )
    ).json()
    assert (
        await client.delete(f"/api/v1/invites/{invite['id']}", headers=headers)
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/invites/{invite['id']}", headers=headers)
    ).status_code == 404

    expired = f"e-{uuid.uuid4().hex[:8]}@kulup.org"
    await client.post(
        "/api/v1/invites", headers=headers, json={"email": expired, "roles": ["viewer"]}
    )
    await superuser.execute(
        "update membership_invites set expires_at = now() - interval '1 day' where email = $1",
        expired,
    )
    for email in (revoked, expired):
        token = make_token(f"x-{uuid.uuid4()}", email=email, email_verified=True)
        me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["memberships"] == []

    # Süresi dolan davetin yerine yenisi verilebilir.
    renewed = await client.post(
        "/api/v1/invites", headers=headers, json={"email": expired, "roles": ["analyst"]}
    )
    assert renewed.status_code == 201


async def test_invites_are_isolated_per_club(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    _, headers_a = await _admin(make_token, superuser, tenants.tenant_a)
    _, headers_b = await _admin(make_token, superuser, tenants.tenant_b)
    invite = (
        await client.post(
            "/api/v1/invites",
            headers=headers_a,
            json={"email": f"i-{uuid.uuid4().hex[:8]}@kulup.org", "roles": ["viewer"]},
        )
    ).json()
    assert (await client.get("/api/v1/invites", headers=headers_b)).json() == []
    response = await client.delete(f"/api/v1/invites/{invite['id']}", headers=headers_b)
    assert response.status_code == 404


async def test_audit_log_pages_and_filters(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    admin, headers = await _admin(make_token, superuser, tenants.tenant_a)
    for i in range(55):
        await superuser.execute(
            "insert into audit_log (tenant_id, actor_id, action, entity, entity_id, after)"
            " values ($1, $2, $3, 'routines', $4, '{}'::jsonb)",
            tenants.tenant_a,
            admin,
            "routine.version" if i % 5 else "privacy.export",
            str(i),
        )
    await superuser.execute(
        "insert into audit_log (tenant_id, action, entity, after)"
        " values ($1, 'routine.version', 'routines', '{}'::jsonb)",
        tenants.tenant_b,
    )

    first = (await client.get("/api/v1/audit", headers=headers)).json()
    assert len(first["items"]) == 50
    assert first["items"][0]["entity_id"] == "54"
    assert first["items"][0]["actor_name"] == "Test Kullanıcı"
    second = (
        await client.get(f"/api/v1/audit?before={first['next_before']}", headers=headers)
    ).json()
    assert len(second["items"]) == 5
    assert second["next_before"] is None

    privacy = (await client.get("/api/v1/audit?action=privacy.", headers=headers)).json()
    assert len(privacy["items"]) == 11
    assert {i["action"] for i in privacy["items"]} == {"privacy.export"}

    bad = await client.get("/api/v1/audit?action=%25", headers=headers)
    assert bad.status_code == 422
