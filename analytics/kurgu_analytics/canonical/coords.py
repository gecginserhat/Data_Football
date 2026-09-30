"""Sağlayıcı koordinatlarından kanonik koordinata dönüşüm (SPEC §4, ADR-0003).

Kanonik saha 105 × 68 m; x hücum yönünde (hücum edilen kale x = 105), y = 0 hücum eden
takımın sağ taç çizgisi. StatsBomb 120 × 80 yarda birimli ve y ekseni aşağı doğru artar
(y = 0 hücum eden takımın sol taç çizgisi), bu yüzden y çevrilir.

Doğrusal ölçekleme ceza sahası gibi çizgileri kaydırır (StatsBomb ceza sahası x = 102,
doğrusal karşılığı 89,25 m; gerçek 88,5 m). Bu yüzden dönüşüm saha çizgilerini referans
alan parçalı doğrusal eşlemedir: her referans çizgi kanonik karşılığına tam oturur,
aradaki noktalar doğrusal ara değerlenir.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence

CANONICAL_LENGTH = 105.0
CANONICAL_WIDTH = 68.0

# (StatsBomb, kanonik) çiftleri, artan sırada. Kaynak: StatsBomb Open Data belgeleri ve
# SPEC §4 referans noktaları.
_SB_X: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (6.0, 5.5),  # altı pas
    (12.0, 11.0),  # penaltı noktası
    (18.0, 16.5),  # ceza sahası
    (60.0, 52.5),  # orta çizgi
    (102.0, 88.5),
    (108.0, 94.0),
    (114.0, 99.5),
    (120.0, 105.0),
)
# StatsBomb y → kanonik y (henüz çevrilmemiş, "üstten" ölçü). Çevirme ayrı yapılır.
_SB_Y: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (18.0, 13.84),  # ceza sahası
    (30.0, 24.84),  # altı pas
    (36.0, 30.34),  # direk
    (40.0, 34.0),  # kale merkezi
    (44.0, 37.66),
    (50.0, 43.16),
    (62.0, 54.16),
    (80.0, 68.0),
)


def _interp(value: float, table: Sequence[tuple[float, float]]) -> float:
    xs = [a for a, _ in table]
    if value <= xs[0]:
        return table[0][1]
    if value >= xs[-1]:
        return table[-1][1]
    i = bisect_right(xs, value) - 1
    (a0, b0), (a1, b1) = table[i], table[i + 1]
    return b0 + (value - a0) * (b1 - b0) / (a1 - a0)


def statsbomb_to_canonical(x: float, y: float) -> tuple[float, float]:
    """StatsBomb (120 × 80, y aşağı) → kanonik (105 × 68, y = 0 sağ taç).

    Girdi olayı yapan takımın hücum yönüne göredir (StatsBomb bunu zaten sağlar).
    Saha dışı değerler sınıra kırpılır. Birim: metre.
    """
    cx = _interp(x, _SB_X)
    cy = CANONICAL_WIDTH - _interp(y, _SB_Y)
    return cx, cy


def flip(x: float, y: float) -> tuple[float, float]:
    """Karşı takımın bakış açısına çevirir: (105 − x, 68 − y)."""
    return CANONICAL_LENGTH - x, CANONICAL_WIDTH - y
