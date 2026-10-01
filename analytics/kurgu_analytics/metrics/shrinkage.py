"""Küçük örneklem büzülmesi (SPEC §6.4).

- Oranlar: beta-binom. Önsel, takımların gözlenen oranlarından momentler yöntemiyle kestirilir.
- Maç başı sayımlar: gamma-Poisson. Önsel, takımların maç başı oranlarından kestirilir.

Her iki modelde sonsal ortalamanın yanında %80 güvenilir aralık (10. ve 90. yüzdelikler) verilir.
Fonksiyonlar saftır; girdiyi değiştirmez.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

CREDIBLE_MASS = 0.8
"""Güvenilir aralık kütlesi; alt ve üst sınırlar (1 ± 0.8) / 2 yüzdelikleridir."""
_LOW_Q = (1 - CREDIBLE_MASS) / 2
_HIGH_Q = 1 - _LOW_Q

KAPPA_MAX = 1000.0
"""Takımlar arasında varyans yoksa önsel ağırlığı bu sınırda kesilir (sonsuz κ yerine)."""
FALLBACK_KAPPA = 2.0
"""Veri önsel kestirmeye yetmezse (κ ≤ 0) kullanılan zayıf önsel ağırlığı."""


@dataclass(frozen=True, slots=True)
class BetaPrior:
    alpha: float
    beta: float


@dataclass(frozen=True, slots=True)
class GammaPrior:
    shape: float
    """a (şekil)."""
    rate: float
    """b (oran); birimi maç."""


def beta_prior_mom(successes: pd.Series, trials: pd.Series) -> BetaPrior:
    """Beta önseli momentler yöntemiyle kestirir.

    Formül (SPEC §6.4): p_i = başarı_i / deneme_i (deneme > 0 olan takımlar),
    μ = ortalama(p), σ² = varyans(p) (ddof = 0), κ = μ(1 − μ) / σ² − 1, α = μκ, β = (1 − μ)κ.
    Birim: boyutsuz.

    Kenar durumlar:
    - İkiden az takım ya da μ ∈ {0, 1}: tekdüze önsel Beta(1, 1).
    - σ² = 0: κ = KAPPA_MAX (tüm takımlar aynıysa önsel lig ortalamasına güçlü çeker).
    - κ ≤ 0 (gözlenen yayılım binom sınırını aşıyor): κ = FALLBACK_KAPPA.
    """
    mask = trials > 0
    rates = (successes[mask] / trials[mask]).astype(float)
    if len(rates) < 2:
        return BetaPrior(1.0, 1.0)
    mu = float(rates.mean())
    if mu <= 0.0 or mu >= 1.0:
        return BetaPrior(1.0, 1.0)
    var = float(rates.var(ddof=0))
    kappa = KAPPA_MAX if var <= 0 else mu * (1 - mu) / var - 1
    if kappa <= 0:
        kappa = FALLBACK_KAPPA
    kappa = min(kappa, KAPPA_MAX)
    return BetaPrior(mu * kappa, (1 - mu) * kappa)


def beta_binomial_shrink(
    successes: pd.Series, trials: pd.Series, prior: BetaPrior | None = None
) -> pd.DataFrame:
    """Oranları beta-binom sonsalına büzer.

    Formül: sonsal = Beta(α + başarı, β + deneme − başarı);
    ortalama = (başarı + α) / (deneme + α + β); aralık = sonsalın %10 ve %90 yüzdelikleri.
    Birim: oran (0-1). Kaynak: SPEC §6.4.
    Çıktı sütunları: `mean`, `low`, `high`; dizin girdiyle aynıdır. Deneme sayısı eksik (NaN)
    olan satırlar NaN döner.
    """
    prior = prior or beta_prior_mom(successes, trials)
    a = successes.astype(float) + prior.alpha
    b = trials.astype(float) - successes.astype(float) + prior.beta
    valid = a.notna() & b.notna()
    out = pd.DataFrame(index=successes.index, columns=["mean", "low", "high"], dtype=float)
    out.loc[valid, "mean"] = a[valid] / (a[valid] + b[valid])
    out.loc[valid, "low"] = stats.beta.ppf(_LOW_Q, a[valid], b[valid])
    out.loc[valid, "high"] = stats.beta.ppf(_HIGH_Q, a[valid], b[valid])
    return out


def gamma_prior_mom(counts: pd.Series, exposures: pd.Series) -> GammaPrior:
    """Gamma önseli takımların maç başı oranlarından momentler yöntemiyle kestirir.

    Formül: r_i = sayım_i / maç_i (maç > 0), μ = ortalama(r), σ² = varyans(r) (ddof = 0);
    Gamma(a, b) için ortalama a / b = μ ve varyans a / b² = σ² olduğundan b = μ / σ², a = μ·b.
    Birim: b maç, a sayım. Kaynak: SPEC §6.4 ("önsel Gamma(a, b) lig takımlarından kestirilir").

    Kenar durumlar: ikiden az takım, μ = 0 ya da σ² = 0 ise bir maçlık zayıf önsel Gamma(μ, 1)
    kullanılır (μ = 0 ise a = 0,5).
    """
    mask = exposures > 0
    rates = (counts[mask] / exposures[mask]).astype(float)
    if len(rates) == 0:
        return GammaPrior(0.5, 1.0)
    mu = float(rates.mean())
    var = float(rates.var(ddof=0)) if len(rates) > 1 else 0.0
    if mu <= 0:
        return GammaPrior(0.5, 1.0)
    if var <= 0:
        return GammaPrior(mu, 1.0)
    rate = mu / var
    return GammaPrior(mu * rate, rate)


def gamma_poisson_shrink(
    counts: pd.Series, exposures: pd.Series, prior: GammaPrior | None = None
) -> pd.DataFrame:
    """Maç başı sayımları gamma-Poisson sonsalına büzer.

    Formül: sonsal = Gamma(a + sayım, b + maç); ortalama = (a + sayım) / (b + maç);
    aralık = sonsalın %10 ve %90 yüzdelikleri. Birim: maç başına sayım. Kaynak: SPEC §6.4.
    Çıktı sütunları: `mean`, `low`, `high`.
    """
    prior = prior or gamma_prior_mom(counts, exposures)
    shape = counts.astype(float) + prior.shape
    rate = exposures.astype(float) + prior.rate
    valid = shape.notna() & rate.notna()
    out = pd.DataFrame(index=counts.index, columns=["mean", "low", "high"], dtype=float)
    out.loc[valid, "mean"] = shape[valid] / rate[valid]
    scale = np.asarray(1.0 / rate[valid], dtype=float)
    out.loc[valid, "low"] = stats.gamma.ppf(_LOW_Q, shape[valid], scale=scale)
    out.loc[valid, "high"] = stats.gamma.ppf(_HIGH_Q, shape[valid], scale=scale)
    return out
