"""Kadro, rakip hedefleri, markaj önerisi ve rol atamaları (SPEC §7.3, ADR-0015, A-79 … A-87).

Formüller `kurgu_analytics` içindedir (hava skoru `metrics.players`, atama `recs.marking`);
burada yalnız kayıtlar okunur ve sonuçlar şemalara dönüştürülür.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from kurgu_analytics.metrics.players import aerial_score
from kurgu_analytics.recs.marking import Marker, Target, suggest_marking
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.problems import ProblemError
from kurgu_api.prep.service import user_ref
from kurgu_api.squad.schemas import (
    AerialOut,
    MarkingRow,
    MarkingSaved,
    SquadPlayerOut,
    TargetOut,
)

SQUAD_SQL = """
select p.id, p.name, p.shirt_number, p.position, p.height_cm, p.aerial_win_pct, p.jump_score,
       p.active, p.is_demo,
       exists (select 1 from memberships m where m.player_id = p.id) as has_account
from squad_players p
where (:all or p.active)
order by p.active desc, p.position = 'GK' desc, p.shirt_number nulls last, p.name
"""

TARGETS_SQL = """
select id, team_id, name, shirt_number, height_cm, aerial_win_pct, sp_goals, notes, updated_at
from opponent_targets where team_id = :team
order by shirt_number nulls last, name
"""

PLAN_SQL = """
select mp.version, mp.assignments, mp.zonal, mp.overridden, mp.note, mp.created_at,
       mp.created_by, u.display_name as created_by_name
from marking_plans mp left join users u on u.id = mp.created_by
where mp.fixture_id = :f order by mp.version desc limit 1
"""

POSITION_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def _aerial(score: Any) -> AerialOut | None:
    if score is None:
        return None
    return AerialOut(value=score.value, components=list(score.components))


def squad_out(row: Any) -> SquadPlayerOut:
    aerial = aerial_score(row.height_cm, _float(row.aerial_win_pct), _float(row.jump_score))
    return SquadPlayerOut(
        id=row.id,
        name=row.name,
        shirt_number=row.shirt_number,
        position=row.position,
        height_cm=row.height_cm,
        aerial_win_pct=_float(row.aerial_win_pct),
        jump_score=_float(row.jump_score),
        active=row.active,
        is_demo=row.is_demo,
        aerial=_aerial(aerial),
        has_account=row.has_account,
    )


def target_out(row: Any) -> TargetOut:
    threat = aerial_score(row.height_cm, _float(row.aerial_win_pct), None, row.sp_goals)
    return TargetOut(
        id=row.id,
        team_id=row.team_id,
        name=row.name,
        shirt_number=row.shirt_number,
        height_cm=row.height_cm,
        aerial_win_pct=_float(row.aerial_win_pct),
        sp_goals=row.sp_goals,
        notes=row.notes,
        threat=_aerial(threat),
        updated_at=row.updated_at,
    )


async def load_squad(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[SquadPlayerOut]:
    rows = await session.execute(text(SQUAD_SQL), {"all": include_inactive})
    return [squad_out(r) for r in rows]


async def squad_player(session: AsyncSession, player_id: uuid.UUID) -> SquadPlayerOut:
    row = (
        await session.execute(
            text(SQUAD_SQL.replace("where (:all or p.active)", "where p.id = :id")),
            {"id": player_id},
        )
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Squad player not found")
    return squad_out(row)


async def load_targets(session: AsyncSession, team_id: uuid.UUID) -> list[TargetOut]:
    return [target_out(r) for r in await session.execute(text(TARGETS_SQL), {"team": team_id})]


def suggestion(
    targets: Sequence[TargetOut], squad: Sequence[SquadPlayerOut], zonal: frozenset[uuid.UUID]
) -> list[MarkingRow]:
    """Önerilen eşleşme: her hedef için bir satır, tehdide göre sıralı (ADR-0015)."""
    scored = [t for t in targets if t.threat is not None]
    markers = [
        Marker(id=str(p.id), capacity=p.aerial.value, position=p.position)
        for p in squad
        if p.active and p.aerial is not None
    ]
    pairs = suggest_marking(
        [Target(id=str(t.id), threat=t.threat.value) for t in scored if t.threat is not None],
        markers,
        fixed=frozenset(str(z) for z in zonal),
    )
    by_target = {uuid.UUID(p.target_id): p for p in pairs}
    ordered = sorted(
        targets,
        key=lambda t: (t.threat is None, -(t.threat.value if t.threat else 0), t.name),
    )
    rows = []
    for t in ordered:
        pair = by_target.get(t.id)
        marker = uuid.UUID(pair.marker_id) if pair else None
        rows.append(
            MarkingRow(
                target_id=t.id,
                marker_id=marker,
                suggested_marker_id=marker,
                overridden=False,
                gap=round(pair.gap, 4) if pair else None,
            )
        )
    return rows


def gap_for(target: TargetOut | None, marker: SquadPlayerOut | None) -> float | None:
    if target is None or marker is None or target.threat is None or marker.aerial is None:
        return None
    return round(target.threat.value - marker.aerial.value, 4)


async def saved_plan(session: AsyncSession, fixture_id: uuid.UUID) -> MarkingSaved | None:
    row = (await session.execute(text(PLAN_SQL), {"f": fixture_id})).one_or_none()
    if row is None:
        return None
    return MarkingSaved(
        version=row.version,
        rows=[MarkingRow.model_validate(r) for r in row.assignments],
        zonal=[uuid.UUID(z) for z in row.zonal],
        overridden=row.overridden,
        note=row.note,
        created_at=row.created_at,
        created_by=user_ref(row.created_by, row.created_by_name),
    )


async def plan_versions(session: AsyncSession, fixture_id: uuid.UUID) -> int:
    count: int = (
        await session.execute(
            text("select count(*) from marking_plans where fixture_id = :f"), {"f": fixture_id}
        )
    ).scalar_one()
    return count
