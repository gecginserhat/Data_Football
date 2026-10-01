"""İçe aktarım uçları (Faz 1.9): karantina, takım onayı, idempotentlik, işleme, izolasyon."""

import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_analytics.testing.imports import event_rows, to_csv
from kurgu_api.dev_identities import DEMO_TENANT_ID, DEV_USERS
from kurgu_api.imports.router import get_store
from kurgu_api.ingestion.storage import LocalObjectStore
from kurgu_api.league.seed import run_seed

from .conftest import Seeded, TokenFactory, add_member

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
ADMIN = next(str(sub) for sub, _, role in DEV_USERS if role.value == "admin")
ANALYST = next(str(sub) for sub, _, role in DEV_USERS if role.value == "analyst")


@pytest.fixture
async def seeded() -> None:
    await run_seed(seed_dir=SEED_DIR)


@pytest.fixture
def store(app: Any, tmp_path: Path) -> LocalObjectStore:
    local = LocalObjectStore(tmp_path)
    app.dependency_overrides[get_store] = lambda: local
    return local


def _auth(make_token: TokenFactory, subject: str = ADMIN) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(subject)}", "X-Kurgu-Tenant": str(DEMO_TENANT_ID)}


async def _season(client: Any, headers: dict[str, str], code: str = "2025_26") -> str:
    items = (await client.get("/api/v1/seasons", headers=headers)).json()["items"]
    return str(
        next(s["id"] for s in items if s["code"] == code and s["competition"]["code"] == "TR-SL")
    )


async def _upload(
    client: Any,
    headers: dict[str, str],
    content: bytes,
    season: str,
    kind: str = "team_season_stats",
    filename: str = "stats.csv",
    key: str | None = None,
) -> Any:
    return await client.post(
        "/api/v1/imports",
        headers=headers | {"Idempotency-Key": key or f"test-{uuid.uuid4()}"},
        data={"kind": kind, "season_id": season},
        files={"file": (filename, content, "text/csv")},
    )


async def test_team_stats_quarantine_confirm_commit(
    client: Any,
    make_token: TokenFactory,
    seeded: None,
    store: LocalObjectStore,
    superuser: asyncpg.Connection,
) -> None:
    headers = _auth(make_token)
    season = await _season(client, headers)

    bad = "Takım;goals;set_piece_goals\nTrabzonspor;50;-3\nGöztepe;40;9\n".encode()
    quarantined = await _upload(client, headers, bad, season)
    assert quarantined.status_code == 201
    body = quarantined.json()
    assert body["status"] == "quarantined"
    assert body["columns"] == {
        "Takım": "team",
        "goals": "goals",
        "set_piece_goals": "set_piece_goals",
    }
    assert body["report"]["critical"] == 1
    assert body["report"]["issues"][0]["rows"] == [2]
    blocked = await client.post(f"/api/v1/imports/{body['id']}/commit", headers=headers)
    assert blocked.status_code == 409
    assert blocked.headers["content-type"] == "application/problem+json"

    fixed = "Takım;goals;set_piece_goals\nTrabzonspor;50;13\nGoztepe SK;40;9\n".encode()
    pending = (await _upload(client, headers, fixed, season)).json()
    assert pending["status"] == "uploaded"
    teams = {t["name"]: t for t in pending["teams"]}
    assert teams["Trabzonspor"]["confirmed"] is True
    goz = teams["Goztepe SK"]
    assert goz["confirmed"] is False
    options = {o["code"]: o["id"] for o in pending["team_options"]}
    assert goz["suggested"] == options["GÖZ"]
    assert len(options) == 18

    early = await client.post(f"/api/v1/imports/{pending['id']}/commit", headers=headers)
    assert early.status_code == 409

    confirmed = await client.put(
        f"/api/v1/imports/{pending['id']}/mapping",
        headers=headers,
        json={"teams": {"Goztepe SK": options["GÖZ"]}},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "validated"

    committed = await client.post(f"/api/v1/imports/{pending['id']}/commit", headers=headers)
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"
    assert committed.json()["result"] == {"teams": 2, "values": 4}

    listing = await client.get(f"/api/v1/seasons/{season}/team-metrics", headers=headers)
    # Kulübün kendi kaydı paylaşılan tohum değerinin yerine geçer (A-36).
    values = {m["team"]["code"]: m["values"] for m in listing.json()["items"]}
    assert values["GÖZ"]["set_piece_goals"]["value"] == 9
    assert values["GÖZ"]["set_piece_goals"]["source"] == "import"
    assert values["GÖZ"]["set_piece_goal_share"]["value"] == 9 / 40
    assert values["GÖZ"]["set_piece_xg"]["source"].startswith("seed")
    assert values["FB"]["set_piece_goals"]["source"].startswith("seed")
    rows = await superuser.fetch(
        "select tenant_id from team_season_stats where source = 'import' and season_id = $1",
        uuid.UUID(season),
    )
    assert {r["tenant_id"] for r in rows} == {DEMO_TENANT_ID}
    actions = await superuser.fetch(
        "select action from audit_log where entity = 'imports' and entity_id = $1 order by id",
        pending["id"],
    )
    assert [a["action"] for a in actions] == ["import.upload", "import.mapping", "import.commit"]

    again = await client.put(
        f"/api/v1/imports/{pending['id']}/mapping", headers=headers, json={"teams": {}}
    )
    assert again.status_code == 409


async def test_idempotency_key(
    client: Any, make_token: TokenFactory, seeded: None, store: LocalObjectStore
) -> None:
    headers = _auth(make_token)
    season = await _season(client, headers)
    key = f"idem-{uuid.uuid4()}"
    content = b"team,goals\nTrabzonspor,50\n"
    first = await _upload(client, headers, content, season, key=key)
    second = await _upload(client, headers, content, season, key=key)
    assert first.json()["id"] == second.json()["id"]
    other = await _upload(client, headers, b"team,goals\nTrabzonspor,51\n", season, key=key)
    assert other.status_code == 409
    missing = await client.post(
        "/api/v1/imports",
        headers=headers,
        data={"kind": "team_season_stats", "season_id": season},
        files={"file": ("a.csv", content, "text/csv")},
    )
    assert missing.status_code == 422


async def test_column_mapping_update_revalidates(
    client: Any, make_token: TokenFactory, seeded: None, store: LocalObjectStore
) -> None:
    headers = _auth(make_token)
    season = await _season(client, headers)
    body = (await _upload(client, headers, b"Kulup Adi,Atilan\nTrabzonspor,50\n", season)).json()
    assert body["status"] == "quarantined"
    assert {i["check"] for i in body["report"]["issues"]} == {"required_column"}

    url = f"/api/v1/imports/{body['id']}/mapping"
    unknown = await client.put(url, headers=headers, json={"columns": {"Atilan": "nope"}})
    assert unknown.status_code == 422
    duplicate = await client.put(
        url, headers=headers, json={"columns": {"Kulup Adi": "team", "Atilan": "team"}}
    )
    assert duplicate.status_code == 422
    fixed = await client.put(
        url, headers=headers, json={"columns": {"Kulup Adi": "team", "Atilan": "goals"}}
    )
    assert fixed.json()["status"] == "validated"


async def test_events_commit_writes_tenant_match_and_set_pieces(
    client: Any,
    make_token: TokenFactory,
    seeded: None,
    store: LocalObjectStore,
    superuser: asyncpg.Connection,
) -> None:
    headers = _auth(make_token)
    season = await _season(client, headers)
    ref = f"M-{uuid.uuid4().hex[:8]}"
    content = to_csv(event_rows(ref, home="Trabzonspor", away="Galatasaray"))

    body = (await _upload(client, headers, content, season, "events", "events.csv")).json()
    assert body["status"] == "validated", body["report"]
    committed = await client.post(f"/api/v1/imports/{body['id']}/commit", headers=headers)
    assert committed.status_code == 200
    assert committed.json()["result"] == {
        "matches": 1,
        "replaced": 0,
        "events": 322,
        "set_pieces": 1,
    }

    match = await superuser.fetchrow(
        "select id, tenant_id, home_score, away_score, source from matches"
        " where extra ->> 'import_ref' = $1",
        ref,
    )
    assert (match["tenant_id"], match["source"]) == (DEMO_TENANT_ID, "import")
    assert (match["home_score"], match["away_score"]) == (1, 0)
    sp = await superuser.fetchrow(
        "select tenant_id, source, sp_type, goal, target_zone from set_pieces where match_id = $1",
        match["id"],
    )
    assert (sp["tenant_id"], sp["source"], sp["sp_type"], sp["goal"]) == (
        DEMO_TENANT_ID,
        "import",
        "corner",
        True,
    )
    events = await superuser.fetchval(
        "select count(*) from events where match_id = $1 and tenant_id = $2",
        match["id"],
        DEMO_TENANT_ID,
    )
    assert events == 322

    # İçe aktarılan diziler kulübün metriklerine ve dizi listesine anında girer (A-36).
    listing = await client.get(f"/api/v1/seasons/{season}/team-metrics", headers=headers)
    ts = next(i for i in listing.json()["items"] if i["team"]["code"] == "TS")
    per_match = ts["values"]["set_pieces_per_match"]
    assert (per_match["value"], per_match["source"], per_match["low_sample"]) == (1, "import", True)
    # Olay toplamları sezon kaydını (34 maç) ezmez; ayrı sütunlarda durur.
    assert (ts["inputs"]["event_matches"], ts["inputs"]["sp_goals"]) == (1, 1)
    assert ts["inputs"]["matches"] == 34
    sps = await client.get(
        f"/api/v1/teams/{ts['team']['id']}/set-pieces",
        params={"season": season, "type": "corner"},
        headers=headers,
    )
    assert [(i["sp_type"], i["goal"], i["source"]) for i in sps.json()["items"]] == [
        ("corner", True, "import")
    ]

    reupload = (await _upload(client, headers, content, season, "events", "events.csv")).json()
    result = (await client.post(f"/api/v1/imports/{reupload['id']}/commit", headers=headers)).json()
    assert result["result"]["replaced"] == 1
    count = "select count(*) from matches where extra ->> 'import_ref' = $1"
    assert await superuser.fetchval(count, ref) == 1


async def test_same_team_on_both_sides_is_quarantined(
    client: Any, make_token: TokenFactory, seeded: None, store: LocalObjectStore
) -> None:
    headers = _auth(make_token)
    season = await _season(client, headers)
    content = to_csv(event_rows("M-same", home="Trabzonspor", away="TS"))
    body = (await _upload(client, headers, content, season, "events", "events.csv")).json()
    assert body["status"] == "quarantined"
    assert {i["check"] for i in body["report"]["issues"]} == {"team_mapping"}


async def test_access_rules(
    client: Any,
    make_token: TokenFactory,
    seeded: None,
    store: LocalObjectStore,
    superuser: asyncpg.Connection,
    tenants: Seeded,
) -> None:
    headers = _auth(make_token)
    season = await _season(client, headers)
    body = (await _upload(client, headers, b"team,goals\nTrabzonspor,1\n", season)).json()

    other = f"admin-{uuid.uuid4()}"
    await add_member(superuser, other, tenants.tenant_b, "admin")
    foreign = {"Authorization": f"Bearer {make_token(other)}"}
    assert (await client.get(f"/api/v1/imports/{body['id']}", headers=foreign)).status_code == 404
    listing = (await client.get("/api/v1/imports", headers=foreign)).json()
    assert body["id"] not in {i["id"] for i in listing}
    commit = await client.post(f"/api/v1/imports/{body['id']}/commit", headers=foreign)
    assert commit.status_code == 404

    analyst = await client.get("/api/v1/imports", headers=_auth(make_token, ANALYST))
    assert analyst.status_code == 403
    pdf = await _upload(client, headers, b"%PDF", season, filename="x.pdf")
    assert pdf.status_code == 415
    unknown_season = await _upload(client, headers, b"team,goals\nA,1\n", str(uuid.uuid4()))
    assert unknown_season.status_code == 422
