"""LLM uçlarının şemaları (SPEC §15, ADR-0013, A-75, A-76)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class BriefingOut(BaseModel):
    fixture_id: uuid.UUID
    status: Literal["verified", "failed", "none"]
    """`verified`: sayılar girdiyle eşleşti; `failed`: üretilemedi; `none`: henüz brifing yok."""
    text: str | None = None
    """Yalnız doğrulanmış metin döner; reddedilen metin kullanıcıya gönderilmez."""
    reason: Literal["unverified", "error"] | None = None
    model: str | None = None
    numbers: int = 0
    """Metinde denetlenen sayı adedi."""
    attempts: int = 0
    created_at: dt.datetime | None = None


class LlmSettings(BaseModel):
    enabled: bool = True
    monthly_requests: int = Field(default=200, ge=0, le=100_000)
    monthly_tokens: int = Field(default=2_000_000, ge=0, le=1_000_000_000)


class LlmUsage(BaseModel):
    period_start: dt.date
    requests: int
    tokens: int


class LlmSettingsOut(BaseModel):
    settings: LlmSettings
    usage: LlmUsage
    configured: bool
    """Sunucuda model ve anahtar tanımlı mı (değerleri gösterilmez)."""
