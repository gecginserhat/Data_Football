"""Antrenman yükü ve iyi oluş (SPEC §8.2, A-83 … A-85).

Fonksiyonlar saftır; girdi DataFrame'ini değiştirmez. Tarihler yerel takvim günüdür
(Europe/Istanbul, `datetime.date`); saat dilimi dönüşümü çağıranın işidir.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

ACUTE_DAYS = 7
CHRONIC_DAYS = 28
ACUTE_LAMBDA = 2 / (ACUTE_DAYS + 1)
CHRONIC_LAMBDA = 2 / (CHRONIC_DAYS + 1)
Z_WINDOW_DAYS = 28
HOOPER_MIN_ENTRIES = 7
ALERT_SD = 2.0
ALERT_MIN_WEEKS = 4
HOOPER_ITEMS = ("sleep", "stress", "fatigue", "soreness")

TREND_COLUMNS = ("player_id", "date", "load", "acute", "chronic", "acwr", "z")


def srpe(rpe: float, minutes: float) -> float:
    """Seans yükü (sRPE) = RPE (CR-10, 0-10) × süre (dakika). Birim: keyfi birim (AU).

    Kaynak: Foster ve ark. (2001); SPEC §8.2.
    """
    if not 0 <= rpe <= 10:
        raise ValueError("RPE must be between 0 and 10")
    if minutes < 0:
        raise ValueError("duration must not be negative")
    return float(rpe) * float(minutes)


def hooper_index(sleep: int, stress: int, fatigue: int, soreness: int) -> int:
    """Hooper indeksi = uyku + stres + yorgunluk + kas ağrısı (her biri 1-7). Aralık 4-28;
    yüksek değer kötü iyi oluş demektir. Birim: puan. Kaynak: Hooper ve Mackinnon (1995); §8.2.
    """
    items = (sleep, stress, fatigue, soreness)
    if any(not 1 <= v <= 7 for v in items):
        raise ValueError("Hooper items must be between 1 and 7")
    return int(sum(items))


def ewma(values: pd.Series, lam: float) -> pd.Series:
    """Üstel ağırlıklı hareketli ortalama: E_t = λ·x_t + (1−λ)·E_{t−1}, E_0 = x_0.

    Birim: girdinin birimi. Kaynak: Williams ve ark. (2017); SPEC §8.2.
    """
    if not 0 < lam <= 1:
        raise ValueError("lambda must be in (0, 1]")
    return values.astype(float).ewm(alpha=lam, adjust=False).mean()


def daily_loads(sessions: pd.DataFrame, until: dt.date) -> pd.DataFrame:
    """Oyuncu başına günlük toplam sRPE; ilk kayıttan `until` gününe kadar seans olmayan
    günler 0'dır (A-84). Girdi: `player_id`, `date`, `srpe`. Çıktı: `player_id`, `date`, `load`.
    """
    if sessions.empty:
        return pd.DataFrame(columns=["player_id", "date", "load"])
    frames = []
    totals = sessions.groupby(["player_id", "date"], sort=True)["srpe"].sum()
    for player, series in totals.groupby(level=0):
        by_day = series.droplevel(0)
        start = min(by_day.index)
        if start > until:
            continue
        days = pd.date_range(start, until, freq="D").date
        filled = by_day.reindex(days, fill_value=0.0).astype(float)
        frames.append(pd.DataFrame({"player_id": player, "date": days, "load": filled.values}))
    if not frames:
        return pd.DataFrame(columns=["player_id", "date", "load"])
    return pd.concat(frames, ignore_index=True)


def load_trend(daily: pd.DataFrame) -> pd.DataFrame:
    """Günlük yükten akut ve kronik EWMA, ACWR ve oyuncu içi z-skoru.

    - Akut EWMA λ = 2/(7+1), kronik EWMA λ = 2/(28+1) (SPEC §8.2).
    - ACWR = akut / kronik; seri 28 günden kısaysa ya da kronik 0 ise boş (A-84). Yalnız bağlam
      bilgisidir, karar aracı değildir.
    - z = (yük − son 28 günün ortalaması) / standart sapması (o gün dahil, en az 7 gün; SD 0 ise
      boş).
    Birim: AU (oran ve z birimsiz).
    """
    if daily.empty:
        return pd.DataFrame(columns=list(TREND_COLUMNS))
    frames = []
    for player, group in daily.sort_values(["player_id", "date"]).groupby("player_id", sort=True):
        load = group["load"].astype(float).reset_index(drop=True)
        acute = ewma(load, ACUTE_LAMBDA)
        chronic = ewma(load, CHRONIC_LAMBDA)
        enough = pd.Series(np.arange(1, len(load) + 1) >= CHRONIC_DAYS)
        acwr = (acute / chronic.where(chronic > 0)).where(enough)
        window = load.rolling(Z_WINDOW_DAYS, min_periods=ACUTE_DAYS)
        sd = window.std(ddof=0)
        z = (load - window.mean()) / sd.where(sd > 0)
        frames.append(
            pd.DataFrame(
                {
                    "player_id": player,
                    "date": group["date"].to_numpy(),
                    "load": load,
                    "acute": acute,
                    "chronic": chronic,
                    "acwr": acwr,
                    "z": z,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def hooper_trend(entries: pd.DataFrame) -> pd.DataFrame:
    """Hooper indeksi ve oyuncu içi z-skoru. Girdi: `player_id`, `date`, sleep, stress, fatigue,
    soreness. z, oyuncunun o güne kadarki kayıtlarına göredir (en az 7 kayıt, A-84).
    Çıktı: `player_id`, `date`, `hooper`, `z`. Birim: puan (4-28), z birimsiz.
    """
    columns = ["player_id", "date", "hooper", "z"]
    if entries.empty:
        return pd.DataFrame(columns=columns)
    data = entries.sort_values(["player_id", "date"]).copy()
    data["hooper"] = data[list(HOOPER_ITEMS)].sum(axis=1).astype(int)
    frames = []
    for _, group in data.groupby("player_id", sort=True):
        h = group["hooper"].astype(float).reset_index(drop=True)
        expanding = h.expanding(min_periods=HOOPER_MIN_ENTRIES)
        sd = expanding.std(ddof=0)
        z = (h - expanding.mean()) / sd.where(sd > 0)
        out = group[["player_id", "date", "hooper"]].reset_index(drop=True)
        out["z"] = z
        frames.append(out)
    return pd.concat(frames, ignore_index=True)[columns]


def week_start(day: dt.date) -> dt.date:
    """Takvim haftasının pazartesisi."""
    return day - dt.timedelta(days=day.weekday())


def weekly_alerts(logs: pd.DataFrame, metric: str, until: dt.date) -> pd.DataFrame:
    """Haftalık sıçrama ya da kafa vuruşu uyarıları (SPEC §8.2, A-85).

    Girdi: `player_id`, `date` ve `metric` sütunu (sayım). Hafta pazartesi başlar; oyuncunun ilk
    kaydının haftasından `until` gününün haftasına kadar boş haftalar 0'dır. Bir hafta için önceki
    en az 4 haftanın ortalaması μ ve standart sapması σ (ddof=1) hesaplanır; toplam > μ + 2σ ise
    uyarı satırı döner. Çıktı: `player_id`, `week`, `total`, `mean`, `sd`, `threshold`, `weeks`.
    Birim: sayım/hafta.
    """
    columns = ["player_id", "week", "total", "mean", "sd", "threshold", "weeks"]
    if logs.empty:
        return pd.DataFrame(columns=columns)
    data = logs[["player_id", "date", metric]].copy()
    data["week"] = data["date"].map(week_start)
    last_week = week_start(until)
    rows = []
    for player, group in data.groupby("player_id", sort=True):
        totals = group.groupby("week")[metric].sum()
        first = min(totals.index)
        if first > last_week:
            continue
        weeks = pd.date_range(first, last_week, freq="7D").date
        series = totals.reindex(weeks, fill_value=0).astype(float).to_numpy()
        for i in range(ALERT_MIN_WEEKS, len(series)):
            history = series[:i]
            mean = float(history.mean())
            sd = float(history.std(ddof=1))
            threshold = mean + ALERT_SD * sd
            if series[i] > threshold:
                rows.append(
                    {
                        "player_id": player,
                        "week": weeks[i],
                        "total": float(series[i]),
                        "mean": mean,
                        "sd": sd,
                        "threshold": threshold,
                        "weeks": i,
                    }
                )
    return pd.DataFrame(rows, columns=columns)
