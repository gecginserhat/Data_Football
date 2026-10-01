"""Kadro, rakip hedefleri, markaj ve rol atamaları (Faz 7; ADR-0015; A-79 … A-82, A-87).

Kabul (SPEC §19 Faz 7): Macar algoritmasıyla gelen markaj önerisi elle düzeltilebilir ve kaydedilir;
rol izinleri doğrulandı.
"""

import uuid
from typing import Any

import asyncpg
import pytest

from .conftest import Seeded, TokenFactory, add_member
from .test_prep import club, fixture_id, seeded

__all__ = ["club", "fixture_id", "seeded"]

DIAGRAM = {
    "schema": 1,
    "players": [
        {"id": "k", "team": "own", "role": "taker", "number": 7, "x": 104, "y": 1},
        {"id": "np", "team": "own", "role": "near_post_runner", "x": 94, "y": 30},
        {"id": "fp", "team": "own", "role": "far_post_runner", "label": "Arka", "x": 94, "y": 40},
        {"id": "o1", "team": "opponent", "role": "marker", "x": 99, "y": 34},
    ],
}


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


@pytest.fixture
async def coach(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "sp_coach")


@pytest.fixture
async def viewer(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "viewer")


async def _add(client: Any, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/squad", headers=headers, json=body)
    assert response.status_code == 201, response.text
    out: dict[str, Any] = response.json()
    return out


async def _target(client: Any, headers: dict[str, str], team: str, **body: Any) -> dict[str, Any]:
    response = await client.post(f"/api/v1/teams/{team}/targets", headers=headers, json=body)
    assert response.status_code == 201, response.text
    out: dict[str, Any] = response.json()
    return out


async def _sam(superuser: asyncpg.Connection) -> str:
    return str(await superuser.fetchval("select id from teams where code = 'SAM'"))


async def test_squad_crud_and_aerial_score(
    client: Any, coach: dict[str, str], viewer: dict[str, str], superuser: asyncpg.Connection
) -> None:
    p = await _add(
        client,
        coach,
        name="Stoper",
        shirt_number=4,
        position="DEF",
        height_cm=191,
        aerial_win_pct=0.6,
        jump_score=0.7,
    )
    # (21/30 + 0.75 + 0.7) / 3
    assert p["aerial"]["value"] == pytest.approx((0.7 + 0.75 + 0.7) / 3, abs=1e-4)
    assert p["aerial"]["components"] == ["height", "aerial", "jump"]
    assert p["has_account"] is False
    none = await _add(client, coach, name="Bilinmeyen", position="MID")
    assert none["aerial"] is None

    clash = await client.post(
        "/api/v1/squad", headers=coach, json={"name": "X", "shirt_number": 4, "position": "MID"}
    )
    assert clash.status_code == 409

    updated = await client.put(
        f"/api/v1/squad/{p['id']}",
        headers=coach,
        json={
            "name": "Stoper",
            "shirt_number": 4,
            "position": "DEF",
            "height_cm": 191,
            "active": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["active"] is False
    listed = (await client.get("/api/v1/squad", headers=viewer)).json()
    assert [x["name"] for x in listed] == ["Bilinmeyen"]
    everyone = (await client.get("/api/v1/squad?include_inactive=true", headers=viewer)).json()
    assert len(everyone) == 2

    audit = await superuser.fetch(
        "select action, before, after from audit_log where entity = 'squad_players' order by at"
    )
    assert [a["action"] for a in audit] == ["squad.create", "squad.create", "squad.update"]


async def test_squad_permissions(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    club: Seeded,
    viewer: dict[str, str],
) -> None:
    body = {"name": "Oyuncu", "position": "DEF"}
    allowed = ("admin", "head_coach", "sp_coach", "performance")
    for role in allowed:
        headers = await _headers(make_token, superuser, club.tenant_a, role)
        response = await client.post("/api/v1/squad", headers=headers, json=body)
        assert response.status_code == 201, (role, response.text)
    for role in ("analyst", "medical", "player", "viewer"):
        headers = await _headers(make_token, superuser, club.tenant_a, role)
        response = await client.post("/api/v1/squad", headers=headers, json=body)
        assert response.status_code == 403, role
    # Okuma: analiz, yük ya da kadro izni olanlar; oyuncu kadroyu listeleyemez.
    medical = await _headers(make_token, superuser, club.tenant_a, "medical")
    assert (await client.get("/api/v1/squad", headers=medical)).status_code == 200
    player = await _headers(make_token, superuser, club.tenant_a, "player")
    assert (await client.get("/api/v1/squad", headers=player)).status_code == 403
    other = await _headers(make_token, superuser, club.tenant_b, "sp_coach")
    assert (await client.get("/api/v1/squad", headers=other)).json() == []


async def test_account_link(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    club: Seeded,
    coach: dict[str, str],
) -> None:
    p = await _add(client, coach, name="Oyuncu", position="FWD")
    subject = f"player-{uuid.uuid4()}"
    user = await add_member(superuser, subject, club.tenant_a, "player")
    admin = await _headers(make_token, superuser, club.tenant_a, "admin")
    link = {"user_id": str(user)}
    assert (
        await client.put(f"/api/v1/squad/{p['id']}/account", headers=coach, json=link)
    ).status_code == 403
    response = await client.put(f"/api/v1/squad/{p['id']}/account", headers=admin, json=link)
    assert response.status_code == 204, response.text
    accounts = (await client.get("/api/v1/squad/accounts", headers=admin)).json()
    assert [a["squad_player_id"] for a in accounts] == [p["id"]]
    me = await client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {make_token(subject)}",
            "X-Kurgu-Tenant": str(club.tenant_a),
        },
    )
    assert me.json()["active_tenant"]["squad_player_id"] == p["id"]
    not_player = await client.put(
        f"/api/v1/squad/{p['id']}/account",
        headers=admin,
        json={
            "user_id": str(
                await superuser.fetchval(
                    "select user_id from memberships where role = 'sp_coach' limit 1"
                )
            )
        },
    )
    assert not_player.status_code == 422


async def test_targets_crud_and_permissions(
    client: Any, coach: dict[str, str], viewer: dict[str, str], superuser: asyncpg.Connection
) -> None:
    sam = await _sam(superuser)
    t = await _target(client, coach, sam, name="Hedef 4", shirt_number=4, height_cm=194, sp_goals=2)
    # boy 0.8 + 2 gol × 0.05
    assert t["threat"]["value"] == pytest.approx(0.9)
    assert t["threat"]["components"] == ["height", "goals"]
    denied = await client.post(f"/api/v1/teams/{sam}/targets", headers=viewer, json={"name": "X"})
    assert denied.status_code == 403
    assert len((await client.get(f"/api/v1/teams/{sam}/targets", headers=viewer)).json()) == 1
    upd = await client.put(
        f"/api/v1/targets/{t['id']}", headers=coach, json={"name": "Hedef 4", "height_cm": 200}
    )
    assert upd.json()["threat"]["value"] == 1
    assert (await client.delete(f"/api/v1/targets/{t['id']}", headers=viewer)).status_code == 403
    assert (await client.delete(f"/api/v1/targets/{t['id']}", headers=coach)).status_code == 204
    assert (await client.get(f"/api/v1/teams/{sam}/targets", headers=viewer)).json() == []


async def _setup_marking(
    client: Any, coach: dict[str, str], superuser: asyncpg.Connection
) -> dict[str, str]:
    """Üç hedef ve beş oyunculuk kadro; ids ada göre."""
    sam = await _sam(superuser)
    ids: dict[str, str] = {}
    for name, height, aerial in (("T1", 196, 0.7), ("T2", 188, None), ("T3", 180, None)):
        ids[name] = (
            await _target(client, coach, sam, name=name, height_cm=height, aerial_win_pct=aerial)
        )["id"]
    for name, pos, height in (
        ("GK", "GK", 195),
        ("D1", "DEF", 183),
        ("D2", "DEF", 194),
        ("M1", "MID", 190),
        ("F1", "FWD", 172),
    ):
        ids[name] = (await _add(client, coach, name=name, position=pos, height_cm=height))["id"]
    return ids


async def test_marking_suggestion_override_and_save(
    client: Any,
    coach: dict[str, str],
    viewer: dict[str, str],
    fixture_id: str,
    superuser: asyncpg.Connection,
) -> None:
    ids = await _setup_marking(client, coach, superuser)
    url = f"/api/v1/fixtures/{fixture_id}/marking"
    first = await client.get(url, headers=viewer)
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["fixture"]["opponent"]["code"] == "SAM"
    assert data["saved"] is None
    assert data["versions"] == 0
    suggested = {r["target_id"]: r["suggested_marker_id"] for r in data["suggestion"]}
    # En güçlü hedef en güçlü savunmacıya; kaleci atanmaz.
    assert suggested[ids["T1"]] == ids["D2"]
    assert ids["GK"] not in suggested.values()
    assert [r["target_id"] for r in data["suggestion"]] == [ids["T1"], ids["T2"], ids["T3"]]

    # Viewer kaydedemez.
    body = {
        "base_version": 0,
        "assignments": [{"target_id": ids["T3"], "marker_id": ids["F1"]}],
        "zonal": [],
        "note": "F1 kısa hedefi alır",
    }
    assert (await client.put(url, headers=viewer, json=body)).status_code == 403

    saved = await client.put(url, headers=coach, json=body)
    assert saved.status_code == 200, saved.text
    plan = saved.json()["saved"]
    assert plan["version"] == 1
    assert plan["overridden"] == 1
    rows = {r["target_id"]: r for r in plan["rows"]}
    assert rows[ids["T3"]]["marker_id"] == ids["F1"]
    assert rows[ids["T3"]]["overridden"] is True
    # Belirtilmeyen hedefler öneriyle kaydedilir.
    assert rows[ids["T1"]]["marker_id"] == ids["D2"]
    assert rows[ids["T1"]]["overridden"] is False
    assert plan["note"] == "F1 kısa hedefi alır"

    # Yeniden okumada kayıt durur.
    again = (await client.get(url, headers=viewer)).json()
    assert again["saved"]["version"] == 1
    assert again["versions"] == 1

    # Eski sürümle kaydetme çakışır.
    assert (await client.put(url, headers=coach, json=body)).status_code == 409

    audit = await superuser.fetchrow(
        "select after from audit_log where action = 'marking.save' order by at desc limit 1"
    )
    assert '"overridden": 1' in audit["after"]


async def test_marking_zonal_and_validation(
    client: Any, coach: dict[str, str], fixture_id: str, superuser: asyncpg.Connection
) -> None:
    ids = await _setup_marking(client, coach, superuser)
    url = f"/api/v1/fixtures/{fixture_id}/marking"
    zonal = (await client.get(f"{url}?zonal={ids['D2']}", headers=coach)).json()
    assert zonal["zonal"] == [ids["D2"]]
    assert ids["D2"] not in {r["suggested_marker_id"] for r in zonal["suggestion"]}

    def put(assignments: list[dict[str, Any]], zonal: list[str] | None = None) -> Any:
        return client.put(
            url,
            headers=coach,
            json={"base_version": 0, "assignments": assignments, "zonal": zonal or []},
        )

    dup = await put(
        [
            {"target_id": ids["T1"], "marker_id": ids["D1"]},
            {"target_id": ids["T2"], "marker_id": ids["D1"]},
        ]
    )
    assert dup.json()["type"].endswith("duplicate-marker")
    zonal_marker = await put([{"target_id": ids["T1"], "marker_id": ids["D2"]}], [ids["D2"]])
    assert zonal_marker.json()["type"].endswith("zonal-marker")
    unknown = await put([{"target_id": str(uuid.uuid4()), "marker_id": None}])
    assert unknown.json()["type"].endswith("unknown-target")

    ok = await put([{"target_id": ids["T1"], "marker_id": None}], [ids["D2"]])
    assert ok.status_code == 200, ok.text
    saved = ok.json()["saved"]
    assert saved["zonal"] == [ids["D2"]]
    row = next(r for r in saved["rows"] if r["target_id"] == ids["T1"])
    assert row["marker_id"] is None
    # Kayıtlı alan oyuncuları sonraki önerinin varsayılanıdır.
    assert ok.json()["zonal"] == [ids["D2"]]


async def test_assignments_and_player_cards(
    client: Any,
    make_token: TokenFactory,
    coach: dict[str, str],
    viewer: dict[str, str],
    fixture_id: str,
    club: Seeded,
    superuser: asyncpg.Connection,
) -> None:
    ids = await _setup_marking(client, coach, superuser)
    routine = await client.post(
        "/api/v1/routines",
        headers=coach,
        json={"name": "Yakın direk", "sp_type": "corner", "side": "left", "diagram": DIAGRAM},
    )
    assert routine.status_code == 201, routine.text
    rid = routine.json()["id"]
    url = f"/api/v1/fixtures/{fixture_id}/assignments"
    assert (await client.get(url, headers=viewer)).json() == {"routines": []}

    body = {
        "routine_id": rid,
        "slots": [
            {"diagram_player_id": "np", "squad_player_id": ids["D2"]},
            {"diagram_player_id": "k", "squad_player_id": ids["F1"]},
        ],
    }
    assert (await client.put(url, headers=viewer, json=body)).status_code == 403
    bad = await client.put(
        url,
        headers=coach,
        json={**body, "slots": [{"diagram_player_id": "o1", "squad_player_id": ids["D2"]}]},
    )
    assert bad.json()["type"].endswith("unknown-slot")
    twice = await client.put(
        url,
        headers=coach,
        json={
            **body,
            "slots": [
                {"diagram_player_id": "np", "squad_player_id": ids["D2"]},
                {"diagram_player_id": "fp", "squad_player_id": ids["D2"]},
            ],
        },
    )
    assert twice.json()["type"].endswith("duplicate-player")

    saved = await client.put(url, headers=coach, json=body)
    assert saved.status_code == 200, saved.text
    out = saved.json()["routines"][0]
    assert out["name"] == "Yakın direk"
    assert out["assigned_version"] == 1
    slots = {s["diagram_player_id"]: s for s in out["slots"]}
    assert set(slots) == {"k", "np", "fp"}
    assert slots["np"]["squad_player_id"] == ids["D2"]
    assert slots["fp"]["squad_player_id"] is None
    assert slots["fp"]["label"] == "Arka"

    marking = await client.put(
        f"/api/v1/fixtures/{fixture_id}/marking",
        headers=coach,
        json={"base_version": 0, "assignments": [], "zonal": [ids["M1"]]},
    )
    assert marking.status_code == 200

    d2 = await _headers(make_token, superuser, club.tenant_a, "player", player=uuid.UUID(ids["D2"]))
    cards = await client.get(f"/api/v1/squad/{ids['D2']}/cards", headers=d2)
    assert cards.status_code == 200, cards.text
    card = cards.json()["cards"][0]
    assert card["fixture"]["opponent"]["code"] == "SAM"
    assert [(r["name"], r["role"]) for r in card["routines"]] == [
        ("Yakın direk", "near_post_runner")
    ]
    assert card["marking"]["zonal"] is False
    assert card["marking"]["target"]["name"] == "T1"

    m1 = await _headers(make_token, superuser, club.tenant_a, "player", player=uuid.UUID(ids["M1"]))
    m1_cards = (await client.get(f"/api/v1/squad/{ids['M1']}/cards", headers=m1)).json()
    assert m1_cards["cards"][0]["marking"] == {"target": None, "zonal": True}
    assert m1_cards["cards"][0]["routines"] == []

    # Oyuncu başkasının kartını göremez; antrenör görür; izleyici göremez.
    assert (await client.get(f"/api/v1/squad/{ids['D2']}/cards", headers=m1)).status_code == 403
    assert (await client.get(f"/api/v1/squad/{ids['D2']}/cards", headers=coach)).status_code == 200
    assert (await client.get(f"/api/v1/squad/{ids['D2']}/cards", headers=viewer)).status_code == 403

    # Tüm atamaları kaldırmak rutini (öneri ya da plan maddesine bağlı değilse) listeden ve
    # karttan çıkarır.
    cleared = await client.put(url, headers=coach, json={"routine_id": rid, "slots": []})
    assert cleared.json() == {"routines": []}
    after = (await client.get(f"/api/v1/squad/{ids['D2']}/cards", headers=d2)).json()
    assert after["cards"][0]["routines"] == []


async def test_marking_tenant_isolation(
    client: Any,
    make_token: TokenFactory,
    coach: dict[str, str],
    fixture_id: str,
    club: Seeded,
    superuser: asyncpg.Connection,
) -> None:
    await _setup_marking(client, coach, superuser)
    await client.put(
        f"/api/v1/fixtures/{fixture_id}/marking",
        headers=coach,
        json={"base_version": 0, "assignments": [], "zonal": []},
    )
    other = await _headers(make_token, superuser, club.tenant_b, "sp_coach")
    data = (await client.get(f"/api/v1/fixtures/{fixture_id}/marking", headers=other)).json()
    assert data["targets"] == []
    assert data["squad"] == []
    assert data["saved"] is None
