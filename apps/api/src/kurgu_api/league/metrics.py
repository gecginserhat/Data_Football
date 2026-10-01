"""Sezon metriklerinin derlenmesi: ham kayıtları okur, formülleri `kurgu_analytics.metrics` ile
uygular (SPEC §6; formüller bu dosyada yoktur).

Kaynak önceliği (A-36):
1. Paylaşılan takım-sezon kaydı (tohum ya da sağlayıcı), en güncel kesit.
2. Eksik `matches` ve `goals` için son puan durumu (`played`, `gf`).
3. Paylaşılan olay toplamları (`v_team_setpiece_season`). Takım-sezon kaydı olmayan sezonlarda
   temel sütunları (`matches`, `set_piece_goals`, `set_piece_xg`) da doldurur.
4. Kiracının kendi kaydı: içe aktarılan takım-sezon değerleri metrik bazında, içe aktarılan
   olay toplamları olay sütunlarının tümünde paylaşılanın yerine geçer.
Sıra, yüzdelik ve lig kıyasları bu birleşik tablodan hesaplanır.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from kurgu_analytics.metrics import METRICS, league_benchmarks, league_totals, team_metrics
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.league.schemas import BenchmarkOut, MetricValueOut, TeamRef

EVENT_COLUMNS = {
    "matches": "event_matches",
    "set_pieces": "set_pieces",
    "corners": "corners",
    "sp_with_contact": "sp_with_contact",
    "sp_first_contact_won": "sp_first_contact_won",
    "sp_with_shot": "sp_with_shot",
    "set_piece_xg": "sp_xg",
    "sp_xg_phase1": "sp_xg_phase1",
    "sp_xg_phase2": "sp_xg_phase2",
    "set_piece_goals": "sp_goals",
    "corner_goals": "corner_goals",
    "def_sp_with_contact": "def_sp_with_contact",
    "def_sp_first_contact_won": "def_sp_first_contact_won",
    "set_piece_goals_against": "set_piece_goals_against",
}
"""Görünüm sütunu → metrik modülündeki ham sütun."""
EVENT_FILLS = ("matches", "set_piece_goals", "set_piece_xg")
"""Takım-sezon kaydı yoksa olay toplamından doldurulan temel sütunlar (görünümde aynı adla)."""
EVENT_SOURCE = "events"
IMPORT_SOURCE = "import"

STATS_SQL = """
select distinct on (team_id, metric, tenant_id is null)
       team_id, metric, value, source, as_of_week, tenant_id is not null as own
from team_season_stats where season_id = :season
order by team_id, metric, tenant_id is null, coalesce(as_of_week, 1000) desc, source
"""
STANDINGS_SQL = """
select team_id, played, gf, source, week from standings_snapshots
where season_id = :season
  and week = (select max(week) from standings_snapshots where season_id = :season)
"""
SHARED_EVENTS_SQL = "select * from v_team_setpiece_season where season_id = :season"
OWN_EVENTS_SQL = (
    "select * from v_team_setpiece_agg where season_id = :season and tenant_id is not null"
)
TOTALS_SQL = "select metric, total from v_league_benchmarks where season_id = :season"


@dataclass
class SeasonMetrics:
    teams: dict[uuid.UUID, TeamRef]
    values: dict[uuid.UUID, dict[str, MetricValueOut]]
    benchmarks: dict[str, BenchmarkOut]
    totals: dict[str, float]
    as_of_week: dict[uuid.UUID, int | None] = field(default_factory=dict)
    inputs: dict[uuid.UUID, dict[str, float]] = field(default_factory=dict)
    """Takım başına birleştirilmiş ham girdiler (kayıttaki değerler)."""


def _float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number


async def _team_refs(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, TeamRef]:
    if not ids:
        return {}
    rows = await session.execute(
        text("select id, code, name from teams where id = any(:ids)"), {"ids": list(ids)}
    )
    return {r.id: TeamRef(id=r.id, code=r.code, name=r.name) for r in rows}


async def compute_season_metrics(session: AsyncSession, season_id: uuid.UUID) -> SeasonMetrics:
    """Sezondaki her takım için metrik değerleri, lig kıyasları ve lig toplamları."""
    params = {"season": season_id}
    raw: dict[uuid.UUID, dict[str, float]] = {}
    sources: dict[uuid.UUID, dict[str, str]] = {}
    weeks: dict[uuid.UUID, int | None] = {}

    def put(team: uuid.UUID, column: str, value: Any, source: str) -> None:
        number = _float(value)
        if number is None:
            return
        raw.setdefault(team, {})[column] = number
        sources.setdefault(team, {})[column] = source

    stats = (await session.execute(text(STATS_SQL), params)).all()
    for r in (r for r in stats if not r.own):
        put(r.team_id, r.metric, r.value, r.source)
        if r.as_of_week is not None or r.team_id not in weeks:
            weeks[r.team_id] = r.as_of_week

    for r in await session.execute(text(STANDINGS_SQL), params):
        team = raw.setdefault(r.team_id, {})
        if "matches" not in team:
            put(r.team_id, "matches", r.played, r.source)
        if "goals" not in team:
            put(r.team_id, "goals", r.gf, r.source)
        weeks.setdefault(r.team_id, r.week)

    for ev in (await session.execute(text(SHARED_EVENTS_SQL), params)).mappings():
        team_id = ev["team_id"]
        for view_col, column in EVENT_COLUMNS.items():
            put(team_id, column, ev[view_col], EVENT_SOURCE)
        for base in EVENT_FILLS:
            if base not in raw[team_id] or sources[team_id][base] == EVENT_SOURCE:
                put(team_id, base, ev[base], EVENT_SOURCE)

    for r in (r for r in stats if r.own):
        put(r.team_id, r.metric, r.value, IMPORT_SOURCE)
    for ev in (await session.execute(text(OWN_EVENTS_SQL), params)).mappings():
        team_id = ev["team_id"]
        for view_col, column in EVENT_COLUMNS.items():
            put(team_id, column, ev[view_col], IMPORT_SOURCE)
        for base in EVENT_FILLS:
            if sources.get(team_id, {}).get(base, EVENT_SOURCE) == EVENT_SOURCE:
                put(team_id, base, ev[base], IMPORT_SOURCE)

    teams = await _team_refs(session, set(raw))
    totals_rows = (await session.execute(text(TOTALS_SQL), params)).all()
    totals = league_totals({r.metric: float(r.total) for r in totals_rows})
    if not raw:
        return SeasonMetrics(teams=teams, values={}, benchmarks={}, totals=totals)

    frame = pd.DataFrame.from_dict(raw, orient="index")
    long = team_metrics(frame)
    values: dict[uuid.UUID, dict[str, MetricValueOut]] = {t: {} for t in raw}
    for row in long.itertuples(index=False):
        metric = METRICS[str(row.metric)]
        team_sources = sources.get(row.team, {})
        used = [team_sources[c] for c in metric.inputs if c in team_sources]
        source = IMPORT_SOURCE if IMPORT_SOURCE in used else (used[0] if used else "unknown")
        values[row.team][metric.id] = MetricValueOut(
            value=float(row.value),
            rank=int(row.rank),
            percentile=_float(row.percentile),
            teams=int(row.teams),
            trials=_float(row.trials),
            matches=_float(row.matches),
            shrunk=_float(row.shrunk_mean),
            shrunk_low=_float(row.shrunk_low),
            shrunk_high=_float(row.shrunk_high),
            low_sample=bool(row.low_sample),
            approx=bool(row.approx),
            indirect=metric.indirect,
            source=source,
        )
    benchmarks = {
        str(b.metric): BenchmarkOut(
            min=float(b.min), max=float(b.max), mean=float(b.mean), teams=int(b.teams)
        )
        for b in league_benchmarks(long).itertuples(index=False)
    }
    return SeasonMetrics(
        teams=teams,
        values=values,
        benchmarks=benchmarks,
        totals=totals,
        as_of_week=weeks,
        inputs=raw,
    )
