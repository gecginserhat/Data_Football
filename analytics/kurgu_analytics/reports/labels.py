"""Rapor metinleri: metrik adları, birimleri ve Türkçe sayı biçimi.

Web tarafındaki karşılıkları `apps/web/src/lib/metric-display.ts` (birim, grup, sıra) ve
`apps/web/messages/tr.json` (`metrics.<id>.label`) dosyalarıdır; `tests/test_report_labels.py`
ikisinin aynı kaldığını denetler. Formül yoktur; değerler hesaplanmış gelir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Unit = Literal["goals", "xg", "diff", "ratio", "per_match", "per_set_piece", "per_100"]
Group = Literal["attack", "defence", "other"]


@dataclass(frozen=True, slots=True)
class MetricLabel:
    label: str
    unit: Unit
    group: Group


METRICS: dict[str, MetricLabel] = {
    "set_piece_goals": MetricLabel("Duran top golü", "goals", "attack"),
    "set_piece_xg": MetricLabel("Duran top xG", "xg", "attack"),
    "set_piece_goal_share": MetricLabel("Duran top payı (gollerin %)", "ratio", "attack"),
    "set_piece_goals_minus_xg": MetricLabel("Gol eksi xG", "diff", "attack"),
    "set_piece_goals_per_match": MetricLabel("Maç başı duran top golü", "per_match", "attack"),
    "set_pieces_per_match": MetricLabel("Maç başı duran top", "per_match", "attack"),
    "corners_per_match": MetricLabel("Korner / maç", "per_match", "attack"),
    "goals_per_100_corners": MetricLabel("100 kornere düşen gol", "per_100", "attack"),
    "first_contact_win_pct": MetricLabel("İlk temas kazanma % (hücum)", "ratio", "attack"),
    "shots_per_set_piece": MetricLabel("Duran top başına şut", "ratio", "attack"),
    "xg_per_set_piece": MetricLabel("Duran top başına xG", "per_set_piece", "attack"),
    "second_phase_xg_share": MetricLabel("İkinci faz xG payı", "ratio", "attack"),
    "headed_goals": MetricLabel("Kafa golü", "goals", "attack"),
    "direct_fk_goals": MetricLabel("Direkt serbest vuruş golü", "goals", "attack"),
    "set_piece_goals_against": MetricLabel("Duran toptan yenilen gol", "goals", "defence"),
    "first_contact_win_pct_def": MetricLabel("İlk temas kazanma % (savunma)", "ratio", "defence"),
    "aerial_win_pct": MetricLabel("Hava topu kazanma %", "ratio", "defence"),
    "aerials_won_per_match": MetricLabel("Kazanılan hava topu / maç", "per_match", "defence"),
    "clearances_per_match": MetricLabel("Uzaklaştırma / maç", "per_match", "defence"),
    "fouls_committed_per_match": MetricLabel("Yapılan faul / maç", "per_match", "defence"),
    "fouls_won_per_match": MetricLabel("Kazanılan faul / maç", "per_match", "other"),
    "fast_break_goals": MetricLabel("Hızlı hücum golü", "goals", "other"),
}

GROUP_LABELS: dict[Group, str] = {"attack": "Hücum", "defence": "Savunma", "other": "Diğer"}
SOURCE_LABELS = {
    "seed": "tohum",
    "events": "olay verisi",
    "import": "kulüp kaydı",
    "provider": "sağlayıcı",
}
SP_TYPES = {"corner": "Korner", "free_kick": "Serbest vuruş", "throw_in": "Uzun taç"}
SIDES = {"left": "sol", "right": "sağ"}
CONFIDENCE = {"high": "Yüksek", "medium": "Orta", "low": "Düşük"}
STATUS = {"suggested": "Önerildi", "accepted": "Kabul edildi", "rejected": "Reddedildi"}

_DECIMALS: dict[Unit, int] = {
    "goals": 0,
    "xg": 1,
    "diff": 1,
    "ratio": 1,
    "per_match": 2,
    "per_set_piece": 3,
    "per_100": 1,
}


def tr_number(x: float, decimals: int) -> str:
    """Türkçe sayı: binlik nokta, ondalık virgül; `-0,0` yazılmaz."""
    text = f"{abs(x):,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"-{text}" if x < 0 and float(f"{abs(x):.{decimals}f}") != 0 else text


def source_key(source: str) -> str:
    if source.startswith("seed"):
        return "seed"
    return source if source in ("events", "import") else "provider"


def metric_label(metric: str) -> str:
    meta = METRICS.get(metric)
    return meta.label if meta else metric


def format_metric(metric: str, value: float) -> str:
    """Web ile aynı biçim: oran yüzde (bir ondalık), gol−xG işaretli, sayım tam sayı."""
    if metric not in METRICS:
        # Katalog dışı kanıt değerleri (rutin ve savunma kaydı sayımları):
        # tam sayı ya da iki ondalık.
        return tr_number(value, 0 if float(value).is_integer() else 2)
    unit = METRICS[metric].unit
    if unit == "ratio":
        return f"%{tr_number(value * 100, 1)}"
    if unit == "goals" and not float(value).is_integer():
        return tr_number(value, 1)
    text = tr_number(value, _DECIMALS[unit])
    if unit == "diff" and not text.startswith("-") and float(f"{value:.1f}") != 0:
        return f"+{text}"
    return text
