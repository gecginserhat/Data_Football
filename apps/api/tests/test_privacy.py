"""KVKK: rıza, dışa aktarma, silme talebi, envanter ve saklama (ADR-0019, A-92)."""

import datetime as dt
import json
import os
import uuid
from typing import Any

import asyncpg
import pytest
from kurgu_api.privacy.consent import CONSENT_VERSION
from kurgu_api.privacy.inventory import covered_tables
from kurgu_api.privacy.jobs import retention_job

from .conftest import Seeded, TokenFactory, add_member

TODAY = dt.date(2026, 9, 30)


async def _headers(
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    tenant: uuid.UUID,
    role: str,
    player: uuid.UUID | None = None,
) -> dict[str, str]:
    subject = f"{role}-{uuid.uuid4()}"
    user = await add_member(superuser, subject, tenant, role)
    if player is not None:
        await superuser.execute(
            "update memberships set player_id = $1 where user_id = $2", player, user
        )
    return {"Authorization": f"Bearer {make_token(subject)}", "X-Kurgu-Tenant": str(tenant)}


async def _player(
    superuser: asyncpg.Connection, tenant: uuid.UUID, name: str, shirt: int
) -> uuid.UUID:
    pid: uuid.UUID = await superuser.fetchval(
        "insert into squad_players (tenant_id, name, shirt_number, position, height_cm)"
        " values ($1, $2, $3, 'DEF', 185) returning id",
        tenant,
        name,
        shirt,
    )
    return pid


def _wellness(player: uuid.UUID, day: dt.date) -> dict[str, Any]:
    return {
        "squad_player_id": str(player),
        "date": day.isoformat(),
        "sleep": 3,
        "stress": 3,
        "fatigue": 4,
        "soreness": 2,
    }


class Ctx:
    def __init__(self, tenants: Seeded, player: uuid.UUID, other: uuid.UUID) -> None:
        self.tenants = tenants
        self.player = player
        self.other = other


@pytest.fixture
async def ctx(superuser: asyncpg.Connection, tenants: Seeded) -> Ctx:
    return Ctx(
        tenants,
        await _player(superuser, tenants.tenant_a, "Oyuncu A", 7),
        await _player(superuser, tenants.tenant_a, "Oyuncu B", 8),
    )


async def test_wellness_requires_consent_and_player_gives_it(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, ctx: Ctx
) -> None:
    me = await _headers(make_token, superuser, ctx.tenants.tenant_a, "player", ctx.player)
    blocked = await client.post("/api/v1/wellness", headers=me, json=_wellness(ctx.player, TODAY))
    assert blocked.status_code == 409
    assert blocked.json()["type"].endswith("/consent-required")

    text = (await client.get("/api/v1/privacy/consent-text", headers=me)).json()
    assert text["version"] == CONSENT_VERSION

    # Oyuncu kâğıt yöntemi seçemez; eski metin sürümüne rıza verilemez.
    paper = {"method": "paper", "reference": "x", "text_version": CONSENT_VERSION}
    assert (
        await client.post(f"/api/v1/squad/{ctx.player}/consent", headers=me, json=paper)
    ).status_code == 422
    stale = {"method": "self", "text_version": "2020-01"}
    assert (
        await client.post(f"/api/v1/squad/{ctx.player}/consent", headers=me, json=stale)
    ).status_code == 409

    given = await client.post(
        f"/api/v1/squad/{ctx.player}/consent",
        headers=me,
        json={"method": "self", "text_version": CONSENT_VERSION},
    )
    assert given.status_code == 201
    assert given.json()["active"]["method"] == "self"
    assert given.json()["can_give_self"] is True

    saved = await client.post("/api/v1/wellness", headers=me, json=_wellness(ctx.player, TODAY))
    assert saved.status_code == 200

    # Başka oyuncunun rızasına dokunamaz.
    assert (await client.get(f"/api/v1/squad/{ctx.other}/consent", headers=me)).status_code == 403

    withdrawn = await client.delete(f"/api/v1/squad/{ctx.player}/consent", headers=me)
    assert withdrawn.json()["active"] is None
    assert withdrawn.json()["history"][0]["withdrawn_at"] is not None
    again = await client.post("/api/v1/wellness", headers=me, json=_wellness(ctx.player, TODAY))
    assert again.status_code == 409

    actions = await superuser.fetch(
        "select action from audit_log where tenant_id = $1 and action like 'consent.%' order by at",
        ctx.tenants.tenant_a,
    )
    assert [a["action"] for a in actions] == ["consent.give", "consent.withdraw"]


async def test_staff_record_paper_consent_and_admin_cannot(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, ctx: Ctx
) -> None:
    perf = await _headers(make_token, superuser, ctx.tenants.tenant_a, "performance")
    admin = await _headers(make_token, superuser, ctx.tenants.tenant_a, "admin")
    coach = await _headers(make_token, superuser, ctx.tenants.tenant_a, "sp_coach")
    url = f"/api/v1/squad/{ctx.player}/consent"

    no_ref = {"method": "paper", "text_version": CONSENT_VERSION}
    assert (await client.post(url, headers=perf, json=no_ref)).status_code == 422
    paper = {**no_ref, "reference": "Form 2026/17"}
    first = await client.post(url, headers=perf, json=paper)
    assert first.status_code == 201
    assert first.json()["active"]["reference"] == "Form 2026/17"
    assert (await client.post(url, headers=perf, json=paper)).status_code == 409

    admin_view = await client.get(url, headers=admin)
    assert admin_view.status_code == 200
    assert admin_view.json()["can_record_paper"] is False
    assert (await client.delete(url, headers=admin)).status_code == 403
    assert (await client.get(url, headers=coach)).status_code == 403


async def test_export_contains_decrypted_wellness_and_is_audited(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, ctx: Ctx
) -> None:
    perf = await _headers(make_token, superuser, ctx.tenants.tenant_a, "performance")
    me = await _headers(make_token, superuser, ctx.tenants.tenant_a, "player", ctx.player)
    admin = await _headers(make_token, superuser, ctx.tenants.tenant_a, "admin")
    await client.post(
        f"/api/v1/squad/{ctx.player}/consent",
        headers=perf,
        json={"method": "paper", "reference": "F1", "text_version": CONSENT_VERSION},
    )
    await client.post("/api/v1/wellness", headers=perf, json=_wellness(ctx.player, TODAY))
    await client.post(
        "/api/v1/sessions",
        headers=perf,
        json={
            "date": TODAY.isoformat(),
            "title": "Seans",
            "loads": [{"squad_player_id": str(ctx.player), "rpe": 6, "minutes": 70}],
        },
    )

    response = await client.get(f"/api/v1/squad/{ctx.player}/export", headers=me)
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = json.loads(response.text)
    assert data["player"]["name"] == "Oyuncu A"
    assert data["wellness"] == [
        {
            "date": TODAY.isoformat(),
            "sleep": 3,
            "stress": 3,
            "fatigue": 4,
            "soreness": 2,
            "hooper": 12,
        }
    ]
    assert data["loads"][0]["rpe"] == 6.0
    assert data["consents"][0]["reference"] == "F1"

    assert (await client.get(f"/api/v1/squad/{ctx.other}/export", headers=me)).status_code == 403
    assert (
        await client.get(f"/api/v1/squad/{ctx.player}/export", headers=admin)
    ).status_code == 403
    audited = await superuser.fetchval(
        "select count(*) from audit_log where action = 'privacy.export' and entity_id = $1",
        str(ctx.player),
    )
    assert audited == 1


async def test_erasure_request_is_approved_by_admin(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, ctx: Ctx
) -> None:
    perf = await _headers(make_token, superuser, ctx.tenants.tenant_a, "performance")
    me = await _headers(make_token, superuser, ctx.tenants.tenant_a, "player", ctx.player)
    admin = await _headers(make_token, superuser, ctx.tenants.tenant_a, "admin")
    await client.post(
        f"/api/v1/squad/{ctx.player}/consent",
        headers=perf,
        json={"method": "paper", "reference": "F1", "text_version": CONSENT_VERSION},
    )
    await client.post("/api/v1/wellness", headers=perf, json=_wellness(ctx.player, TODAY))

    created = await client.post(
        "/api/v1/privacy/requests",
        headers=me,
        json={"squad_player_id": str(ctx.player), "reason": "Kulüpten ayrıldım"},
    )
    assert created.status_code == 201
    duplicate = await client.post(
        "/api/v1/privacy/requests", headers=me, json={"squad_player_id": str(ctx.player)}
    )
    assert duplicate.status_code == 409
    assert (
        await client.post(
            "/api/v1/privacy/requests", headers=admin, json={"squad_player_id": str(ctx.player)}
        )
    ).status_code == 403
    mine = (await client.get("/api/v1/privacy/requests", headers=me)).json()
    assert [r["status"] for r in mine] == ["open"]

    request_id = created.json()["id"]
    assert (
        await client.post(
            f"/api/v1/privacy/requests/{request_id}/decision", headers=perf, json={"approve": True}
        )
    ).status_code == 403
    decided = await client.post(
        f"/api/v1/privacy/requests/{request_id}/decision",
        headers=admin,
        json={"approve": True, "note": "Onaylandı"},
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["request"]["status"] == "completed"
    assert body["erased"] == {"wellness": 1, "loads": 0, "assignments": 0, "consents": 1}

    row = await superuser.fetchrow(
        "select name, shirt_number, active, erased_at from squad_players where id = $1",
        ctx.player,
    )
    assert row["name"] == "Silinmiş oyuncu"
    assert row["shirt_number"] is None
    assert row["active"] is False
    assert row["erased_at"] is not None
    linked = await superuser.fetchval(
        "select count(*) from memberships where player_id = $1", ctx.player
    )
    assert linked == 0
    again = await client.post(
        f"/api/v1/privacy/requests/{request_id}/decision", headers=admin, json={"approve": False}
    )
    assert again.status_code == 409


async def test_inventory_covers_every_personal_table(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    linked = {
        r["table_name"]
        for r in await superuser.fetch(
            """
            select distinct tc.table_name
            from information_schema.table_constraints tc
            join information_schema.constraint_column_usage ccu
              on ccu.constraint_name = tc.constraint_name
            where tc.constraint_type = 'FOREIGN KEY'
              and ccu.table_name in ('users', 'squad_players')
            """
        )
    }
    named = {
        r["table_name"]
        for r in await superuser.fetch(
            "select table_name from information_schema.columns where table_schema = 'public'"
            " and column_name in ('email', 'display_name', 'ip')"
        )
    }
    personal = (linked | named | {"squad_players", "players", "opponent_targets"}) - {"tenants"}
    assert personal - covered_tables() == set()

    admin = await _headers(make_token, superuser, tenants.tenant_a, "admin")
    settings = (await client.get("/api/v1/privacy/settings", headers=admin)).json()
    wellness = next(i for i in settings["inventory"] if i["key"] == "wellness")
    assert wellness["special_category"] is True
    assert wellness["encrypted"] is True
    assert wellness["retention_days"] == 730
    assert settings["data_region"] == "tr"
    coach = await _headers(make_token, superuser, tenants.tenant_a, "head_coach")
    assert (await client.get("/api/v1/privacy/settings", headers=coach)).status_code == 403


async def test_retention_job_purges_expired_records(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, ctx: Ctx
) -> None:
    admin = await _headers(make_token, superuser, ctx.tenants.tenant_a, "admin")
    perf = await _headers(make_token, superuser, ctx.tenants.tenant_a, "performance")
    too_short = {"wellness_days": 10, "loads_days": 60, "audit_days": 365}
    assert (
        await client.put("/api/v1/privacy/retention", headers=admin, json=too_short)
    ).status_code == 422
    updated = await client.put(
        "/api/v1/privacy/retention",
        headers=admin,
        json={"wellness_days": 30, "loads_days": 60, "audit_days": 365},
    )
    assert updated.status_code == 200

    await client.post(
        f"/api/v1/squad/{ctx.player}/consent",
        headers=perf,
        json={"method": "paper", "reference": "F1", "text_version": CONSENT_VERSION},
    )
    for day in (TODAY - dt.timedelta(days=31), TODAY - dt.timedelta(days=29)):
        await client.post("/api/v1/wellness", headers=perf, json=_wellness(ctx.player, day))
    for day in (TODAY - dt.timedelta(days=61), TODAY - dt.timedelta(days=5)):
        await client.post(
            "/api/v1/sessions",
            headers=perf,
            json={
                "date": day.isoformat(),
                "title": "Seans",
                "loads": [{"squad_player_id": str(ctx.player), "rpe": 5, "minutes": 60}],
            },
        )
    await superuser.execute(
        "insert into audit_log (tenant_id, action, entity, at) values ($1, 'old', 'x', $2)",
        ctx.tenants.tenant_a,
        dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    )

    from kurgu_api.config import get_settings
    from kurgu_api.core.db import dispose_engine

    # Worker kendi rolüyle bağlanır (RLS altında, kiracıları yalnız okuyabilir).
    worker_url = get_settings().database_url.replace(
        "kurgu_app:test-app", "kurgu_worker:test-worker"
    )

    previous = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = worker_url
    get_settings.cache_clear()
    await dispose_engine()
    try:
        report = await retention_job({}, today=TODAY)
    finally:
        os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        await dispose_engine()

    removed = report[str(ctx.tenants.tenant_a)]
    assert removed["wellness"] == 1
    assert removed["loads"] == 1
    assert removed["sessions"] == 1
    assert removed["audit"] >= 1
    left = await superuser.fetchval(
        "select count(*) from wellness_entries where squad_player_id = $1", ctx.player
    )
    assert left == 1
    logged = await superuser.fetchval(
        "select after from audit_log where tenant_id = $1 and action = 'privacy.retention_run'",
        ctx.tenants.tenant_a,
    )
    assert json.loads(logged)["wellness"] == 1
