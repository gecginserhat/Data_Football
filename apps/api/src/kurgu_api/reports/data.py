"""Rapor girdilerinin toplanması (SPEC §14, ADR-0012, A-68 … A-72, A-77, A-78).

Hazırlık sayfasıyla aynı kaynakları kullanır: fikstür, öneri motoru (canlı öneriler ve kararlar),
Faz 2 sezon metrikleri, MD planı, rutinler. Sayılar burada biçimlendirilmez; şablon biçimlendirir.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

from kurgu_analytics.reports.diagram import Diagram
from kurgu_analytics.reports.documents import (
    Briefing,
    ClipLink,
    Evidence,
    FixtureLabel,
    MatchPlanReport,
    MetricRow,
    OpponentReport,
    PlanDay,
    PlanItem,
    Recommendation,
    ReportMeta,
    RoutineBlock,
    TeamLabel,
    ZoneCount,
)
from kurgu_analytics.reports.labels import METRICS
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.config import get_settings
from kurgu_api.league.metrics import SeasonMetrics
from kurgu_api.league.schemas import TeamRef
from kurgu_api.prep.facts import FixtureInfo, MetricsCache, load_fixture
from kurgu_api.prep.schemas import RecommendationOut
from kurgu_api.prep.service import evaluate_fixture, load_plan, merged_recommendations

SP_TYPES = ("corner", "free_kick", "throw_in")
MAX_CLIPS = 6

STANDING_SQL = """
select st.position, st.played, st.pts, st.week
from standings_snapshots st
where st.season_id = :season and st.team_id = :team
order by st.week desc
limit 1
"""
FORM_SQL = """
select m.home_team_id, m.home_score, m.away_score
from matches m
where m.season_id = :season and m.status = 'finished'
  and (m.home_team_id = :team or m.away_team_id = :team)
order by m.week desc nulls last, m.kickoff_at desc nulls last, m.id
limit 5
"""
ZONES_SQL = """
select coalesce(p.target_zone, '') as zone, count(*) as n
from set_pieces p join matches m on m.id = p.match_id
where p.team_id = :team and m.season_id = any(:seasons) and p.sp_type = any(:types)
group by 1
"""
CLIPS_SQL = """
select c.id, c.asset_id, c.title, c.start_s, p.sp_type, p.start_time_s, m.week
from video_clips c
join video_assets a on a.id = c.asset_id and a.status = 'ready'
join set_pieces p on p.id = c.set_piece_id
join matches m on m.id = p.match_id
where p.team_id = :team
order by m.week desc nulls last, p.start_time_s, c.id
limit :limit
"""
ROUTINES_SQL = """
select r.id, r.name, r.sp_type, r.is_defensive, v.version, v.side, v.notes, v.when_to_use,
       v.diagram
from routines r
join routine_versions v on v.routine_id = r.id and v.version = r.current_version
where r.id = any(:ids)
order by r.is_defensive, r.name, r.id
"""
BRIEFING_SQL = """
select output, created_at from llm_runs
where fixture_id = :fixture and kind = 'briefing' and status = 'verified'
order by created_at desc
limit 1
"""
USER_SQL = "select display_name, email from users where id = :id"
SP_LABELS = {"corner": "korner", "free_kick": "serbest vuruş", "throw_in": "uzun taç"}


def _team(ref: TeamRef) -> TeamLabel:
    return TeamLabel(code=ref.code, name=ref.name)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def fixture_label(fixture: FixtureInfo) -> FixtureLabel:
    out = fixture.out
    return FixtureLabel(
        week=out.week,
        kickoff_at=out.kickoff_at,
        is_home=out.is_home,
        club=_team(out.club),
        opponent=_team(out.opponent),
    )


async def _user_name(session: AsyncSession, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    row = (await session.execute(text(USER_SQL), {"id": user_id})).one_or_none()
    return (row.display_name or row.email) if row else None


def _recommendation(rec: RecommendationOut) -> Recommendation:
    return Recommendation(
        area=rec.area,
        priority=rec.priority,
        confidence=rec.confidence,
        title=rec.title,
        why=rec.why,
        action=rec.action,
        status=rec.status,
        routine=rec.routine.name if rec.routine else None,
        evidence=[
            Evidence(
                subject=e.subject,
                metric=e.metric,
                value=e.value,
                rank=e.rank,
                teams=e.teams,
                league_mean=e.league_mean,
                low_sample=e.low_sample,
            )
            for e in rec.evidence
        ],
    )


def profile_rows(
    profile: SeasonMetrics | None,
    current: SeasonMetrics | None,
    opponent: uuid.UUID,
    club: uuid.UUID,
) -> list[MetricRow]:
    """Rakibin profil satırları (katalog sırasıyla); kulüp ve içinde bulunulan sezon yanında."""
    base = profile or current
    if base is None:
        return []
    values = base.values.get(opponent, {})
    club_values = base.values.get(club, {})
    now = current.values.get(opponent, {}) if current is not None and current is not base else {}
    rows = []
    for metric in METRICS:
        v = values.get(metric)
        if v is None:
            continue
        c = club_values.get(metric)
        n = now.get(metric)
        bench = base.benchmarks.get(metric)
        rows.append(
            MetricRow(
                metric=metric,
                value=v.value,
                rank=v.rank,
                teams=v.teams,
                league_mean=bench.mean if bench else None,
                low_sample=v.low_sample,
                approx=v.approx,
                indirect=v.indirect,
                source=v.source,
                club_value=c.value if c else None,
                club_rank=c.rank if c else None,
                current_value=n.value if n else None,
                current_rank=n.rank if n else None,
                current_teams=n.teams if n else None,
                current_low_sample=n.low_sample if n else False,
            )
        )
    return rows


async def _meta(
    session: AsyncSession,
    fixture: FixtureInfo,
    current: SeasonMetrics | None,
    profile_label: str | None,
    sources: set[str],
    user_id: uuid.UUID | None,
) -> ReportMeta:
    out = fixture.out
    week = current.as_of_week.get(fixture.opponent_id) if current else None
    return ReportMeta(
        club=_team(out.club),
        generated_at=dt.datetime.now(dt.UTC),
        generated_by=await _user_name(session, user_id),
        season=out.season.label,
        profile_season=profile_label,
        data_week=week,
        sources=sorted(sources),
    )


async def _standing(session: AsyncSession, season: uuid.UUID, fixture: FixtureInfo) -> str | None:
    row = (
        await session.execute(text(STANDING_SQL), {"season": season, "team": fixture.opponent_id})
    ).one_or_none()
    if row is None:
        return None
    name = fixture.out.opponent.name
    return f"{name} {row.played} maçta {row.pts} puanla {row.position}. sırada ({row.week}. hafta)."


async def _form(session: AsyncSession, season: uuid.UUID, team: uuid.UUID) -> list[Any]:
    rows = await session.execute(text(FORM_SQL), {"season": season, "team": team})
    form = []
    for r in rows:
        if r.home_score is None or r.away_score is None:
            continue
        home = r.home_team_id == team
        gf, ga = (r.home_score, r.away_score) if home else (r.away_score, r.home_score)
        form.append("W" if gf > ga else "D" if gf == ga else "L")
    return form


async def _clips(session: AsyncSession, team: uuid.UUID) -> list[ClipLink]:
    web = get_settings().kurgu_public_web_url.rstrip("/")
    rows = await session.execute(text(CLIPS_SQL), {"team": team, "limit": MAX_CLIPS})
    links = []
    for r in rows:
        minute, second = divmod(int(r.start_time_s or 0), 60)
        detail = f"{r.week}. hafta · " if r.week else ""
        detail += f"{SP_LABELS.get(r.sp_type, r.sp_type)} {minute:02d}:{second:02d}"
        links.append(
            ClipLink(
                title=r.title or "Klip",
                detail=detail,
                url=f"{web}/video/{r.asset_id}?clip={r.id}",
            )
        )
    return links


async def _briefing(session: AsyncSession, fixture_id: uuid.UUID) -> Briefing | None:
    row = (await session.execute(text(BRIEFING_SQL), {"fixture": fixture_id})).one_or_none()
    return Briefing(text=row.output, created_at=row.created_at) if row else None


async def _profile(
    session: AsyncSession, cache: MetricsCache, fixture: FixtureInfo
) -> tuple[SeasonMetrics, list[MetricRow], str]:
    """İçinde bulunulan sezon, rakip profil satırları ve profilin sezonu (A-78)."""
    out = fixture.out
    current = await cache.get(session, out.season.id)
    profile = await cache.get(session, out.previous_season.id) if out.previous_season else None
    if profile is not None and fixture.opponent_id not in profile.values:
        profile = None  # rakip önceki sezonda ligde değil
    label = (
        out.previous_season.label
        if profile is not None and out.previous_season
        else out.season.label
    )
    return current, profile_rows(profile, current, fixture.opponent_id, fixture.club_id), label


async def opponent_report(
    session: AsyncSession, fixture_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> OpponentReport:
    fixture = await load_fixture(session, fixture_id)
    ev = await evaluate_fixture(session, fixture)
    recs = await merged_recommendations(session, ev, tenant_id)
    out = fixture.out
    current, metrics, profile_label = await _profile(session, ev.cache, fixture)
    standing_season = out.season.id
    standing = await _standing(session, standing_season, fixture)
    if standing is None and out.previous_season:
        standing_season = out.previous_season.id
        standing = await _standing(session, standing_season, fixture)
    seasons = [out.season.id] + ([out.previous_season.id] if out.previous_season else [])
    zone_rows = await session.execute(
        text(ZONES_SQL),
        {"team": fixture.opponent_id, "seasons": seasons, "types": list(SP_TYPES)},
    )
    counts = {r.zone: int(r.n) for r in zone_rows}
    total = sum(counts.values())
    zones = [ZoneCount(zone=z, count=n) for z, n in counts.items() if z]
    return OpponentReport(
        meta=await _meta(
            session, fixture, current, profile_label, {m.source for m in metrics}, user_id
        ),
        fixture=fixture_label(fixture),
        standing=standing,
        form=await _form(session, standing_season, fixture.opponent_id),
        metrics=metrics,
        recommendations=[_recommendation(r) for r in recs if r.status != "rejected"],
        zones=zones,
        set_pieces=total,
        clips=await _clips(session, fixture.opponent_id),
        briefing=await _briefing(session, fixture.id),
    )


async def _routines(session: AsyncSession, ids: list[uuid.UUID]) -> list[RoutineBlock]:
    if not ids:
        return []
    rows = await session.execute(text(ROUTINES_SQL), {"ids": ids})
    return [
        RoutineBlock(
            name=r.name,
            sp_type=r.sp_type,
            side=r.side,
            is_defensive=r.is_defensive,
            version=r.version,
            notes=r.notes or "",
            when_to_use=r.when_to_use or "",
            diagram=Diagram.model_validate(_json(r.diagram)),
        )
        for r in rows
    ]


async def match_plan_report(
    session: AsyncSession, fixture_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> MatchPlanReport:
    fixture = await load_fixture(session, fixture_id)
    ev = await evaluate_fixture(session, fixture)
    accepted = [
        r for r in await merged_recommendations(session, ev, tenant_id) if r.status == "accepted"
    ]
    plan = await load_plan(session, fixture)
    routine_ids: list[uuid.UUID] = []
    for rec in accepted:
        if rec.routine and rec.routine.id not in routine_ids:
            routine_ids.append(rec.routine.id)
    days: list[PlanDay] = []
    if plan is not None:
        for item in plan.items:
            if item.routine and item.routine.id not in routine_ids:
                routine_ids.append(item.routine.id)
        by_day: dict[str, list[PlanItem]] = {}
        for item in plan.items:
            by_day.setdefault(item.md_code, []).append(
                PlanItem(
                    title=item.title,
                    detail=item.detail,
                    done=item.status == "done",
                    assignee=item.assignee.name if item.assignee else None,
                    routine=item.routine.name if item.routine else None,
                )
            )
        days = [
            PlanDay(md_code=d.md_code, date=d.date, focus=d.focus, items=by_day.pop(d.md_code, []))
            for d in plan.days
        ]
        days += [
            PlanDay(md_code=code, date=None, focus="", items=items)
            for code, items in by_day.items()
        ]
    # Kaynak ve veri tarihi önerilerin dayandığı rakip profilinden gelir.
    current, metrics, profile_label = await _profile(session, ev.cache, fixture)
    return MatchPlanReport(
        meta=await _meta(
            session, fixture, current, profile_label, {m.source for m in metrics}, user_id
        ),
        fixture=fixture_label(fixture),
        recommendations=[_recommendation(r) for r in accepted],
        routines=await _routines(session, routine_ids),
        days=days,
        plan_done=plan.done if plan else 0,
        plan_total=plan.total if plan else 0,
    )
