"""Yükleme çerçevesi (Faz 1.5): durum makinesi, ham yük idempotentliği, karantina, API tetikleme."""

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_analytics.canonical.model import CanonicalMatch, Match
from kurgu_analytics.ingestion.base import RawPayload
from kurgu_analytics.ingestion.statsbomb import events_to_actions, match_from_json
from kurgu_analytics.testing.statsbomb import SBEvents, match_json
from kurgu_api.ingestion.pipeline import run_ingestion
from kurgu_api.ingestion.router import get_queue
from kurgu_api.ingestion.runs import (
    InvalidTransitionError,
    check_transition,
    create_run,
)
from kurgu_api.ingestion.storage import LocalObjectStore
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .conftest import Seeded, TokenFactory, _url, add_member


class FakeProvider:
    """Sentetik maçlar üretir. `broken` maçlar kalite kontrolünden geçmez (az aksiyon)."""

    name = "fake"

    def __init__(self, match_ids: list[int], broken: set[int] | None = None) -> None:
        self.match_ids = match_ids
        self.broken = broken or set()

    def list_matches(self, params: dict[str, Any]) -> list[Match]:
        return [
            match_from_json(match_json(mid, home=mid * 10, away=mid * 10 + 1))
            for mid in self.match_ids
        ]

    def fetch_events(self, match: Match) -> RawPayload:
        ev = SBEvents(home=int(match.home.provider_id), away=int(match.away.provider_id))
        count = 50 if int(match.provider_id) in self.broken else 400
        for i in range(count):
            ev.pass_(i * 2.0, (40 + i % 30, 40), (50 + i % 30, 42), player=i % 11 + 1)
        ev.shot(900, (110, 40), outcome="Goal", xg=0.5)
        ev.pass_(950, (120, 80), (114, 36), pass_type="Corner", height="High Pass")
        ev.shot(951.5, (114, 36), outcome="Goal", xg=0.4, body_part="Head", player=9)
        return RawPayload(self.name, "events", match.provider_id, json.dumps(ev.events).encode())

    def to_canonical(self, match: Match, raw: RawPayload) -> CanonicalMatch:
        events = json.loads(raw.content)
        return CanonicalMatch(match=match, players=(), actions=tuple(events_to_actions(events)))


@pytest.fixture
async def worker_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_url("kurgu_worker"))
    yield engine
    await engine.dispose()


def test_state_machine() -> None:
    check_transition("pending", "running")
    check_transition("running", "quarantined")
    check_transition("quarantined", "pending")
    for current, target in (("pending", "succeeded"), ("succeeded", "running")):
        with pytest.raises(InvalidTransitionError):
            check_transition(current, target)  # type: ignore[arg-type]


async def _new_run(engine: AsyncEngine) -> uuid.UUID:
    async with engine.begin() as conn:
        return await create_run(conn, tenant_id=None, provider="fake", kind="events", params={})


async def test_pipeline_loads_and_is_idempotent(
    worker_engine: AsyncEngine, superuser: asyncpg.Connection, tmp_path: Path
) -> None:
    store = LocalObjectStore(tmp_path)
    ids = [uuid.uuid4().int % 10_000 + 1000]
    provider = FakeProvider(ids)

    run = await _new_run(worker_engine)
    stats = await run_ingestion(
        worker_engine, store, run, tenant_id=None, provider=provider, params={}
    )
    assert stats == {"matches": 1, "loaded": 1, "skipped": 0, "quarantined": 0}
    row = await superuser.fetchrow("select status, stats from ingestion_runs where id = $1", run)
    assert row["status"] == "succeeded"

    match_id = await superuser.fetchval(
        "select kurgu_id from provider_id_map where entity_type = 'match' and provider = 'fake'"
        " and provider_id = $1",
        str(ids[0]),
    )
    events = "select count(*) from events where match_id = $1"
    assert await superuser.fetchval(events, match_id) == 403
    sp = await superuser.fetchrow(
        "select id, sp_type, target_zone, goal, phase_of_goal, xg_total, outcome, source, tenant_id"
        " from set_pieces where match_id = $1",
        match_id,
    )
    assert (sp["sp_type"], sp["target_zone"], sp["outcome"], sp["source"]) == (
        "corner",
        "FP",  # StatsBomb (114, 36) → kanonik (99,5, 37,66): arka direk
        "goal",
        "provider",
    )
    assert (sp["goal"], sp["phase_of_goal"], sp["tenant_id"]) == (True, 1, None)
    assert sp["xg_total"] == pytest.approx(0.4)
    linked = "select count(*) from events where set_piece_id = $1"
    assert await superuser.fetchval(linked, sp["id"]) == 2
    raw = await superuser.fetchrow(
        "select storage_key, tenant_id from raw_payloads where id ="
        " (select raw_ref from events where match_id = $1 limit 1)",
        match_id,
    )
    assert raw["tenant_id"] is None
    assert (tmp_path / raw["storage_key"]).is_file()

    rerun = await _new_run(worker_engine)
    stats = await run_ingestion(
        worker_engine, store, rerun, tenant_id=None, provider=provider, params={}
    )
    assert stats["skipped"] == 1
    assert await superuser.fetchval(events, match_id) == 403
    set_pieces = "select count(*) from set_pieces where match_id = $1"
    assert await superuser.fetchval(set_pieces, match_id) == 1


async def test_quality_failure_quarantines_match(
    worker_engine: AsyncEngine, superuser: asyncpg.Connection, tmp_path: Path
) -> None:
    good, bad = (uuid.uuid4().int % 10_000 + 20_000 for _ in range(2))
    provider = FakeProvider([good, bad], broken={bad})
    run = await _new_run(worker_engine)

    stats = await run_ingestion(
        worker_engine, LocalObjectStore(tmp_path), run, tenant_id=None, provider=provider, params={}
    )

    assert stats["loaded"] == 1
    assert stats["quarantined"] == 1
    row = await superuser.fetchrow(
        "select status, quality_report from ingestion_runs where id = $1", run
    )
    assert row["status"] == "quarantined"
    report = json.loads(row["quality_report"])
    assert report[str(bad)]["critical"] == 1
    assert (
        await superuser.fetchval(
            "select count(*) from provider_id_map where provider = 'fake' and provider_id = $1",
            str(bad),
        )
        == 0
    )


async def test_failure_marks_run_failed(
    worker_engine: AsyncEngine, superuser: asyncpg.Connection, tmp_path: Path
) -> None:
    class Exploding(FakeProvider):
        def fetch_events(self, match: Match) -> RawPayload:
            raise RuntimeError("upstream down")

    run = await _new_run(worker_engine)
    with pytest.raises(RuntimeError):
        await run_ingestion(
            worker_engine,
            LocalObjectStore(tmp_path),
            run,
            tenant_id=None,
            provider=Exploding([1]),
            params={},
        )
    row = await superuser.fetchrow("select status, error from ingestion_runs where id = $1", run)
    assert (row["status"], row["error"]) == ("failed", "upstream down")


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[Any, ...]] = []

    async def enqueue_job(self, name: str, *args: Any) -> None:
        self.jobs.append((name, *args))


async def test_api_creates_run_and_enqueues(
    app: Any, client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    queue = FakeQueue()
    app.dependency_overrides[get_queue] = lambda: queue
    admin = f"admin-{uuid.uuid4()}"
    await add_member(superuser, admin, tenants.tenant_a, "admin")
    headers = {"Authorization": f"Bearer {make_token(admin)}"}

    response = await client.post(
        "/api/v1/ingestion-runs",
        json={"provider": "statsbomb_open", "params": {"competition_id": 43, "season_id": 106}},
        headers=headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert queue.jobs == [
        (
            "run_ingestion_job",
            body["id"],
            str(tenants.tenant_a),
            "statsbomb_open",
            {"competition_id": 43, "season_id": 106},
        )
    ]
    own = await client.get(f"/api/v1/ingestion-runs/{body['id']}", headers=headers)
    assert own.status_code == 200

    other = f"admin-{uuid.uuid4()}"
    await add_member(superuser, other, tenants.tenant_b, "admin")
    foreign = await client.get(
        f"/api/v1/ingestion-runs/{body['id']}",
        headers={"Authorization": f"Bearer {make_token(other)}"},
    )
    assert foreign.status_code == 404
    listing = await client.get(
        "/api/v1/ingestion-runs", headers={"Authorization": f"Bearer {make_token(other)}"}
    )
    assert body["id"] not in {r["id"] for r in listing.json()}


async def test_api_requires_admin(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    analyst = f"analyst-{uuid.uuid4()}"
    await add_member(superuser, analyst, tenants.tenant_a, "analyst")
    response = await client.post(
        "/api/v1/ingestion-runs",
        json={"provider": "statsbomb_open", "params": {"competition_id": 43, "season_id": 106}},
        headers={"Authorization": f"Bearer {make_token(analyst)}"},
    )
    assert response.status_code == 403
