"""Takım duran top metrikleri (SPEC §6.1).

Girdi, takım başına bir satırlık "ham" tablodur (dizin takım kimliği). Sütunlar isteğe bağlıdır;
bir metriğin girdisi yoksa o metrik hesaplanmaz. Ham sütunlar iki kaynaktan gelir:

- Takım-sezon kaydı (tohum, sağlayıcı ya da içe aktarım): `matches`, `goals`, `set_piece_goals`,
  `set_piece_xg`, `corners_per_match`, `headed_goals`, `direct_fk_goals`, `fast_break_goals`,
  `aerial_win_pct` (0-100), `aerials_won_per_match`, `fouls_committed`, `fouls_won` (sezon
  toplamı), `clearances_per_match`.
- Olay verisinden dizi toplamları (`mv_team_setpiece_season`): `set_pieces`, `corners`,
  `sp_with_contact`, `sp_first_contact_won`, `sp_with_shot`, `sp_xg_phase1`, `sp_xg_phase2`,
  `corner_goals`, `set_piece_goals_against`, `def_sp_with_contact`, `def_sp_first_contact_won`.

Penaltı hiçbir girdide yer almaz (duran top tanımı dışında; ayrı raporlanır).
Tüm fonksiyonlar saftır. Oranlar 0-1 aralığında döner (yüzde biçimi arayüzün işidir).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from kurgu_analytics.metrics.ranking import league_percentile, league_rank, low_sample
from kurgu_analytics.metrics.shrinkage import beta_binomial_shrink, gamma_poisson_shrink

Kind = Literal["count", "rate", "per_match", "diff", "ratio"]
Unit = Literal["goals", "xg", "ratio", "per_match", "per_set_piece", "per_100"]


def _col(raw: pd.DataFrame, name: str) -> pd.Series:
    if name in raw.columns:
        return pd.to_numeric(raw[name], errors="coerce").astype(float)
    return pd.Series(np.nan, index=raw.index, dtype=float)


def _divide(num: pd.Series, den: pd.Series) -> pd.Series:
    """Payda 0 ya da eksikse NaN; aksi halde bölüm."""
    return num.where(den > 0) / den.where(den > 0)


# --- Formüller -----------------------------------------------------------------------------


def set_piece_goals(raw: pd.DataFrame) -> pd.Series:
    """Duran top golü.

    Formül: duran top dizilerinden gelen goller (penaltı hariç); kayıttaki değer.
    Birim: gol. Kaynak: SPEC §6.1, tohum `set_piece_goals` ya da olay verisi.
    """
    return _col(raw, "set_piece_goals")


def set_piece_xg(raw: pd.DataFrame) -> pd.Series:
    """Duran top xG.

    Formül: Σ şut xG (tüm fazlar). Birim: xG. Kaynak: SPEC §6.1.
    """
    return _col(raw, "set_piece_xg")


def set_piece_goal_share(raw: pd.DataFrame) -> pd.Series:
    """Duran top payı.

    Formül: set_piece_goals / goals (goals > 0). Birim: oran (0-1).
    Kaynak: SPEC §6.1; 2025/26 lig toplamı 166 / 812 = %20,4.
    """
    return _divide(_col(raw, "set_piece_goals"), _col(raw, "goals"))


def set_piece_goals_minus_xg(raw: pd.DataFrame) -> pd.Series:
    """Gol eksi xG.

    Formül: set_piece_goals − set_piece_xg. Birim: gol. Kalıcı bir beceri göstergesi değildir
    (bitiricilik ya da şans). Kaynak: SPEC §6.1.
    """
    return _col(raw, "set_piece_goals") - _col(raw, "set_piece_xg")


def set_piece_goals_per_match(raw: pd.DataFrame) -> pd.Series:
    """Maç başı duran top golü.

    Formül: set_piece_goals / matches. Birim: maç başına gol. Kaynak: SPEC §6.1, §6.4.
    """
    return _divide(_col(raw, "set_piece_goals"), _col(raw, "matches"))


def set_pieces_per_match(raw: pd.DataFrame) -> pd.Series:
    """Maç başı duran top.

    Formül: set_pieces / matches (korner, serbest vuruş ve ceza sahasına uzun taç; penaltı
    hariç). Birim: maç başına dizi. Kaynak: SPEC §6.1, olay verisi.
    """
    return _divide(_col(raw, "set_pieces"), _col(raw, "matches"))


def corner_count(raw: pd.DataFrame) -> pd.Series:
    """Korner sayısı.

    Formül: olay verisinde `corners`; yoksa corners_per_match × matches (tohum).
    Birim: korner. Kaynak: SPEC §6.1.
    """
    from_events = _col(raw, "corners")
    from_rate = _col(raw, "corners_per_match") * _col(raw, "matches")
    return from_events.fillna(from_rate)


def corners_per_match(raw: pd.DataFrame) -> pd.Series:
    """Korner / maç.

    Formül: corners / matches; olay verisi yoksa kayıttaki corners_per_match.
    Birim: maç başına korner. Kaynak: SPEC §6.1.
    """
    return _divide(_col(raw, "corners"), _col(raw, "matches")).fillna(
        _col(raw, "corners_per_match")
    )


def first_contact_win_pct(raw: pd.DataFrame) -> pd.Series:
    """İlk temas kazanma % (hücum).

    Formül: kendi ilk temaslarımız / ilk teması belli teslimler
    (sp_first_contact_won / sp_with_contact). Birim: oran (0-1). Kaynak: SPEC §6.1, olay verisi.
    """
    return _divide(_col(raw, "sp_first_contact_won"), _col(raw, "sp_with_contact"))


def first_contact_win_pct_def(raw: pd.DataFrame) -> pd.Series:
    """İlk temas kazanma % (savunma).

    Formül: rakip teslimlerinde ilk temasın bizde olduğu dizi / ilk teması belli rakip teslimleri
    (def_sp_first_contact_won / def_sp_with_contact). Birim: oran (0-1). Kaynak: SPEC §6.1.
    """
    return _divide(_col(raw, "def_sp_first_contact_won"), _col(raw, "def_sp_with_contact"))


def shots_per_set_piece(raw: pd.DataFrame) -> pd.Series:
    """Duran top başına şut.

    Formül: şutlu dizi / dizi (sp_with_shot / set_pieces). Birim: oran (0-1).
    Kaynak: SPEC §6.1.
    """
    return _divide(_col(raw, "sp_with_shot"), _col(raw, "set_pieces"))


def xg_per_set_piece(raw: pd.DataFrame) -> pd.Series:
    """Duran top başına xG.

    Formül: set_piece_xg / set_pieces. Birim: dizi başına xG. Kaynak: SPEC §6.1.
    """
    return _divide(_col(raw, "set_piece_xg"), _col(raw, "set_pieces"))


def phase_xg_shares(raw: pd.DataFrame) -> pd.DataFrame:
    """Birinci ve ikinci faz xG payları.

    Formül: payₖ = sp_xg_phaseₖ / (sp_xg_phase1 + sp_xg_phase2), k ∈ {1, 2}; iki payın toplamı 1.
    Birim: oran (0-1). Kaynak: SPEC §3.2 (faz tanımı), §6.1.
    """
    p1, p2 = _col(raw, "sp_xg_phase1"), _col(raw, "sp_xg_phase2")
    total = p1 + p2
    return pd.DataFrame({"phase1": _divide(p1, total), "phase2": _divide(p2, total)})


def second_phase_xg_share(raw: pd.DataFrame) -> pd.Series:
    """İkinci faz payı.

    Formül: faz 2 xG / toplam duran top xG (bkz. `phase_xg_shares`). Birim: oran (0-1).
    Kaynak: SPEC §6.1.
    """
    return phase_xg_shares(raw)["phase2"]


def corner_goals_or_approx(raw: pd.DataFrame) -> pd.DataFrame:
    """100 kornere düşen gol hesabının payı.

    Formül: olay verisinde korner golleri (`corner_goals`); yoksa tüm duran top golleri
    (yaklaşık, A-37). Çıktı: `goals` ve `approx` (yaklaşık mı) sütunları. Kaynak: SPEC §6.1 notu.
    """
    exact = _col(raw, "corner_goals")
    approx = exact.isna() & _col(raw, "set_piece_goals").notna()
    return pd.DataFrame({"goals": exact.fillna(_col(raw, "set_piece_goals")), "approx": approx})


def goals_per_100_corners(raw: pd.DataFrame) -> pd.Series:
    """100 kornere düşen gol.

    Formül: korner golleri / korner × 100 (bkz. `corner_goals_or_approx`, `corner_count`).
    Birim: 100 korner başına gol. Kaynak: SPEC §6.1.
    """
    return _divide(corner_goals_or_approx(raw)["goals"], corner_count(raw)) * 100


def set_piece_goals_against(raw: pd.DataFrame) -> pd.Series:
    """Duran toptan yenilen gol.

    Formül: rakip dizilerinden yenilen goller. Yalnızca olay verisinden ya da kulübün kendi
    kaydından gelir; kamuya açık tohumda yoktur. Birim: gol. Kaynak: SPEC §6.1, CLAUDE.md.
    """
    return _col(raw, "set_piece_goals_against")


def headed_goals(raw: pd.DataFrame) -> pd.Series:
    """Kafa golü. Formül: kayıttaki değer. Birim: gol. Kaynak: SPEC §6.1, tohum."""
    return _col(raw, "headed_goals")


def direct_fk_goals(raw: pd.DataFrame) -> pd.Series:
    """Direkt serbest vuruş golü. Formül: kayıttaki değer. Birim: gol. Kaynak: SPEC §6.1."""
    return _col(raw, "direct_fk_goals")


def fast_break_goals(raw: pd.DataFrame) -> pd.Series:
    """Hızlı hücum golü. Formül: kayıttaki değer. Birim: gol. Kaynak: SPEC §6.1, tohum."""
    return _col(raw, "fast_break_goals")


def aerial_win_pct(raw: pd.DataFrame) -> pd.Series:
    """Hava topu kazanma % (savunma için dolaylı gösterge).

    Formül: kayıttaki yüzde / 100 (tohum 0-100 verir). Birim: oran (0-1).
    Kaynak: SPEC §6.1, tohum `aerial_win_pct`.
    """
    return _col(raw, "aerial_win_pct") / 100


def aerials_won_per_match(raw: pd.DataFrame) -> pd.Series:
    """Kazanılan hava topu / maç (dolaylı). Formül: kayıttaki değer. Birim: maç başına."""
    return _col(raw, "aerials_won_per_match")


def fouls_committed_per_match(raw: pd.DataFrame) -> pd.Series:
    """Yapılan faul / maç (dolaylı; rakibe serbest vuruş verme eğilimi).

    Formül: fouls_committed / matches. Birim: maç başına faul. Kaynak: SPEC §6.1, tohum.
    """
    return _divide(_col(raw, "fouls_committed"), _col(raw, "matches"))


def fouls_won_per_match(raw: pd.DataFrame) -> pd.Series:
    """Kazanılan faul / maç. Formül: fouls_won / matches. Birim: maç başına faul."""
    return _divide(_col(raw, "fouls_won"), _col(raw, "matches"))


def clearances_per_match(raw: pd.DataFrame) -> pd.Series:
    """Uzaklaştırma / maç (dolaylı; ikinci top göstergesi). Formül: kayıttaki değer."""
    return _col(raw, "clearances_per_match")


# --- Katalog -------------------------------------------------------------------------------

Pair = Callable[[pd.DataFrame], tuple[pd.Series, pd.Series]]
"""Büzülme girdisi: (başarı ya da sayım, deneme ya da maç)."""


def _pair(num: Callable[[pd.DataFrame], pd.Series], den: str) -> Pair:
    return lambda raw: (num(raw), _col(raw, den))


def _per_match_pair(per_match: Callable[[pd.DataFrame], pd.Series]) -> Pair:
    return lambda raw: (per_match(raw) * _col(raw, "matches"), _col(raw, "matches"))


@dataclass(frozen=True, slots=True)
class MetricDef:
    id: str
    kind: Kind
    unit: Unit
    formula: Callable[[pd.DataFrame], pd.Series]
    indirect: bool = False
    """Savunma için dolaylı gösterge (hava topu, faul, uzaklaştırma)."""
    shrink: Literal["beta", "gamma"] | None = None
    pair: Pair | None = None
    scale: float = 1.0
    """Büzülmüş değerin birimi için çarpan (ör. 100 kornere gol)."""


CATALOG: tuple[MetricDef, ...] = (
    MetricDef("set_piece_goals", "count", "goals", set_piece_goals),
    MetricDef("set_piece_xg", "count", "xg", set_piece_xg),
    MetricDef(
        "set_piece_goal_share",
        "rate",
        "ratio",
        set_piece_goal_share,
        shrink="beta",
        pair=_pair(set_piece_goals, "goals"),
    ),
    MetricDef("set_piece_goals_minus_xg", "diff", "goals", set_piece_goals_minus_xg),
    MetricDef(
        "set_piece_goals_per_match",
        "per_match",
        "per_match",
        set_piece_goals_per_match,
        shrink="gamma",
        pair=_pair(set_piece_goals, "matches"),
    ),
    MetricDef(
        "set_pieces_per_match",
        "per_match",
        "per_match",
        set_pieces_per_match,
        shrink="gamma",
        pair=_pair(lambda r: _col(r, "set_pieces"), "matches"),
    ),
    MetricDef(
        "corners_per_match",
        "per_match",
        "per_match",
        corners_per_match,
        shrink="gamma",
        pair=_pair(corner_count, "matches"),
    ),
    MetricDef(
        "first_contact_win_pct",
        "rate",
        "ratio",
        first_contact_win_pct,
        shrink="beta",
        pair=_pair(lambda r: _col(r, "sp_first_contact_won"), "sp_with_contact"),
    ),
    MetricDef(
        "first_contact_win_pct_def",
        "rate",
        "ratio",
        first_contact_win_pct_def,
        shrink="beta",
        pair=_pair(lambda r: _col(r, "def_sp_first_contact_won"), "def_sp_with_contact"),
    ),
    MetricDef(
        "shots_per_set_piece",
        "rate",
        "ratio",
        shots_per_set_piece,
        shrink="beta",
        pair=_pair(lambda r: _col(r, "sp_with_shot"), "set_pieces"),
    ),
    MetricDef("xg_per_set_piece", "ratio", "per_set_piece", xg_per_set_piece),
    MetricDef("second_phase_xg_share", "ratio", "ratio", second_phase_xg_share),
    MetricDef(
        "goals_per_100_corners",
        "rate",
        "per_100",
        goals_per_100_corners,
        shrink="beta",
        pair=lambda r: (corner_goals_or_approx(r)["goals"], corner_count(r)),
        scale=100.0,
    ),
    MetricDef("set_piece_goals_against", "count", "goals", set_piece_goals_against),
    MetricDef("headed_goals", "count", "goals", headed_goals),
    MetricDef("direct_fk_goals", "count", "goals", direct_fk_goals),
    MetricDef("fast_break_goals", "count", "goals", fast_break_goals),
    MetricDef("aerial_win_pct", "rate", "ratio", aerial_win_pct, indirect=True),
    MetricDef(
        "aerials_won_per_match",
        "per_match",
        "per_match",
        aerials_won_per_match,
        indirect=True,
        shrink="gamma",
        pair=_per_match_pair(aerials_won_per_match),
    ),
    MetricDef(
        "fouls_committed_per_match",
        "per_match",
        "per_match",
        fouls_committed_per_match,
        indirect=True,
        shrink="gamma",
        pair=_pair(lambda r: _col(r, "fouls_committed"), "matches"),
    ),
    MetricDef(
        "fouls_won_per_match",
        "per_match",
        "per_match",
        fouls_won_per_match,
        shrink="gamma",
        pair=_pair(lambda r: _col(r, "fouls_won"), "matches"),
    ),
    MetricDef(
        "clearances_per_match",
        "per_match",
        "per_match",
        clearances_per_match,
        indirect=True,
        shrink="gamma",
        pair=_per_match_pair(clearances_per_match),
    ),
)
METRICS: dict[str, MetricDef] = {m.id: m for m in CATALOG}

APPROX_METRICS = frozenset({"goals_per_100_corners"})
"""Tohumda yaklaşık hesaplanabilen metrikler (A-37)."""

TEAM_METRIC_COLUMNS = [
    "team",
    "metric",
    "value",
    "rank",
    "percentile",
    "teams",
    "trials",
    "matches",
    "shrunk_mean",
    "shrunk_low",
    "shrunk_high",
    "low_sample",
    "approx",
]


def team_metrics(raw: pd.DataFrame) -> pd.DataFrame:
    """Tüm katalog metriklerini takım başına hesaplar, sıralar ve büzer.

    Çıktı uzun biçimdedir (`TEAM_METRIC_COLUMNS`): takım × hesaplanabilen metrik başına bir satır.
    - `rank`, `percentile`: ham değer üzerinden lig sırası (1 = en yüksek; eşitler aynı sıra).
    - `teams`: o metrikte değeri olan takım sayısı.
    - `shrunk_*`: beta-binom ya da gamma-Poisson sonsal ortalaması ve %80 aralık (A-35); büzülme
      girdisi olmayan metriklerde boş.
    - `trials`: oran metriklerinde deneme sayısı; `low_sample`: deneme < 8 ya da maç < 5.
    - `approx`: değer yaklaşık mı (A-37).
    Kaynak: SPEC §6.1, §6.4.
    """
    matches = _col(raw, "matches")
    frames: list[pd.DataFrame] = []
    for metric in CATALOG:
        values = metric.formula(raw)
        valid = values.notna()
        if not valid.any():
            continue
        trials = pd.Series(np.nan, index=raw.index, dtype=float)
        shrunk = pd.DataFrame(np.nan, index=raw.index, columns=["mean", "low", "high"])
        if metric.pair is not None:
            successes, exposure = metric.pair(raw)
            usable = valid & successes.notna() & exposure.notna()
            if usable.any():
                shrink = beta_binomial_shrink if metric.shrink == "beta" else gamma_poisson_shrink
                shrunk.loc[usable] = (
                    shrink(successes[usable], exposure[usable]).to_numpy() * metric.scale
                )
            if metric.shrink == "beta":
                trials = exposure
        approx = (
            corner_goals_or_approx(raw)["approx"]
            if metric.id in APPROX_METRICS
            else pd.Series(False, index=raw.index)
        )
        part = pd.DataFrame(
            {
                "team": raw.index,
                "metric": metric.id,
                "value": values,
                "rank": league_rank(values),
                "percentile": league_percentile(values),
                "teams": int(valid.sum()),
                "trials": trials if metric.shrink == "beta" else np.nan,
                "matches": matches,
                "shrunk_mean": shrunk["mean"],
                "shrunk_low": shrunk["low"],
                "shrunk_high": shrunk["high"],
                "low_sample": low_sample(trials if metric.shrink == "beta" else None, matches),
                "approx": approx.astype(bool),
            },
            index=raw.index,
        )
        frames.append(part[valid])
    if not frames:
        return pd.DataFrame(columns=TEAM_METRIC_COLUMNS)
    return pd.concat(frames, ignore_index=True)[TEAM_METRIC_COLUMNS]


def league_benchmarks(metrics: pd.DataFrame) -> pd.DataFrame:
    """Metrik başına lig kıyası: en düşük, en yüksek, ortalama ve takım sayısı.

    Formül: min, max ve aritmetik ortalama (takım değerleri üzerinden; ağırlıksız).
    Girdi `team_metrics` çıktısıdır. Birim: metriğin birimi. Kaynak: SPEC §13.2 (profil
    çubukları lig en düşük ve en yüksek değeri arasında çizilir, lig ortalaması işaretlenir).
    """
    if metrics.empty:
        return pd.DataFrame(columns=["metric", "min", "max", "mean", "teams"])
    grouped = metrics.groupby("metric", sort=False)["value"]
    return pd.DataFrame(
        {
            "min": grouped.min(),
            "max": grouped.max(),
            "mean": grouped.mean(),
            "teams": grouped.count(),
        }
    ).reset_index()


def league_totals(raw: pd.DataFrame) -> dict[str, float]:
    """Lig toplamları ve toplamdan oranlar.

    Formül: Σ goals, Σ set_piece_goals, lig maçı = Σ matches / 2;
    set_piece_goal_share = Σ set_piece_goals / Σ goals;
    set_piece_goals_per_match = Σ set_piece_goals / lig maçı.
    Birim: gol, maç, oran. Kaynak: SPEC §6.1 (2025/26: 166 / 812 = %20,4; 166 / 306 = 0,542).
    Bir girdisi eksik olan toplam döndürülmez.
    """
    out: dict[str, float] = {}
    sums = {c: _col(raw, c) for c in ("goals", "set_piece_goals", "matches", "set_piece_xg")}
    for name, col in sums.items():
        if col.notna().any() and col.notna().all():
            out[name] = float(col.sum())
    if "matches" in out:
        out["matches"] = out["matches"] / 2
    if out.get("goals") and "set_piece_goals" in out:
        out["set_piece_goal_share"] = out["set_piece_goals"] / out["goals"]
    if out.get("matches") and "set_piece_goals" in out:
        out["set_piece_goals_per_match"] = out["set_piece_goals"] / out["matches"]
    return out
