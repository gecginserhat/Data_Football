"""Yük ve iyi oluş metrikleri (SPEC §8.2, A-83 … A-85)."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from kurgu_analytics.metrics.load import (
    ACUTE_LAMBDA,
    CHRONIC_LAMBDA,
    daily_loads,
    ewma,
    hooper_index,
    hooper_trend,
    load_trend,
    srpe,
    week_start,
    weekly_alerts,
)

D0 = dt.date(2026, 9, 7)  # pazartesi


def day(i: int) -> dt.date:
    return D0 + dt.timedelta(days=i)


def test_srpe_is_rpe_times_minutes() -> None:
    assert srpe(7, 90) == 630
    assert srpe(0, 60) == 0
    with pytest.raises(ValueError, match="RPE"):
        srpe(11, 60)
    with pytest.raises(ValueError, match="duration"):
        srpe(5, -1)


def test_hooper_index_sums_four_items() -> None:
    assert hooper_index(3, 2, 4, 5) == 14
    assert hooper_index(1, 1, 1, 1) == 4
    assert hooper_index(7, 7, 7, 7) == 28
    with pytest.raises(ValueError, match="Hooper"):
        hooper_index(0, 2, 3, 4)


def test_lambdas_follow_spec() -> None:
    assert abs(ACUTE_LAMBDA - 0.25) < 1e-12
    assert abs(CHRONIC_LAMBDA - 2 / 29) < 1e-12


def test_ewma_recursion_by_hand() -> None:
    out = ewma(pd.Series([100.0, 0.0, 200.0]), 0.25)
    assert out.tolist() == pytest.approx([100.0, 75.0, 106.25])


@given(st.lists(st.floats(min_value=0, max_value=2000, allow_nan=False), min_size=1, max_size=60))
def test_ewma_stays_within_the_range_of_its_input(values: list[float]) -> None:
    out = ewma(pd.Series(values), ACUTE_LAMBDA)
    assert out.min() >= min(values) - 1e-6
    assert out.max() <= max(values) + 1e-6


def test_daily_loads_fill_missing_days_with_zero() -> None:
    sessions = pd.DataFrame(
        {
            "player_id": ["a", "a", "a", "b"],
            "date": [day(0), day(0), day(2), day(3)],
            "srpe": [300.0, 200.0, 400.0, 100.0],
        }
    )
    out = daily_loads(sessions, day(3))
    a = out[out.player_id == "a"]
    assert a["load"].tolist() == [500.0, 0.0, 400.0, 0.0]
    assert out[out.player_id == "b"]["load"].tolist() == [100.0]


def test_acwr_is_hidden_until_28_days() -> None:
    sessions = pd.DataFrame(
        {"player_id": "a", "date": [day(i) for i in range(30)], "srpe": [400.0] * 30}
    )
    trend = load_trend(daily_loads(sessions, day(29)))
    assert trend["acwr"].iloc[:27].isna().all()
    assert trend["acwr"].iloc[27] == pytest.approx(1.0)
    # Sabit yükte SD 0; z tanımsız kalır.
    assert trend["z"].isna().all()


def test_z_score_flags_a_spike() -> None:
    loads = [300.0] * 6 + [350.0] * 6 + [900.0]
    sessions = pd.DataFrame({"player_id": "a", "date": [day(i) for i in range(13)], "srpe": loads})
    trend = load_trend(daily_loads(sessions, day(12)))
    assert trend["z"].iloc[-1] > 2
    assert trend["z"].iloc[:6].isna().all()


@given(st.lists(st.integers(min_value=1, max_value=7), min_size=4, max_size=4))
def test_hooper_trend_matches_the_index(items: list[int]) -> None:
    entries = pd.DataFrame(
        [
            {
                "player_id": "a",
                "date": day(0),
                "sleep": items[0],
                "stress": items[1],
                "fatigue": items[2],
                "soreness": items[3],
            }
        ]
    )
    out = hooper_trend(entries)
    assert out["hooper"].tolist() == [hooper_index(*items)]
    assert np.isnan(out["z"].iloc[0])


def test_week_start_is_monday() -> None:
    assert week_start(dt.date(2026, 10, 1)) == dt.date(2026, 9, 28)
    assert week_start(dt.date(2026, 9, 28)) == dt.date(2026, 9, 28)


def _jumps(per_week: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": "a",
            "date": [day(7 * i + 1) for i in range(len(per_week))],
            "jumps": per_week,
            "headers": [0] * len(per_week),
        }
    )


def test_weekly_jump_alert_above_two_sd() -> None:
    logs = _jumps([40, 50, 45, 55, 120])
    alerts = weekly_alerts(logs, "jumps", day(29))
    assert len(alerts) == 1
    row = alerts.iloc[0]
    assert row["week"] == day(28)
    assert row["total"] == 120
    assert row["mean"] == pytest.approx(47.5)
    assert row["sd"] == pytest.approx(np.std([40, 50, 45, 55], ddof=1))
    assert row["threshold"] == pytest.approx(47.5 + 2 * np.std([40, 50, 45, 55], ddof=1))


def test_no_alert_without_four_weeks_or_within_range() -> None:
    assert weekly_alerts(_jumps([10, 10, 300]), "jumps", day(15)).empty
    assert weekly_alerts(_jumps([40, 50, 45, 55, 60]), "jumps", day(29)).empty
    assert weekly_alerts(_jumps([40, 50, 45, 55, 60]), "headers", day(29)).empty


def test_empty_weeks_count_as_zero() -> None:
    logs = pd.DataFrame(
        {"player_id": "a", "date": [day(1), day(29)], "jumps": [5, 50], "headers": [0, 0]}
    )
    alerts = weekly_alerts(logs, "jumps", day(29))
    assert alerts["weeks"].tolist() == [4]
    assert alerts["mean"].tolist() == [pytest.approx(1.25)]
