"""Lig ve takım uçları: tohum değerleriyle altın testler, lisans izolasyonu, sayfalama, ETag.

Altın değerler doğrudan `seed/super_lig.json` dosyasından okunur (Faz 1.4).
"""

import json
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_api.dev_identities import DEMO_TENANT_ID, DEV_USERS, SECOND_TENANT_ID
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


@pytest.fixture
async def clean(make_token: TokenFactory, superuser: asyncpg.Connection) -> dict[str, str]:
    """İçe aktarımı olmayan ikinci geliştirme kiracısı: yalnızca paylaşılan tohum verisini görür.

    Demo kiracısının içe aktarım testleri bıraktığı satırlar (A-36) altın değerleri bozmasın diye.
    """
    subject = f"analyst-{uuid.uuid4()}"
    await add_member(superuser, subject, SECOND_TENANT_ID, "analyst")
    return {
        "Authorization": f"Bearer {make_token(subject)}",
        "X-Kurgu-Tenant": str(SECOND_TENANT_ID),
    }


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


async def test_team_metrics_match_seed(client: Any, seeded: None, clean: dict[str, str]) -> None:
    season = await _season_id(client, clean, "2025_26")

    response = await client.get(f"/api/v1/seasons/{season}/team-metrics", headers=clean)

    assert response.status_code == 200
    items = {i["team"]["code"]: i for i in response.json()["items"]}
    assert len(items) == 18
    codes = {t["id"]: t["code"] for t in SEED["teams"]}
    for stats in SEED["seasons"]["2025_26"]["team_stats"]:
        inputs = items[codes[stats["team_id"]]]["inputs"]
        for metric, value in stats.items():
            if metric != "team_id":
                assert inputs[metric] == pytest.approx(value), (stats["team_id"], metric)
    # SPEC §19 Faz 2 altın değerleri.
    ts, goz = items["TS"]["values"], items["GÖZ"]["values"]
    assert (ts["set_piece_goals"]["value"], ts["set_piece_goals"]["rank"]) == (15, 1)
    assert goz["set_piece_xg"]["value"] == pytest.approx(15.4)
    assert goz["set_piece_xg"]["rank"] == 1
    assert ts["set_piece_goals"]["source"] == SEED_SOURCE
    assert ts["set_piece_goals"]["low_sample"] is False
    share = ts["set_piece_goal_share"]
    assert share["value"] == pytest.approx(15 / items["TS"]["inputs"]["goals"])
    assert share["shrunk_low"] <= share["shrunk"] <= share["shrunk_high"]
    assert ts["aerial_win_pct"]["indirect"] is True
    assert ts["goals_per_100_corners"]["approx"] is True
    assert "set_piece_goals_against" not in ts  # kamuya açık tohumda yok
    assert items["TS"]["as_of_week"] is None


async def test_current_season_metrics_carry_week(
    client: Any, seeded: None, clean: dict[str, str]
) -> None:
    season = await _season_id(client, clean, "2026_27")
    response = await client.get(f"/api/v1/seasons/{season}/team-metrics", headers=clean)
    items = {i["team"]["code"]: i for i in response.json()["items"]}
    amd = next(r for r in SEED["seasons"]["2026_27"]["set_piece_to_date"] if r["team_id"] == "amd")
    row = next(
        r for r in SEED["seasons"]["2026_27"]["standings_after_week_6"] if r["team_id"] == "amd"
    )
    assert items["AMD"]["as_of_week"] == 6
    assert items["AMD"]["inputs"] == {
        "set_piece_goals": amd["set_piece_goals"],
        "set_piece_xg": pytest.approx(amd["set_piece_xg"]),
        "matches": row["played"],
        "goals": row["gf"],
    }
    values = items["AMD"]["values"]
    assert values["set_piece_goal_share"]["value"] == pytest.approx(
        amd["set_piece_goals"] / row["gf"]
    )
    assert values["set_piece_goals_per_match"]["low_sample"] is False  # 6 maç ≥ 5


async def test_benchmarks(client: Any, seeded: None, clean: dict[str, str]) -> None:
    season = await _season_id(client, clean, "2025_26")
    response = await client.get(f"/api/v1/seasons/{season}/benchmarks", headers=clean)
    assert response.status_code == 200
    body = response.json()
    totals = body["totals"]
    assert (totals["set_piece_goals"], totals["goals"], totals["matches"]) == (166, 812, 306)
    assert round(totals["set_piece_goal_share"], 3) == 0.204
    assert round(totals["set_piece_goals_per_match"], 3) == 0.542
    goals = body["metrics"]["set_piece_goals"]
    assert (goals["max"], goals["teams"]) == (15, 18)
    assert goals["mean"] == pytest.approx(166 / 18)
    refs = {(r["competition"]["code"], r["metric"]): r["value"] for r in body["references"]}
    assert refs[("TR-SL", "set_piece_goal_share")] == pytest.approx(0.2044)
    pl = SEED["benchmarks"]["premier_league_2025_26"]
    assert (
        next(v for (c, m), v in refs.items() if c != "TR-SL" and m == "set_piece_goals")
        == (pl["set_piece_goals"])
    )


async def test_team_profile(client: Any, make_token: TokenFactory, seeded: None) -> None:
    headers = _auth(make_token)
    season = await _season_id(client, headers, "2026_27")
    standings = (await client.get(f"/api/v1/seasons/{season}/standings", headers=headers)).json()
    gs = next(r for r in standings["rows"] if r["team"]["code"] == "GS")

    response = await client.get(
        f"/api/v1/teams/{gs['team']['id']}/profile", params={"season": season}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["team"]["name"] == "Galatasaray"
    assert body["standing"] == gs
    assert body["standing_week"] == 6
    gs_seed = next(
        r for r in SEED["seasons"]["2026_27"]["set_piece_to_date"] if r["team_id"] == "gs"
    )
    assert body["values"]["set_piece_goals"]["value"] == gs_seed["set_piece_goals"]
    assert body["as_of_week"] == 6
    assert body["club"]["code"] == "TS"  # demo kiracısının kulübü
    assert "set_piece_goals" in body["club_values"]
    assert body["benchmarks"]["set_piece_goals"]["teams"] == 18

    results = [
        r for r in SEED["seasons"]["2026_27"]["results_weeks_1_6"] if "gs" in (r["home"], r["away"])
    ]
    results.sort(key=lambda r: -r["week"])
    expected = []
    for r in results[:5]:
        home = r["home"] == "gs"
        gf, ga = (r["home_goals"], r["away_goals"]) if home else (r["away_goals"], r["home_goals"])
        expected.append((r["week"], home, gf, ga, "W" if gf > ga else "D" if gf == ga else "L"))
    got = [
        (f["week"], f["home"], f["goals_for"], f["goals_against"], f["result"])
        for f in body["form"]
    ]
    assert got == expected


async def test_pagination_walks_all_teams(client: Any, seeded: None, clean: dict[str, str]) -> None:
    season = await _season_id(client, clean, "2025_26")
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"limit": 5} | ({"cursor": cursor} if cursor else {})
        page = (
            await client.get(f"/api/v1/seasons/{season}/team-metrics", params=params, headers=clean)
        ).json()
        seen += [i["team"]["code"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 18
    assert len(set(seen)) == 18


async def test_fixtures_upcoming_for_team(client: Any, seeded: None, clean: dict[str, str]) -> None:
    season = await _season_id(client, clean, "2026_27")
    teams = (await client.get(f"/api/v1/seasons/{season}/standings", headers=clean)).json()
    ts = next(r["team"]["id"] for r in teams["rows"] if r["team"]["code"] == "TS")
    response = await client.get(
        "/api/v1/fixtures",
        params={"team": ts, "season": season, "status": "scheduled", "limit": 3},
        headers=clean,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    expected = [
        f
        for f in SEED["seasons"]["2026_27"]["fixtures_weeks_7_12"]
        if "ts" in (f["home"], f["away"])
    ]
    assert [i["week"] for i in items] == [f["week"] for f in expected][:3]
    assert all(i["status"] == "scheduled" for i in items)
    assert response.json()["next_cursor"] is not None

    one = await client.get(f"/api/v1/fixtures/{items[0]['id']}", headers=clean)
    assert one.status_code == 200
    assert one.json() == items[0]
    missing = await client.get(f"/api/v1/fixtures/{uuid.uuid4()}", headers=clean)
    assert missing.status_code == 404


async def test_set_pieces_empty_without_event_data(
    client: Any, seeded: None, clean: dict[str, str]
) -> None:
    season = await _season_id(client, clean, "2025_26")
    teams = (await client.get(f"/api/v1/seasons/{season}/team-metrics", headers=clean)).json()
    ts = next(i["team"]["id"] for i in teams["items"] if i["team"]["code"] == "TS")
    response = await client.get(
        f"/api/v1/teams/{ts}/set-pieces", params={"season": season}, headers=clean
    )
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}
    bad = await client.get(
        f"/api/v1/teams/{ts}/set-pieces",
        params={"season": season, "type": "penalty"},
        headers=clean,
    )
    assert bad.status_code == 422  # penaltı duran top değildir


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
