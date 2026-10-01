"""Yük, iyi oluş ve uyarı uçları (SPEC §8.2-8.3, §12.1; ADR-0014; A-83 … A-86).

`load_wellness` kapsamları: `all` (performans, sağlık) tam erişim; `summary` (yönetici) yalnız takım
özeti; `own` (oyuncu) yalnız kendi verisi ve kendi iyi oluş girişi. İyi oluş puanları şifreli
saklanır; her okuma ve yazma denetim kaydına girer.
"""

import datetime as dt
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from kurgu_analytics.metrics.load import hooper_index, week_start
from sqlalchemy import text

from kurgu_api.core.audit import write_audit
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission, Scope
from kurgu_api.identity.service import Principal
from kurgu_api.performance.schemas import (
    DayPoint,
    HooperPoint,
    OverviewOut,
    PlayerLoadOut,
    PlayerLoadRow,
    PlayerSession,
    SessionIn,
    TeamSummary,
    TrainingSessionOut,
    WeekPoint,
    WellnessIn,
    WellnessOut,
)
from kurgu_api.performance.service import (
    CHRONIC_DAYS,
    alerts,
    hooper,
    load_data,
    num,
    seal,
    today,
    trends,
)

router = APIRouter(tags=["performance"])

ScopeDep = Annotated[Scope, Depends(require(Permission.LOAD_WELLNESS))]

SESSIONS_SQL = """
select ts.id, ts.date, ts.md_code, ts.title, ts.is_demo, count(sl.id) as players,
       coalesce(avg(sl.rpe * sl.minutes), 0) as mean_srpe,
       coalesce(sum(sl.headers), 0) as headers, coalesce(sum(sl.jumps), 0) as jumps
from training_sessions ts left join session_loads sl on sl.session_id = ts.id
where ts.date between :since and :until
group by ts.id
order by ts.date desc, ts.created_at desc
limit :limit
"""


def _tenant(principal: Principal) -> uuid.UUID:
    assert principal.tenant is not None
    return principal.tenant.tenant_id


def _full(scope: Scope) -> None:
    if scope != "all":
        raise ProblemError(403, "forbidden", "Full load and wellness access is required")


async def _audit_read(
    session: SessionDep, principal: Principal, entity_id: uuid.UUID, **after: object
) -> None:
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="wellness.read",
        entity="wellness_entries",
        entity_id=entity_id,
        after={k: str(v) if isinstance(v, dt.date | uuid.UUID) else v for k, v in after.items()},
    )


async def _sessions(
    session: SessionDep, since: dt.date, until: dt.date
) -> list[TrainingSessionOut]:
    rows = await session.execute(text(SESSIONS_SQL), {"since": since, "until": until, "limit": 20})
    return [
        TrainingSessionOut(
            id=r.id,
            date=r.date,
            md_code=r.md_code,
            title=r.title,
            is_demo=r.is_demo,
            players=r.players,
            mean_srpe=round(float(r.mean_srpe), 1),
            headers=r.headers,
            jumps=r.jumps,
        )
        for r in rows
    ]


@router.post(
    "/sessions",
    response_model=TrainingSessionOut,
    status_code=201,
    operation_id="createTrainingSession",
)
async def create_session(
    session: SessionDep, principal: PrincipalDep, scope: ScopeDep, body: SessionIn
) -> TrainingSessionOut:
    """Seans ve oyuncu başına RPE, süre, kafa vuruşu ve sıçrama kaydı (A-83)."""
    _full(scope)
    ids = [load.squad_player_id for load in body.loads]
    if len(set(ids)) != len(ids):
        raise ProblemError(422, "duplicate-player", "A player appears twice in the session")
    known = {
        r.id
        for r in await session.execute(
            text("select id from squad_players where id = any(:ids)"), {"ids": ids}
        )
    }
    if missing := set(ids) - known:
        raise ProblemError(
            422, "unknown-player", f"Unknown squad players: {sorted(map(str, missing))}"
        )
    tenant = _tenant(principal)
    session_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into training_sessions (tenant_id, date, md_code, fixture_id, title,"
                " created_by) values (:t, :d, :md, :f, :title, :u) returning id"
            ),
            {
                "t": tenant,
                "d": body.date,
                "md": body.md_code,
                "f": body.fixture_id,
                "title": body.title,
                "u": principal.user_id,
            },
        )
    ).scalar_one()
    for load in body.loads:
        await session.execute(
            text(
                "insert into session_loads (tenant_id, session_id, squad_player_id, rpe, minutes,"
                " headers, jumps) values (:t, :s, :p, :rpe, :min, :h, :j)"
            ),
            {
                "t": tenant,
                "s": session_id,
                "p": load.squad_player_id,
                "rpe": load.rpe,
                "min": load.minutes,
                "h": load.headers,
                "j": load.jumps,
            },
        )
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action="session.create",
        entity="training_sessions",
        entity_id=session_id,
        after={"date": body.date.isoformat(), "title": body.title, "players": len(body.loads)},
    )
    return next(s for s in await _sessions(session, body.date, body.date) if s.id == session_id)


@router.get(
    "/sessions",
    response_model=list[TrainingSessionOut],
    operation_id="listTrainingSessions",
)
async def list_sessions(
    session: SessionDep,
    scope: ScopeDep,
    since: dt.date | None = None,
    until: dt.date | None = None,
) -> list[TrainingSessionOut]:
    """Seanslar ve takım ortalamaları (oyuncu ayrıntısı yok)."""
    if scope == "own":
        raise ProblemError(403, "forbidden", "Players can see only their own load")
    end = until or today()
    return await _sessions(session, since or end - dt.timedelta(days=27), end)


@router.post(
    "/wellness",
    response_model=WellnessOut,
    operation_id="saveWellness",
)
async def save_wellness(
    session: SessionDep, principal: PrincipalDep, scope: ScopeDep, body: WellnessIn
) -> WellnessOut:
    """Günlük iyi oluş kaydı; aynı gün yeniden giriş üzerine yazar (A-83). Puanlar şifrelenir."""
    assert principal.tenant is not None
    if scope == "summary":
        raise ProblemError(403, "forbidden", "Summary access cannot enter wellness")
    if scope == "own" and principal.tenant.player_id != body.squad_player_id:
        raise ProblemError(403, "forbidden", "Players can enter only their own wellness")
    if body.date > today():
        raise ProblemError(422, "future-date", "Wellness cannot be entered for a future date")
    exists = (
        await session.execute(
            text("select 1 from squad_players where id = :id"), {"id": body.squad_player_id}
        )
    ).first()
    if exists is None:
        raise ProblemError(404, "not-found", "Squad player not found")
    scores = {k: getattr(body, k) for k in ("sleep", "stress", "fatigue", "soreness")}
    total = hooper_index(**scores)
    tenant = _tenant(principal)
    entry_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into wellness_entries (tenant_id, squad_player_id, date, scores,"
                " entered_by) values (:t, :p, :d, cast(:s as jsonb), :u)"
                " on conflict (tenant_id, squad_player_id, date) do update set"
                " scores = excluded.scores, entered_by = excluded.entered_by, updated_at = now()"
                " returning id"
            ),
            {
                "t": tenant,
                "p": body.squad_player_id,
                "d": body.date,
                "s": json.dumps(seal(scores, tenant)),
                "u": principal.user_id,
            },
        )
    ).scalar_one()
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action="wellness.write",
        entity="wellness_entries",
        entity_id=entry_id,
        after={"squad_player_id": str(body.squad_player_id), "date": body.date.isoformat()},
    )
    return WellnessOut(squad_player_id=body.squad_player_id, date=body.date, hooper=total, **scores)


@router.get(
    "/load/overview",
    response_model=OverviewOut,
    operation_id="getLoadOverview",
)
async def load_overview(
    session: SessionDep, principal: PrincipalDep, scope: ScopeDep, until: dt.date | None = None
) -> OverviewOut:
    """Takım yük tablosu ve uyarılar (`all`) ya da yalnız takım özeti (`summary`)."""
    if scope == "own":
        raise ProblemError(403, "forbidden", "Players can see only their own load")
    as_of = until or today()
    tenant = _tenant(principal)
    data = await load_data(session, tenant, as_of)
    week = week_start(as_of)
    last7 = as_of - dt.timedelta(days=6)
    recent = data.sessions[data.sessions["date"] >= last7]
    recent_wellness = data.wellness[data.wellness["date"] >= last7]
    per_player = recent.groupby("player_id")["srpe"].sum()
    hooper_frame = hooper(data)
    recent_hooper = hooper_frame[hooper_frame["date"] >= last7]
    summary = TeamSummary(
        players=len(data.players),
        players_with_data=int(data.sessions["player_id"].nunique()),
        sessions_7d=len(await _sessions(session, last7, as_of)),
        mean_load_7d=num(per_player.mean()) if len(per_player) else None,
        wellness_entries_7d=len(recent_wellness),
        mean_hooper_7d=num(recent_hooper["hooper"].mean()) if len(recent_hooper) else None,
    )
    await _audit_read(session, principal, tenant, scope=scope, until=as_of, view="overview")
    if scope == "summary":
        return OverviewOut(
            as_of=as_of,
            scope="summary",
            summary=summary,
            players=None,
            alerts=None,
            sessions=await _sessions(session, as_of - dt.timedelta(days=27), as_of),
        )

    trend = trends(data, as_of)
    latest = trend.sort_values("date").groupby("player_id").tail(1).set_index("player_id")
    days = trend.groupby("player_id").size()
    this_week = (
        data.sessions[data.sessions["date"] >= week]
        .groupby("player_id")[["jumps", "headers"]]
        .sum()
    )
    last_session = data.sessions.groupby("player_id")["date"].max()
    latest_hooper = recent_hooper.sort_values("date").groupby("player_id").tail(1)
    hooper_by = {r.player_id: r for r in latest_hooper.itertuples(index=False)}
    rows = []
    for pid, ref in data.players.items():
        t = latest.loc[pid] if pid in latest.index else None
        h = hooper_by.get(pid)
        n = int(days.get(pid, 0))
        rows.append(
            PlayerLoadRow(
                player=ref,
                last_session=last_session.get(pid),
                load_7d=round(float(per_player.get(pid, 0.0)), 1),
                acute=num(t["acute"]) if t is not None else None,
                chronic=num(t["chronic"]) if t is not None else None,
                acwr=num(t["acwr"]) if t is not None else None,
                z=num(t["z"]) if t is not None else None,
                hooper=HooperPoint(date=h.date, value=int(h.hooper), z=num(h.z)) if h else None,
                jumps_week=int(this_week["jumps"].get(pid, 0)) if len(this_week) else 0,
                headers_week=int(this_week["headers"].get(pid, 0)) if len(this_week) else 0,
                days=n,
                low_data=n < CHRONIC_DAYS,
            )
        )
    return OverviewOut(
        as_of=as_of,
        scope="all",
        summary=summary,
        players=rows,
        alerts=alerts(data, as_of, since=week - dt.timedelta(days=7)),
        sessions=await _sessions(session, as_of - dt.timedelta(days=27), as_of),
    )


@router.get(
    "/players/{player_id}/load",
    response_model=PlayerLoadOut,
    operation_id="getPlayerLoad",
)
async def player_load(
    session: SessionDep,
    principal: PrincipalDep,
    scope: ScopeDep,
    player_id: uuid.UUID,
    until: dt.date | None = None,
    days: int = 56,
) -> PlayerLoadOut:
    """Oyuncunun günlük yük trendi, iyi oluşu, haftalık sıçrama ve kafa vuruşu, uyarıları."""
    assert principal.tenant is not None
    if scope == "summary":
        raise ProblemError(403, "forbidden", "Summary access cannot see player detail")
    if scope == "own" and principal.tenant.player_id != player_id:
        raise ProblemError(403, "forbidden", "Players can see only their own load")
    days = max(7, min(days, 365))
    as_of = until or today()
    tenant = _tenant(principal)
    data = await load_data(session, tenant, as_of, player=player_id)
    ref = data.players.get(player_id)
    if ref is None:
        raise ProblemError(404, "not-found", "Squad player not found")
    since = as_of - dt.timedelta(days=days - 1)
    trend = trends(data, as_of)
    hooper_frame = hooper(data)
    await _audit_read(session, principal, player_id, until=as_of, days=days, view="player")
    weekly = data.sessions.assign(week=data.sessions["date"].map(week_start))
    weeks = weekly[weekly["week"] >= week_start(since)].groupby("week")[["jumps", "headers"]].sum()
    shown = trend[trend["date"] >= since]
    return PlayerLoadOut(
        player=ref,
        as_of=as_of,
        days=[
            DayPoint(
                date=r.date,
                load=round(float(r.load), 1),
                acute=round(float(r.acute), 2),
                chronic=round(float(r.chronic), 2),
                acwr=num(r.acwr),
                z=num(r.z),
            )
            for r in shown.itertuples(index=False)
        ],
        wellness=[
            WellnessOut(
                squad_player_id=player_id,
                date=r.date,
                sleep=r.sleep,
                stress=r.stress,
                fatigue=r.fatigue,
                soreness=r.soreness,
                hooper=hooper_index(r.sleep, r.stress, r.fatigue, r.soreness),
            )
            for r in data.wellness[data.wellness["date"] >= since].itertuples(index=False)
        ],
        hooper=[
            HooperPoint(date=r.date, value=int(r.hooper), z=num(r.z))
            for r in hooper_frame[hooper_frame["date"] >= since].itertuples(index=False)
        ],
        weeks=[
            WeekPoint(week=w, jumps=int(r.jumps), headers=int(r.headers))
            for w, r in weeks.iterrows()
        ],
        alerts=alerts(data, as_of, since=week_start(since)),
        sessions=[
            PlayerSession(
                date=r.date,
                title=r.title,
                md_code=r.md_code,
                rpe=float(r.rpe),
                minutes=int(r.minutes),
                srpe=round(float(r.srpe), 1),
                headers=int(r.headers),
                jumps=int(r.jumps),
            )
            for r in data.sessions[data.sessions["date"] >= since]
            .sort_values("date", ascending=False)
            .itertuples(index=False)
        ],
        low_data=len(trend) < CHRONIC_DAYS,
    )
