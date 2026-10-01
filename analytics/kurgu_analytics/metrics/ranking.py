"""Lig sırası, yüzdelik ve az veri bayrağı (SPEC §6.4)."""

from __future__ import annotations

import pandas as pd

MIN_TRIALS = 8
"""Bu sayının altındaki deneme "Az veri" sayılır."""
MIN_MATCHES = 5
"""Bu sayının altındaki maç "Az veri" sayılır."""


def league_rank(values: pd.Series) -> pd.Series:
    """Lig sırası: en yüksek değer 1; eşit değerler aynı sırayı alır, sonraki sıra atlanır.

    Formül: sıra_i = 1 + #{j : değer_j > değer_i} (rekabet sıralaması, "min" yöntemi).
    Birim: sıra (tam sayı). Eksik değerler sıralanmaz (NA). Kaynak: SPEC §6.4, CLAUDE.md sözlüğü.
    """
    return values.rank(method="min", ascending=False).astype("Int64")


def league_percentile(values: pd.Series) -> pd.Series:
    """Sıradan türetilen yüzdelik: en yüksek 100, en düşük 0.

    Formül: yüzdelik_i = (n − sıra_i) / (n − 1) × 100; n geçerli değer sayısıdır, n = 1 ise 100.
    Eşit değerler aynı yüzdeliği alır. Birim: yüzde (0-100). Kaynak: SPEC §6.4.
    """
    ranks = league_rank(values).astype("Float64")
    n = int(values.notna().sum())
    if n <= 1:
        return ranks.where(ranks.isna(), 100.0)
    return (n - ranks) / (n - 1) * 100


def low_sample(trials: pd.Series | None, matches: pd.Series) -> pd.Series:
    """ "Az veri" bayrağı.

    Kural: deneme < 8 ya da maç < 5. Deneme sayısı olmayan metriklerde yalnızca maç sayısına
    bakılır. Maç sayısı bilinmiyorsa bayrak kalkar (veri yetersiz sayılır).
    Kaynak: SPEC §6.4, CLAUDE.md.
    """
    flag = matches.isna() | (matches < MIN_MATCHES)
    if trials is not None:
        flag = flag | (trials < MIN_TRIALS).fillna(False)
    return flag.astype(bool)
