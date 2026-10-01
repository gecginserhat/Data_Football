"""Kadro, rakip hedefleri, markaj ve rol atamaları şemaları (SPEC §7.3, ADR-0015, A-79 … A-87)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from kurgu_analytics.reports.diagram import Diagram
from pydantic import BaseModel, Field

from kurgu_api.prep.schemas import PrepFixtureOut
from kurgu_api.routines.schemas import UserRef

Position = Literal["GK", "DEF", "MID", "FWD"]
Name = Annotated[str, Field(min_length=1, max_length=120)]
Shirt = Annotated[int, Field(ge=1, le=99)]
Height = Annotated[int, Field(ge=150, le=215)]
Unit = Annotated[float, Field(ge=0, le=1)]


class AerialOut(BaseModel):
    """Hava skoru (0-1) ve skora giren bileşenler (A-81)."""

    value: float
    components: list[str]


class SquadPlayerIn(BaseModel):
    name: Name
    shirt_number: Shirt | None = None
    position: Position
    height_cm: Height | None = None
    aerial_win_pct: Unit | None = None
    """Hava topu kazanma oranı (0-1)."""
    jump_score: Unit | None = None
    active: bool = True


class SquadPlayerOut(SquadPlayerIn):
    id: uuid.UUID
    is_demo: bool
    aerial: AerialOut | None
    """Hava kapasitesi; bileşen yoksa boş ve oyuncu markaj atamasına giremez."""
    has_account: bool
    """Bir oyuncu hesabı bu kayda bağlı mı (A-79)."""


class AccountLink(BaseModel):
    user_id: uuid.UUID | None
    """Bağlanacak oyuncu hesabı; boşsa bağlantı kaldırılır."""


class PlayerAccountOut(BaseModel):
    user_id: uuid.UUID
    name: str | None
    squad_player_id: uuid.UUID | None


class TargetIn(BaseModel):
    name: Name
    shirt_number: Shirt | None = None
    height_cm: Height | None = None
    aerial_win_pct: Unit | None = None
    sp_goals: int | None = Field(default=None, ge=0, le=50)
    """Duran top golü (kulüp kaydı)."""
    notes: str = Field(default="", max_length=400)


class TargetOut(TargetIn):
    id: uuid.UUID
    team_id: uuid.UUID
    threat: AerialOut | None
    """Hava tehdidi; bileşen yoksa boş ve hedef atamaya giremez."""
    updated_at: dt.datetime


class MarkingPair(BaseModel):
    target_id: uuid.UUID
    marker_id: uuid.UUID | None
    """Boşsa hedef adamsız (alan savunmasına) kalır."""


class MarkingRow(MarkingPair):
    suggested_marker_id: uuid.UUID | None
    overridden: bool
    """Kayıttaki eşleşme öneriden farklı mı ("elle değiştirildi")."""
    gap: float | None
    """Tehdit − kapasite; pozitifse savunmacı dezavantajlı."""


class MarkingSaved(BaseModel):
    version: int
    rows: list[MarkingRow]
    zonal: list[uuid.UUID]
    overridden: int
    note: str | None
    created_at: dt.datetime
    created_by: UserRef | None


class MarkingOut(BaseModel):
    fixture: PrepFixtureOut
    targets: list[TargetOut]
    squad: list[SquadPlayerOut]
    """Aktif kadro; kaleciler ve hava skoru olmayanlar atamaya girmez."""
    zonal: list[uuid.UUID]
    """Öneride sabit tutulan (alan savunması) oyuncular."""
    suggestion: list[MarkingRow]
    """Macar algoritmasının önerisi; her hedef için bir satır (adamsız kalanlar dahil)."""
    saved: MarkingSaved | None
    versions: int


class MarkingIn(BaseModel):
    base_version: int = Field(ge=0)
    """Okunan son sürüm (hiç kayıt yoksa 0). Daha yeni bir kayıt varsa 409."""
    assignments: list[MarkingPair] = Field(max_length=30)
    zonal: list[uuid.UUID] = Field(default_factory=list, max_length=11)
    note: str | None = Field(default=None, max_length=400)


class SlotOut(BaseModel):
    diagram_player_id: str
    role: str
    number: int | None
    label: str | None
    squad_player_id: uuid.UUID | None


class RoutineAssignmentOut(BaseModel):
    routine_id: uuid.UUID
    name: str
    sp_type: str
    version: int
    sources: list[str]
    """Rutinin bu fikstüre geldiği yer: kabul edilen öneri ya da plan maddesi başlıkları."""
    slots: list[SlotOut]
    assigned_version: int | None
    """Atamaların yapıldığı sürüm; güncel sürümden eskiyse arayüz uyarır."""


class AssignmentsOut(BaseModel):
    routines: list[RoutineAssignmentOut]


class SlotIn(BaseModel):
    diagram_player_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    squad_player_id: uuid.UUID | None


class AssignmentsIn(BaseModel):
    routine_id: uuid.UUID
    slots: list[SlotIn] = Field(max_length=30)


class CardRoutine(BaseModel):
    routine_id: uuid.UUID
    name: str
    sp_type: str
    version: int
    diagram_player_id: str
    role: str
    number: int | None
    label: str | None
    diagram: Diagram


class CardMarking(BaseModel):
    target: TargetOut | None
    zonal: bool


class TaskCard(BaseModel):
    fixture: PrepFixtureOut
    routines: list[CardRoutine]
    marking: CardMarking | None


class CardsOut(BaseModel):
    player: SquadPlayerOut
    cards: list[TaskCard]
