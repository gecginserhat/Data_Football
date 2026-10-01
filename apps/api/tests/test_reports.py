"""PDF raporlar (Faz 6, ADR-0012): kuyruk, worker işi, gerçek Chromium ile PDF, imzalı indirme,
izinler ve kiracı izolasyonu.

Kabul (SPEC §19 Faz 6): rakip raporu ve maç planı PDF'i 15 sn içinde üretilir.
"""

import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_api.config import get_settings
from kurgu_api.core.db import get_sessionmaker, set_request_context
from kurgu_api.reports import data
from kurgu_api.reports.jobs import run_report
from kurgu_api.reports.pdf import page_count

from .conftest import Seeded, TokenFactory
from .test_live import FakeQueue, queue
from .test_prep import _decide, _headers, _prep, _rec, club, fixture_id, seeded

__all__ = ["club", "fixture_id", "queue", "seeded"]

BASE = "http://test"
CHROMIUM = "/opt/pw-browsers/chromium"
CORNERS = "Korner savunması haftanın öncelikli çalışması"


@pytest.fixture(autouse=True)
def local_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "objects"
    monkeypatch.setenv("KURGU_STORAGE_BACKEND", "local")
    monkeypatch.setenv("KURGU_STORAGE_DIR", str(root))
    monkeypatch.setenv("KURGU_PUBLIC_API_URL", BASE)
    monkeypatch.setenv("KURGU_PUBLIC_WEB_URL", "https://kurgu.test")
    if not os.environ.get("KURGU_CHROMIUM_PATH") and Path(CHROMIUM).exists():
        monkeypatch.setenv("KURGU_CHROMIUM_PATH", CHROMIUM)
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture
async def coach(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "sp_coach")


@pytest.fixture
async def viewer(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "viewer")


@pytest.fixture
async def other(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_b, "head_coach")


async def _request(
    client: Any, headers: dict[str, str], fixture: str, kind: str = "opponent"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/reports", headers=headers, json={"type": kind, "fixture_id": fixture}
    )
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


async def _get(client: Any, headers: dict[str, str], report: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/reports/{report}", headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _download(client: Any, url: str) -> bytes:
    assert url.startswith(BASE), url
    response = await client.get(url[len(BASE) :])
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    content: bytes = response.content
    return content


async def test_opponent_report_pdf_within_15_seconds(
    client: Any, coach: dict[str, str], fixture_id: str, club: Seeded, queue: FakeQueue
) -> None:
    created = await _request(client, coach, fixture_id)
    assert created["status"] == "queued"
    assert created["progress"] == 0
    assert created["download_url"] is None
    assert created["fixture"]["home_code"] == "SAM"
    assert created["fixture"]["away_code"] == "TS"
    assert queue.jobs == [("generate_report_job", created["id"], str(club.tenant_a))]

    started = time.monotonic()
    assert await run_report(created["id"], str(club.tenant_a)) == "ready"
    assert time.monotonic() - started < 15

    report = await _get(client, coach, created["id"])
    assert report["status"] == "ready"
    assert report["progress"] == 100
    assert report["error"] is None
    assert 2 <= report["pages"] <= 4
    assert report["duration_ms"] < 15_000
    assert report["data_as_of"]["season"] == "2026/27"
    assert report["data_as_of"]["profile_season"] == "2025/26"
    assert report["data_as_of"]["sources"]
    pdf = await _download(client, report["download_url"])
    assert pdf.startswith(b"%PDF")
    assert len(pdf) == report["size_bytes"]
    assert page_count(pdf) == report["pages"]


async def test_match_plan_report_with_accepted_recommendation(
    client: Any, coach: dict[str, str], fixture_id: str, club: Seeded, queue: FakeQueue
) -> None:
    prep = await _prep(client, coach, fixture_id)
    corners = _rec(prep, CORNERS)
    decided = await _decide(client, coach, fixture_id, corners["id"], "accepted")
    assert decided.status_code == 200, decided.text

    async with get_sessionmaker()() as session, session.begin():
        await set_request_context(session, user_id=None, tenant_id=club.tenant_a)
        document = await data.match_plan_report(session, uuid.UUID(fixture_id), club.tenant_a, None)
    assert [r.title for r in document.recommendations] == [CORNERS]
    assert document.fixture.opponent.code == "SAM"

    created = await _request(client, coach, fixture_id, "match_plan")
    started = time.monotonic()
    assert await run_report(created["id"], str(club.tenant_a)) == "ready"
    assert time.monotonic() - started < 15
    report = await _get(client, coach, created["id"])
    assert report["type"] == "match_plan"
    assert report["pages"] >= 1
    assert (await _download(client, report["download_url"])).startswith(b"%PDF")


async def test_opponent_report_data(fixture_id: str, club: Seeded) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await set_request_context(session, user_id=None, tenant_id=club.tenant_a)
        document = await data.opponent_report(session, uuid.UUID(fixture_id), club.tenant_a, None)
    assert document.meta.club.code == "TS"
    assert document.meta.season == "2026/27"
    assert document.meta.profile_season == "2025/26"
    assert document.fixture.is_home is False
    rows = {r.metric: r for r in document.metrics}
    assert rows["fouls_committed_per_match"].rank == 4
    assert rows["fouls_committed_per_match"].club_value is not None
    assert {r.title for r in document.recommendations} >= {CORNERS}
    assert all(r.status != "rejected" for r in document.recommendations)
    assert document.briefing is None


async def test_failed_render_is_recorded(
    client: Any, coach: dict[str, str], fixture_id: str, club: Seeded, queue: FakeQueue
) -> None:
    async def broken(html: str, footer: str) -> bytes:
        raise RuntimeError("chromium crashed")

    created = await _request(client, coach, fixture_id)
    assert await run_report(created["id"], str(club.tenant_a), renderer=broken) == "failed"
    report = await _get(client, coach, created["id"])
    assert report["status"] == "failed"
    assert report["error"] == "chromium crashed"
    assert report["download_url"] is None
    # Tekrar çalıştırma işi yinelemez.
    assert await run_report(created["id"], str(club.tenant_a), renderer=broken) == "failed"


async def test_viewer_can_request_and_list(
    client: Any, viewer: dict[str, str], fixture_id: str, queue: FakeQueue
) -> None:
    created = await _request(client, viewer, fixture_id)
    listed = await client.get(f"/api/v1/reports?fixture_id={fixture_id}", headers=viewer)
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [created["id"]]


async def test_reports_are_tenant_isolated(
    client: Any,
    coach: dict[str, str],
    other: dict[str, str],
    fixture_id: str,
    club: Seeded,
    queue: FakeQueue,
) -> None:
    created = await _request(client, coach, fixture_id)
    assert (await client.get(f"/api/v1/reports/{created['id']}", headers=other)).status_code == 404
    assert (await client.get("/api/v1/reports", headers=other)).json() == []
    # Worker yanlış kiracı bağlamıyla raporu göremez.
    assert await run_report(created["id"], str(club.tenant_b)) == "missing"


async def test_validation_and_auth(
    client: Any, coach: dict[str, str], superuser: asyncpg.Connection, queue: FakeQueue
) -> None:
    not_club = await superuser.fetchval(
        """
        select m.id from matches m join teams h on h.id = m.home_team_id
        join teams a on a.id = m.away_team_id
        where h.code <> 'TS' and a.code <> 'TS' limit 1
        """
    )
    response = await client.post(
        "/api/v1/reports", headers=coach, json={"type": "opponent", "fixture_id": str(not_club)}
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("not-club-fixture")
    bad = await client.post(
        "/api/v1/reports", headers=coach, json={"type": "player", "fixture_id": str(not_club)}
    )
    assert bad.status_code == 422
    unauth = await client.post(
        "/api/v1/reports", json={"type": "opponent", "fixture_id": str(not_club)}
    )
    assert unauth.status_code == 401
    assert queue.jobs == []
