import uuid
from typing import Any

import asyncpg

from .conftest import Seeded, TokenFactory, add_member


async def test_invalid_token_is_rejected(client: Any, make_token: TokenFactory) -> None:
    token = make_token(aud="someone-else")
    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["type"].endswith("/invalid-token")


async def test_me_returns_role_for_single_membership(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    subject = f"coach-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, "sp_coach")

    response = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {make_token(subject)}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_tenant"]["tenant_id"] == str(tenants.tenant_a)
    assert body["active_tenant"]["roles"] == ["sp_coach"]
    permissions = body["active_tenant"]["permissions"]
    assert permissions["decide_recommendations"] == "all"
    assert "user_admin_audit" not in permissions
    assert [m["tenant_id"] for m in body["memberships"]] == [str(tenants.tenant_a)]


async def test_first_login_creates_user_once(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection
) -> None:
    subject = f"new-{uuid.uuid4()}"
    for _ in range(2):
        response = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {make_token(subject)}"}
        )
        assert response.status_code == 200
        assert response.json()["memberships"] == []
        assert response.json()["active_tenant"] is None
    count = await superuser.fetchval("select count(*) from users where subject = $1", subject)
    assert count == 1


async def test_multiple_memberships_need_tenant_header(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    subject = f"multi-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, "analyst")
    await add_member(superuser, subject, tenants.tenant_b, "admin")
    auth = {"Authorization": f"Bearer {make_token(subject)}"}

    no_header = (await client.get("/api/v1/me", headers=auth)).json()
    assert no_header["active_tenant"] is None
    assert len(no_header["memberships"]) == 2

    chosen = await client.get(
        "/api/v1/me", headers={**auth, "X-Kurgu-Tenant": str(tenants.tenant_b)}
    )
    assert chosen.json()["active_tenant"]["roles"] == ["admin"]


async def test_tenant_without_membership_is_forbidden(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    subject = f"outsider-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, "viewer")
    response = await client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {make_token(subject)}",
            "X-Kurgu-Tenant": str(tenants.tenant_b),
        },
    )
    assert response.status_code == 403
    assert response.json()["type"].endswith("/not-a-member")


async def test_mfa_is_enforced_for_sensitive_roles(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    tenants: Seeded,
    monkeypatch: Any,
) -> None:
    from kurgu_api.config import get_settings

    subject = f"medic-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, "medical")
    monkeypatch.setattr(get_settings(), "kurgu_require_mfa", True)

    without = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {make_token(subject)}"}
    )
    assert without.status_code == 403
    assert without.json()["type"].endswith("/mfa-required")

    with_mfa = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {make_token(subject, amr=['pwd', 'otp'])}"},
    )
    assert with_mfa.status_code == 200
