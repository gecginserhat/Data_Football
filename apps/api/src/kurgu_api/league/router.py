"""Lig, takım ve fikstür uçları (SPEC §11). Veriler RLS ile lisanslı kiracıya sınırlıdır.

Türetilmiş metrikler, sıralar, lig kıyasları ve büzülmüş değerler `league.metrics` üzerinden
`kurgu_analytics.metrics` ile hesaplanır; bu dosyada formül yoktur.
"""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

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
from kurgu_api.league.metrics import compute_season_metrics
from kurgu_api.league.schemas import (
    BenchmarksOut,
    CompetitionRef,
    FixtureOut,
    FixturePage,
    FormOut,
    ReferenceOut,
    SeasonOut,
    SeasonPage,
    SetPieceOut,
    SetPiecePage,
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


async def _club_team_id(session: SessionDep) -> uuid.UUID | None:
    club: uuid.UUID | None = (
        await session.execute(
            text("select club_team_id from tenants where id = kurgu_current_tenant()")
        )
    ).scalar_one_or_none()
    return club


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
    """Takım başına sezon metrikleri: değer, lig sırası, yüzdelik, büzülmüş değer, az veri ve
    kaynak (SPEC §6). Takım koduna göre sıralı."""
    await _get_season(session, season_id)
    after = decode_cursor(cursor, 2)
    computed = await compute_season_metrics(session, season_id)
    teams = sorted(computed.teams.values(), key=lambda t: (t.code, str(t.id)))
    if after:
        teams = [t for t in teams if (t.code, str(t.id)) > (after[0], after[1])]
    items = [
        TeamMetricsOut(
            team=t,
            as_of_week=computed.as_of_week.get(t.id),
            values=computed.values[t.id],
            inputs=computed.inputs.get(t.id, {}),
        )
        for t in teams[:limit]
    ]
    next_cursor = None
    if len(teams) > limit:
        last = items[-1].team
        next_cursor = encode_cursor([last.code, str(last.id)])
    return etag_response(
        request,
        TeamMetricsPage(
            season_id=season_id,
            club_team_id=await _club_team_id(session),
            items=items,
            next_cursor=next_cursor,
        ),
    )


REFERENCES_SQL = """
select c.id as competition_id, c.code as competition_code, c.name as competition_name,
       s.code as season_code, st.metric, st.value, st.source
from season_stats st
join seasons s on s.id = st.season_id
join competitions c on c.id = s.competition_id
where s.id = :season or (s.code = :code and s.competition_id <> :competition)
order by c.code, st.metric
"""


@router.get(
    "/seasons/{season_id}/benchmarks", response_model=BenchmarksOut, operation_id="getBenchmarks"
)
async def get_benchmarks(request: Request, session: SessionDep, season_id: uuid.UUID) -> Response:
    """Lig kıyasları: metrik başına en düşük, en yüksek ve ortalama; lig toplamları; aynı sezonun
    kayıttaki referans kıyasları (ör. Premier League)."""
    season = await _get_season(session, season_id)
    computed = await compute_season_metrics(session, season_id)
    rows = await session.execute(
        text(REFERENCES_SQL),
        {"season": season_id, "code": season.code, "competition": season.competition.id},
    )
    references = [
        ReferenceOut(
            competition=CompetitionRef(
                id=r.competition_id, code=r.competition_code, name=r.competition_name
            ),
            season_code=r.season_code,
            metric=r.metric,
            value=float(r.value),
            source=r.source,
        )
        for r in rows
    ]
    return etag_response(
        request,
        BenchmarksOut(
            season_id=season_id,
            metrics=computed.benchmarks,
            totals=computed.totals,
            references=references,
        ),
    )


FORM_SQL = """
select m.id, m.week, m.home_team_id, m.away_team_id, m.home_score, m.away_score,
       t.id as opp_id, t.code as opp_code, t.name as opp_name
from matches m
join teams t on t.id = case when m.home_team_id = :team then m.away_team_id
                            else m.home_team_id end
where m.season_id = :season and m.status = 'finished'
  and (m.home_team_id = :team or m.away_team_id = :team)
order by m.week desc nulls last, m.kickoff_at desc nulls last, m.id
limit 5
"""


def _form(row: Any, team_id: uuid.UUID) -> FormOut:
    home = row.home_team_id == team_id
    gf, ga = (row.home_score, row.away_score) if home else (row.away_score, row.home_score)
    result: Literal["W", "D", "L"] = "W" if gf > ga else "D" if gf == ga else "L"
    return FormOut(
        match_id=row.id,
        week=row.week,
        opponent=TeamRef(id=row.opp_id, code=row.opp_code, name=row.opp_name),
        home=home,
        goals_for=gf,
        goals_against=ga,
        result=result,
    )


async def _get_team(session: SessionDep, team_id: uuid.UUID) -> Any:
    team = (
        await session.execute(
            text("select id, code, name, official_name from teams where id = :id"),
            {"id": team_id},
        )
    ).first()
    if team is None:
        raise ProblemError(404, "not-found", "Team not found")
    return team


@router.get(
    "/teams/{team_id}/profile", response_model=TeamProfileOut, operation_id="getTeamProfile"
)
async def get_team_profile(
    request: Request,
    session: SessionDep,
    team_id: uuid.UUID,
    season: Annotated[uuid.UUID, Query(description="Sezon kimliği")],
) -> Response:
    """Takım profili: metrikler ve sıralar, lig kıyasları, kendi kulübümüzün değerleri, son puan
    durumu satırı ve son 5 maçın formu."""
    team = await _get_team(session, team_id)
    season_out = await _get_season(session, season)
    computed = await compute_season_metrics(session, season)
    club_id = await _club_team_id(session)

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
    form_rows = await session.execute(text(FORM_SQL), {"season": season, "team": team_id})

    return etag_response(
        request,
        TeamProfileOut(
            team=TeamOut(
                id=team.id, code=team.code, name=team.name, official_name=team.official_name
            ),
            season=season_out,
            as_of_week=computed.as_of_week.get(team_id),
            values=computed.values.get(team_id, {}),
            benchmarks=computed.benchmarks,
            club=computed.teams.get(club_id) if club_id else None,
            club_values=computed.values.get(club_id, {}) if club_id else {},
            standing=standing,
            standing_week=week if standing else None,
            form=[_form(r, team_id) for r in form_rows],
        ),
    )


SET_PIECES_SQL = """
select p.id, p.match_id, m.week, p.period, p.start_time_s, p.sp_type, p.sp_subtype, p.side,
       p.target_zone, p.first_contact_team_id, p.outcome, p.shots, p.xg_total, p.goal,
       p.phase_of_goal, p.source, t.id as opp_id, t.code as opp_code, t.name as opp_name
from set_pieces p
join matches m on m.id = p.match_id
join teams t on t.id = case when m.home_team_id = p.team_id then m.away_team_id
                            else m.home_team_id end
where p.team_id = :team and m.season_id = :season {filters}
order by p.match_id, p.period, p.start_time_s, p.id
limit :limit
"""
SpType = Literal["corner", "free_kick", "throw_in"]


@router.get(
    "/teams/{team_id}/set-pieces", response_model=SetPiecePage, operation_id="listTeamSetPieces"
)
async def list_team_set_pieces(
    request: Request,
    session: SessionDep,
    team_id: uuid.UUID,
    season: Annotated[uuid.UUID, Query(description="Sezon kimliği")],
    sp_type: Annotated[SpType | None, Query(alias="type", description="Duran top türü")] = None,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Response:
    """Takımın sezondaki duran top dizileri (olay verisi ya da kulübün kendi kaydı)."""
    await _get_team(session, team_id)
    await _get_season(session, season)
    after = decode_cursor(cursor, 4)
    filters = ""
    params: dict[str, Any] = {"team": team_id, "season": season, "limit": limit + 1}
    if sp_type:
        filters += " and p.sp_type = :type"
        params["type"] = sp_type
    if after:
        filters += (
            " and (p.match_id, p.period, p.start_time_s, p.id)"
            " > (cast(:m as uuid), :p, :s, cast(:i as uuid))"
        )
        params |= {"m": after[0], "p": after[1], "s": after[2], "i": after[3]}
    rows = (await session.execute(text(SET_PIECES_SQL.format(filters=filters)), params)).all()
    items = [
        SetPieceOut(
            id=r.id,
            match_id=r.match_id,
            week=r.week,
            opponent=TeamRef(id=r.opp_id, code=r.opp_code, name=r.opp_name),
            period=r.period,
            start_time_s=r.start_time_s,
            sp_type=r.sp_type,
            sp_subtype=r.sp_subtype,
            side=r.side,
            target_zone=r.target_zone,
            first_contact_team_id=r.first_contact_team_id,
            outcome=r.outcome,
            shots=r.shots,
            xg_total=r.xg_total,
            goal=r.goal,
            phase_of_goal=r.phase_of_goal,
            source=r.source,
        )
        for r in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(
            [str(last.match_id), last.period, last.start_time_s, str(last.id)]
        )
    return etag_response(request, SetPiecePage(items=items, next_cursor=next_cursor))


FIXTURES_SQL = """
select m.id, m.season_id, m.week, m.kickoff_at, m.status, m.home_score, m.away_score,
       h.id as home_id, h.code as home_code, h.name as home_name,
       a.id as away_id, a.code as away_code, a.name as away_name
from matches m
join teams h on h.id = m.home_team_id
join teams a on a.id = m.away_team_id
where true {filters}
order by m.kickoff_at nulls last, m.week, m.id
limit :limit
"""


@router.get("/fixtures", response_model=FixturePage, operation_id="listFixtures")
async def list_fixtures(
    request: Request,
    session: SessionDep,
    team: uuid.UUID | None = None,
    season: uuid.UUID | None = None,
    from_: Annotated[dt.date | None, Query(alias="from")] = None,
    status: Literal["scheduled", "finished"] | None = None,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Response:
    """Fikstür ve sonuçlar: başlama zamanına göre sıralı. `from` verilirse o günden itibaren
    (saati belli olmayan planlı maçlar dahil)."""
    filters = ""
    params: dict[str, Any] = {"limit": limit + 1}
    if team:
        filters += " and (m.home_team_id = :team or m.away_team_id = :team)"
        params["team"] = team
    if season:
        filters += " and m.season_id = :season"
        params["season"] = season
    if status:
        filters += " and m.status = :status"
        params["status"] = status
    if from_:
        filters += (
            " and (m.kickoff_at >= :from or (m.kickoff_at is null and m.status = 'scheduled'))"
        )
        params["from"] = dt.datetime.combine(from_, dt.time(), tzinfo=dt.UTC)
    after = decode_cursor(cursor, 1)
    rows = (await session.execute(text(FIXTURES_SQL.format(filters=filters)), params)).all()
    if after:
        ids = [str(r.id) for r in rows]
        rows = rows[ids.index(after[0]) + 1 :] if after[0] in ids else []
    items = [
        FixtureOut(
            id=r.id,
            season_id=r.season_id,
            week=r.week,
            kickoff_at=r.kickoff_at,
            status=r.status,
            home=TeamRef(id=r.home_id, code=r.home_code, name=r.home_name),
            away=TeamRef(id=r.away_id, code=r.away_code, name=r.away_name),
            home_score=r.home_score,
            away_score=r.away_score,
        )
        for r in rows[:limit]
    ]
    next_cursor = encode_cursor([str(items[-1].id)]) if len(rows) > limit else None
    return etag_response(request, FixturePage(items=items, next_cursor=next_cursor))
