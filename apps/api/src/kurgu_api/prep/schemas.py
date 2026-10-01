"""Maç hazırlığı uçlarının şemaları (SPEC §11 Hazırlık, Kurallar)."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from kurgu_api.league.schemas import TeamRef
from kurgu_api.routines.schemas import UserRef

Area = Literal["attack", "defense", "balance", "season"]
Confidence = Literal["high", "medium", "low"]
Decision = Literal["suggested", "accepted", "rejected"]
MdCode = Literal["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"]
PlanTemplate = Literal["standard", "congested"]
RuleStatus = Literal["fired", "not_met", "missing_data", "low_sample", "disabled"]


class EvidenceOut(BaseModel):
    """Kanıt satırı (SPEC §7.1): metrik, değer, lig sırası, lig ortalaması, örneklem."""

    subject: str
    metric: str
    value: float
    rank: int | None
    teams: int | None
    league_mean: float | None
    matches: float | None
    trials: float | None
    low_sample: bool
    approx: bool
    indirect: bool
    source: str | None
    op: str
    threshold: float | bool | None


class TemplateRef(BaseModel):
    id: str
    name: str


class RoutineRef(BaseModel):
    id: uuid.UUID
    name: str


class RecommendationOut(BaseModel):
    id: uuid.UUID
    """Belirlenimci: kiracı, fikstür, kural ve rutin (A-50)."""
    rule_id: str
    rule_set_version: int
    area: Area
    priority: int
    confidence: Confidence
    title: str
    why: str
    action: str
    template: TemplateRef | None
    routine: RoutineRef | None
    evidence: list[EvidenceOut]
    status: Decision
    reason: str | None
    decided_by: UserRef | None
    decided_at: dt.datetime | None
    active: bool
    """Kural güncel veriyle hâlâ tetikleniyor mu (kararı verilmiş öneride yanlış olabilir)."""


class SeasonRef(BaseModel):
    id: uuid.UUID
    label: str


class PrepFixtureOut(BaseModel):
    id: uuid.UUID
    week: int | None
    kickoff_at: dt.datetime | None
    status: str
    home: TeamRef
    away: TeamRef
    club: TeamRef
    opponent: TeamRef
    is_home: bool
    season: SeasonRef
    previous_season: SeasonRef | None


class SideValue(BaseModel):
    value: float
    rank: int
    teams: int
    low_sample: bool
    approx: bool


class MatchupRow(BaseModel):
    """Eşleşme notu: aynı metrikte rakip ve kulüp, lig ortalamasıyla."""

    metric: str
    indirect: bool
    opponent: SideValue | None
    opponent_current: SideValue | None
    club: SideValue | None
    league_mean: float | None


class PlanItemOut(BaseModel):
    id: uuid.UUID
    md_code: MdCode
    position: int
    title: str
    detail: str
    status: Literal["todo", "done"]
    assignee: UserRef | None
    done_by: UserRef | None
    done_at: dt.datetime | None
    recommendation_id: uuid.UUID | None
    routine: RoutineRef | None


class PlanDay(BaseModel):
    md_code: MdCode
    date: dt.date | None
    focus: str


class PlanOut(BaseModel):
    id: uuid.UUID
    template: PlanTemplate
    days: list[PlanDay]
    items: list[PlanItemOut]
    done: int
    total: int


class RuleSetRef(BaseModel):
    version: int
    label: str | None
    is_default: bool


class PrepOut(BaseModel):
    fixture: PrepFixtureOut
    rule_set: RuleSetRef
    recommendations: list[RecommendationOut]
    matchup: list[MatchupRow]
    plan: PlanOut | None
    assignees: list[UserRef]
    """Plan maddesi sorumlusu olabilecek kulüp üyeleri (plan işaretleme izni olanlar)."""
    routines: list[RoutineRef]
    """Plan maddesine bağlanabilecek rutinler (arşivde olmayanlar)."""


class DecisionIn(BaseModel):
    fixture_id: uuid.UUID
    decision: Decision
    """`suggested` kararı geri alır."""
    reason: str | None = Field(default=None, max_length=1000)


class PlanCreate(BaseModel):
    template: PlanTemplate


class PlanItemCreate(BaseModel):
    md_code: MdCode
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=2000)
    routine_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None


class PlanItemPatch(BaseModel):
    status: Literal["todo", "done"] | None = None
    assignee_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=2000)
    md_code: MdCode | None = None


# --- Genel bakış --------------------------------------------------------------------------------


class ThreatOut(BaseModel):
    rule_id: str
    title: str
    confidence: Confidence


class UpcomingThreats(BaseModel):
    fixture: PrepFixtureOut
    threats: list[ThreatOut]
    """En çok iki savunma önerisi (tehdit etiketi)."""
    recommendations: int
    """Maçta gösterilen öneri sayısı."""


class OverviewRecsOut(BaseModel):
    season: SeasonRef | None
    rule_set: RuleSetRef
    recommendations: list[RecommendationOut]
    """Sezon kapsamındaki öneriler (karar alınmaz)."""
    upcoming: list[UpcomingThreats]


# --- Kural setleri ------------------------------------------------------------------------------


class RuleSetOut(BaseModel):
    version: int
    label: str | None
    is_default: bool
    message: str | None
    published_at: dt.datetime
    published_by: UserRef | None
    rules: list[dict[str, Any]]


class RuleSetVersionOut(BaseModel):
    version: int
    label: str | None
    is_default: bool
    message: str | None
    published_at: dt.datetime
    published_by: UserRef | None


class RuleSetUpdate(BaseModel):
    base_version: int = Field(ge=0)
    rules: list[dict[str, Any]] = Field(max_length=200)
    message: str | None = Field(default=None, max_length=200)


class DryRunIn(BaseModel):
    fixture_id: uuid.UUID
    rules: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    """Verilirse kaydedilmemiş taslak set denenir; yoksa güncel set."""


class ConditionOut(BaseModel):
    subject: str
    metric: str
    op: str
    threshold: float | bool | None
    value: float | None
    rank: int | None
    teams: int | None
    passed: bool | None


class DryRunRule(BaseModel):
    rule_id: str
    scope: Literal["fixture", "season"]
    area: Area
    priority: int
    enabled: bool
    status: RuleStatus
    shown: bool
    """Tetiklendi ve tekilleştirmeden sonra ekranda görünür."""
    confidence: Confidence | None
    strength: float
    title: str
    why: str
    routine: RoutineRef | None
    conditions: list[ConditionOut]


class DryRunOut(BaseModel):
    fixture: PrepFixtureOut
    results: list[DryRunRule]
