"""Video ve klip uçlarının şemaları (SPEC §11 Video, ADR-0010)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from kurgu_api.routines.schemas import UserRef

MAX_BYTES = 8 * 1024**3
PART_SIZE = 16 * 1024**2
CONTENT_TYPES = ("video/mp4", "video/quicktime", "video/x-matroska", "video/webm")
ContentType = Literal["video/mp4", "video/quicktime", "video/x-matroska", "video/webm"]
Status = Literal["uploading", "processing", "ready", "failed"]


class UploadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    content_type: ContentType
    size_bytes: int = Field(gt=0, le=MAX_BYTES)
    match_id: uuid.UUID | None = None
    offset_s: float = Field(default=0, ge=-7200, le=7200)


class PartUrl(BaseModel):
    number: int
    url: str


class AssetOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    content_type: str
    size_bytes: int
    match_id: uuid.UUID | None
    offset_s: float
    status: Status
    error: str | None
    duration_s: float | None
    created_at: dt.datetime
    created_by: UserRef | None


class UploadOut(BaseModel):
    asset: AssetOut
    part_size: int
    parts: list[PartUrl]
    """Parça başına imzalı PUT adresi; yanıttaki ETag başlığı `complete` çağrısına verilir."""


class CompleteIn(BaseModel):
    etags: list[str] = Field(min_length=1, max_length=10000)


class AssetPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    match_id: uuid.UUID | None = None
    offset_s: float | None = Field(default=None, ge=-7200, le=7200)


class ClipSetPiece(BaseModel):
    id: uuid.UUID
    sp_type: str
    team_code: str
    period: int
    start_time_s: float
    outcome: str | None
    routine_id: uuid.UUID | None


class ClipOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    asset_title: str
    match_id: uuid.UUID | None
    start_s: float
    end_s: float
    title: str
    set_piece: ClipSetPiece | None
    created_at: dt.datetime


class ClipCreate(BaseModel):
    asset_id: uuid.UUID
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    title: str = Field(default="", max_length=200)
    set_piece_id: uuid.UUID | None = None


class ClipPatch(BaseModel):
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=200)
    set_piece_id: uuid.UUID | None = None
