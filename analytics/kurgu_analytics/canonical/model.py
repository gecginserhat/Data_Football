"""Kanonik (silver) veri modeli: SPADL uyumlu aksiyonlar ve maç bağlamı (SPEC §5.3, ADR-0003).

Koordinatlar kanoniktir (105 × 68 m, aksiyonu yapan takımın hücum yönünde, SPEC §4).
Sağlayıcıya özgü bilgiler `extra` içinde taşınır; duran top çıkarımı bunlara bakmaz
(yalnızca alt tür sınıflandırması ve doğrulama kullanır).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Final

# SPADL sözlüğü (socceraction.spadl.config ile aynı adlar).
ACTION_TYPES: Final = (
    "pass",
    "cross",
    "throw_in",
    "freekick_crossed",
    "freekick_short",
    "corner_crossed",
    "corner_short",
    "take_on",
    "foul",
    "tackle",
    "interception",
    "shot",
    "shot_penalty",
    "shot_freekick",
    "keeper_save",
    "keeper_claim",
    "keeper_punch",
    "keeper_pick_up",
    "clearance",
    "bad_touch",
    "non_action",
    "dribble",
    "goalkick",
)
RESULTS: Final = ("fail", "success", "offside", "owngoal", "yellow_card", "red_card")
BODYPARTS: Final = ("foot", "head", "other", "head/other", "foot_left", "foot_right")

SHOT_TYPES: Final = frozenset({"shot", "shot_freekick", "shot_penalty"})


@dataclass(frozen=True, slots=True)
class Team:
    provider_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Player:
    provider_id: str
    name: str
    team_provider_id: str


@dataclass(frozen=True, slots=True)
class Match:
    provider_id: str
    competition_provider_id: str
    competition_name: str
    season_provider_id: str
    season_name: str
    home: Team
    away: Team
    kickoff_at: dt.datetime | None
    home_score: int | None
    away_score: int | None
    week: int | None = None
    stage: str | None = None


@dataclass(frozen=True, slots=True)
class Action:
    """Tek SPADL aksiyonu. `time_s` periyot içindeki saniyedir."""

    action_index: int
    period: int
    time_s: float
    team_provider_id: str
    player_provider_id: str | None
    type: str
    result: str
    bodypart: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    xg: float | None = None
    xg_source: str | None = None
    provider_event_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_shot(self) -> bool:
        return self.type in SHOT_TYPES


@dataclass(frozen=True, slots=True)
class CanonicalMatch:
    match: Match
    players: tuple[Player, ...]
    actions: tuple[Action, ...]
