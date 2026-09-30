"""Lig ve takım uçları: tohum değerleriyle altın testler, lisans izolasyonu, sayfalama, ETag.

Altın değerler doğrudan `seed/super_lig.json` dosyasından okunur (Faz 1.4).
"""

import json
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_api.dev_identities import DEMO_TENANT_ID, DEV_USERS
from kurgu_api.league.seed import run_seed

from .conftest import Seeded, TokenFactory, add_member

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
SEED = json.loads((SEED_DIR / "super_lig.json").read_text(encoding="utf-8"))
SEED_SOURCE = "seed:super_lig.json"
SP_COACH = next(str(sub) for sub, _, role in DEV_USERS if role.value == "sp_coach")


@pytest.fixture
async def seeded() -> None:
    await run_seed(seed_dir=SEED_DIR)


def _auth(make_token: TokenFactory, subject: str = SP_COACH) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(subject)}", "X-Kurgu-Tenant": str(DEMO_TENANT_ID)}


async def _season_id(client: Any, headers: dict[str, str], code: str) -> str:
    response = await client.get("/api/v1/seasons", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    return str(
        next(s["id"] for s in items if s["code"] == code and s["competition"]["code"] == "TR-SL")
    )


async def test_standings_match_seed(client: Any, make_token: TokenFactory, seeded: None) -> None:
    headers = _auth(make_token)
    season = await _season_id(client, headers, "2026_27")

    response = await client.get(f"/api/v1/seasons/{season}/standings", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["week"] == 6
    assert body["source"] == "seed:super_lig.json"
    expected = SEED["seasons"]["2026_27"]["standings_after_week_6"]
    ids = {t["code"]: t["id"] for t in SEED["teams"]}
    got = [
        {
            "pos": r["position"],
            "team_id": ids[r["team"]["code"]],
            **{k: r[k] for k in ("played", "won", "drawn", "lost", "gf", "ga", "pts")},
        }
        for r in body["rows"]
    ]
    assert got == expected
    assert (body["rows"][0]["team"]["code"], body["rows"][0]["pts"]) == ("AMD", 13)


async def test_team_metrics_match_seed(client: Any, make_token: TokenFactory, seeded: None) -> None:
    headers = _auth(make_token)
    season = await _season_id(client, headers, "2025_26")

    response = await client.get(f"/api/v1/seasons/{season}/team-metrics", headers=headers)

    assert response.status_code == 200
    items = {i["team"]["code"]: i for i in response.json()["items"] if i["source"] == SEED_SOURCE}
    assert len(items) == 18
    codes = {t["id"]: t["code"] for t in SEED["teams"]}
    for stats in SEED["seasons"]["2025_26"]["team_stats"]:
        metrics = items[codes[stats["team_id"]]]["metrics"]
        for metric, value in stats.items():
            if metric != "team_id":
                assert metrics[metric] == pytest.approx(value), (stats["team_id"], metric)
    assert items["TS"]["metrics"]["set_piece_goals"] == 15
    assert items["GÖZ"]["metrics"]["set_piece_xg"] == pytest.approx(15.4)
    assert items["TS"]["as_of_week"] is None


async def test_current_season_metrics_carry_week(
    client: Any, make_token: TokenFactory, seeded: None
) -> None:
    headers = _auth(make_token)
    season = await _season_id(client, headers, "2026_27")
    response = await client.get(f"/api/v1/seasons/{season}/team-metrics", headers=headers)
    items = {i["team"]["code"]: i for i in response.json()["items"]}
    amd = next(r for r in SEED["seasons"]["2026_27"]["set_piece_to_date"] if r["team_id"] == "amd")
    assert items["AMD"]["as_of_week"] == 6
    assert items["AMD"]["metrics"] == {
        "set_piece_goals": amd["set_piece_goals"],
        "set_piece_xg": pytest.approx(amd["set_piece_xg"]),
    }


async def test_team_profile(client: Any, make_token: TokenFactory, seeded: None) -> None:
    headers = _auth(make_token)
    season = await _season_id(client, headers, "2026_27")
    standings = (await client.get(f"/api/v1/seasons/{season}/standings", headers=headers)).json()
    ts = next(r for r in standings["rows"] if r["team"]["code"] == "TS")

    response = await client.get(
        f"/api/v1/teams/{ts['team']['id']}/profile", params={"season": season}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["team"]["name"] == "Trabzonspor"
    assert body["standing"] == ts
    assert body["standing_week"] == 6
    ts_seed = next(
        r for r in SEED["seasons"]["2026_27"]["set_piece_to_date"] if r["team_id"] == "ts"
    )
    assert body["metrics"]["set_piece_goals"] == ts_seed["set_piece_goals"]
    assert body["as_of_week"] == 6


async def test_pagination_walks_all_teams(
    client: Any, make_token: TokenFactory, seeded: None
) -> None:
    headers = _auth(make_token)
    season = await _season_id(client, headers, "2025_26")
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"limit": 5} | ({"cursor": cursor} if cursor else {})
        page = (
            await client.get(
                f"/api/v1/seasons/{season}/team-metrics", params=params, headers=headers
            )
        ).json()
        # Kiracının içe aktardığı değerler ayrı kaynak olarak gelir (test_imports).
        seen += [i["team"]["code"] for i in page["items"] if i["source"] == SEED_SOURCE]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 18
    assert len(set(seen)) == 18


async def test_bad_cursor_is_problem(client: Any, make_token: TokenFactory, seeded: None) -> None:
    headers = _auth(make_token)
    response = await client.get("/api/v1/seasons", params={"cursor": "!!"}, headers=headers)
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_etag_returns_304(client: Any, make_token: TokenFactory, seeded: None) -> None:
    headers = _auth(make_token)
    season = await _season_id(client, headers, "2026_27")
    url = f"/api/v1/seasons/{season}/standings"
    first = await client.get(url, headers=headers)
    etag = first.headers["etag"]
    second = await client.get(url, headers=headers | {"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""


async def test_unlicensed_tenant_sees_nothing(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    tenants: Seeded,
    seeded: None,
) -> None:
    licensed = await _season_id(client, _auth(make_token), "2026_27")
    subject = f"analyst-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, "analyst")
    headers = {"Authorization": f"Bearer {make_token(subject)}"}

    listing = await client.get("/api/v1/seasons", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    direct = await client.get(f"/api/v1/seasons/{licensed}/standings", headers=headers)
    assert direct.status_code == 404


async def test_player_role_cannot_read_league(
    client: Any, make_token: TokenFactory, seeded: None
) -> None:
    player = next(str(sub) for sub, _, role in DEV_USERS if role.value == "player")
    response = await client.get("/api/v1/seasons", headers=_auth(make_token, player))
    assert response.status_code == 403
