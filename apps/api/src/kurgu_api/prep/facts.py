"""Öneri motoruna giden olguların derlenmesi (A-46, ADR-0009).

- `opponent`, `club`: fikstürün sezonundan bir önceki sezon (aynı yarışma).
- `opponent_current`, `club_current`: fikstürün sezonu.
- `league`: önceki sezonun lig toplamları.
- `own_log.routine`: kulübün rutin istatistikleri (rutin başına özne).
- `own_log.defense`: kulübün kendi kaydında, güncel sezonda rakiplerin kulübe karşı duran topları.

Metrik değerleri Faz 2'nin `compute_season_metrics` fonksiyonundan gelir (kaynak önceliği A-36).
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import pandas as pd
from kurgu_analytics.metrics import routine_metrics
from kurgu_analytics.recs import Fact, Subject
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.memo import FrameMemo
from kurgu_api.core.problems import ProblemError
from kurgu_api.league.metrics import SeasonMetrics, compute_season_metrics
from kurgu_api.league.schemas import TeamRef
from kurgu_api.prep.schemas import PrepFixtureOut, SeasonRef

FIXTURE_SQL = """
select m.id, m.season_id, m.week, m.kickoff_at, m.status,
       s.label as season_label, s.code as season_code, s.competition_id,
       h.id as home_id, h.code as home_code, h.name as home_name,
       a.id as away_id, a.code as away_code, a.name as away_name
from matches m
join seasons s on s.id = m.season_id
join teams h on h.id = m.home_team_id
join teams a on a.id = m.away_team_id
where m.id = :id
"""
PREVIOUS_SEASON_SQL = """
select id, label from seasons
where competition_id = :competition and code < :code
order by code desc
limit 1
"""
CLUB_SQL = "select club_team_id from tenants where id = kurgu_current_tenant()"
ROUTINES_SQL = """
select r.id, r.name from routines r where r.archived_at is null order by r.name, r.id
"""
DEFENSE_SQL = """
select count(*) as set_pieces,
       count(*) filter (where p.shots > 0) as shots,
       count(distinct p.match_id) as matches
from set_pieces p
join matches m on m.id = p.match_id
where p.tenant_id = kurgu_current_tenant()
  and m.season_id = :season
  and (m.home_team_id = :club or m.away_team_id = :club)
  and p.team_id <> :club
"""


@dataclass(frozen=True, slots=True)
class FixtureInfo:
    out: PrepFixtureOut
    competition_id: uuid.UUID

    @property
    def id(self) -> uuid.UUID:
        return self.out.id

    @property
    def club_id(self) -> uuid.UUID:
        return self.out.club.id

    @property
    def opponent_id(self) -> uuid.UUID:
        return self.out.opponent.id


@dataclass(slots=True)
class MetricsCache:
    """İstek boyunca sezon metrikleri ve rutin özneleri bir kez hesaplanır."""

    by_season: dict[uuid.UUID, SeasonMetrics] = field(default_factory=dict)
    routines: list[Subject] | None = None

    async def get(self, session: AsyncSession, season_id: uuid.UUID) -> SeasonMetrics:
        if season_id not in self.by_season:
            self.by_season[season_id] = await compute_season_metrics(session, season_id)
        return self.by_season[season_id]

    async def routine_subjects(self, session: AsyncSession) -> list[Subject]:
        if self.routines is None:
            self.routines = await routine_subjects(session)
        return self.routines


async def club_team_id(session: AsyncSession) -> uuid.UUID | None:
    club: uuid.UUID | None = (await session.execute(text(CLUB_SQL))).scalar_one_or_none()
    return club


async def load_fixture(session: AsyncSession, fixture_id: uuid.UUID) -> FixtureInfo:
    """Kulübün fikstürü; kulüp maçta yoksa 422, fikstür görünmüyorsa 404."""
    row = (await session.execute(text(FIXTURE_SQL), {"id": fixture_id})).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Fixture not found")
    club = await club_team_id(session)
    if club is None or club not in (row.home_id, row.away_id):
        raise ProblemError(422, "not-club-fixture", "Your club does not play in this fixture")
    home = TeamRef(id=row.home_id, code=row.home_code, name=row.home_name)
    away = TeamRef(id=row.away_id, code=row.away_code, name=row.away_name)
    is_home = club == row.home_id
    previous = (
        await session.execute(
            text(PREVIOUS_SEASON_SQL),
            {"competition": row.competition_id, "code": row.season_code},
        )
    ).one_or_none()
    return FixtureInfo(
        out=PrepFixtureOut(
            id=row.id,
            week=row.week,
            kickoff_at=row.kickoff_at,
            status=row.status,
            home=home,
            away=away,
            club=home if is_home else away,
            opponent=away if is_home else home,
            is_home=is_home,
            season=SeasonRef(id=row.season_id, label=row.season_label),
            previous_season=SeasonRef(id=previous.id, label=previous.label) if previous else None,
        ),
        competition_id=row.competition_id,
    )


def team_subject(metrics: SeasonMetrics | None, team_id: uuid.UUID) -> Subject | None:
    """Bir takımın sezon metrikleri, lig ortalamasıyla."""
    if metrics is None or team_id not in metrics.values:
        return None
    facts: dict[str, Fact] = {}
    for name, v in metrics.values[team_id].items():
        bench = metrics.benchmarks.get(name)
        facts[name] = Fact(
            value=v.value,
            rank=v.rank,
            teams=v.teams,
            percentile=v.percentile,
            matches=v.matches,
            trials=v.trials,
            low_sample=v.low_sample,
            approx=v.approx,
            indirect=v.indirect,
            league_mean=bench.mean if bench else None,
            source=v.source,
        )
    matches = metrics.inputs.get(team_id, {}).get("matches")
    return Subject(metrics=facts, matches=matches)


def league_subject(metrics: SeasonMetrics | None) -> Subject | None:
    if metrics is None or not metrics.totals:
        return None
    return Subject(metrics={k: Fact(value=v) for k, v in metrics.totals.items()})


_routine_metrics = FrameMemo(routine_metrics)


async def routine_subjects(session: AsyncSession) -> list[Subject]:
    """Arşivde olmayan her rutin için bir özne (kullanım, şut, gol, büzülmüş şut oranı)."""
    names = {r.id: r.name for r in await session.execute(text(ROUTINES_SQL))}
    if not names:
        return []
    rows = (await session.execute(text("select * from v_routine_stats"))).mappings().all()
    stats = _routine_metrics(pd.DataFrame([dict(r) for r in rows])) if rows else pd.DataFrame()
    raw = {r["routine_id"]: r for r in rows}
    out: list[Subject] = []
    for record in stats.to_dict("records") if len(stats) else []:
        rid = record["routine_id"]
        if rid not in names:
            continue
        low = bool(record["low_sample"])

        def fact(value: object, *, low: bool = low) -> Fact | None:
            if value is None:
                return None
            f = float(value)  # type: ignore[arg-type]
            return None if math.isnan(f) else Fact(value=f, low_sample=low)

        metrics = {
            "uses": fact(record["uses"]),
            "shots": fact(raw[rid]["with_shot"]),
            "goals": fact(record["goals"]),
            "xg": fact(record["xg"]),
            "shot_rate": fact(record["shot_rate"]),
            "shot_rate_posterior": fact(record["shot_shrunk"]),
            "first_contact_rate": fact(record["first_contact_shrunk"]),
        }
        out.append(
            Subject(
                metrics={k: v for k, v in metrics.items() if v is not None},
                labels={"name": names[rid]},
                matches=float(record["matches"]),
                key=str(rid),
            )
        )
    return out


async def defense_subject(
    session: AsyncSession, season_id: uuid.UUID, club: uuid.UUID
) -> Subject | None:
    row = (await session.execute(text(DEFENSE_SQL), {"season": season_id, "club": club})).one()
    if not row.set_pieces:
        return None
    n = float(row.set_pieces)
    low = n < 8 or row.matches < 5
    return Subject(
        metrics={
            "set_pieces": Fact(value=n, low_sample=low),
            "shots": Fact(value=float(row.shots), low_sample=low),
            "shot_rate": Fact(value=row.shots / n, trials=n, low_sample=low),
        },
        matches=float(row.matches),
    )


async def fixture_facts(
    session: AsyncSession, fixture: FixtureInfo, cache: MetricsCache
) -> tuple[dict[str, Subject], list[Subject]]:
    """Fikstür kurallarının ve sezon kurallarının olguları; ayrıca rutin özneleri."""
    current = await cache.get(session, fixture.out.season.id)
    previous = (
        await cache.get(session, fixture.out.previous_season.id)
        if fixture.out.previous_season
        else None
    )
    subjects = {
        "opponent": team_subject(previous, fixture.opponent_id),
        "opponent_current": team_subject(current, fixture.opponent_id),
        "club": team_subject(previous, fixture.club_id),
        "club_current": team_subject(current, fixture.club_id),
        "league": league_subject(previous),
        "own_log.defense": await defense_subject(session, fixture.out.season.id, fixture.club_id),
    }
    facts = {k: v for k, v in subjects.items() if v is not None}
    return facts, await cache.routine_subjects(session)


def md_date(kickoff: dt.datetime | None, offset_days: int) -> dt.date | None:
    """Başlama saatinin İstanbul günü + gün farkı (A-52)."""
    if kickoff is None:
        return None
    local = kickoff.astimezone(ZoneInfo("Europe/Istanbul")).date()
    return local + dt.timedelta(days=offset_days)
