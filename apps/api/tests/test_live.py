"""Canlı kayıt senkronizasyonu (Faz 5, ADR-0004): idempotentlik, son yazan kazanır, silme kazanır,
iki cihaz, duran top satırları, izinler ve kiracı izolasyonu.
"""

import datetime as dt
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_api.ingestion.router import get_queue
from kurgu_api.league.seed import run_seed

from .conftest import Seeded, TokenFactory, add_member

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
T0 = dt.datetime(2026, 10, 10, 13, 5, tzinfo=dt.UTC)


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[Any, ...]] = []

    async def enqueue_job(self, name: str, *args: Any) -> None:
        self.jobs.append((name, *args))


@pytest.fixture
async def queue(app: Any) -> FakeQueue:
    fake = FakeQueue()
    app.dependency_overrides[get_queue] = lambda: fake
    return fake


@pytest.fixture
async def club(superuser: asyncpg.Connection, tenants: Seeded) -> Seeded:
    await run_seed(seed_dir=SEED_DIR)
    ts = await superuser.fetchval("select id from teams where code = 'TS'")
    competition = await superuser.fetchval("select id from competitions where code = 'TR-SL'")
    for tenant in (tenants.tenant_a, tenants.tenant_b):
        await superuser.execute("update tenants set club_team_id = $1 where id = $2", ts, tenant)
        await superuser.execute(
            "insert into data_licenses (tenant_id, provider, competition_id)"
            " values ($1, 'test', $2)",
            tenant,
            competition,
        )
    return tenants


@pytest.fixture
async def match_id(superuser: asyncpg.Connection, club: Seeded) -> str:
    """SAM–TS, 2026/27 7. hafta: ev sahibi SAM, deplasman TS (kulüp)."""
    row = await superuser.fetchval(
        """
        select m.id from matches m join seasons s on s.id = m.season_id
        join teams h on h.id = m.home_team_id join teams a on a.id = m.away_team_id
        where s.code = '2026_27' and m.week = 7 and h.code = 'SAM' and a.code = 'TS'
        """
    )
    return str(row)


async def _headers(
    make_token: TokenFactory, superuser: asyncpg.Connection, tenant: uuid.UUID, role: str
) -> dict[str, str]:
    subject = f"{role}-{uuid.uuid4()}"
    await add_member(superuser, subject, tenant, role)
    return {"Authorization": f"Bearer {make_token(subject)}", "X-Kurgu-Tenant": str(tenant)}


@pytest.fixture
async def analyst(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "analyst")


@pytest.fixture
async def other(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_b, "analyst")


def _tag(**overrides: Any) -> dict[str, Any]:
    payload = {
        "sp_type": "corner",
        "team": "away",
        "outcome": "shot_on_target",
        "period": 1,
        "clock_s": 754.0,
        "first_contact": "attack",
        "side": "right",
    }
    return payload | overrides


def _upsert(tag_id: uuid.UUID, ts: dt.datetime = T0, **payload: Any) -> dict[str, Any]:
    return {
        "id": str(tag_id),
        "op": "upsert",
        "payload": _tag(**payload),
        "client_ts": ts.isoformat(),
    }


async def _open(client: Any, headers: dict[str, str], match: str, device: str = "dev-a") -> str:
    response = await client.post(
        "/api/v1/tagging-sessions", headers=headers, json={"match_id": match, "device_id": device}
    )
    assert response.status_code == 200, response.text
    session_id: str = response.json()["id"]
    return session_id


async def _sync(
    client: Any,
    headers: dict[str, str],
    session_id: str,
    changes: list[dict[str, Any]],
    device: str = "dev-a",
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/tagging-sessions/{session_id}/sync",
        headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
        json={"device_id": device, "changes": changes},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_devices_share_one_session_per_match(
    client: Any, analyst: dict[str, str], match_id: str
) -> None:
    first = await _open(client, analyst, match_id, "dev-a")
    second = await _open(client, analyst, match_id, "dev-b")
    assert first == second


async def test_twenty_offline_tags_sync_once(
    client: Any,
    analyst: dict[str, str],
    match_id: str,
    queue: FakeQueue,
    superuser: asyncpg.Connection,
) -> None:
    session_id = await _open(client, analyst, match_id)
    changes = [
        _upsert(uuid.uuid4(), T0 + dt.timedelta(seconds=i), clock_s=60.0 * i) for i in range(20)
    ]

    first = await _sync(client, analyst, session_id, changes)
    # Bağlantı koptu sanılıp aynı kuyruk yeniden gönderilir.
    again = await _sync(client, analyst, session_id, changes)

    assert len(first["accepted"]) == 20
    assert first["rejected"] == []
    assert first["server_seq"] == 20
    assert again["server_seq"] == 20
    assert len(again["accepted"]) == 20
    count = await superuser.fetchval(
        "select count(*) from live_tags where session_id = $1", uuid.UUID(session_id)
    )
    pieces = await superuser.fetchval(
        "select count(*) from set_pieces where id = any($1) and source = 'live_tag'",
        [uuid.UUID(c["id"]) for c in changes],
    )
    assert (count, pieces) == (20, 20)
    assert queue.jobs == [("refresh_metric_views_job",)]


async def test_set_piece_row_mirrors_tag(
    client: Any, analyst: dict[str, str], match_id: str, superuser: asyncpg.Connection
) -> None:
    session_id = await _open(client, analyst, match_id)
    tag_id = uuid.uuid4()
    await _sync(client, analyst, session_id, [_upsert(tag_id, outcome="goal")])

    row = await superuser.fetchrow(
        "select p.*, t.code from set_pieces p join teams t on t.id = p.team_id where p.id = $1",
        tag_id,
    )
    assert row is not None
    assert row["code"] == "TS"
    assert (row["sp_type"], row["outcome"], row["goal"], row["shots"]) == (
        "corner",
        "goal",
        True,
        1,
    )
    assert row["first_contact_team_id"] == row["team_id"]
    assert row["start_time_s"] == 754.0
    assert row["xg_total"] == 0


async def test_last_writer_wins_and_stale_is_rejected(
    client: Any, analyst: dict[str, str], match_id: str, superuser: asyncpg.Connection
) -> None:
    session_id = await _open(client, analyst, match_id)
    tag_id = uuid.uuid4()
    await _sync(client, analyst, session_id, [_upsert(tag_id, T0, outcome="cleared")])

    newer = await _sync(
        client,
        analyst,
        session_id,
        [_upsert(tag_id, T0 + dt.timedelta(seconds=5), outcome="goal")],
        device="dev-b",
    )
    stale = await _sync(
        client, analyst, session_id, [_upsert(tag_id, T0 + dt.timedelta(seconds=1))]
    )

    assert newer["accepted"] == [str(tag_id)]
    assert stale["rejected"] == [{"id": str(tag_id), "reason": "stale"}]
    outcome = await superuser.fetchval("select outcome from set_pieces where id = $1", tag_id)
    assert outcome == "goal"


async def test_delete_wins_and_pull_returns_tombstones(
    client: Any, analyst: dict[str, str], match_id: str, superuser: asyncpg.Connection
) -> None:
    session_id = await _open(client, analyst, match_id)
    keep, drop = uuid.uuid4(), uuid.uuid4()
    await _sync(client, analyst, session_id, [_upsert(keep), _upsert(drop)])
    deleted = await _sync(
        client,
        analyst,
        session_id,
        [{"id": str(drop), "op": "delete", "client_ts": T0.isoformat()}],
    )
    revive = await _sync(
        client, analyst, session_id, [_upsert(drop, T0 + dt.timedelta(hours=1))], device="dev-b"
    )

    assert deleted["server_seq"] == 3
    assert revive["rejected"] == [{"id": str(drop), "reason": "deleted"}]
    assert await superuser.fetchval("select count(*) from set_pieces where id = $1", drop) == 0

    pulled = await client.get(
        f"/api/v1/tagging-sessions/{session_id}/tags", headers=analyst, params={"since": 0}
    )
    assert pulled.status_code == 200
    body = pulled.json()
    assert body["server_seq"] == 3
    assert [(t["id"], t["deleted"]) for t in body["tags"]] == [
        (str(keep), False),
        (str(drop), True),
    ]


async def test_invalid_payload_and_foreign_routine_are_rejected(
    client: Any,
    analyst: dict[str, str],
    match_id: str,
    superuser: asyncpg.Connection,
    club: Seeded,
) -> None:
    session_id = await _open(client, analyst, match_id)
    routine = await superuser.fetchval(
        "insert into routines (tenant_id, name, sp_type, current_version)"
        " values ($1, 'Arka direk', 'corner', 1) returning id",
        club.tenant_a,
    )
    bad, home_routine, ok = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    result = await _sync(
        client,
        analyst,
        session_id,
        [
            {
                "id": str(bad),
                "op": "upsert",
                "payload": {"sp_type": "penalty"},
                "client_ts": T0.isoformat(),
            },
            _upsert(home_routine, team="home", routine_id=str(routine)),
            _upsert(ok, routine_id=str(routine)),
        ],
    )

    assert result["accepted"] == [str(ok)]
    assert {r["id"]: r["reason"] for r in result["rejected"]} == {
        str(bad): "invalid-payload",
        str(home_routine): "routine-not-own",
    }
    uses = await superuser.fetchval(
        "select uses from v_routine_stats where routine_id = $1", routine
    )
    assert uses == 1


async def test_sync_requires_idempotency_key(
    client: Any, analyst: dict[str, str], match_id: str
) -> None:
    session_id = await _open(client, analyst, match_id)
    response = await client.post(
        f"/api/v1/tagging-sessions/{session_id}/sync",
        headers=analyst,
        json={"device_id": "dev-a", "changes": []},
    )
    assert response.status_code == 400


async def test_viewer_cannot_tag(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    club: Seeded,
    match_id: str,
) -> None:
    viewer = await _headers(make_token, superuser, club.tenant_a, "viewer")
    response = await client.post(
        "/api/v1/tagging-sessions", headers=viewer, json={"match_id": match_id, "device_id": "x"}
    )
    assert response.status_code == 403
    # Maçın duran topları okuma iznidir (hazırlık sayfasındaki geri bildirim paneli, A-63).
    pieces = await client.get(f"/api/v1/fixtures/{match_id}/set-pieces", headers=viewer)
    assert pieces.status_code == 200


async def test_sessions_and_tags_are_tenant_isolated(
    client: Any, analyst: dict[str, str], other: dict[str, str], match_id: str
) -> None:
    mine = await _open(client, analyst, match_id)
    await _sync(client, analyst, mine, [_upsert(uuid.uuid4())])
    theirs = await _open(client, other, match_id)

    assert theirs != mine
    hidden = await client.get(f"/api/v1/tagging-sessions/{mine}/tags", headers=other)
    assert hidden.status_code == 404
    pieces = await client.get(f"/api/v1/fixtures/{match_id}/set-pieces", headers=other)
    assert all(p["source"] != "live_tag" for p in pieces.json())
    own = await client.get(f"/api/v1/fixtures/{match_id}/set-pieces", headers=analyst)
    assert [p["source"] for p in own.json()] == ["live_tag"]
