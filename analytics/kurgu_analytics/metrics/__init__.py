"""Metrik formülleri; saf fonksiyonlar, docstring ve birim testle (SPEC §6).

Formüller yalnızca bu pakette bulunur (CLAUDE.md). API ve worker ham toplamları okur, metrikleri
buradaki fonksiyonlarla hesaplar.
"""

from kurgu_analytics.metrics.ranking import (
    MIN_MATCHES,
    MIN_TRIALS,
    league_percentile,
    league_rank,
    low_sample,
)
from kurgu_analytics.metrics.shrinkage import (
    BetaPrior,
    GammaPrior,
    beta_binomial_shrink,
    beta_prior_mom,
    gamma_poisson_shrink,
    gamma_prior_mom,
)
from kurgu_analytics.metrics.team import (
    CATALOG,
    METRICS,
    TEAM_METRIC_COLUMNS,
    MetricDef,
    league_benchmarks,
    league_totals,
    phase_xg_shares,
    team_metrics,
)

__all__ = [
    "CATALOG",
    "METRICS",
    "MIN_MATCHES",
    "MIN_TRIALS",
    "TEAM_METRIC_COLUMNS",
    "BetaPrior",
    "GammaPrior",
    "MetricDef",
    "beta_binomial_shrink",
    "beta_prior_mom",
    "gamma_poisson_shrink",
    "gamma_prior_mom",
    "league_benchmarks",
    "league_percentile",
    "league_rank",
    "league_totals",
    "low_sample",
    "phase_xg_shares",
    "team_metrics",
]
