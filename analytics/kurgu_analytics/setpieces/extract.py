"""Duran top çıkarımı (SPEC §3.1, §3.2, §5.5).

Girdi: bir maçın sıralı SPADL aksiyonları (kanonik koordinat; her aksiyon kendi takımının hücum
yönünde). Çıktı: duran top dizileri. Algoritma SPEC §5.5'teki sözde kodun aynısıdır; eklemeler
açıkça işaretlidir:

- Penaltı (`shot_penalty`) yeni bir ölü top sayılır ve diziyi keser; penaltılar duran top
  metriklerine girmez (CLAUDE.md, SPEC §3.1).
- Başlama vuruşu SPADL'da ayrı tür değildir; orta noktadan (52,5, 34) başlayan pas olarak tanınır.
- Yalnızca hücum eden takımın şutları diziye yazılır; savunmanın kendi kalesine golü (`owngoal`)
  diziye gol olarak yazılır.
- Faz geçişi için sayılan paslara SPADL `cross` da dahildir (SPADL'da orta bir pas türüdür).

Çıkarım sağlayıcıya özgü alanlara (`extra`) bakmaz. Tek istisna korner alt türüdür: sağlayıcı
kavis bilgisini (`extra.technique`) veriyorsa kullanılır, yoksa ayak ve taraftan türetilir
(ADR-0003).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from kurgu_analytics.canonical.model import Action
from kurgu_analytics.setpieces.zones import ZoneCode, zone

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

RESTARTS = frozenset(
    {
        "corner_crossed",
        "corner_short",
        "freekick_crossed",
        "freekick_short",
        "shot_freekick",
        "throw_in",
    }
)
# Diziyi kesen diğer ölü toplar (başlama vuruşu ayrıca konumdan tanınır).
DEAD_BALLS = frozenset({"goalkick", "shot_penalty"})
SHOTS = frozenset({"shot", "shot_freekick"})
NON_TOUCH = frozenset({"foul", "non_action"})
POSSESSION = frozenset(
    {"pass", "cross", "dribble", "take_on", "keeper_claim", "keeper_pick_up", "goalkick"}
)

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
FINAL_THIRD_X = 70.0
POSTS_Y = (30.34, 37.66)


@dataclass(frozen=True, slots=True)
class Config:
    """Ayarlanabilir eşikler (SPEC §3.2, §5.5)."""

    window_s: float = 20.0
    phase1_s: float = 5.0
    phase1_max_passes: int = 1
    counter_s: float = 15.0
    long_throw_min_x: float = 70.0
    long_throw_box_x: float = 88.5
    long_throw_min_length: float = 20.0
    # Doğrulama için: True ise tüm taçlar duran top sayılır (A-07).
    all_throw_ins: bool = False


@dataclass(frozen=True, slots=True)
class Shot:
    action_index: int
    phase: Literal[1, 2]
    xg: float
    goal: bool
    outcome: Literal["goal", "shot_on_target", "shot_off_target", "shot_blocked"]


@dataclass(slots=True)
class SetPiece:
    team: str
    period: int
    start_time_s: float
    start_action_index: int
    sp_type: SpType
    sp_subtype: str
    side: Literal["left", "right"]
    taker: str | None
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    target_zone: ZoneCode
    first_contact_team: str | None = None
    first_contact_player: str | None = None
    shots: list[Shot] = field(default_factory=list)
    action_indices: list[int] = field(default_factory=list)
    own_goal_phase: Literal[1, 2] | None = None
    ended_by_turnover: bool = False
    outcome: Outcome = "cleared"

    @property
    def xg_phase1(self) -> float:
        return sum(s.xg for s in self.shots if s.phase == 1)

    @property
    def xg_phase2(self) -> float:
        return sum(s.xg for s in self.shots if s.phase == 2)

    @property
    def xg_total(self) -> float:
        return self.xg_phase1 + self.xg_phase2

    @property
    def goal(self) -> bool:
        return self.phase_of_goal is not None

    @property
    def phase_of_goal(self) -> Literal[1, 2] | None:
        for s in self.shots:
            if s.goal:
                return s.phase
        return self.own_goal_phase


# --- Yardımcılar -----------------------------------------------------------


def length(a: Action) -> float:
    """Aksiyonun başlangıç ve bitiş noktası arasındaki mesafe (metre)."""
    return math.hypot(a.end_x - a.start_x, a.end_y - a.start_y)


def is_kickoff(a: Action) -> bool:
    return a.type == "pass" and abs(a.start_x - 52.5) <= 1.5 and abs(a.start_y - 34) <= 1.5


def is_long_throw(a: Action, cfg: Config) -> bool:
    """SPEC §5.5: hücum üçte birinden ceza sahasına ya da en az 20 m atılan taç."""
    return a.start_x >= cfg.long_throw_min_x and (
        a.end_x >= cfg.long_throw_box_x or length(a) >= cfg.long_throw_min_length
    )


def classify(a: Action) -> tuple[SpType, str]:
    """Tür ve alt tür (SPEC §3.1)."""
    if a.type.startswith("corner"):
        if a.type == "corner_short":
            return "corner", "short"
        return "corner", _corner_curve(a)
    if a.type == "shot_freekick":
        return "free_kick", "direct_shot"
    if a.type == "freekick_crossed":
        return "free_kick", "crossed"
    if a.type == "freekick_short":
        return "free_kick", "short"
    if a.type == "throw_in":
        return "throw_in", "long"
    raise ValueError(f"duran top değil: {a.type}")


def _corner_curve(a: Action) -> str:
    technique = a.extra.get("technique")
    if technique == "Inswinging":
        return "inswing"
    if technique == "Outswinging":
        return "outswing"
    if technique == "Straight":
        return "driven"
    # Sağ taraftan (y < 34) sağ ayakla kullanılan korner kaleden uzağa döner (outswing).
    if a.bodypart in {"foot_left", "foot_right"}:
        right_side = side_of(a) == "right"
        right_foot = a.bodypart == "foot_right"
        return "outswing" if right_side == right_foot else "inswing"
    return "other"


def side_of(a: Action) -> Literal["left", "right"]:
    """Teslimin yapıldığı taraf, hücum yönüne göre: y < 34 sağ, değilse sol (SPEC §4)."""
    return "right" if a.start_y < PITCH_WIDTH / 2 else "left"


def is_touch(b: Action) -> bool:
    return b.type not in NON_TOUCH


def lost_possession(b: Action, team: str) -> bool:
    """Rakip topu kontrollü oynuyor (pas, top sürme, kaleci tutuşu)."""
    return b.team_provider_id != team and b.type in POSSESSION


def ball_left_final_third(b: Action, team: str) -> bool:
    """Top, hücum eden takımın bakışıyla hücum üçte birinin dışında mı (x < 70)."""
    x = b.end_x if b.team_provider_id == team else PITCH_LENGTH - b.end_x
    return x < FINAL_THIRD_X


def shot_outcome(
    actions: Sequence[Action], i: int
) -> Literal["goal", "shot_on_target", "shot_off_target", "shot_blocked"]:
    """Şut sonucu, sağlayıcıdan bağımsız: gol, kaleci kurtarışı, bitiş noktası.

    Rakip kalecinin hemen ardından gelen kurtarışı isabetli sayılır. Top kale çizgisine
    (x ≥ 104) ulaştıysa isabetsiz, ulaşmadan durduysa engellenmiş sayılır.
    """
    s = actions[i]
    if s.result == "success":
        return "goal"
    for nxt in actions[i + 1 : i + 3]:
        if nxt.team_provider_id != s.team_provider_id and nxt.type == "keeper_save":
            return "shot_on_target"
        if nxt.time_s - s.time_s > 3:
            break
    return "shot_off_target" if s.end_x >= 104.0 else "shot_blocked"


def derive_outcome(sp: SetPiece, counter_shot: bool) -> Outcome:
    """Sonuç (SPEC §3.2). Öncelik: gol > şut > kontra > temas."""
    if sp.goal:
        return "goal"
    if sp.shots:
        order = ("shot_on_target", "shot_off_target", "shot_blocked")
        return min((s.outcome for s in sp.shots), key=order.index)
    if counter_shot:
        return "counter_conceded"
    if sp.first_contact_team == sp.team:
        return "possession_retained" if sp.sp_subtype == "short" else "first_contact_no_shot"
    return "cleared"


# --- Çıkarım ---------------------------------------------------------------


def extract(actions: Sequence[Action], cfg: Config | None = None) -> list[SetPiece]:
    """Bir maçın aksiyonlarından duran top dizileri (SPEC §5.5)."""
    cfg = cfg or Config()
    result: list[SetPiece] = []
    for i, a in enumerate(actions):
        if a.type not in RESTARTS:
            continue
        if a.type == "throw_in" and not (cfg.all_throw_ins or is_long_throw(a, cfg)):
            continue
        sp_type, subtype = classify(a)
        sp = SetPiece(
            team=a.team_provider_id,
            period=a.period,
            start_time_s=a.time_s,
            start_action_index=a.action_index,
            sp_type=sp_type,
            sp_subtype=subtype,
            side=side_of(a),
            taker=a.player_provider_id,
            start_x=a.start_x,
            start_y=a.start_y,
            end_x=a.end_x,
            end_y=a.end_y,
            target_zone=zone(a.end_x, a.end_y, a.start_y),
            action_indices=[a.action_index],
        )
        if a.type == "shot_freekick":
            # Teslimin kendisi şut: doğrudan birinci faz şutu (SPEC §5.5).
            sp.shots.append(_shot(actions, i, 1))
        phase: Literal[1, 2] = 1
        passes_after = 0
        end = len(actions)
        for j in range(i + 1, len(actions)):
            b = actions[j]
            if b.period != a.period or b.time_s - a.time_s > cfg.window_s:
                end = j
                break
            if b.type in RESTARTS or b.type in DEAD_BALLS or is_kickoff(b):
                end = j
                break
            if lost_possession(b, sp.team) and ball_left_final_third(b, sp.team):
                sp.ended_by_turnover = True
                end = j
                break
            sp.action_indices.append(b.action_index)
            if sp.first_contact_team is None and is_touch(b):
                sp.first_contact_team = b.team_provider_id
                sp.first_contact_player = b.player_provider_id
            if b.type in {"pass", "cross"} and b.team_provider_id == sp.team:
                passes_after += 1
            if b.time_s - a.time_s > cfg.phase1_s or passes_after > cfg.phase1_max_passes:
                phase = 2
            if b.type in SHOTS and b.team_provider_id == sp.team:
                sp.shots.append(_shot(actions, j, phase))
            own_goal = b.result == "owngoal" and b.team_provider_id != sp.team
            if own_goal and sp.own_goal_phase is None:
                sp.own_goal_phase = phase
        counter = sp.ended_by_turnover and _opponent_shot_after(actions, end, sp, cfg)
        sp.outcome = derive_outcome(sp, counter)
        result.append(sp)
    return result


def _shot(actions: Sequence[Action], i: int, phase: Literal[1, 2]) -> Shot:
    s = actions[i]
    return Shot(s.action_index, phase, s.xg or 0.0, s.result == "success", shot_outcome(actions, i))


def _opponent_shot_after(actions: Sequence[Action], start: int, sp: SetPiece, cfg: Config) -> bool:
    """Dizi top kaybıyla bittiyse, rakip `counter_s` saniye içinde şut çekti mi."""
    if start >= len(actions):
        return False
    t0 = actions[start].time_s
    for b in actions[start:]:
        if b.period != sp.period or b.time_s - t0 > cfg.counter_s:
            return False
        if b.team_provider_id == sp.team and b.type in RESTARTS | DEAD_BALLS:
            return False
        if b.team_provider_id != sp.team and b.type in SHOTS:
            return True
    return False
