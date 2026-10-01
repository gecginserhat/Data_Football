"""Oyuncu hava skoru (SPEC §7.3, A-81).

Hava kapasitesi (kendi savunmacılarımız) ve hava tehdidi (rakip hedefleri) aynı 0-1 ölçeğidir.
"""

from __future__ import annotations

from dataclasses import dataclass

HEIGHT_RANGE = (170.0, 200.0)
"""Boy (cm): 170 → 0, 200 → 1."""
AERIAL_RANGE = (0.30, 0.70)
"""Hava topu kazanma oranı: %30 → 0, %70 → 1."""
GOAL_BONUS = 0.05
GOAL_BONUS_MAX = 0.15


@dataclass(frozen=True, slots=True)
class AerialScore:
    value: float
    components: tuple[str, ...]
    """Skora giren bileşenler: `height`, `aerial`, `jump`, `goals`."""


def _scale(value: float, low: float, high: float) -> float:
    return min(1.0, max(0.0, (value - low) / (high - low)))


def aerial_score(
    height_cm: float | None,
    aerial_win_pct: float | None = None,
    jump_score: float | None = None,
    sp_goals: int | None = None,
) -> AerialScore | None:
    """Hava skoru = mevcut bileşenlerin ortalaması (+ duran top golü başına 0,05, en çok 0,15).

    - Boy: (boy − 170) / 30, [0, 1] aralığına kırpılır.
    - Hava topu kazanma oranı (0-1): (oran − 0,30) / 0,40, kırpılır.
    - Sıçrama skoru: 0-1 olarak girilir.
    - Duran top golü yalnız rakip tehdidinde verilir. Sonuç en çok 1'dir.
    Bileşen yoksa `None` döner. Birim: birimsiz (0-1). Kaynak: SPEC §7.3, A-81.
    """
    parts: list[float] = []
    names: list[str] = []
    if height_cm is not None:
        parts.append(_scale(float(height_cm), *HEIGHT_RANGE))
        names.append("height")
    if aerial_win_pct is not None:
        if not 0 <= aerial_win_pct <= 1:
            raise ValueError("aerial_win_pct must be between 0 and 1")
        parts.append(_scale(float(aerial_win_pct), *AERIAL_RANGE))
        names.append("aerial")
    if jump_score is not None:
        if not 0 <= jump_score <= 1:
            raise ValueError("jump_score must be between 0 and 1")
        parts.append(float(jump_score))
        names.append("jump")
    if not parts:
        return None
    value = sum(parts) / len(parts)
    if sp_goals:
        value += min(GOAL_BONUS_MAX, GOAL_BONUS * sp_goals)
        names.append("goals")
    return AerialScore(round(min(1.0, value), 4), tuple(names))
