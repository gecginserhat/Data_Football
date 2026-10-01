"""Rutin kütüphanesi uçları (Faz 3, ADR-0008): şablonlar, sürümleme, izinler, izolasyon."""

import json
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_api.league.seed import run_product_content

from .conftest import Seeded, TokenFactory, add_member

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
TEMPLATES = json.loads((SEED_DIR / "routine_templates.json").read_text(encoding="utf-8"))
URL = "/api/v1/routines"


@pytest.fixture
async def templates() -> None:
    await run_product_content(seed_dir=SEED_DIR)


async def _headers(
    make_token: TokenFactory, superuser: asyncpg.Connection, tenant: uuid.UUID, role: str
) -> dict[str, str]:
    subject = f"{role}-{uuid.uuid4()}"
    await add_member(superuser, subject, tenant, role)
    return {"Authorization": f"Bearer {make_token(subject)}", "X-Kurgu-Tenant": str(tenant)}


@pytest.fixture
async def coach(make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded) -> Any:
    return await _headers(make_token, superuser, tenants.tenant_a, "sp_coach")


@pytest.fixture
async def other(make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded) -> Any:
    return await _headers(make_token, superuser, tenants.tenant_b, "sp_coach")


@pytest.fixture
async def viewer(make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded) -> Any:
    return await _headers(make_token, superuser, tenants.tenant_a, "viewer")


def _diagram(**overrides: Any) -> dict[str, Any]:
    diagram: dict[str, Any] = {
        "schema": 1,
        "players": [
            {"id": "p1", "team": "own", "role": "taker", "number": 7, "x": 104.0, "y": 1.0},
            {"id": "p2", "team": "own", "role": "target", "number": 9, "x": 88.0, "y": 40.0},
        ],
        "lines": [
            {
                "id": "l1",
                "kind": "ball_path",
                "from": [104.0, 1.0],
                "to": [99.0, 38.0],
                "curve": 0.2,
            },
            {
                "id": "l2",
                "kind": "run",
                "from": [88.0, 40.0],
                "to": [99.0, 38.0],
                "curve": 0.0,
                "player_id": "p2",
            },
        ],
        "zones": [],
        "ball": [104.0, 1.0],
        "frames": [],
    }
    diagram.update(overrides)
    return diagram


async def _create(client: Any, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    payload = {"name": "Arka direk", "sp_type": "corner", "side": "right", "diagram": _diagram()}
    response = await client.post(URL, headers=headers, json=payload | body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _update(routine: dict[str, Any], **changes: Any) -> dict[str, Any]:
    v = routine["version"]
    body = {
        "base_version": routine["current_version"],
        "name": v["name"],
        "side": v["side"],
        "notes": v["notes"],
        "when_to_use": v["when_to_use"],
        "diagram": v["diagram"],
    }
    return body | changes


async def test_templates_are_loaded_from_seed(
    client: Any, templates: None, coach: dict[str, str]
) -> None:
    response = await client.get("/api/v1/routine-templates", headers=coach)

    assert response.status_code == 200
    items = response.json()
    assert [t["id"] for t in items] == [t["id"] for t in TEMPLATES["templates"]]
    assert len(items) == 7
    by_id = {t["id"]: t for t in items}
    for tpl in TEMPLATES["templates"]:
        got = by_id[tpl["id"]]
        assert got["name"] == tpl["name"]
        assert len(got["diagram"]["players"]) == len(tpl["players"])
        assert len(got["diagram"]["lines"]) == len(tpl["lines"])
    etag = response.headers["etag"]
    cached = await client.get("/api/v1/routine-templates", headers=coach | {"If-None-Match": etag})
    assert cached.status_code == 304


async def test_template_loading_is_idempotent(superuser: asyncpg.Connection) -> None:
    await run_product_content(seed_dir=SEED_DIR)
    before = await superuser.fetch("select id, updated_at from routine_templates order by id")
    await run_product_content(seed_dir=SEED_DIR)
    after = await superuser.fetch("select id, updated_at from routine_templates order by id")
    assert before == after


async def test_add_template_to_library(
    client: Any, templates: None, coach: dict[str, str], superuser: asyncpg.Connection
) -> None:
    response = await client.post(f"{URL}/from-template/tpl-arka", headers=coach)

    assert response.status_code == 201, response.text
    routine = response.json()
    tpl = next(t for t in TEMPLATES["templates"] if t["id"] == "tpl-arka")
    assert routine["name"] == tpl["name"]
    assert routine["from_template"] == "tpl-arka"
    assert routine["current_version"] == 1
    assert routine["version"]["when_to_use"] == tpl["when_to_use"]
    assert len(routine["version"]["diagram"]["players"]) == len(tpl["players"])
    assert routine["stats"]["uses"] == 0
    assert routine["stats"]["low_sample"] is True
    audit = await superuser.fetchrow(
        "select action, after from audit_log where entity = 'routines' and entity_id = $1",
        routine["id"],
    )
    assert audit is not None
    assert audit["action"] == "routine.create"

    renamed = await client.post(
        f"{URL}/from-template/tpl-kisa", headers=coach, json={"name": "Kısa korner (sol)"}
    )
    assert renamed.json()["name"] == "Kısa korner (sol)"
    missing = await client.post(f"{URL}/from-template/tpl-yok", headers=coach)
    assert missing.status_code == 404


async def test_versioning(client: Any, coach: dict[str, str]) -> None:
    routine = await _create(client, coach)
    moved = _diagram()
    moved["players"][1]["x"] = 90.0

    v2 = await client.put(
        f"{URL}/{routine['id']}",
        headers=coach,
        json=_update(routine, diagram=moved, message="Hedef öne alındı"),
    )
    assert v2.status_code == 200, v2.text
    assert v2.json()["current_version"] == 2
    assert v2.json()["version"]["message"] == "Hedef öne alındı"

    # Aynı içerik yeni sürüm açmaz.
    same = await client.put(f"{URL}/{routine['id']}", headers=coach, json=_update(v2.json()))
    assert same.json()["current_version"] == 2

    # Eski tabanla kayıt çakışır.
    stale = await client.put(f"{URL}/{routine['id']}", headers=coach, json=_update(routine))
    assert stale.status_code == 409
    assert stale.headers["content-type"].startswith("application/problem+json")
    assert stale.json()["current_version"] == 2

    versions = (await client.get(f"{URL}/{routine['id']}/versions", headers=coach)).json()
    assert [v["version"] for v in versions] == [2, 1]
    v1 = (await client.get(f"{URL}/{routine['id']}/versions/1", headers=coach)).json()
    assert v1["diagram"]["players"][1]["x"] == 88.0
    assert (await client.get(f"{URL}/{routine['id']}/versions/9", headers=coach)).status_code == 404


async def test_mirror_and_rename_create_versions(client: Any, coach: dict[str, str]) -> None:
    routine = await _create(client, coach)
    response = await client.put(
        f"{URL}/{routine['id']}",
        headers=coach,
        json=_update(routine, name="Arka direk (sol)", side="left"),
    )
    body = response.json()
    assert body["name"] == "Arka direk (sol)"
    assert body["side"] == "left"
    listed = (await client.get(URL, headers=coach)).json()["items"]
    assert listed[0]["name"] == "Arka direk (sol)"


@pytest.mark.parametrize(
    ("diagram", "fragment"),
    [
        ({"players": [{"id": "p1", "team": "own", "role": "taker", "x": 120, "y": 3}]}, "players"),
        ({"lines": [{"id": "l1", "kind": "arrow", "from": [90, 3], "to": [95, 3]}]}, "lines"),
        ({"frames": [{"id": "f1", "positions": {"p9": [90, 30]}}]}, "unknown players"),
    ],
)
async def test_invalid_diagram_is_rejected(
    client: Any, coach: dict[str, str], diagram: dict[str, Any], fragment: str
) -> None:
    response = await client.post(
        URL,
        headers=coach,
        json={"name": "Hatalı", "sp_type": "corner", "diagram": _diagram(**diagram)},
    )
    assert response.status_code == 422
    assert fragment in response.text


async def test_permissions(client: Any, coach: dict[str, str], viewer: dict[str, str]) -> None:
    routine = await _create(client, coach)

    assert (await client.get(f"{URL}/{routine['id']}", headers=viewer)).status_code == 200
    denied = await client.post(URL, headers=viewer, json={"name": "x", "sp_type": "corner"})
    assert denied.status_code == 403
    put = await client.put(f"{URL}/{routine['id']}", headers=viewer, json=_update(routine))
    assert put.status_code == 403
    patch = await client.patch(f"{URL}/{routine['id']}", headers=viewer, json={"archived": True})
    assert patch.status_code == 403


async def test_tenant_isolation(client: Any, coach: dict[str, str], other: dict[str, str]) -> None:
    routine = await _create(client, coach)

    assert (await client.get(f"{URL}/{routine['id']}", headers=other)).status_code == 404
    assert (await client.get(f"{URL}/{routine['id']}/versions", headers=other)).status_code == 404
    put = await client.put(f"{URL}/{routine['id']}", headers=other, json=_update(routine))
    assert put.status_code == 404
    assert (await client.get(URL, headers=other)).json()["items"] == []


async def test_archive(client: Any, coach: dict[str, str]) -> None:
    routine = await _create(client, coach)
    archived = await client.patch(f"{URL}/{routine['id']}", headers=coach, json={"archived": True})
    assert archived.json()["archived"] is True

    assert (await client.get(URL, headers=coach)).json()["items"] == []
    items = (await client.get(URL, headers=coach, params={"archived": True})).json()["items"]
    assert [i["id"] for i in items] == [routine["id"]]
    edit = await client.put(f"{URL}/{routine['id']}", headers=coach, json=_update(routine))
    assert edit.status_code == 409

    restored = await client.patch(f"{URL}/{routine['id']}", headers=coach, json={"archived": False})
    assert restored.json()["archived"] is False


async def test_list_filters_and_pagination(client: Any, coach: dict[str, str]) -> None:
    for i in range(3):
        await _create(client, coach, name=f"Korner {i}")
    await _create(client, coach, name="Uzun taç", sp_type="throw_in")

    throws = (await client.get(URL, headers=coach, params={"type": "throw_in"})).json()["items"]
    assert [i["name"] for i in throws] == ["Uzun taç"]
    found = (await client.get(URL, headers=coach, params={"q": "korner 1"})).json()["items"]
    assert [i["name"] for i in found] == ["Korner 1"]

    first = (await client.get(URL, headers=coach, params={"limit": 3})).json()
    assert len(first["items"]) == 3
    rest = (
        await client.get(URL, headers=coach, params={"limit": 3, "cursor": first["next_cursor"]})
    ).json()
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None
    names = [i["name"] for i in first["items"] + rest["items"]]
    assert sorted(names) == ["Korner 0", "Korner 1", "Korner 2", "Uzun taç"]


async def test_versions_are_immutable(
    client: Any, coach: dict[str, str], app_conn: asyncpg.Connection, tenants: Seeded
) -> None:
    await _create(client, coach)
    await app_conn.execute("select set_config('app.tenant_id', $1, false)", str(tenants.tenant_a))
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("update routine_versions set name = 'x'")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("delete from routine_versions")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("delete from routines")


async def _match(superuser: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    code = uuid.uuid4().hex[:8]
    comp = await superuser.fetchval(
        "insert into competitions (code, name) values ($1, 'Lig') returning id", f"R-{code}"
    )
    season = await superuser.fetchval(
        "insert into seasons (competition_id, code, label) values ($1, '2025_26', '2025/26')"
        " returning id",
        comp,
    )
    home = await superuser.fetchval(
        "insert into teams (code, name) values ('EV', 'Ev') returning id"
    )
    away = await superuser.fetchval(
        "insert into teams (code, name) values ('DP', 'Dep') returning id"
    )
    match = await superuser.fetchval(
        "insert into matches (season_id, week, home_team_id, away_team_id, status, source)"
        " values ($1, 1, $2, $3, 'scheduled', 'test') returning id",
        season,
        home,
        away,
    )
    return match, home, away


async def test_routine_stats_from_tagged_set_pieces(
    client: Any, coach: dict[str, str], superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    used = await _create(client, coach, name="Kullanılan")
    unused = await _create(client, coach, name="Kullanılmayan")
    match, team, opponent = await _match(superuser)
    rows = [  # (ilk temas bizde mi, şut, xg, gol)
        (True, 1, 0.3, True),
        (True, 0, 0.0, False),
        (False, 1, 0.1, False),
        (None, 0, 0.0, False),
    ]
    for i, (won, shots, xg, goal) in enumerate(rows):
        contact = None if won is None else (team if won else opponent)
        await superuser.execute(
            "insert into set_pieces (tenant_id, match_id, team_id, period, start_time_s, sp_type,"
            " first_contact_team_id, shots, xg_total, goal, routine_id, source)"
            " values ($1, $2, $3, 1, $4, 'corner', $5, $6, $7, $8, $9, 'live_tag')",
            tenants.tenant_a,
            match,
            team,
            float(i * 60),
            contact,
            shots,
            xg,
            goal,
            uuid.UUID(used["id"]),
        )

    stats = (await client.get(f"{URL}/{used['id']}", headers=coach)).json()["stats"]
    assert stats["uses"] == 4
    assert stats["matches"] == 1
    assert stats["goals"] == 1
    assert stats["xg"] == pytest.approx(0.4)
    assert stats["xg_per_use"] == pytest.approx(0.1)
    assert stats["first_contact"]["trials"] == 3
    assert stats["first_contact"]["value"] == pytest.approx(2 / 3)
    assert stats["shot"]["value"] == pytest.approx(0.5)
    assert stats["first_contact"]["low"] <= stats["first_contact"]["shrunk"]
    assert stats["low_sample"] is True
    empty = (await client.get(f"{URL}/{unused['id']}", headers=coach)).json()["stats"]
    assert empty["uses"] == 0
    assert empty["first_contact"]["value"] is None


async def test_set_piece_cannot_point_to_another_tenants_routine(
    client: Any, coach: dict[str, str], superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    routine = await _create(client, coach)
    match, team, _ = await _match(superuser)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await superuser.execute(
            "insert into set_pieces (tenant_id, match_id, team_id, period, start_time_s, sp_type,"
            " routine_id, source) values ($1, $2, $3, 1, 0, 'corner', $4, 'live_tag')",
            tenants.tenant_b,
            match,
            team,
            uuid.UUID(routine["id"]),
        )


@pytest.mark.parametrize(
    ("fmt", "magic", "ctype"),
    [("pdf", b"%PDF", "application/pdf"), ("png", b"\x89PNG", "image/png")],
)
async def test_export(
    client: Any, coach: dict[str, str], viewer: dict[str, str], fmt: str, magic: bytes, ctype: str
) -> None:
    routine = await _create(client, coach, name="Arka direğe geç koşu")
    response = await client.get(
        f"{URL}/{routine['id']}/versions/1/export", headers=viewer, params={"format": fmt}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == ctype
    assert response.content.startswith(magic)
    assert f'filename="arka-direge-gec-kosu-v1.{fmt}"' in response.headers["content-disposition"]


async def test_export_rejects_unknown_format_and_other_tenants(
    client: Any, coach: dict[str, str], other: dict[str, str]
) -> None:
    routine = await _create(client, coach)
    url = f"{URL}/{routine['id']}/versions/1/export"
    assert (await client.get(url, headers=coach, params={"format": "svg"})).status_code == 422
    assert (await client.get(url, headers=other)).status_code == 404
    assert (
        await client.get(f"{URL}/{routine['id']}/versions/5/export", headers=coach)
    ).status_code == 404
