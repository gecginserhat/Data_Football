"""Rutin metrikleri (SPEC §6.3, A-44)."""

import math

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from kurgu_analytics.metrics import routine_metrics


def _raw(rows: list[tuple[str, int, int, int, int, int, float, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "routine_id",
            "uses",
            "matches",
            "with_contact",
            "first_contact_won",
            "with_shot",
            "xg",
            "goals",
        ],
    )


def test_raw_rates_and_per_use() -> None:
    out = routine_metrics(_raw([("a", 10, 6, 8, 6, 4, 1.2, 2), ("b", 20, 9, 20, 5, 2, 0.8, 0)]))
    a = out.set_index("routine_id").loc["a"]
    assert a["first_contact_rate"] == pytest.approx(0.75)
    assert a["shot_rate"] == pytest.approx(0.4)
    assert a["xg_per_use"] == pytest.approx(0.12)
    assert a["goals"] == 2
    assert a["first_contact_trials"] == 8
    assert not a["low_sample"]


def test_shrinkage_pulls_towards_the_club_mean() -> None:
    out = routine_metrics(
        _raw(
            [
                ("a", 10, 6, 10, 9, 5, 1.0, 1),
                ("b", 10, 6, 10, 3, 1, 0.5, 0),
                ("c", 2, 1, 2, 2, 2, 0.4, 1),
            ]
        )
    ).set_index("routine_id")
    c = out.loc["c"]
    # Ham oran 1.0; sonsal ortalama kulüp ortalamasına doğru çekilir ve aralık içindedir.
    assert c["first_contact_rate"] == 1.0
    assert c["first_contact_shrunk"] < 1.0
    assert c["first_contact_low"] <= c["first_contact_shrunk"] <= c["first_contact_high"]
    assert c["low_sample"]


def test_unused_routines_have_no_rates() -> None:
    out = routine_metrics(_raw([("a", 0, 0, 0, 0, 0, 0.0, 0), ("b", 9, 5, 9, 4, 3, 0.9, 1)]))
    a = out.set_index("routine_id").loc["a"]
    assert a["uses"] == 0
    for col in (
        "first_contact_rate",
        "first_contact_shrunk",
        "shot_rate",
        "shot_shrunk",
        "xg_per_use",
    ):
        assert math.isnan(a[col])
    assert a["low_sample"]


def test_rejects_missing_columns_and_keeps_input_unchanged() -> None:
    raw = _raw([("a", 3, 1, 3, 1, 1, 0.3, 0)])
    before = raw.copy()
    routine_metrics(raw)
    pd.testing.assert_frame_equal(raw, before)
    with pytest.raises(ValueError, match="missing columns"):
        routine_metrics(raw.drop(columns=["goals"]))


@given(
    st.lists(
        st.tuples(st.integers(0, 40), st.integers(0, 40), st.integers(0, 40), st.floats(0, 5)),
        min_size=1,
        max_size=12,
    )
)
def test_rates_stay_in_unit_interval(rows: list[tuple[int, int, int, float]]) -> None:
    data = []
    for i, (uses, a, b, xg) in enumerate(rows):
        contact = min(a, uses)
        won = min(b, contact)
        shot = min(b, uses)
        data.append((f"r{i}", uses, min(uses, 10), contact, won, shot, xg, 0))
    out = routine_metrics(_raw(data))
    for col in ("first_contact_rate", "first_contact_shrunk", "shot_rate", "shot_shrunk"):
        values = out[col].dropna()
        assert ((values >= 0) & (values <= 1)).all()
    both = out.dropna(subset=["first_contact_low"])
    assert (both["first_contact_low"] <= both["first_contact_high"]).all()
