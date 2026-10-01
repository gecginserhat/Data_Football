"""Metrik modülü (SPEC §6): formüller, büzülme, sıralama ve tohum altın değerleri."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from kurgu_analytics.metrics import (
    METRICS,
    beta_binomial_shrink,
    beta_prior_mom,
    gamma_poisson_shrink,
    gamma_prior_mom,
    league_benchmarks,
    league_percentile,
    league_rank,
    league_totals,
    low_sample,
    phase_xg_shares,
    team_metrics,
)
from kurgu_analytics.metrics import team as f

SEED = Path(__file__).resolve().parents[2] / "seed" / "super_lig.json"


@pytest.fixture(scope="module")
def seed_2025() -> pd.DataFrame:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    return pd.DataFrame(data["seasons"]["2025_26"]["team_stats"]).set_index("team_id")


def _value(metrics: pd.DataFrame, team: object, metric: str, column: str = "value") -> object:
    row = metrics[(metrics.team == team) & (metrics.metric == metric)]
    assert len(row) == 1
    return row.iloc[0][column]


# --- Formüller ------------------------------------------------------------------------------


def test_formulas_on_hand_values() -> None:
    raw = pd.DataFrame(
        {
            "matches": [10, 0],
            "event_matches": [10, 0],
            "goals": [20, 0],
            "set_piece_goals": [5, 0],
            "set_piece_xg": [4.0, 0.0],
            "sp_xg": [4.0, 0.0],
            "set_pieces": [80, 0],
            "corners": [50, 0],
            "corner_goals": [2, 0],
            "sp_with_contact": [60, 0],
            "sp_first_contact_won": [24, 0],
            "sp_with_shot": [16, 0],
            "sp_xg_phase1": [3.0, 0.0],
            "sp_xg_phase2": [1.0, 0.0],
            "fouls_committed": [120, 0],
            "aerial_win_pct": [55.0, 50.0],
        },
        index=["a", "b"],
    )
    assert f.set_piece_goal_share(raw)["a"] == 0.25
    assert np.isnan(f.set_piece_goal_share(raw)["b"])  # payda 0 → tanımsız
    assert f.set_piece_goals_minus_xg(raw)["a"] == 1.0
    assert f.set_piece_goals_per_match(raw)["a"] == 0.5
    assert f.set_pieces_per_match(raw)["a"] == 8.0
    assert f.corners_per_match(raw)["a"] == 5.0
    assert f.first_contact_win_pct(raw)["a"] == 0.4
    assert f.shots_per_set_piece(raw)["a"] == 0.2
    assert f.xg_per_set_piece(raw)["a"] == 0.05
    assert f.second_phase_xg_share(raw)["a"] == 0.25
    assert f.goals_per_100_corners(raw)["a"] == 4.0
    assert f.fouls_committed_per_match(raw)["a"] == 12.0
    assert f.aerial_win_pct(raw)["a"] == 0.55


def test_event_metrics_use_event_matches() -> None:
    """3 maçlık içe aktarım tohumdaki 34 maçla bölünmez; az veri bayrağı da 3 maça bakar."""
    raw = pd.DataFrame(
        {
            "matches": [34],
            "event_matches": [3],
            "set_pieces": [30],
            "corners": [15],
            "sp_with_contact": [20],
            "sp_first_contact_won": [9],
        }
    )
    out = team_metrics(raw)
    assert _value(out, 0, "set_pieces_per_match") == 10
    assert _value(out, 0, "corners_per_match") == 5
    assert bool(_value(out, 0, "first_contact_win_pct", "low_sample")) is True
    assert _value(out, 0, "first_contact_win_pct", "matches") == 3


def test_missing_inputs_skip_metric() -> None:
    raw = pd.DataFrame({"matches": [34], "set_piece_goals": [10]}, index=["a"])
    out = team_metrics(raw)
    assert "first_contact_win_pct" not in set(out.metric)
    assert "set_piece_goal_share" not in set(out.metric)  # goals yok
    assert {"set_piece_goals", "set_piece_goals_per_match"} <= set(out.metric)


def test_goals_per_100_corners_approximates_from_seed() -> None:
    raw = pd.DataFrame({"matches": [34], "corners_per_match": [5.0], "set_piece_goals": [17]})
    out = team_metrics(raw)
    assert _value(out, 0, "goals_per_100_corners") == pytest.approx(10.0)
    assert bool(_value(out, 0, "goals_per_100_corners", "approx")) is True
    exact = raw.assign(corners=[170], corner_goals=[8], event_matches=[34])
    assert bool(_value(team_metrics(exact), 0, "goals_per_100_corners", "approx")) is False


def test_indirect_flags_match_claude_md() -> None:
    indirect = {m.id for m in METRICS.values() if m.indirect}
    assert indirect == {
        "aerial_win_pct",
        "aerials_won_per_match",
        "fouls_committed_per_match",
        "clearances_per_match",
    }


def test_league_totals_fall_back_to_standings_and_events() -> None:
    totals = league_totals({"standings.goals": 40, "standings.matches": 20, "set_piece_goals": 8})
    assert totals["set_piece_goal_share"] == 0.2
    assert totals["matches"] == 10
    events = league_totals({"events.set_piece_goals": 3, "events.matches": 4})
    assert events["set_piece_goals_per_match"] == 1.5
    assert "set_piece_goal_share" not in events


def test_no_penalty_metric_in_catalog() -> None:
    assert not any("penalty" in m for m in METRICS)


# --- Büzülme --------------------------------------------------------------------------------


def test_beta_prior_matches_spec_formula() -> None:
    successes = pd.Series([2, 4, 6])
    trials = pd.Series([10, 10, 10])
    prior = beta_prior_mom(successes, trials)
    mu, var = 0.4, np.var([0.2, 0.4, 0.6])
    kappa = mu * (1 - mu) / var - 1
    assert prior.alpha == pytest.approx(mu * kappa)
    assert prior.beta == pytest.approx((1 - mu) * kappa)


def test_beta_shrink_pulls_small_samples_harder() -> None:
    successes = pd.Series([1, 30, 10, 12])
    trials = pd.Series([2, 60, 40, 40])
    out = beta_binomial_shrink(successes, trials)
    raw = successes / trials
    prior = beta_prior_mom(successes, trials)
    mu = prior.alpha / (prior.alpha + prior.beta)
    # İki takımın ham oranı aynı (0,5); az denemeli olan ortalamaya daha çok yaklaşır.
    assert abs(out["mean"][0] - mu) < abs(out["mean"][1] - mu)
    assert raw[0] == raw[1]
    assert (out["low"] <= out["mean"]).all()
    assert (out["mean"] <= out["high"]).all()


def test_beta_prior_edge_cases() -> None:
    one = beta_prior_mom(pd.Series([3]), pd.Series([10]))
    assert (one.alpha, one.beta) == (1.0, 1.0)
    zero = beta_prior_mom(pd.Series([0, 0]), pd.Series([5, 9]))
    assert (zero.alpha, zero.beta) == (1.0, 1.0)
    same = beta_prior_mom(pd.Series([5, 5]), pd.Series([10, 10]))
    assert same.alpha + same.beta == pytest.approx(1000.0)


def test_gamma_prior_and_posterior() -> None:
    counts = pd.Series([10.0, 20.0, 30.0])
    matches = pd.Series([10.0, 10.0, 10.0])
    prior = gamma_prior_mom(counts, matches)
    mu, var = 2.0, np.var([1.0, 2.0, 3.0])
    assert prior.rate == pytest.approx(mu / var)
    assert prior.shape == pytest.approx(mu * mu / var)
    out = gamma_poisson_shrink(counts, matches, prior)
    expected = (prior.shape + counts) / (prior.rate + matches)
    assert out["mean"].to_numpy() == pytest.approx(expected.to_numpy())
    assert (out["low"] < out["mean"]).all()
    assert (out["mean"] < out["high"]).all()


# --- Sıralama ve az veri ------------------------------------------------------------------


def test_rank_ties_share_rank_and_skip() -> None:
    values = pd.Series([15, 14, 15, 9, np.nan])
    assert league_rank(values).tolist() == [1, 3, 1, 4, pd.NA]
    pct = league_percentile(values)
    assert pct[0] == 100
    assert pct[3] == 0
    assert pd.isna(pct[4])


def test_low_sample_rule() -> None:
    trials = pd.Series([7, 8, 20, 20])
    matches = pd.Series([10, 10, 4, 5])
    assert low_sample(trials, matches).tolist() == [True, False, True, False]
    assert low_sample(None, matches).tolist() == [False, False, True, False]


# --- Değişmezler (hypothesis) ---------------------------------------------------------------

_counts = st.lists(
    st.tuples(st.integers(0, 60), st.integers(1, 120)).map(lambda t: (min(t), max(t))),
    min_size=2,
    max_size=20,
)


@given(_counts)
@settings(max_examples=150, deadline=None)
def test_shrunk_rates_stay_in_unit_interval(pairs: list[tuple[int, int]]) -> None:
    successes = pd.Series([s for s, _ in pairs])
    trials = pd.Series([n for _, n in pairs])
    out = beta_binomial_shrink(successes, trials)
    # Çarpık sonsalda ortalama aralığın dışında kalabilir; değişmez olan sınırların sırasıdır.
    assert ((out["low"] >= 0) & (out["high"] <= 1)).all()
    assert (out["low"] <= out["high"]).all()
    assert ((out["mean"] >= 0) & (out["mean"] <= 1)).all()


@given(
    st.lists(
        st.tuples(st.floats(0, 5, allow_nan=False), st.floats(0, 5, allow_nan=False)),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=150, deadline=None)
def test_phase_shares_sum_to_one(phases: list[tuple[float, float]]) -> None:
    raw = pd.DataFrame(phases, columns=["sp_xg_phase1", "sp_xg_phase2"])
    shares = phase_xg_shares(raw)
    total = raw.sum(axis=1)
    defined = total > 0
    assert (shares[defined].sum(axis=1) - 1).abs().max() < 1e-9 if defined.any() else True
    assert shares[~defined].isna().all().all()
    assert ((shares[defined] >= 0) & (shares[defined] <= 1)).all().all()


@given(st.lists(st.integers(0, 40), min_size=1, max_size=25))
@settings(max_examples=150, deadline=None)
def test_rank_is_consistent_with_values(values: list[int]) -> None:
    series = pd.Series(values, dtype=float)
    ranks = league_rank(series)
    pct = league_percentile(series)
    for i in range(len(values)):
        assert ranks[i] == 1 + sum(v > values[i] for v in values)
        for j in range(len(values)):
            if values[i] > values[j]:
                assert ranks[i] < ranks[j]
                assert pct[i] > pct[j]
            if values[i] == values[j]:
                assert ranks[i] == ranks[j]


@given(
    st.lists(
        st.tuples(st.integers(0, 30), st.integers(1, 40), st.integers(0, 15)),
        min_size=2,
        max_size=18,
    )
)
@settings(max_examples=100, deadline=None)
def test_team_metrics_rates_in_range(rows: list[tuple[int, int, int]]) -> None:
    raw = pd.DataFrame(
        {
            "goals": [max(g, s) for g, _, s in rows],
            "matches": [m for _, m, _ in rows],
            "set_piece_goals": [s for _, _, s in rows],
        }
    )
    out = team_metrics(raw)
    share = out[out.metric == "set_piece_goal_share"]
    assert ((share.value >= 0) & (share.value <= 1)).all()
    assert ((share.shrunk_mean >= 0) & (share.shrunk_mean <= 1)).all()


# --- Tohum altın değerleri (SPEC §19 Faz 2) -------------------------------------------------


def test_seed_golden_values(seed_2025: pd.DataFrame) -> None:
    totals = league_totals({c: float(seed_2025[c].sum()) for c in seed_2025.columns})
    assert totals["set_piece_goals"] == 166
    assert totals["goals"] == 812
    assert round(totals["set_piece_goal_share"], 3) == 0.204
    assert round(totals["set_piece_goals_per_match"], 3) == 0.542

    out = team_metrics(seed_2025)
    assert _value(out, "ts", "set_piece_goals") == 15
    assert _value(out, "ts", "set_piece_goals", "rank") == 1
    assert _value(out, "goz", "set_piece_xg") == pytest.approx(15.4)
    assert _value(out, "goz", "set_piece_xg", "rank") == 1
    assert not out.low_sample.any()  # 34 maç, deneme sayısı yeterli

    bench = league_benchmarks(out).set_index("metric")
    assert bench.loc["set_piece_goals", "max"] == 15
    assert bench.loc["set_piece_goals", "teams"] == 18
    assert bench.loc["aerial_win_pct", "max"] <= 1


def test_catalog_inputs_cover_formulas() -> None:
    """Her metriğin girdileri verildiğinde değer hesaplanır; girdiler kaynak takibi için tamdır."""
    for metric in METRICS.values():
        assert metric.inputs, metric.id
        raw = pd.DataFrame({c: [10.0, 6.0] for c in metric.inputs})
        assert metric.formula(raw).notna().all(), metric.id
