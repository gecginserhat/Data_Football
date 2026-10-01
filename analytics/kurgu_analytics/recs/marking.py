"""Duran top markaj ataması (SPEC §7.3, ADR-0015, A-82).

Rakip hedefleri ile savunmacılar arasındaki eşleşme Macar algoritmasıyla
(`scipy.optimize.linear_sum_assignment`) en düşük toplam maliyetle bulunur.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

POSITION_PENALTY = 0.15
"""Savunmacı olmayan oyuncuya markaj verilmesinin cezası."""
TIE_BREAK = 0.01


@dataclass(frozen=True, slots=True)
class Target:
    id: str
    threat: float


@dataclass(frozen=True, slots=True)
class Marker:
    id: str
    capacity: float
    position: str
    """`GK`, `DEF`, `MID`, `FWD`."""


@dataclass(frozen=True, slots=True)
class Pair:
    target_id: str
    marker_id: str
    cost: float
    gap: float
    """Tehdit − kapasite (pozitifse savunmacı dezavantajlı)."""


def pair_cost(threat: float, capacity: float, position: str) -> float:
    """Maliyet = max(0, tehdit − kapasite) + mevki cezası + 0,01 × |tehdit − kapasite|.

    Mevki cezası savunmacı (`DEF`) olmayan oyuncu için 0,15'tir. Eşitlik bozucu terim güçlü
    hedefi güçlü savunmacıyla eşler. Birim: birimsiz. Kaynak: SPEC §7.3, A-82.
    """
    gap = threat - capacity
    penalty = 0.0 if position == "DEF" else POSITION_PENALTY
    return max(0.0, gap) + penalty + TIE_BREAK * abs(gap)


def suggest_marking(
    targets: list[Target], markers: list[Marker], fixed: frozenset[str] = frozenset()
) -> list[Pair]:
    """Önerilen eşleşme. Kaleciler ve `fixed` (alan savunması) oyuncular atamaya girmez.

    Hedef sayısı adam sayısını aşarsa en düşük tehditli hedefler eşleşmeden kalır. Sonuç
    hedeflerin tehdidine göre (yüksekten düşüğe) sıralıdır.
    """
    pool = [m for m in markers if m.position != "GK" and m.id not in fixed]
    ranked = sorted(targets, key=lambda t: (-t.threat, t.id))
    if not pool or not ranked:
        return []
    chosen = ranked[: len(pool)]
    cost = np.array(
        [[pair_cost(t.threat, m.capacity, m.position) for m in pool] for t in chosen], dtype=float
    )
    rows, cols = linear_sum_assignment(cost)
    pairs = [
        Pair(
            target_id=chosen[r].id,
            marker_id=pool[c].id,
            cost=round(float(cost[r, c]), 4),
            gap=round(chosen[r].threat - pool[c].capacity, 4),
        )
        for r, c in zip(rows, cols, strict=True)
    ]
    order = {t.id: i for i, t in enumerate(chosen)}
    return sorted(pairs, key=lambda p: order[p.target_id])
