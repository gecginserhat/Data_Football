"""Rapor girdileri (SPEC §14, ADR-0012). API veriyi toplar, şablonlar yalnızca bunları okur.

Değerler ham gelir (oranlar 0-1); biçimlendirme şablonda `labels.format_metric` ile yapılır.
Her raporda kaynak ve veri tarihi bulunur (`ReportMeta`).
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from kurgu_analytics.reports.diagram import Diagram

Area = Literal["attack", "defense"]


class TeamLabel(BaseModel):
    code: str
    name: str


class ReportMeta(BaseModel):
    club: TeamLabel
    generated_at: dt.datetime
    generated_by: str | None = None
    season: str
    """Sezon etiketi, örn. `2025/26`."""
    data_week: int | None = None
    """Verinin geçerli olduğu son hafta; tamamlanmış sezonda boş."""
    sources: list[str] = Field(default_factory=list)
    """Değerlerin kaynak anahtarları (`seed`, `events`, `import`, `provider`)."""
    demo: bool = False
    """Raporda örnek (demo) veri var mı ("Örnek veri" rozeti)."""


class FixtureLabel(BaseModel):
    week: int | None
    kickoff_at: dt.datetime | None
    is_home: bool
    club: TeamLabel
    opponent: TeamLabel


class MetricRow(BaseModel):
    metric: str
    value: float
    rank: int
    teams: int
    league_mean: float | None = None
    low_sample: bool = False
    approx: bool = False
    indirect: bool = False
    source: str = "seed"
    club_value: float | None = None
    club_rank: int | None = None


class Evidence(BaseModel):
    subject: str
    """`opponent`, `club`, `league` ya da rutin adı."""
    metric: str
    value: float
    rank: int | None = None
    teams: int | None = None
    league_mean: float | None = None
    low_sample: bool = False


class Recommendation(BaseModel):
    area: Area
    priority: int
    confidence: str
    title: str
    why: str
    action: str
    status: str
    routine: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class ZoneCount(BaseModel):
    zone: str
    count: int


class ClipLink(BaseModel):
    title: str
    detail: str
    url: str


class Briefing(BaseModel):
    text: str
    created_at: dt.datetime


class OpponentReport(BaseModel):
    meta: ReportMeta
    fixture: FixtureLabel
    standing: str | None = None
    form: list[Literal["W", "D", "L"]] = Field(default_factory=list)
    metrics: list[MetricRow]
    recommendations: list[Recommendation]
    zones: list[ZoneCount]
    set_pieces: int
    """Isı haritasının dayandığı duran top sayısı (bölgesiz olanlar dahil)."""
    clips: list[ClipLink] = Field(default_factory=list)
    briefing: Briefing | None = None


class RoutineBlock(BaseModel):
    name: str
    sp_type: str
    side: str | None
    is_defensive: bool
    version: int
    notes: str = ""
    when_to_use: str = ""
    roles: list[str] = Field(default_factory=list)
    """Kulübün rol etiketleri (rol adı ve serbest metin oyuncu etiketi)."""
    diagram: Diagram


class PlanItem(BaseModel):
    title: str
    detail: str = ""
    done: bool
    assignee: str | None = None
    routine: str | None = None


class PlanDay(BaseModel):
    md_code: str
    date: dt.date | None
    focus: str
    items: list[PlanItem]


class MatchPlanReport(BaseModel):
    meta: ReportMeta
    fixture: FixtureLabel
    recommendations: list[Recommendation]
    """Kabul edilen öneriler (hücum ve savunma)."""
    routines: list[RoutineBlock]
    days: list[PlanDay]
    plan_done: int = 0
    plan_total: int = 0
