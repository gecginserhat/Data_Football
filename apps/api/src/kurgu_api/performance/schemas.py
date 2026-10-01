"""Yük, iyi oluş ve uyarı şemaları (SPEC §8.2-8.3, A-83 … A-86)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

MdCode = Literal["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"]
Item = Annotated[int, Field(ge=1, le=7)]


class PlayerRef(BaseModel):
    id: uuid.UUID
    name: str
    shirt_number: int | None
    position: str
    is_demo: bool


class LoadIn(BaseModel):
    squad_player_id: uuid.UUID
    rpe: float = Field(ge=0, le=10, multiple_of=0.5)
    """CR-10 ölçeği."""
    minutes: int = Field(ge=0, le=300)
    headers: int = Field(default=0, ge=0, le=500)
    jumps: int = Field(default=0, ge=0, le=1000)
    """Maksimal sıçrama tekrarı."""


class SessionIn(BaseModel):
    date: dt.date
    md_code: MdCode | None = None
    fixture_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=120)
    loads: list[LoadIn] = Field(min_length=1, max_length=40)


class TrainingSessionOut(BaseModel):
    id: uuid.UUID
    date: dt.date
    md_code: MdCode | None
    title: str
    is_demo: bool
    players: int
    mean_srpe: float
    """Oyuncu başına ortalama sRPE (AU)."""
    headers: int
    jumps: int


class WellnessIn(BaseModel):
    squad_player_id: uuid.UUID
    date: dt.date
    sleep: Item
    stress: Item
    fatigue: Item
    soreness: Item


class WellnessOut(BaseModel):
    squad_player_id: uuid.UUID
    date: dt.date
    sleep: int
    stress: int
    fatigue: int
    soreness: int
    hooper: int
    """Hooper indeksi (4-28; yüksek = kötü)."""


class AlertOut(BaseModel):
    """Haftalık sıçrama ya da kafa vuruşu uyarısı: "dikkat" niteliğindedir, tanı değildir."""

    player: PlayerRef
    metric: Literal["jumps", "headers"]
    week: dt.date
    """Haftanın pazartesisi."""
    total: int
    mean: float
    sd: float
    threshold: float
    weeks: int
    """Ortalamaya giren önceki hafta sayısı."""


class HooperPoint(BaseModel):
    date: dt.date
    value: int
    z: float | None


class PlayerLoadRow(BaseModel):
    player: PlayerRef
    last_session: dt.date | None
    load_7d: float
    """Son 7 günün toplam sRPE'si (AU)."""
    acute: float | None
    chronic: float | None
    acwr: float | None
    """Yalnız bağlam bilgisi; 28 günden kısa seride boş."""
    z: float | None
    hooper: HooperPoint | None
    """Son 7 gündeki en yeni iyi oluş kaydı."""
    jumps_week: int
    headers_week: int
    days: int
    """Yük serisinin gün sayısı."""
    low_data: bool
    """28 günden kısa seri ("Az veri")."""


class TeamSummary(BaseModel):
    players: int
    players_with_data: int
    sessions_7d: int
    mean_load_7d: float | None
    """Verisi olan oyuncu başına son 7 günün ortalama toplam sRPE'si (AU)."""
    wellness_entries_7d: int
    mean_hooper_7d: float | None


class OverviewOut(BaseModel):
    as_of: dt.date
    scope: Literal["all", "summary"]
    summary: TeamSummary
    players: list[PlayerLoadRow] | None
    """Yalnız tam erişimde (`performance`, `medical`)."""
    alerts: list[AlertOut] | None
    sessions: list[TrainingSessionOut]


class DayPoint(BaseModel):
    date: dt.date
    load: float
    acute: float
    chronic: float
    acwr: float | None
    z: float | None


class WeekPoint(BaseModel):
    week: dt.date
    jumps: int
    headers: int


class PlayerSession(BaseModel):
    date: dt.date
    title: str
    md_code: MdCode | None
    rpe: float
    minutes: int
    srpe: float
    headers: int
    jumps: int


class PlayerLoadOut(BaseModel):
    player: PlayerRef
    as_of: dt.date
    days: list[DayPoint]
    wellness: list[WellnessOut]
    hooper: list[HooperPoint]
    weeks: list[WeekPoint]
    alerts: list[AlertOut]
    sessions: list[PlayerSession]
    low_data: bool
