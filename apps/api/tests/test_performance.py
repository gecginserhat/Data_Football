"""Yük ve iyi oluş (Faz 7, SPEC §8.2-8.3, ADR-0014, A-83 … A-86).

Kabul (SPEC §19 Faz 7): sRPE, Hooper ve EWMA hesapları test edildi; sıçrama ve kafa vuruşu
uyarıları çalışır; rol izinleri doğrulandı.
"""

import datetime as dt
import json
import uuid
from typing import Any

import asyncpg
import pytest
from kurgu_api.core.crypto import decrypt

from .conftest import Seeded, TokenFactory, add_member

UNTIL = dt.date(2026, 9, 30)  # Çarşamba
MONDAY = dt.date(2026, 9, 28)


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
    superuser: asyncpg.Connection, tenant: uuid.UUID, name: str, position: str = "DEF"
) -> uuid.UUID:
    pid: uuid.UUID = await superuser.fetchval(
        "insert into squad_players (tenant_id, name, position, height_cm) values ($1, $2, $3, 185)"
        " returning id",
        tenant,
        name,
        position,
    )
    return pid


class Club:
    def __init__(self, tenants: Seeded, a: uuid.UUID, b: uuid.UUID, other: uuid.UUID) -> None:
        self.tenants = tenants
        self.a = a
        self.b = b
        self.other_tenant_player = other


@pytest.fixture
async def squad(superuser: asyncpg.Connection, tenants: Seeded) -> Club:
    a = await _player(superuser, tenants.tenant_a, "Oyuncu A")
    b = await _player(superuser, tenants.tenant_a, "Oyuncu B", "MID")
    other = await _player(superuser, tenants.tenant_b, "Başka kulüp")
    return Club(tenants, a, b, other)


@pytest.fixture
async def perf(make_token: TokenFactory, superuser: asyncpg.Connection, squad: Club) -> Any:
    return await _headers(make_token, superuser, squad.tenants.tenant_a, "performance")


async def _session(
    client: Any, headers: dict[str, str], day: dt.date, loads: list[dict[str, Any]]
) -> Any:
    return await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"date": day.isoformat(), "md_code": "MD-3", "title": "Seans", "loads": loads},
    )


async def _wellness(
    client: Any, headers: dict[str, str], player: uuid.UUID, day: dt.date, **scores: int
) -> Any:
    body = {"sleep": 3, "stress": 2, "fatigue": 4, "soreness": 5, **scores}
    return await client.post(
        "/api/v1/wellness",
        headers=headers,
        json={"squad_player_id": str(player), "date": day.isoformat(), **body},
    )


async def test_session_srpe_and_ewma(client: Any, perf: dict[str, str], squad: Club) -> None:
    created = await _session(
        client,
        perf,
        UNTIL,
        [
            {"squad_player_id": str(squad.a), "rpe": 6, "minutes": 75, "jumps": 20, "headers": 9},
            {"squad_player_id": str(squad.b), "rpe": 4.5, "minutes": 60},
        ],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["players"] == 2
    assert body["mean_srpe"] == (450 + 270) / 2

    overview = await client.get(f"/api/v1/load/overview?until={UNTIL}", headers=perf)
    assert overview.status_code == 200, overview.text
    data = overview.json()
    assert data["scope"] == "all"
    rows = {r["player"]["id"]: r for r in data["players"]}
    a = rows[str(squad.a)]
    # Tek günlük seride EWMA ilk değere eşittir; ACWR 28 günden önce gösterilmez.
    assert a["load_7d"] == 450
    assert a["acute"] == 450
    assert a["chronic"] == 450
    assert a["acwr"] is None
    assert a["low_data"] is True
    assert a["jumps_week"] == 20
    assert a["headers_week"] == 9
    assert data["summary"]["players_with_data"] == 2
    assert data["summary"]["mean_load_7d"] == 360

    # İkinci gün: akut = λ·x + (1−λ)·önceki.
    await _session(
        client,
        perf,
        UNTIL + dt.timedelta(days=1),
        [{"squad_player_id": str(squad.a), "rpe": 0, "minutes": 0}],
    )
    nxt = await client.get(
        f"/api/v1/players/{squad.a}/load?until={UNTIL + dt.timedelta(days=1)}", headers=perf
    )
    days = nxt.json()["days"]
    assert [d["load"] for d in days] == [450, 0]
    assert days[1]["acute"] == round(450 * (1 - 2 / 8), 2)
    assert days[1]["chronic"] == round(450 * (1 - 2 / 29), 2)


async def test_session_validation(client: Any, perf: dict[str, str], squad: Club) -> None:
    dup = await _session(
        client,
        perf,
        UNTIL,
        [
            {"squad_player_id": str(squad.a), "rpe": 5, "minutes": 60},
            {"squad_player_id": str(squad.a), "rpe": 5, "minutes": 60},
        ],
    )
    assert dup.status_code == 422
    other = await _session(
        client,
        perf,
        UNTIL,
        [{"squad_player_id": str(squad.other_tenant_player), "rpe": 5, "minutes": 60}],
    )
    assert other.status_code == 422
    assert other.json()["type"].endswith("unknown-player")
    bad = await _session(
        client, perf, UNTIL, [{"squad_player_id": str(squad.a), "rpe": 11, "minutes": 60}]
    )
    assert bad.status_code == 422


async def test_wellness_is_encrypted_and_audited(
    client: Any, perf: dict[str, str], squad: Club, superuser: asyncpg.Connection
) -> None:
    saved = await _wellness(client, perf, squad.a, UNTIL, sleep=6)
    assert saved.status_code == 200, saved.text
    assert saved.json()["hooper"] == 6 + 2 + 4 + 5

    raw = await superuser.fetchval(
        "select scores::text from wellness_entries where squad_player_id = $1", squad.a
    )
    envelope = json.loads(raw)
    assert set(envelope) == {"v", "kid", "wrapped_dek", "nonce", "ciphertext"}
    assert "sleep" not in raw
    assert decrypt(
        envelope, tenant_id=squad.tenants.tenant_a, table="wellness_entries", field="scores"
    ) == {"sleep": 6, "stress": 2, "fatigue": 4, "soreness": 5}

    # Aynı gün yeniden giriş üzerine yazar.
    again = await _wellness(client, perf, squad.a, UNTIL, sleep=1)
    assert again.json()["hooper"] == 1 + 2 + 4 + 5
    count = await superuser.fetchval(
        "select count(*) from wellness_entries where squad_player_id = $1", squad.a
    )
    assert count == 1

    detail = await client.get(f"/api/v1/players/{squad.a}/load?until={UNTIL}", headers=perf)
    assert detail.status_code == 200
    assert detail.json()["wellness"][0]["sleep"] == 1
    assert detail.json()["hooper"][0] == {"date": UNTIL.isoformat(), "value": 12, "z": None}

    actions = await superuser.fetch(
        "select action, after from audit_log where tenant_id = $1 and action like 'wellness.%'"
        " order by at",
        squad.tenants.tenant_a,
    )
    assert [a["action"] for a in actions] == ["wellness.write", "wellness.write", "wellness.read"]
    assert all("sleep" not in a["after"] for a in actions)


async def test_hooper_z_after_seven_entries(client: Any, perf: dict[str, str], squad: Club) -> None:
    for i in range(7):
        day = UNTIL - dt.timedelta(days=6 - i)
        response = await _wellness(client, perf, squad.a, day, sleep=2 + (i % 3))
        assert response.status_code == 200
    detail = (
        await client.get(f"/api/v1/players/{squad.a}/load?until={UNTIL}", headers=perf)
    ).json()
    zs = [h["z"] for h in detail["hooper"]]
    assert zs[:6] == [None] * 6
    assert zs[6] is not None


async def _history(
    superuser: asyncpg.Connection, tenant: uuid.UUID, player: uuid.UUID, metric: str
) -> None:
    """5 önceki hafta (her biri 20 ± 2) ve bu hafta 60 sayım."""
    weekly = [18, 22, 20, 19, 21]
    for i, total in enumerate([*weekly, 60]):
        day = MONDAY - dt.timedelta(weeks=len(weekly) - i)
        session = await superuser.fetchval(
            "insert into training_sessions (tenant_id, date, title) values ($1, $2, 'Geçmiş')"
            " returning id",
            tenant,
            day,
        )
        await superuser.execute(
            f"insert into session_loads (tenant_id, session_id, squad_player_id, rpe, minutes,"  # noqa: S608
            f" {metric}) values ($1, $2, $3, 5, 60, $4)",
            tenant,
            session,
            player,
            total,
        )


@pytest.mark.parametrize("metric", ["jumps", "headers"])
async def test_weekly_alerts(
    client: Any, perf: dict[str, str], squad: Club, superuser: asyncpg.Connection, metric: str
) -> None:
    await _history(superuser, squad.tenants.tenant_a, squad.a, metric)
    data = (await client.get(f"/api/v1/load/overview?until={UNTIL}", headers=perf)).json()
    alerts = data["alerts"]
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["player"]["id"] == str(squad.a)
    assert alert["metric"] == metric
    assert alert["week"] == MONDAY.isoformat()
    assert alert["total"] == 60
    assert alert["weeks"] == 5
    assert alert["mean"] == 20
    assert alert["threshold"] == pytest.approx(20 + 2 * alert["sd"], abs=0.02)
    detail = (
        await client.get(f"/api/v1/players/{squad.a}/load?until={UNTIL}", headers=perf)
    ).json()
    assert [a["metric"] for a in detail["alerts"]] == [metric]
    assert detail["weeks"][-1][metric] == 60
    # B oyuncusunda geçmiş yok, uyarı yok.
    assert all(a["player"]["id"] != str(squad.b) for a in alerts)


async def test_role_permissions(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    squad: Club,
    perf: dict[str, str],
) -> None:
    tenant = squad.tenants.tenant_a
    await _session(
        client, perf, UNTIL, [{"squad_player_id": str(squad.a), "rpe": 5, "minutes": 60}]
    )
    await _wellness(client, perf, squad.a, UNTIL)
    admin = await _headers(make_token, superuser, tenant, "admin")
    medical = await _headers(make_token, superuser, tenant, "medical")
    coach = await _headers(make_token, superuser, tenant, "sp_coach")
    viewer = await _headers(make_token, superuser, tenant, "viewer")
    player = await _headers(make_token, superuser, tenant, "player", player=squad.a)
    overview = f"/api/v1/load/overview?until={UNTIL}"
    detail_a = f"/api/v1/players/{squad.a}/load?until={UNTIL}"
    detail_b = f"/api/v1/players/{squad.b}/load?until={UNTIL}"

    # Yönetici: yalnız takım özeti.
    summary = await client.get(overview, headers=admin)
    assert summary.status_code == 200
    body = summary.json()
    assert body["scope"] == "summary"
    assert body["players"] is None
    assert body["alerts"] is None
    assert body["summary"]["wellness_entries_7d"] == 1
    assert body["summary"]["mean_hooper_7d"] == 14
    assert (await client.get(detail_a, headers=admin)).status_code == 403
    assert (await _wellness(client, admin, squad.a, UNTIL)).status_code == 403
    assert (await client.get("/api/v1/sessions", headers=admin)).status_code == 200

    # Sağlık: tam erişim.
    assert (await client.get(overview, headers=medical)).json()["scope"] == "all"
    assert (await client.get(detail_b, headers=medical)).status_code == 200

    # Oyuncu: yalnız kendi verisi.
    assert (await client.get(detail_a, headers=player)).status_code == 200
    assert (await client.get(detail_b, headers=player)).status_code == 403
    assert (await client.get(overview, headers=player)).status_code == 403
    assert (await client.get("/api/v1/sessions", headers=player)).status_code == 403
    assert (await _wellness(client, player, squad.a, UNTIL)).status_code == 200
    assert (await _wellness(client, player, squad.b, UNTIL)).status_code == 403
    own_session = await _session(
        client, player, UNTIL, [{"squad_player_id": str(squad.a), "rpe": 5, "minutes": 60}]
    )
    assert own_session.status_code == 403

    # Yük izni olmayan roller.
    for headers in (coach, viewer):
        assert (await client.get(overview, headers=headers)).status_code == 403
        assert (await client.get(detail_a, headers=headers)).status_code == 403
        assert (await _wellness(client, headers, squad.a, UNTIL)).status_code == 403


async def test_tenant_isolation(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    squad: Club,
    perf: dict[str, str],
) -> None:
    await _session(
        client, perf, UNTIL, [{"squad_player_id": str(squad.a), "rpe": 5, "minutes": 60}]
    )
    await _wellness(client, perf, squad.a, UNTIL)
    other = await _headers(make_token, superuser, squad.tenants.tenant_b, "performance")
    data = (await client.get(f"/api/v1/load/overview?until={UNTIL}", headers=other)).json()
    assert [r["player"]["name"] for r in data["players"]] == ["Başka kulüp"]
    assert data["sessions"] == []
    assert data["summary"]["wellness_entries_7d"] == 0
    detail = await client.get(f"/api/v1/players/{squad.a}/load?until={UNTIL}", headers=other)
    assert detail.status_code == 404
    assert (await _wellness(client, other, squad.a, UNTIL)).status_code == 404


async def test_future_wellness_rejected(client: Any, perf: dict[str, str], squad: Club) -> None:
    future = dt.date.today() + dt.timedelta(days=3)
    assert (await _wellness(client, perf, squad.a, future)).status_code == 422
