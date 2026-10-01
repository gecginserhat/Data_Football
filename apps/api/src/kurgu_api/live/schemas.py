"""Canlı kayıt uçlarının şemaları (SPEC §11 Canlı kayıt, A-58)."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

SpType = Literal["corner", "free_kick", "throw_in"]
Outcome = Literal[
    "goal",
    "shot_on_target",
    "shot_off_target",
    "shot_blocked",
    "first_contact_no_shot",
    "cleared",
    "possession_retained",
    "counter_conceded",
]
SHOT_OUTCOMES = frozenset({"goal", "shot_on_target", "shot_off_target", "shot_blocked"})


class TagPayload(BaseModel):
    """Bir canlı kaydın içeriği. Takım ev sahibi ya da deplasman olarak tutulur (A-58)."""

    sp_type: SpType
    team: Literal["home", "away"]
    outcome: Outcome
    period: int = Field(ge=1, le=5)
    clock_s: float = Field(ge=0, le=10800)
    routine_id: uuid.UUID | None = None
    first_contact: Literal["attack", "defense"] | None = None
    side: Literal["left", "right"] | None = None
    note: str = Field(default="", max_length=200)


class SessionCreate(BaseModel):
    match_id: uuid.UUID
    device_id: str = Field(min_length=1, max_length=64)


class SessionOut(BaseModel):
    id: uuid.UUID
    match_id: uuid.UUID
    last_seq: int
    created_at: dt.datetime


class Change(BaseModel):
    id: uuid.UUID
    op: Literal["upsert", "delete"]
    payload: dict[str, Any] | None = None
    """`upsert` için zorunlu; kayıt düzeyinde doğrulanır, hatalı kayıt reddedilir."""
    client_ts: dt.datetime


class SyncIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    changes: list[Change] = Field(max_length=500)


class Rejected(BaseModel):
    id: uuid.UUID
    reason: str


class SyncOut(BaseModel):
    server_seq: int
    accepted: list[uuid.UUID]
    rejected: list[Rejected]


class TagOut(BaseModel):
    id: uuid.UUID
    device_id: str
    client_ts: dt.datetime
    server_seq: int
    deleted: bool
    payload: dict[str, Any]


class TagsOut(BaseModel):
    server_seq: int
    tags: list[TagOut]


class MatchSetPieceOut(BaseModel):
    """Bir maçın görünen duran topları (sağlayıcı ve kulübün kendi kaydı); klip bağlamak için."""

    id: uuid.UUID
    team_id: uuid.UUID
    team_code: str
    period: int
    start_time_s: float
    sp_type: str
    outcome: str | None
    routine_id: uuid.UUID | None
    source: str
