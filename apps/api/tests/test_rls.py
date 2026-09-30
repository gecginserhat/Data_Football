"""Kiracılar arası izolasyon (Faz 1 kabul kriterinin kimlik tabloları kısmı, ADR-0002)."""

import uuid

import asyncpg
import pytest

from .conftest import Seeded, add_member

TENANT_TABLES = ["tenants", "memberships"]


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_rls_is_enabled_and_forced(superuser: asyncpg.Connection, table: str) -> None:
    row = await superuser.fetchrow(
        "select relrowsecurity, relforcerowsecurity from pg_class where relname = $1", table
    )
    assert row is not None
    assert row["relrowsecurity"]
    assert row["relforcerowsecurity"]


async def test_app_role_cannot_bypass_rls(superuser: asyncpg.Connection) -> None:
    row = await superuser.fetchrow(
        "select rolbypassrls, rolsuper from pg_roles where rolname = 'kurgu_app'"
    )
    assert row is not None
    assert not row["rolbypassrls"]
    assert not row["rolsuper"]


async def _as_tenant(conn: asyncpg.Connection, tenant: uuid.UUID | None) -> None:
    await conn.execute("select set_config('app.tenant_id', $1, false)", str(tenant or ""))
    await conn.execute("select set_config('app.user_id', '', false)")


async def test_no_context_sees_nothing(app_conn: asyncpg.Connection, tenants: Seeded) -> None:
    await _as_tenant(app_conn, None)
    assert await app_conn.fetchval("select count(*) from tenants") == 0
    assert await app_conn.fetchval("select count(*) from memberships") == 0


async def test_tenant_sees_only_its_own_rows(
    app_conn: asyncpg.Connection, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    await add_member(superuser, f"a-{uuid.uuid4()}", tenants.tenant_a, "analyst")
    await add_member(superuser, f"b-{uuid.uuid4()}", tenants.tenant_b, "analyst")

    await _as_tenant(app_conn, tenants.tenant_a)
    visible_tenants = {r["id"] for r in await app_conn.fetch("select id from tenants")}
    visible_members = {
        r["tenant_id"] for r in await app_conn.fetch("select tenant_id from memberships")
    }

    assert visible_tenants == {tenants.tenant_a}
    assert visible_members == {tenants.tenant_a}
    assert (
        await app_conn.fetchval("select count(*) from tenants where id = $1", tenants.tenant_b) == 0
    )


async def test_cannot_write_into_another_tenant(
    app_conn: asyncpg.Connection, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    user_id = await add_member(superuser, f"w-{uuid.uuid4()}", tenants.tenant_a)
    await _as_tenant(app_conn, tenants.tenant_a)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute(
            "insert into memberships (user_id, tenant_id, role) values ($1, $2, 'viewer')",
            user_id,
            tenants.tenant_b,
        )
