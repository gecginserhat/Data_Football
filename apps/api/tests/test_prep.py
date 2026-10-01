"""Maç hazırlığı uçları (Faz 4, ADR-0009): öneriler, kararlar, MD planı, kural setleri.

Kabul testi (SPEC §19 Faz 4): kulüp TS, 2026/27 7. hafta Samsunspor deplasmanı.
"""

import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_api.league.seed import run_seed

from .conftest import Seeded, TokenFactory, add_member

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
FOULS = "Ceza sahası çevresinde faul kazanın"
CORNERS = "Korner savunması haftanın öncelikli çalışması"


@pytest.fixture
async def seeded() -> None:
    await run_seed(seed_dir=SEED_DIR)


@pytest.fixture
async def club(superuser: asyncpg.Connection, tenants: Seeded, seeded: None) -> Seeded:
    """Her iki test kiracısının kulübü TS; Süper Lig lisanslı, içe aktarımı ve kararı yok."""
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
async def fixture_id(superuser: asyncpg.Connection, seeded: None) -> str:
    row = await superuser.fetchval(
        """
        select m.id from matches m
        join seasons s on s.id = m.season_id
        join teams h on h.id = m.home_team_id
        join teams a on a.id = m.away_team_id
        where s.code = '2026_27' and m.week = 7 and h.code = 'SAM' and a.code = 'TS'
        """
    )
    assert row is not None
    return str(row)


async def _headers(
    make_token: TokenFactory, superuser: asyncpg.Connection, tenant: uuid.UUID, role: str
) -> dict[str, str]:
    subject = f"{role}-{uuid.uuid4()}"
    await add_member(superuser, subject, tenant, role)
    return {"Authorization": f"Bearer {make_token(subject)}", "X-Kurgu-Tenant": str(tenant)}


@pytest.fixture
async def coach(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "sp_coach")


@pytest.fixture
async def head(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "head_coach")


@pytest.fixture
async def viewer(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "viewer")


@pytest.fixture
async def other(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_b, "head_coach")


async def _prep(client: Any, headers: dict[str, str], fixture: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/fixtures/{fixture}/prep", headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _rec(prep: dict[str, Any], title: str) -> dict[str, Any]:
    return next(r for r in prep["recommendations"] if r["title"] == title)


async def _decide(
    client: Any, headers: dict[str, str], fixture: str, rec: str, decision: str, **extra: Any
) -> Any:
    return await client.post(
        f"/api/v1/recommendations/{rec}/decision",
        headers=headers,
        json={"fixture_id": fixture, "decision": decision, **extra},
    )


async def test_acceptance_samsunspor_week_7(
    client: Any, coach: dict[str, str], fixture_id: str
) -> None:
    prep = await _prep(client, coach, fixture_id)

    assert prep["fixture"]["opponent"]["code"] == "SAM"
    assert prep["fixture"]["is_home"] is False
    assert prep["fixture"]["week"] == 7
    assert prep["rule_set"] == {"version": 0, "label": "1.0.0", "is_default": True}
    titles = [r["title"] for r in prep["recommendations"]]
    assert FOULS in titles
    assert CORNERS in titles
    corners = _rec(prep, CORNERS)
    assert corners["area"] == "defense"
    assert corners["confidence"] == "high"
    assert corners["status"] == "suggested"
    assert corners["active"] is True
    assert corners["template"] is not None
    evidence = {e["metric"]: e for e in corners["evidence"]}
    assert any(e["rank"] == 2 and e["subject"] == "opponent" for e in evidence.values())
    fouls = _rec(prep, FOULS)
    assert any(e["rank"] == 4 for e in fouls["evidence"])
    assert "4." in fouls["why"]
    assert prep["plan"] is None
    assert prep["matchup"]


async def test_recommendation_ids_are_stable(
    client: Any, coach: dict[str, str], fixture_id: str
) -> None:
    first = await _prep(client, coach, fixture_id)
    second = await _prep(client, coach, fixture_id)
    assert [r["id"] for r in first["recommendations"]] == [
        r["id"] for r in second["recommendations"]
    ]


async def test_accept_creates_plan_and_item(
    client: Any, coach: dict[str, str], fixture_id: str, superuser: asyncpg.Connection
) -> None:
    rec = _rec(await _prep(client, coach, fixture_id), CORNERS)

    response = await _decide(client, coach, fixture_id, rec["id"], "accepted")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"
    assert response.json()["decided_by"] is not None
    prep = await _prep(client, coach, fixture_id)
    plan = prep["plan"]
    assert plan["template"] == "standard"
    assert [d["md_code"] for d in plan["days"]] == ["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"]
    # 2026-10-10 13:00Z = İstanbul'da 10 Ekim; MD-4 6 Ekim.
    assert plan["days"][0]["date"] == "2026-10-06"
    linked = [i for i in plan["items"] if i["recommendation_id"] == rec["id"]]
    assert len(linked) == 1
    assert linked[0]["md_code"] == "MD-4"
    assert plan["total"] == len(plan["items"]) == 7
    audit = await superuser.fetchval(
        "select count(*) from audit_log where action = 'recommendation.accept' and entity_id = $1",
        rec["id"],
    )
    assert audit == 1


async def test_reject_requires_reason_and_undo(
    client: Any, coach: dict[str, str], fixture_id: str
) -> None:
    rec = _rec(await _prep(client, coach, fixture_id), FOULS)

    missing = await _decide(client, coach, fixture_id, rec["id"], "rejected", reason="  ")
    assert missing.status_code == 422
    assert missing.json()["type"].endswith("/reason-required")

    rejected = await _decide(
        client, coach, fixture_id, rec["id"], "rejected", reason="Rakip hakemi farklı"
    )
    assert rejected.status_code == 200
    assert rejected.json()["reason"] == "Rakip hakemi farklı"
    assert _rec(await _prep(client, coach, fixture_id), FOULS)["status"] == "rejected"

    undone = await _decide(client, coach, fixture_id, rec["id"], "suggested")
    assert undone.status_code == 200
    assert undone.json()["status"] == "suggested"
    assert undone.json()["reason"] is None


async def test_undo_removes_open_plan_item(
    client: Any, coach: dict[str, str], fixture_id: str
) -> None:
    rec = _rec(await _prep(client, coach, fixture_id), FOULS)
    await _decide(client, coach, fixture_id, rec["id"], "accepted")
    plan = (await _prep(client, coach, fixture_id))["plan"]
    linked = next(i for i in plan["items"] if i["recommendation_id"] == rec["id"])
    assert linked["md_code"] == "MD-3"

    await _decide(client, coach, fixture_id, rec["id"], "suggested")

    plan = (await _prep(client, coach, fixture_id))["plan"]
    assert all(i["recommendation_id"] != rec["id"] for i in plan["items"])


async def test_unknown_recommendation_is_404(
    client: Any, coach: dict[str, str], fixture_id: str
) -> None:
    response = await _decide(client, coach, fixture_id, str(uuid.uuid4()), "accepted")
    assert response.status_code == 404


async def test_viewer_reads_but_cannot_decide(
    client: Any, viewer: dict[str, str], fixture_id: str
) -> None:
    prep = await _prep(client, viewer, fixture_id)
    rec = prep["recommendations"][0]

    response = await _decide(client, viewer, fixture_id, rec["id"], "accepted")
    assert response.status_code == 403
    plan = await client.post(
        f"/api/v1/fixtures/{fixture_id}/plan", headers=viewer, json={"template": "standard"}
    )
    assert plan.status_code == 403


async def test_decisions_are_tenant_isolated(
    client: Any, coach: dict[str, str], other: dict[str, str], fixture_id: str
) -> None:
    mine = _rec(await _prep(client, coach, fixture_id), CORNERS)
    await _decide(client, coach, fixture_id, mine["id"], "accepted")

    theirs = await _prep(client, other, fixture_id)

    assert theirs["plan"] is None
    corners = _rec(theirs, CORNERS)
    assert corners["id"] != mine["id"]
    assert corners["status"] == "suggested"
    # Diğer kiracının öneri kimliğiyle karar verilemez.
    response = await _decide(client, other, fixture_id, mine["id"], "accepted")
    assert response.status_code == 404


async def test_non_club_fixture_is_422(
    client: Any, coach: dict[str, str], superuser: asyncpg.Connection, seeded: None
) -> None:
    fixture = await superuser.fetchval(
        """
        select m.id from matches m
        join teams h on h.id = m.home_team_id join teams a on a.id = m.away_team_id
        where h.code <> 'TS' and a.code <> 'TS' limit 1
        """
    )
    response = await client.get(f"/api/v1/fixtures/{fixture}/prep", headers=coach)
    assert response.status_code == 422
    assert response.json()["type"].endswith("/not-club-fixture")


async def test_plan_crud(client: Any, coach: dict[str, str], fixture_id: str) -> None:
    url = f"/api/v1/fixtures/{fixture_id}/plan"
    created = await client.post(url, headers=coach, json={"template": "congested"})
    assert created.status_code == 201, created.text
    plan = created.json()
    assert [d["md_code"] for d in plan["days"]] == ["MD-2", "MD-1", "MD", "MD+1"]
    assert (plan["done"], plan["total"]) == (0, 4)

    again = await client.post(url, headers=coach, json={"template": "standard"})
    assert again.status_code == 409

    me = (await client.get("/api/v1/me", headers=coach)).json()
    added = await client.post(
        f"{url}/items",
        headers=coach,
        json={"md_code": "MD-1", "title": "Kısa korner provası", "assignee_id": me["user_id"]},
    )
    assert added.status_code == 201, added.text
    item = next(i for i in added.json()["items"] if i["title"] == "Kısa korner provası")
    assert item["assignee"]["id"] == me["user_id"]

    stranger = await client.post(
        f"{url}/items",
        headers=coach,
        json={"md_code": "MD-1", "title": "x", "assignee_id": str(uuid.uuid4())},
    )
    assert stranger.status_code == 422

    done = await client.patch(
        f"/api/v1/plan-items/{item['id']}", headers=coach, json={"status": "done"}
    )
    assert done.status_code == 200, done.text
    assert (done.json()["done"], done.json()["total"]) == (1, 5)
    marked = next(i for i in done.json()["items"] if i["id"] == item["id"])
    assert marked["done_by"]["id"] == me["user_id"]
    assert marked["done_at"] is not None

    removed = await client.delete(f"/api/v1/plan-items/{item['id']}", headers=coach)
    assert removed.status_code in (200, 204)
    prep = await _prep(client, coach, fixture_id)
    assert prep["plan"]["total"] == 4


async def test_items_need_plan(client: Any, coach: dict[str, str], fixture_id: str) -> None:
    response = await client.post(
        f"/api/v1/fixtures/{fixture_id}/plan/items",
        headers=coach,
        json={"md_code": "MD-1", "title": "x"},
    )
    assert response.status_code == 409
    assert response.json()["type"].endswith("/plan-missing")


async def test_overview_has_threats_and_season_recs(client: Any, coach: dict[str, str]) -> None:
    response = await client.get("/api/v1/prep/overview", headers=coach)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["upcoming"]
    assert all(len(u["threats"]) <= 2 for u in body["upcoming"])
    assert all(r["area"] == "season" for r in body["recommendations"])


async def test_rule_set_publish_conflict_and_history(
    client: Any, head: dict[str, str], coach: dict[str, str], other: dict[str, str]
) -> None:
    current = (await client.get("/api/v1/rule-sets/current", headers=head)).json()
    assert current["is_default"] is True
    rules = current["rules"]
    rule = next(r for r in rules if r["id"] == "ATK_WIN_FOULS")
    rule["enabled"] = False

    forbidden = await client.put(
        "/api/v1/rule-sets/current",
        headers=coach,
        json={"base_version": 0, "rules": rules},
    )
    assert forbidden.status_code == 403

    published = await client.put(
        "/api/v1/rule-sets/current",
        headers=head,
        json={"base_version": 0, "rules": rules, "message": "Faul kuralı kapalı"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["version"] == 1
    assert published.json()["is_default"] is False

    stale = await client.put(
        "/api/v1/rule-sets/current", headers=head, json={"base_version": 0, "rules": rules}
    )
    assert stale.status_code == 409
    assert stale.json()["current_version"] == 1

    same = await client.put(
        "/api/v1/rule-sets/current", headers=head, json={"base_version": 1, "rules": rules}
    )
    assert same.json()["version"] == 1

    versions = (await client.get("/api/v1/rule-sets/versions", headers=head)).json()
    assert [(v["version"], v["is_default"]) for v in versions] == [(1, False), (0, True)]

    # Diğer kiracı hâlâ varsayılan seti görür.
    theirs = (await client.get("/api/v1/rule-sets/current", headers=other)).json()
    assert theirs["version"] == 0


async def test_disabled_rule_hides_recommendation(
    client: Any, head: dict[str, str], fixture_id: str
) -> None:
    rules = (await client.get("/api/v1/rule-sets/current", headers=head)).json()["rules"]
    next(r for r in rules if r["id"] == "ATK_WIN_FOULS")["enabled"] = False
    await client.put(
        "/api/v1/rule-sets/current", headers=head, json={"base_version": 0, "rules": rules}
    )

    prep = await _prep(client, head, fixture_id)

    assert prep["rule_set"]["version"] == 1
    assert FOULS not in [r["title"] for r in prep["recommendations"]]
    assert CORNERS in [r["title"] for r in prep["recommendations"]]


async def test_invalid_rules_are_rejected(client: Any, head: dict[str, str]) -> None:
    rules = (await client.get("/api/v1/rule-sets/current", headers=head)).json()["rules"]
    rules[0]["when"] = {"all": [{"subject": "opponent", "metric": "x", "op": "eval", "value": 1}]}

    response = await client.put(
        "/api/v1/rule-sets/current", headers=head, json={"base_version": 0, "rules": rules}
    )

    assert response.status_code == 422
    assert response.json()["type"].endswith("/invalid-rules")


async def test_dry_run_with_draft(client: Any, head: dict[str, str], fixture_id: str) -> None:
    rules = (await client.get("/api/v1/rule-sets/current", headers=head)).json()["rules"]
    corner = next(r for r in rules if r["id"] == "DEF_CORNER_PRIORITY")

    response = await client.post(
        "/api/v1/rule-sets/dry-run", headers=head, json={"fixture_id": fixture_id}
    )
    assert response.status_code == 200, response.text
    rows = {r["rule_id"]: r for r in response.json()["results"]}
    assert rows["DEF_CORNER_PRIORITY"]["status"] == "fired"
    assert rows["DEF_CORNER_PRIORITY"]["shown"] is True
    assert rows["DEF_CORNER_PRIORITY"]["conditions"][0]["passed"] is True
    assert rows["ATK_WIN_FOULS"]["status"] == "fired"

    corner["enabled"] = False
    draft = await client.post(
        "/api/v1/rule-sets/dry-run", headers=head, json={"fixture_id": fixture_id, "rules": rules}
    )
    rows = {r["rule_id"]: r for r in draft.json()["results"]}
    assert rows["DEF_CORNER_PRIORITY"]["status"] == "disabled"
    assert rows["DEF_CORNER_PRIORITY"]["shown"] is False
    # Dry-run kaydetmez.
    current = (await client.get("/api/v1/rule-sets/current", headers=head)).json()
    assert current["version"] == 0
