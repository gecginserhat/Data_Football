"""Rutin uçlarının istek ve yanıt şemaları (SPEC §11, ADR-0008)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from kurgu_analytics.reports.diagram import Diagram
from pydantic import BaseModel, Field, RootModel

SpType = Literal["corner", "free_kick", "throw_in"]
Side = Literal["left", "right"]

Name = Annotated[str, Field(min_length=1, max_length=120)]
Notes = Annotated[str, Field(max_length=4000)]


class UserRef(BaseModel):
    id: uuid.UUID
    name: str | None


class TemplateOut(BaseModel):
    id: str
    name: str
    sp_type: SpType
    side: Side | None
    is_defensive: bool
    when_to_use: str
    notes: str
    diagram: Diagram


class TemplateList(RootModel[list[TemplateOut]]):
    pass


class RateOut(BaseModel):
    """Oran ve beta-binom büzülmesi (SPEC §6.4)."""

    value: float | None
    shrunk: float | None
    low: float | None
    high: float | None
    trials: int


class RoutineStatsOut(BaseModel):
    """Rutin performansı (SPEC §6.3). Rutine bağlı duran top dizilerinden (A-44)."""

    uses: int
    matches: int
    goals: int
    xg: float
    xg_per_use: float | None
    first_contact: RateOut
    shot: RateOut
    low_sample: bool


class RoutineSummary(BaseModel):
    id: uuid.UUID
    name: str
    sp_type: SpType
    side: Side | None
    is_defensive: bool
    from_template: str | None
    current_version: int
    archived: bool
    updated_at: dt.datetime
    updated_by: UserRef | None
    diagram: Diagram
    """Güncel sürümün çizimi (kütüphane önizlemesi)."""
    stats: RoutineStatsOut


class RoutinePage(BaseModel):
    items: list[RoutineSummary]
    next_cursor: str | None


class VersionSummary(BaseModel):
    version: int
    name: str
    message: str | None
    created_at: dt.datetime
    created_by: UserRef | None


class VersionOut(VersionSummary):
    side: Side | None
    notes: str
    when_to_use: str
    diagram: Diagram


class RoutineOut(BaseModel):
    id: uuid.UUID
    name: str
    sp_type: SpType
    side: Side | None
    is_defensive: bool
    from_template: str | None
    current_version: int
    archived: bool
    created_at: dt.datetime
    updated_at: dt.datetime
    version: VersionOut
    """Güncel sürüm."""
    stats: RoutineStatsOut


class RoutineCreate(BaseModel):
    name: Name
    sp_type: SpType
    side: Side | None = None
    is_defensive: bool = False
    notes: Notes = ""
    when_to_use: Notes = ""
    diagram: Diagram = Field(default_factory=Diagram)


class RoutineFromTemplate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class RoutineUpdate(BaseModel):
    """Yeni sürüm. `base_version` güncel sürüm değilse 409 (A-41)."""

    base_version: int = Field(ge=1)
    name: Name
    side: Side | None = None
    notes: Notes = ""
    when_to_use: Notes = ""
    diagram: Diagram
    message: str | None = Field(default=None, max_length=200)


class RoutinePatch(BaseModel):
    archived: bool
