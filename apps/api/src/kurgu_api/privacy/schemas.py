"""KVKK şemaları (SPEC §12.3, ADR-0019, A-92)."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ConsentTextOut(BaseModel):
    version: str
    text: str


class ConsentOut(BaseModel):
    id: uuid.UUID
    text_version: str
    method: Literal["self", "paper"]
    reference: str | None
    given_at: dt.datetime
    withdrawn_at: dt.datetime | None
    is_demo: bool


class ConsentStatusOut(BaseModel):
    squad_player_id: uuid.UUID
    player_name: str
    active: ConsentOut | None
    history: list[ConsentOut]
    current_version: str
    can_record_paper: bool
    """Performans ve sağlık ekibi kâğıt rızayı kaydedebilir."""
    can_give_self: bool
    """Oyuncu kendi rızasını verebilir."""


class ConsentIn(BaseModel):
    method: Literal["self", "paper"]
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    """Kâğıt rızanın belge numarası ya da arşiv yeri."""
    text_version: str = Field(min_length=1, max_length=32)
    """Kullanıcının gördüğü metnin sürümü; güncel sürümle aynı olmalıdır."""

    @model_validator(mode="after")
    def _paper_needs_reference(self) -> "ConsentIn":
        if self.method == "paper" and not self.reference:
            raise ValueError("paper consent needs a document reference")
        return self


class InventoryItemOut(BaseModel):
    key: str
    title: str
    tables: list[str]
    fields: list[str]
    subjects: str
    purpose: str
    legal_basis: str
    special_category: bool
    encrypted: bool
    retention: str
    retention_days: int | None


class Retention(BaseModel):
    wellness_days: int = Field(default=730, ge=30, le=3650)
    loads_days: int = Field(default=1095, ge=30, le=3650)
    audit_days: int = Field(default=730, ge=365, le=3650)


class PrivacySettingsOut(BaseModel):
    retention: Retention
    data_region: str
    inventory: list[InventoryItemOut]


class RequestIn(BaseModel):
    squad_player_id: uuid.UUID
    kind: Literal["erasure"] = "erasure"
    reason: str | None = Field(default=None, max_length=500)


class RequestOut(BaseModel):
    id: uuid.UUID
    squad_player_id: uuid.UUID
    player_name: str
    kind: Literal["erasure"]
    status: Literal["open", "completed", "rejected"]
    reason: str | None
    created_at: dt.datetime
    decided_at: dt.datetime | None
    note: str | None


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class ErasureResult(BaseModel):
    wellness: int
    loads: int
    assignments: int
    consents: int


class RequestDecisionOut(BaseModel):
    request: RequestOut
    erased: ErasureResult | None


class PlayerExport(BaseModel):
    """Veri sahibinin verisinin kopyası (KVKK m.11)."""

    generated_at: dt.datetime
    player: dict[str, Any]
    consents: list[ConsentOut]
    wellness: list[dict[str, Any]]
    loads: list[dict[str, Any]]
    assignments: list[dict[str, Any]]
    requests: list[RequestOut]
