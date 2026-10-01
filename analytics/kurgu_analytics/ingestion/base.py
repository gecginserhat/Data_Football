"""Sağlayıcı adaptör arayüzü (SPEC §5.2).

Her sağlayıcı üç iş yapar: maçları listeler, bir maçın ham yükünü getirir, ham yükü kanonik
modele çevirir. Ham yük değişmezdir ve `source_hash` (SHA-256) ile tanınır; aynı yük iki kez
işlenmez. Veritabanı ve nesne deposu bu katmanda yoktur (API/worker tarafı).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from kurgu_analytics.canonical.model import CanonicalMatch, Match


@dataclass(frozen=True, slots=True)
class RawPayload:
    provider: str
    kind: str
    key: str
    """Sağlayıcı içindeki anahtar (ör. StatsBomb maç kimliği)."""
    content: bytes
    content_type: str = "application/json"

    @property
    def source_hash(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class Provider(Protocol):
    name: str

    def list_matches(self, params: dict[str, Any]) -> list[Match]: ...

    def fetch_events(self, match: Match) -> RawPayload: ...

    def to_canonical(self, match: Match, raw: RawPayload) -> CanonicalMatch: ...
