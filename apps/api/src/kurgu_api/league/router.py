"""Lig ve takım uçları (SPEC §11). Veriler RLS ile lisanslı kiracıya sınırlıdır.

Faz 1'de yalnızca kayıttaki ham değerler döner (tohum ya da sağlayıcı). Sıralar, lig
kıyasları ve büzülmüş oranlar Faz 2'de `kurgu_analytics.metrics` üzerinden eklenir.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import text

from kurgu_api.core.http import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    decode_cursor,
    encode_cursor,
    etag_response,
)
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.league.schemas import (
    CompetitionRef,
    SeasonOut,
    SeasonPage,
    StandingRowOut,
    StandingsOut,
    TeamMetricsOut,
    TeamMetricsPage,
    TeamOut,
    TeamProfileOut,
    TeamRef,
)

router = APIRouter(tags=["league"], dependencies=[Depends(require(Permission.READ_ANALYSIS))])
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]

SEASON_SQL = """
select s.id, s.code, s.label, s.matches_per_team,
       c.id as competition_id, c.code as competition_code, c.name as competition_name
from seasons s join competitions c on c.id = s.competition_id
"""


def _season(row: Any) -> SeasonOut:
    return SeasonOut(
        id=row.id,
        code=row.code,
        label=row.label,
        matches_per_team=row.matches_per_team,
        competition=CompetitionRef(
            id=row.competition_id, code=row.competition_code, name=row.competition_name
        ),
    )


def _number(value: Decimal) -> float:
    return float(value)


async def _get_season(session: SessionDep, season_id: uuid.UUID) -> SeasonOut:
    row = (await session.execute(text(SEASON_SQL + " where s.id = :id"), {"id": season_id})).first()
    if row is None:
        raise ProblemError(404, "not-found", "Season not found")
    return _season(row)


@router.get("/seasons", response_model=SeasonPage, operation_id="listSeasons")
async def list_seasons(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Response:
    after = decode_cursor(cursor, 3)
    where, params = "", {"limit": limit + 1}
    if after:
        where = " where (c.code, s.code, s.id::text) > (:c, :s, :i)"
        params |= {"c": after[0], "s": after[1], "i": after[2]}
    rows = (
        await session.execute(
            text(SEASON_SQL + where + " order by c.code, s.code, s.id::text limit :limit"), params
        )
    ).all()
    items = [_season(r) for r in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = encode_cursor([last.competition.code, last.code, str(last.id)])
    return etag_response(request, SeasonPage(items=items, next_cursor=next_cursor))


STANDINGS_SQL = """
select st.position, st.played, st.won, st.drawn, st.lost, st.gf, st.ga, st.pts, st.source,
       t.id as team_id, t.code as team_code, t.name as team_name
from standings_snapshots st join teams t on t.id = st.team_id
where st.season_id = :season and st.week = :week
order by st.position, t.code
"""


def _standing(row: Any) -> StandingRowOut:
    return StandingRowOut(
        position=row.position,
        team=TeamRef(id=row.team_id, code=row.team_code, name=row.team_name),
        played=row.played,
        won=row.won,
        drawn=row.drawn,
        lost=row.lost,
        gf=row.gf,
        ga=row.ga,
        pts=row.pts,
    )


async def _latest_week(session: SessionDep, season_id: uuid.UUID) -> int | None:
    week: int | None = (
        await session.execute(
            text("select max(week) from standings_snapshots where season_id = :s"),
            {"s": season_id},
        )
    ).scalar_one()
    return week


@router.get(
    "/seasons/{season_id}/standings", response_model=StandingsOut, operation_id="getStandings"
)
async def get_standings(
    request: Request,
    session: SessionDep,
    season_id: uuid.UUID,
    week: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    """Puan durumu. `week` verilmezse kayıttaki son hafta."""
    await _get_season(session, season_id)
    week = week or await _latest_week(session, season_id)
    rows = (
        (await session.execute(text(STANDINGS_SQL), {"season": season_id, "week": week})).all()
        if week
        else []
    )
    if not rows:
        raise ProblemError(404, "not-found", "No standings for this season and week")
    return etag_response(
        request,
        StandingsOut(
            season_id=season_id,
            week=week or 0,
            source=rows[0].source,
            rows=[_standing(r) for r in rows],
        ),
    )


# Sezon başına en güncel kesit: tamamlanmış sezonda as_of_week boş, sürende en büyük hafta.
METRICS_SQL = """
with latest as (
  select team_id, source, max(coalesce(as_of_week, 1000)) as w
  from team_season_stats where season_id = :season group by team_id, source
)
select t.id as team_id, t.code as team_code, t.name as team_name,
       v.metric, v.value, v.as_of_week, v.source
from team_season_stats v
join latest l on l.team_id = v.team_id and l.source = v.source
  and coalesce(v.as_of_week, 1000) = l.w
join teams t on t.id = v.team_id
where v.season_id = :season {filter}
order by t.code, t.id, v.source, v.metric
"""


def _group_metrics(rows: list[Any]) -> list[TeamMetricsOut]:
    grouped: dict[tuple[uuid.UUID, str], TeamMetricsOut] = {}
    for r in rows:
        key = (r.team_id, r.source)
        item = grouped.get(key)
        if item is None:
            item = grouped[key] = TeamMetricsOut(
                team=TeamRef(id=r.team_id, code=r.team_code, name=r.team_name),
                as_of_week=r.as_of_week,
                source=r.source,
                metrics={},
            )
        item.metrics[r.metric] = _number(r.value)
    return list(grouped.values())


@router.get(
    "/seasons/{season_id}/team-metrics",
    response_model=TeamMetricsPage,
    operation_id="listTeamMetrics",
)
async def list_team_metrics(
    request: Request,
    session: SessionDep,
    season_id: uuid.UUID,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Response:
    """Takım başına sezon metrikleri (ham kayıt değerleri), takım koduna göre sıralı."""
    await _get_season(session, season_id)
    after = decode_cursor(cursor, 2)
    params: dict[str, Any] = {"season": season_id}
    team_filter = ""
    if after:
        team_filter = "and (t.code, t.id::text) > (:c, :i)"
        params |= {"c": after[0], "i": after[1]}
    rows = (await session.execute(text(METRICS_SQL.format(filter=team_filter)), params)).all()
    items = _group_metrics(list(rows))
    next_cursor = None
    if len(items) > limit:
        items = items[:limit]
        last = items[-1].team
        next_cursor = encode_cursor([last.code, str(last.id)])
    return etag_response(
        request, TeamMetricsPage(season_id=season_id, items=items, next_cursor=next_cursor)
    )


@router.get(
    "/teams/{team_id}/profile", response_model=TeamProfileOut, operation_id="getTeamProfile"
)
async def get_team_profile(
    request: Request,
    session: SessionDep,
    team_id: uuid.UUID,
    season: Annotated[uuid.UUID, Query(description="Sezon kimliği")],
) -> Response:
    """Takım profili: sezon metrikleri ve son puan durumu satırı (Faz 1: ham değerler)."""
    team = (
        await session.execute(
            text("select id, code, name, official_name from teams where id = :id"),
            {"id": team_id},
        )
    ).first()
    if team is None:
        raise ProblemError(404, "not-found", "Team not found")
    season_out = await _get_season(session, season)

    rows = (
        await session.execute(
            text(METRICS_SQL.format(filter="and t.id = :team")),
            {"season": season, "team": team_id},
        )
    ).all()
    groups = _group_metrics(list(rows))
    # Birden çok kaynak varsa Faz 1'de ilk kaynak (tohum ya da sağlayıcı) gösterilir.
    metrics = groups[0] if groups else None

    week = await _latest_week(session, season)
    standing = None
    if week:
        row = (
            await session.execute(
                text(STANDINGS_SQL.replace("order by", "and st.team_id = :team order by")),
                {"season": season, "week": week, "team": team_id},
            )
        ).first()
        standing = _standing(row) if row else None

    return etag_response(
        request,
        TeamProfileOut(
            team=TeamOut(
                id=team.id, code=team.code, name=team.name, official_name=team.official_name
            ),
            season=season_out,
            as_of_week=metrics.as_of_week if metrics else None,
            source=metrics.source if metrics else None,
            metrics=metrics.metrics if metrics else {},
            standing=standing,
            standing_week=week if standing else None,
        ),
    )
