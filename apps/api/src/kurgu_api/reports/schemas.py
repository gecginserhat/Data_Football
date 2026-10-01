"""Rapor uçlarının şemaları (SPEC §14, ADR-0012, A-68 … A-71)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel

from kurgu_api.routines.schemas import UserRef

ReportType = Literal["opponent", "match_plan"]
ReportStatus = Literal["queued", "running", "ready", "failed"]


class ReportCreate(BaseModel):
    type: ReportType
    fixture_id: uuid.UUID


class ReportFixture(BaseModel):
    id: uuid.UUID
    week: int | None
    kickoff_at: dt.datetime | None
    home_code: str
    away_code: str


class ReportOut(BaseModel):
    id: uuid.UUID
    type: ReportType
    fixture: ReportFixture
    status: ReportStatus
    progress: int
    """0-100; worker adımlarıyla ilerler."""
    size_bytes: int | None
    pages: int | None
    error: str | None
    data_as_of: dict[str, object] | None
    """Raporun dayandığı sezon ve hafta (A-71)."""
    created_at: dt.datetime
    finished_at: dt.datetime | None
    duration_ms: int | None
    """Kuyruğa girişten dosyanın hazır olmasına kadar geçen süre (A-71)."""
    created_by: UserRef | None
    download_url: str | None = None
    """Hazır raporlar için kısa ömürlü imzalı adres (A-70)."""
