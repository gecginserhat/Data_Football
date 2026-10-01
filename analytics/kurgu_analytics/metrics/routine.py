"""Rutin metrikleri (SPEC §6.3).

Girdi, `v_routine_stats` görünümünün rutin başına ham sayımlarıdır (A-44). Oranlar kulübün
tüm rutinlerinden kestirilen beta önseliyle büzülür (SPEC §6.4); hiç kullanılmamış rutinler
önseli etkilemez ve oranları boş kalır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from kurgu_analytics.metrics.ranking import low_sample
from kurgu_analytics.metrics.shrinkage import beta_binomial_shrink, beta_prior_mom

ROUTINE_INPUT_COLUMNS = (
    "routine_id",
    "uses",
    "matches",
    "with_contact",
    "first_contact_won",
    "with_shot",
    "xg",
    "goals",
)
ROUTINE_OUTPUT_COLUMNS = (
    "routine_id",
    "uses",
    "matches",
    "goals",
    "xg",
    "xg_per_use",
    "first_contact_rate",
    "first_contact_shrunk",
    "first_contact_low",
    "first_contact_high",
    "first_contact_trials",
    "shot_rate",
    "shot_shrunk",
    "shot_low",
    "shot_high",
    "low_sample",
)


def _rate(successes: pd.Series, trials: pd.Series) -> pd.Series:
    return (successes / trials.where(trials > 0)).astype(float)


def routine_metrics(raw: pd.DataFrame) -> pd.DataFrame:
    """Rutin başına kullanım, ilk temas oranı, şut oranı, kullanım başına xG ve gol.

    Formüller (SPEC §6.3):
    - İlk temas oranı = ilk teması kazanılan / ilk teması belli olan kullanım. Birim: oran (0-1).
    - Şut oranı = şutla biten kullanım / kullanım. Birim: oran (0-1).
    - Kullanım başına xG = toplam xG / kullanım. Birim: xG.
    - Gol: sayım.
    Oranların yanında beta-binom sonsal ortalaması ve %80 aralığı verilir; önsel, kulübün
    kullanılmış rutinlerinden momentler yöntemiyle (`beta_prior_mom`). "Az veri": kullanım < 8
    ya da maç < 5. Kaynak: SPEC §6.3-6.4, A-44.
    Saf fonksiyon: girdi değişmez; çıktı satır sırası girdiyle aynıdır.
    """
    missing = set(ROUTINE_INPUT_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    df = raw.loc[:, list(ROUTINE_INPUT_COLUMNS)].copy()
    for col in ROUTINE_INPUT_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col]).astype(float)
    used = df["uses"] > 0

    out = pd.DataFrame(index=df.index)
    out["routine_id"] = df["routine_id"]
    out["uses"] = df["uses"].astype(int)
    out["matches"] = df["matches"].astype(int)
    out["goals"] = df["goals"].astype(int)
    out["xg"] = df["xg"]
    out["xg_per_use"] = _rate(df["xg"], df["uses"])

    contact = df["with_contact"]
    out["first_contact_rate"] = _rate(df["first_contact_won"], contact)
    out["first_contact_trials"] = contact.astype(int)
    shrunk = beta_binomial_shrink(
        df["first_contact_won"], contact, beta_prior_mom(df["first_contact_won"], contact)
    )
    has_contact = contact > 0
    for src, dst in (("mean", "shrunk"), ("low", "low"), ("high", "high")):
        out[f"first_contact_{dst}"] = shrunk[src].where(has_contact, np.nan)

    shots = beta_binomial_shrink(
        df["with_shot"], df["uses"], beta_prior_mom(df["with_shot"], df["uses"])
    )
    out["shot_rate"] = _rate(df["with_shot"], df["uses"])
    for src, dst in (("mean", "shrunk"), ("low", "low"), ("high", "high")):
        out[f"shot_{dst}"] = shots[src].where(used, np.nan)

    out["low_sample"] = low_sample(df["uses"], df["matches"])
    return out.loc[:, list(ROUTINE_OUTPUT_COLUMNS)]
