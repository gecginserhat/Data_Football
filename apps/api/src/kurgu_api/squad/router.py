"""Kadro, rakip hedefleri, markaj ve rol atama uçları (SPEC §7.3, §11; ADR-0015; A-79 … A-87).

İzinler (SPEC §12.1 ve A-79): kadroyu okuma `read_analysis`, `load_wellness` ya da `edit_squad`;
düzenleme `edit_squad`; hesap bağlama `user_admin_audit`; rakip hedefleri, markaj kaydı ve rol
atamaları `decide_recommendations`, okuma `read_analysis`; görev kartı `player_cards` (oyuncu yalnız
kendi kartını görür). Her yazma denetim kaydına girer.
"""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from kurgu_api.core.audit import write_audit
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission, Scope, scope_for
from kurgu_api.identity.service import Principal
from kurgu_api.prep.facts import load_fixture
from kurgu_api.squad.schemas import (
    AccountLink,
    AssignmentsIn,
    AssignmentsOut,
    CardMarking,
    CardRoutine,
    CardsOut,
    MarkingIn,
    MarkingOut,
    MarkingRow,
    PlayerAccountOut,
    RoutineAssignmentOut,
    SlotOut,
    SquadPlayerIn,
    SquadPlayerOut,
    TargetIn,
    TargetOut,
    TaskCard,
)
from kurgu_api.squad.service import (
    gap_for,
    load_squad,
    load_targets,
    plan_versions,
    saved_plan,
    squad_player,
    suggestion,
    target_out,
)

router = APIRouter(tags=["squad"])

read = [Depends(require(Permission.READ_ANALYSIS))]
decide = [Depends(require(Permission.DECIDE_RECOMMENDATIONS))]
edit = [Depends(require(Permission.EDIT_SQUAD))]
admin = [Depends(require(Permission.USER_ADMIN_AUDIT))]


async def _squad_reader(principal: PrincipalDep) -> None:
    """Kadroyu analiz, kadro düzenleme ya da tam/özet yük izni olanlar okur; oyuncu okuyamaz."""
    if principal.tenant is None:
        raise ProblemError(400, "tenant-required", "Select a tenant")
    roles = principal.roles
    if (
        scope_for(roles, Permission.READ_ANALYSIS) is None
        and scope_for(roles, Permission.EDIT_SQUAD) is None
        and scope_for(roles, Permission.LOAD_WELLNESS) not in {"all", "summary"}
    ):
        raise ProblemError(403, "forbidden", "Missing permission to read the squad")


squad_read = [Depends(_squad_reader)]


def _tenant(principal: Principal) -> uuid.UUID:
    assert principal.tenant is not None
    return principal.tenant.tenant_id


# --- Kadro ---------------------------------------------------------------------------------------


@router.get(
    "/squad",
    response_model=list[SquadPlayerOut],
    operation_id="listSquad",
    dependencies=squad_read,
)
async def list_squad(session: SessionDep, include_inactive: bool = False) -> list[SquadPlayerOut]:
    """Kulübün kadrosu ve hava kapasitesi (A-79, A-81)."""
    return await load_squad(session, include_inactive=include_inactive)


def _player_values(body: SquadPlayerIn) -> dict[str, Any]:
    return body.model_dump()


async def _unique_shirt(session: SessionDep, body: SquadPlayerIn, player: uuid.UUID | None) -> None:
    if body.shirt_number is None or not body.active:
        return
    clash = (
        await session.execute(
            text(
                "select 1 from squad_players where active and shirt_number = :n"
                " and (cast(:id as uuid) is null or id <> :id)"
            ),
            {"n": body.shirt_number, "id": player},
        )
    ).first()
    if clash:
        raise ProblemError(409, "shirt-taken", f"Shirt number {body.shirt_number} is taken")


@router.post(
    "/squad",
    response_model=SquadPlayerOut,
    status_code=201,
    operation_id="createSquadPlayer",
    dependencies=edit,
)
async def create_squad_player(
    session: SessionDep, principal: PrincipalDep, body: SquadPlayerIn
) -> SquadPlayerOut:
    await _unique_shirt(session, body, None)
    values = _player_values(body)
    player_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into squad_players (tenant_id, name, shirt_number, position, height_cm,"
                " aerial_win_pct, jump_score, active, created_by) values (:t, :name, :shirt_number,"
                " :position, :height_cm, :aerial_win_pct, :jump_score, :active, :u) returning id"
            ),
            {**values, "t": _tenant(principal), "u": principal.user_id},
        )
    ).scalar_one()
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="squad.create",
        entity="squad_players",
        entity_id=player_id,
        after=values,
    )
    return await squad_player(session, player_id)


@router.put(
    "/squad/{player_id}",
    response_model=SquadPlayerOut,
    operation_id="updateSquadPlayer",
    dependencies=edit,
)
async def update_squad_player(
    session: SessionDep, principal: PrincipalDep, player_id: uuid.UUID, body: SquadPlayerIn
) -> SquadPlayerOut:
    """Oyuncuyu günceller; kadrodan çıkarmak için `active=false` (kayıtlar silinmez)."""
    before = await squad_player(session, player_id)
    await _unique_shirt(session, body, player_id)
    values = _player_values(body)
    await session.execute(
        text(
            "update squad_players set name = :name, shirt_number = :shirt_number,"
            " position = :position, height_cm = :height_cm, aerial_win_pct = :aerial_win_pct,"
            " jump_score = :jump_score, active = :active, updated_at = now() where id = :id"
        ),
        {**values, "id": player_id},
    )
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="squad.update",
        entity="squad_players",
        entity_id=player_id,
        before=SquadPlayerIn.model_validate(before.model_dump()).model_dump(),
        after=values,
    )
    return await squad_player(session, player_id)


@router.get(
    "/squad/accounts",
    response_model=list[PlayerAccountOut],
    operation_id="listPlayerAccounts",
    dependencies=admin,
)
async def list_player_accounts(session: SessionDep) -> list[PlayerAccountOut]:
    """Oyuncu rolündeki üyeler ve bağlı oldukları kadro kaydı."""
    rows = await session.execute(
        text(
            "select m.user_id, coalesce(u.display_name, u.email) as name, m.player_id"
            " from memberships m join users u on u.id = m.user_id"
            " where m.tenant_id = kurgu_current_tenant() and m.role = 'player' order by name"
        )
    )
    return [
        PlayerAccountOut(user_id=r.user_id, name=r.name, squad_player_id=r.player_id) for r in rows
    ]


@router.put(
    "/squad/{player_id}/account",
    status_code=204,
    operation_id="linkSquadAccount",
    dependencies=admin,
)
async def link_account(
    session: SessionDep, principal: PrincipalDep, player_id: uuid.UUID, body: AccountLink
) -> Response:
    """Oyuncu hesabını kadro kaydına bağlar (A-79). Kayıt başına en çok bir hesap."""
    await squad_player(session, player_id)
    await session.execute(
        text("update memberships set player_id = null where player_id = :p"), {"p": player_id}
    )
    if body.user_id is not None:
        updated = await session.execute(
            text(
                "update memberships set player_id = :p where user_id = :u and role = 'player'"
                " and tenant_id = kurgu_current_tenant()"
            ),
            {"p": player_id, "u": body.user_id},
        )
        if updated.rowcount == 0:  # type: ignore[attr-defined]
            raise ProblemError(422, "not-a-player", "User has no player membership")
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="squad.link_account",
        entity="squad_players",
        entity_id=player_id,
        after={"user_id": str(body.user_id) if body.user_id else None},
    )
    return Response(status_code=204)


# --- Rakip hedefleri -----------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/targets",
    response_model=list[TargetOut],
    operation_id="listOpponentTargets",
    dependencies=read,
)
async def list_targets(session: SessionDep, team_id: uuid.UUID) -> list[TargetOut]:
    return await load_targets(session, team_id)


async def _target(session: SessionDep, target_id: uuid.UUID) -> TargetOut:
    row = (
        await session.execute(
            text(
                "select id, team_id, name, shirt_number, height_cm, aerial_win_pct, sp_goals,"
                " notes, updated_at from opponent_targets where id = :id"
            ),
            {"id": target_id},
        )
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Target not found")
    return target_out(row)


@router.post(
    "/teams/{team_id}/targets",
    response_model=TargetOut,
    status_code=201,
    operation_id="createOpponentTarget",
    dependencies=decide,
)
async def create_target(
    session: SessionDep, principal: PrincipalDep, team_id: uuid.UUID, body: TargetIn
) -> TargetOut:
    team = (
        await session.execute(text("select id from teams where id = :id"), {"id": team_id})
    ).one_or_none()
    if team is None:
        raise ProblemError(404, "not-found", "Team not found")
    values = body.model_dump()
    target_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into opponent_targets (tenant_id, team_id, name, shirt_number, height_cm,"
                " aerial_win_pct, sp_goals, notes, created_by) values (:t, :team, :name,"
                " :shirt_number, :height_cm, :aerial_win_pct, :sp_goals, :notes, :u) returning id"
            ),
            {**values, "t": _tenant(principal), "team": team_id, "u": principal.user_id},
        )
    ).scalar_one()
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="target.create",
        entity="opponent_targets",
        entity_id=target_id,
        after={**values, "team_id": str(team_id)},
    )
    return await _target(session, target_id)


@router.put(
    "/targets/{target_id}",
    response_model=TargetOut,
    operation_id="updateOpponentTarget",
    dependencies=decide,
)
async def update_target(
    session: SessionDep, principal: PrincipalDep, target_id: uuid.UUID, body: TargetIn
) -> TargetOut:
    before = await _target(session, target_id)
    values = body.model_dump()
    await session.execute(
        text(
            "update opponent_targets set name = :name, shirt_number = :shirt_number,"
            " height_cm = :height_cm, aerial_win_pct = :aerial_win_pct, sp_goals = :sp_goals,"
            " notes = :notes, updated_at = now() where id = :id"
        ),
        {**values, "id": target_id},
    )
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="target.update",
        entity="opponent_targets",
        entity_id=target_id,
        before=TargetIn.model_validate(before.model_dump()).model_dump(),
        after=values,
    )
    return await _target(session, target_id)


@router.delete(
    "/targets/{target_id}",
    status_code=204,
    operation_id="deleteOpponentTarget",
    dependencies=decide,
)
async def delete_target(
    session: SessionDep, principal: PrincipalDep, target_id: uuid.UUID
) -> Response:
    """Hedefi listeden çıkarır. Kayıtlı markaj sürümleri değişmez."""
    before = await _target(session, target_id)
    await session.execute(text("delete from opponent_targets where id = :id"), {"id": target_id})
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="target.delete",
        entity="opponent_targets",
        entity_id=target_id,
        before=TargetIn.model_validate(before.model_dump()).model_dump(),
        after={},
    )
    return Response(status_code=204)


# --- Markaj --------------------------------------------------------------------------------------


@router.get(
    "/fixtures/{fixture_id}/marking",
    response_model=MarkingOut,
    operation_id="getFixtureMarking",
    dependencies=read,
)
async def get_marking(
    session: SessionDep, fixture_id: uuid.UUID, zonal: str | None = None
) -> MarkingOut:
    """Rakip hedefleri, kadro, Macar algoritması önerisi ve son kayıtlı eşleşme (ADR-0015).

    `zonal`: virgülle ayrılmış kadro kimlikleri; öneride sabit (alan savunması) tutulur. Verilmezse
    son kayıttaki alan oyuncuları kullanılır.
    """
    fixture = await load_fixture(session, fixture_id)
    saved = await saved_plan(session, fixture_id)
    if zonal is not None:
        try:
            fixed = frozenset(uuid.UUID(z) for z in zonal.split(",") if z)
        except ValueError as exc:
            raise ProblemError(422, "invalid-zonal", "zonal must be a list of ids") from exc
    else:
        fixed = frozenset(saved.zonal) if saved else frozenset()
    targets = await load_targets(session, fixture.out.opponent.id)
    squad = await load_squad(session)
    return MarkingOut(
        fixture=fixture.out,
        targets=targets,
        squad=squad,
        zonal=sorted(fixed, key=str),
        suggestion=suggestion(targets, squad, fixed),
        saved=saved,
        versions=await plan_versions(session, fixture_id),
    )


@router.put(
    "/fixtures/{fixture_id}/marking",
    response_model=MarkingOut,
    operation_id="saveFixtureMarking",
    dependencies=decide,
)
async def save_marking(
    session: SessionDep, principal: PrincipalDep, fixture_id: uuid.UUID, body: MarkingIn
) -> MarkingOut:
    """Eşleşmeyi yeni sürüm olarak kaydeder; öneriden farklı satırlar "elle değiştirildi"."""
    fixture = await load_fixture(session, fixture_id)
    await session.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"marking:{fixture_id}"},
    )
    current = await plan_versions(session, fixture_id)
    if body.base_version != current:
        raise ProblemError(409, "version-conflict", f"Marking was saved as version {current}")
    targets = {t.id: t for t in await load_targets(session, fixture.out.opponent.id)}
    squad = {p.id: p for p in await load_squad(session)}
    zonal = frozenset(body.zonal)
    if unknown := zonal - squad.keys():
        raise ProblemError(422, "unknown-player", f"Unknown squad players: {sorted(unknown)}")
    seen_targets: set[uuid.UUID] = set()
    seen_markers: set[uuid.UUID] = set()
    for pair in body.assignments:
        if pair.target_id not in targets:
            raise ProblemError(422, "unknown-target", f"Unknown target {pair.target_id}")
        if pair.target_id in seen_targets:
            raise ProblemError(422, "duplicate-target", f"Target {pair.target_id} is repeated")
        seen_targets.add(pair.target_id)
        if pair.marker_id is None:
            continue
        if pair.marker_id not in squad:
            raise ProblemError(422, "unknown-player", f"Unknown squad player {pair.marker_id}")
        if pair.marker_id in zonal:
            raise ProblemError(422, "zonal-marker", "A zonal player cannot mark a target")
        if pair.marker_id in seen_markers:
            raise ProblemError(422, "duplicate-marker", "A player can mark only one target")
        seen_markers.add(pair.marker_id)

    suggested = {
        r.target_id: r for r in suggestion(list(targets.values()), list(squad.values()), zonal)
    }
    chosen = {p.target_id: p.marker_id for p in body.assignments}
    rows: list[MarkingRow] = []
    for target_id, row in suggested.items():
        marker = chosen.get(target_id, row.suggested_marker_id)
        rows.append(
            MarkingRow(
                target_id=target_id,
                marker_id=marker,
                suggested_marker_id=row.suggested_marker_id,
                overridden=marker != row.suggested_marker_id,
                gap=gap_for(targets[target_id], squad.get(marker) if marker else None),
            )
        )
    overridden = sum(1 for r in rows if r.overridden)
    payload = [r.model_dump(mode="json") for r in rows]
    plan_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into marking_plans (tenant_id, fixture_id, version, assignments, zonal,"
                " suggested, overridden, note, created_by) values (:t, :f, :v,"
                " cast(:a as jsonb), cast(:z as jsonb), cast(:s as jsonb), :o, :note, :u)"
                " returning id"
            ),
            {
                "t": _tenant(principal),
                "f": fixture_id,
                "v": current + 1,
                "a": json.dumps(payload),
                "z": json.dumps(sorted(str(z) for z in zonal)),
                "s": json.dumps(
                    [
                        {"target_id": str(r.target_id), "marker_id": str(r.suggested_marker_id)}
                        for r in suggested.values()
                        if r.suggested_marker_id
                    ]
                ),
                "o": overridden,
                "note": body.note,
                "u": principal.user_id,
            },
        )
    ).scalar_one()
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="marking.save",
        entity="marking_plans",
        entity_id=plan_id,
        after={
            "fixture_id": str(fixture_id),
            "version": current + 1,
            "overridden": overridden,
            "assignments": payload,
        },
    )
    return await get_marking(session, fixture_id, None)


# --- Rol atamaları -------------------------------------------------------------------------------

SOURCES_SQL = """
select routine_id, title from recommendations
where fixture_id = :f and status = 'accepted' and routine_id is not null
union all
select pi.routine_id, pi.title from plan_items pi join fixture_plans fp on fp.id = pi.plan_id
where fp.fixture_id = :f and pi.routine_id is not null
union all
select distinct routine_id, null from routine_assignments where fixture_id = :f
"""

ROUTINES_SQL = """
select r.id, r.name, r.sp_type, r.current_version, v.diagram
from routines r
join routine_versions v on v.routine_id = r.id and v.version = r.current_version
where r.id = any(:ids)
order by r.name
"""


def _own_players(diagram: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in diagram.get("players", []) if p.get("team") == "own"]


async def _assignments(session: SessionDep, fixture_id: uuid.UUID) -> AssignmentsOut:
    sources: dict[uuid.UUID, list[str]] = {}
    for row in await session.execute(text(SOURCES_SQL), {"f": fixture_id}):
        titles = sources.setdefault(row.routine_id, [])
        if row.title and row.title not in titles:
            titles.append(row.title)
    assigned: dict[uuid.UUID, dict[str, tuple[uuid.UUID, int]]] = {}
    for row in await session.execute(
        text(
            "select routine_id, routine_version, diagram_player_id, squad_player_id"
            " from routine_assignments where fixture_id = :f"
        ),
        {"f": fixture_id},
    ):
        assigned.setdefault(row.routine_id, {})[row.diagram_player_id] = (
            row.squad_player_id,
            row.routine_version,
        )
    out = []
    for row in await session.execute(text(ROUTINES_SQL), {"ids": list(sources)}):
        slots_map = assigned.get(row.id, {})
        versions = {v for _, v in slots_map.values()}
        out.append(
            RoutineAssignmentOut(
                routine_id=row.id,
                name=row.name,
                sp_type=row.sp_type,
                version=row.current_version,
                sources=sources[row.id],
                slots=[
                    SlotOut(
                        diagram_player_id=p["id"],
                        role=p["role"],
                        number=p.get("number"),
                        label=p.get("label"),
                        squad_player_id=slots_map[p["id"]][0] if p["id"] in slots_map else None,
                    )
                    for p in _own_players(row.diagram)
                ],
                assigned_version=min(versions) if versions else None,
            )
        )
    return AssignmentsOut(routines=out)


@router.get(
    "/fixtures/{fixture_id}/assignments",
    response_model=AssignmentsOut,
    operation_id="getFixtureAssignments",
    dependencies=read,
)
async def get_assignments(session: SessionDep, fixture_id: uuid.UUID) -> AssignmentsOut:
    """Fikstürün rutinleri (kabul edilen öneri, plan maddesi ya da önceki atama) ve rolleri."""
    await load_fixture(session, fixture_id)
    return await _assignments(session, fixture_id)


@router.put(
    "/fixtures/{fixture_id}/assignments",
    response_model=AssignmentsOut,
    operation_id="saveFixtureAssignments",
    dependencies=decide,
)
async def save_assignments(
    session: SessionDep, principal: PrincipalDep, fixture_id: uuid.UUID, body: AssignmentsIn
) -> AssignmentsOut:
    """Bir rutinin rollerini kadro oyuncularına atar (A-87). Boş oyuncu atamayı kaldırır."""
    await load_fixture(session, fixture_id)
    routine = (
        await session.execute(
            text(ROUTINES_SQL.replace("r.id = any(:ids)", "r.id = :id")), {"id": body.routine_id}
        )
    ).one_or_none()
    if routine is None:
        raise ProblemError(404, "not-found", "Routine not found")
    roles = {p["id"]: p["role"] for p in _own_players(routine.diagram)}
    squad = {p.id for p in await load_squad(session)}
    used: set[uuid.UUID] = set()
    for slot in body.slots:
        if slot.diagram_player_id not in roles:
            raise ProblemError(422, "unknown-slot", f"Unknown role {slot.diagram_player_id}")
        if slot.squad_player_id is None:
            continue
        if slot.squad_player_id not in squad:
            raise ProblemError(
                422, "unknown-player", f"Unknown squad player {slot.squad_player_id}"
            )
        if slot.squad_player_id in used:
            raise ProblemError(422, "duplicate-player", "A player can take only one role")
        used.add(slot.squad_player_id)
    tenant = _tenant(principal)
    await session.execute(
        text("delete from routine_assignments where fixture_id = :f and routine_id = :r"),
        {"f": fixture_id, "r": body.routine_id},
    )
    for slot in body.slots:
        if slot.squad_player_id is None:
            continue
        await session.execute(
            text(
                "insert into routine_assignments (tenant_id, fixture_id, routine_id,"
                " routine_version, diagram_player_id, role, squad_player_id, assigned_by)"
                " values (:t, :f, :r, :v, :slot, :role, :p, :u)"
            ),
            {
                "t": tenant,
                "f": fixture_id,
                "r": body.routine_id,
                "v": routine.current_version,
                "slot": slot.diagram_player_id,
                "role": roles[slot.diagram_player_id],
                "p": slot.squad_player_id,
                "u": principal.user_id,
            },
        )
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action="assignments.save",
        entity="routines",
        entity_id=body.routine_id,
        after={
            "fixture_id": str(fixture_id),
            "version": routine.current_version,
            "slots": {s.diagram_player_id: str(s.squad_player_id) for s in body.slots},
        },
    )
    return await _assignments(session, fixture_id)


# --- Görev kartları ------------------------------------------------------------------------------

CARD_FIXTURES_SQL = """
with latest as (
  select distinct on (fixture_id) fixture_id, assignments, zonal
  from marking_plans order by fixture_id, version desc
)
select m.id from matches m
where m.status = 'scheduled' and (
  exists (select 1 from routine_assignments ra
          where ra.fixture_id = m.id and ra.squad_player_id = :p)
  or exists (
    select 1 from latest l where l.fixture_id = m.id and (
      l.zonal ? cast(:p as text)
      or exists (select 1 from jsonb_array_elements(l.assignments) a
                 where a->>'marker_id' = cast(:p as text))
    )
  )
)
order by m.kickoff_at nulls last, m.week
limit 5
"""

CARD_ROUTINES_SQL = """
select ra.routine_id, r.name, r.sp_type, ra.routine_version, ra.diagram_player_id, ra.role,
       v.diagram
from routine_assignments ra
join routines r on r.id = ra.routine_id
join routine_versions v on v.routine_id = ra.routine_id and v.version = ra.routine_version
where ra.fixture_id = :f and ra.squad_player_id = :p
order by r.name
"""


@router.get(
    "/squad/{player_id}/cards",
    response_model=CardsOut,
    operation_id="getPlayerCards",
)
async def get_cards(
    session: SessionDep,
    principal: PrincipalDep,
    player_id: uuid.UUID,
    scope: Scope = Depends(require(Permission.PLAYER_CARDS)),  # noqa: B008
) -> CardsOut:
    """Oyuncunun yaklaşan maçlardaki görev kartları: rutin rolü ve markaj görevi (A-87)."""
    assert principal.tenant is not None
    if scope == "own" and principal.tenant.player_id != player_id:
        raise ProblemError(403, "forbidden", "Players can see only their own cards")
    player = await squad_player(session, player_id)
    cards = []
    fixtures = await session.execute(text(CARD_FIXTURES_SQL), {"p": player_id})
    for (fixture_id,) in fixtures.all():
        fixture = await load_fixture(session, fixture_id)
        routines = []
        for row in await session.execute(
            text(CARD_ROUTINES_SQL), {"f": fixture_id, "p": player_id}
        ):
            slot = next(
                (p for p in _own_players(row.diagram) if p["id"] == row.diagram_player_id), {}
            )
            routines.append(
                CardRoutine(
                    routine_id=row.routine_id,
                    name=row.name,
                    sp_type=row.sp_type,
                    version=row.routine_version,
                    diagram_player_id=row.diagram_player_id,
                    role=row.role,
                    number=slot.get("number"),
                    label=slot.get("label"),
                    diagram=row.diagram,
                )
            )
        marking = None
        saved = await saved_plan(session, fixture_id)
        if saved is not None:
            if player_id in saved.zonal:
                marking = CardMarking(target=None, zonal=True)
            else:
                row_for = next((r for r in saved.rows if r.marker_id == player_id), None)
                if row_for is not None:
                    targets = {
                        t.id: t for t in await load_targets(session, fixture.out.opponent.id)
                    }
                    marking = CardMarking(target=targets.get(row_for.target_id), zonal=False)
        cards.append(TaskCard(fixture=fixture.out, routines=routines, marking=marking))
    return CardsOut(player=player, cards=cards)
