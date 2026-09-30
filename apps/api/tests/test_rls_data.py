"""Veri çekirdeği RLS testleri (Faz 1.1, ADR-0002).

- Meta test: şemadaki her tabloda RLS açık; kiracı tablolarında zorunlu (FORCE).
- Paylaşılan lig verisi yalnızca lisanslı kiracıya görünür.
- Kiracı tablolarında A'nın satırı B'ye görünmez ve B adına yazılamaz.
- `audit_log` yalnızca eklemedir.
"""

import uuid

import asyncpg
import pytest

from .conftest import Seeded

# Göçün sahibi olduğu sistem tablosu dışında RLS'siz tablo olmamalı.
NON_RLS_TABLES = {"alembic_version"}


async def _as_tenant(conn: asyncpg.Connection, tenant: uuid.UUID | None) -> None:
    await conn.execute("select set_config('app.tenant_id', $1, false)", str(tenant or ""))
    await conn.execute("select set_config('app.user_id', '', false)")


async def test_every_table_has_rls(superuser: asyncpg.Connection) -> None:
    rows = await superuser.fetch(
        """
        select c.relname, c.relrowsecurity, c.relforcerowsecurity,
               exists (select 1 from pg_attribute a where a.attrelid = c.oid
                       and a.attname = 'tenant_id' and not a.attisdropped) as has_tenant
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r'
        """
    )
    tables = {r["relname"]: r for r in rows}
    assert {"events", "set_pieces", "audit_log", "imports"} <= tables.keys()
    for name, row in tables.items():
        if name in NON_RLS_TABLES:
            continue
        assert row["relrowsecurity"], f"{name}: RLS kapalı"
        if row["has_tenant"]:
            assert row["relforcerowsecurity"], f"{name}: kiracı tablosunda FORCE RLS yok"


async def test_every_rls_table_has_a_policy(superuser: asyncpg.Connection) -> None:
    missing = await superuser.fetch(
        """
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity
          and not exists (select 1 from pg_policy p where p.polrelid = c.oid)
        """
    )
    assert [r["relname"] for r in missing] == []


# --- Paylaşılan lig verisi -------------------------------------------------


async def _league(superuser: asyncpg.Connection) -> dict[str, uuid.UUID]:
    code = uuid.uuid4().hex[:8]
    comp = await superuser.fetchval(
        "insert into competitions (code, name) values ($1, 'Lig') returning id", f"L-{code}"
    )
    season = await superuser.fetchval(
        "insert into seasons (competition_id, code, label) values ($1, '2025_26', '2025/26')"
        " returning id",
        comp,
    )
    home = await superuser.fetchval(
        "insert into teams (code, name) values ('HH', 'Ev') returning id"
    )
    away = await superuser.fetchval(
        "insert into teams (code, name) values ('AA', 'Dep') returning id"
    )
    match = await superuser.fetchval(
        "insert into matches (season_id, week, home_team_id, away_team_id, source)"
        " values ($1, 1, $2, $3, 'test') returning id",
        season,
        home,
        away,
    )
    await superuser.execute(
        "insert into events (match_id, action_index, period, time_s, team_id, type, result,"
        " bodypart, start_x, start_y, end_x, end_y, provider)"
        " values ($1, 0, 1, 0, $2, 'pass', 'success', 'foot', 52.5, 34, 60, 30, 'test')",
        match,
        home,
    )
    return {"competition": comp, "season": season, "match": match, "team": home}


async def test_shared_data_needs_a_license(
    app_conn: asyncpg.Connection, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    league = await _league(superuser)
    await superuser.execute(
        "insert into data_licenses (tenant_id, provider, competition_id) values ($1, 'test', $2)",
        tenants.tenant_a,
        league["competition"],
    )

    await _as_tenant(app_conn, tenants.tenant_a)
    assert await app_conn.fetchval("select count(*) from matches where id = $1", league["match"])
    assert await app_conn.fetchval(
        "select count(*) from events where match_id = $1", league["match"]
    )
    assert await app_conn.fetchval("select count(*) from teams where id = $1", league["team"])

    await _as_tenant(app_conn, tenants.tenant_b)
    for table, column, key in (
        ("competitions", "id", "competition"),
        ("seasons", "id", "season"),
        ("matches", "id", "match"),
        ("events", "match_id", "match"),
        ("teams", "id", "team"),
    ):
        count = await app_conn.fetchval(
            f"select count(*) from {table} where {column} = $1",  # noqa: S608 (sabit liste)
            league[key],
        )
        assert count == 0, f"{table} lisanssız kiracıya görünüyor"


async def test_expired_license_hides_data(
    app_conn: asyncpg.Connection, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    league = await _league(superuser)
    await superuser.execute(
        "insert into data_licenses (tenant_id, provider, competition_id, valid_from, valid_to)"
        " values ($1, 'test', $2, current_date - 30, current_date - 1)",
        tenants.tenant_b,
        league["competition"],
    )
    await _as_tenant(app_conn, tenants.tenant_b)
    assert (
        await app_conn.fetchval("select count(*) from matches where id = $1", league["match"]) == 0
    )


async def test_app_cannot_write_shared_tables(
    app_conn: asyncpg.Connection, tenants: Seeded
) -> None:
    await _as_tenant(app_conn, tenants.tenant_a)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("insert into teams (code, name) values ('XX', 'Sahte')")


async def test_app_cannot_grant_itself_a_license(
    app_conn: asyncpg.Connection, tenants: Seeded
) -> None:
    await _as_tenant(app_conn, tenants.tenant_a)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute(
            "insert into data_licenses (tenant_id, provider) values ($1, 'x')", tenants.tenant_a
        )


# --- Kiracı tabloları ------------------------------------------------------


async def _import_row(conn: asyncpg.Connection, tenant: uuid.UUID) -> uuid.UUID:
    row_id: uuid.UUID = await conn.fetchval(
        "insert into imports (tenant_id, kind, filename, content_type, size_bytes, source_hash,"
        " storage_key) values ($1, 'events', 'a.csv', 'text/csv', 10, $2, 'k') returning id",
        tenant,
        uuid.uuid4().hex * 2,
    )
    return row_id


async def test_tenant_rows_are_isolated(
    app_conn: asyncpg.Connection, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    row_a = await _import_row(superuser, tenants.tenant_a)

    await _as_tenant(app_conn, tenants.tenant_b)
    assert await app_conn.fetchval("select count(*) from imports where id = $1", row_a) == 0
    assert await app_conn.execute("update imports set status = 'failed' where id = $1", row_a) == (
        "UPDATE 0"
    )
    assert await app_conn.execute("delete from imports where id = $1", row_a) == "DELETE 0"
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _import_row(app_conn, tenants.tenant_a)

    await _as_tenant(app_conn, tenants.tenant_a)
    assert await app_conn.fetchval("select count(*) from imports where id = $1", row_a) == 1


async def test_provider_set_pieces_are_shared_live_tags_are_not(
    app_conn: asyncpg.Connection, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    league = await _league(superuser)
    for tenant in (tenants.tenant_a, tenants.tenant_b):
        await superuser.execute(
            "insert into data_licenses (tenant_id, provider, competition_id)"
            " values ($1, 'test', $2)",
            tenant,
            league["competition"],
        )
    insert = (
        "insert into set_pieces (tenant_id, match_id, team_id, period, start_time_s, sp_type,"
        " source) values ($1, $2, $3, 1, 10, 'corner', $4) returning id"
    )
    shared = await superuser.fetchval(insert, None, league["match"], league["team"], "provider")
    own = await superuser.fetchval(
        insert, tenants.tenant_a, league["match"], league["team"], "live_tag"
    )

    await _as_tenant(app_conn, tenants.tenant_b)
    visible = {r["id"] for r in await app_conn.fetch("select id from set_pieces")}
    assert shared in visible
    assert own not in visible
    # Uygulama rolü paylaşılan diziyi değiştiremez.
    assert (
        await app_conn.execute("update set_pieces set goal = true where id = $1", shared)
        == "UPDATE 0"
    )


async def test_set_piece_source_must_match_owner(
    superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    league = await _league(superuser)
    with pytest.raises(asyncpg.CheckViolationError):
        await superuser.execute(
            "insert into set_pieces (tenant_id, match_id, team_id, period, start_time_s, sp_type,"
            " source) values ($1, $2, $3, 1, 10, 'corner', 'provider')",
            tenants.tenant_a,
            league["match"],
            league["team"],
        )


async def test_audit_log_is_append_only(app_conn: asyncpg.Connection, tenants: Seeded) -> None:
    await _as_tenant(app_conn, tenants.tenant_a)
    row_id = await app_conn.fetchval(
        "insert into audit_log (tenant_id, action, entity) values ($1, 'test', 'x') returning id",
        tenants.tenant_a,
    )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("update audit_log set action = 'y' where id = $1", row_id)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("delete from audit_log where id = $1", row_id)


async def test_worker_writes_shared_rows_but_not_foreign_tenant_rows(
    superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    from .conftest import _url

    worker = await asyncpg.connect(_url("kurgu_worker", "postgresql"))
    try:
        await _as_tenant(worker, None)
        team = await worker.fetchval(
            "insert into teams (code, name) values ('WW', 'Worker') returning id"
        )
        assert team is not None
        run = await worker.fetchval(
            "insert into ingestion_runs (provider, kind) values ('statsbomb', 'events')"
            " returning id"
        )
        assert run is not None
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await worker.execute(
                "insert into ingestion_runs (tenant_id, provider, kind)"
                " values ($1, 'csv', 'events')",
                tenants.tenant_a,
            )
    finally:
        await worker.close()
