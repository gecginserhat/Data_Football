"""Hava skoru ve markaj ataması (SPEC §7.3, ADR-0015, A-81, A-82)."""

import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from kurgu_analytics.metrics.players import aerial_score
from kurgu_analytics.recs.marking import Marker, Target, pair_cost, suggest_marking


def test_aerial_score_components() -> None:
    assert aerial_score(None) is None
    tall = aerial_score(200)
    assert tall is not None
    assert tall.value == 1.0
    assert tall.components == ("height",)
    mixed = aerial_score(185, 0.5, 0.8)
    assert mixed is not None
    assert mixed.value == pytest.approx((0.5 + 0.5 + 0.8) / 3, abs=1e-4)
    assert aerial_score(160).value == 0.0  # type: ignore[union-attr]
    goals = aerial_score(185, sp_goals=5)
    assert goals is not None
    assert goals.value == pytest.approx(0.5 + 0.15)
    assert goals.components == ("height", "goals")
    with pytest.raises(ValueError, match="aerial"):
        aerial_score(185, 1.2)


def test_pair_cost() -> None:
    assert pair_cost(0.8, 0.6, "DEF") == pytest.approx(0.2 + 0.002)
    assert pair_cost(0.4, 0.6, "DEF") == pytest.approx(0.002)
    assert pair_cost(0.4, 0.6, "MID") == pytest.approx(0.152)


def test_strong_targets_get_strong_defenders_and_keepers_are_excluded() -> None:
    targets = [Target("t1", 0.9), Target("t2", 0.5), Target("t3", 0.2)]
    markers = [
        Marker("gk", 1.0, "GK"),
        Marker("d1", 0.4, "DEF"),
        Marker("d2", 0.85, "DEF"),
        Marker("m1", 0.6, "MID"),
    ]
    pairs = suggest_marking(targets, markers)
    assert [(p.target_id, p.marker_id) for p in pairs] == [
        ("t1", "d2"),
        ("t2", "m1"),
        ("t3", "d1"),
    ]
    assert all(p.marker_id != "gk" for p in pairs)


def test_zonal_players_are_fixed_and_extra_targets_stay_unmarked() -> None:
    targets = [Target("t1", 0.9), Target("t2", 0.7), Target("t3", 0.3)]
    markers = [Marker("d1", 0.8, "DEF"), Marker("d2", 0.7, "DEF"), Marker("d3", 0.9, "DEF")]
    pairs = suggest_marking(targets, markers, frozenset({"d3"}))
    assert {p.marker_id for p in pairs} == {"d1", "d2"}
    assert {p.target_id for p in pairs} == {"t1", "t2"}


def test_empty_inputs() -> None:
    assert suggest_marking([], [Marker("d1", 0.5, "DEF")]) == []
    assert suggest_marking([Target("t1", 0.5)], [Marker("g", 0.5, "GK")]) == []


scores = st.floats(min_value=0, max_value=1, allow_nan=False)


@settings(max_examples=60)
@given(
    st.lists(scores, min_size=1, max_size=4),
    st.lists(st.tuples(scores, st.sampled_from(["DEF", "MID", "FWD"])), min_size=1, max_size=4),
)
def test_assignment_is_optimal_against_brute_force(
    threats: list[float], markers_in: list[tuple[float, str]]
) -> None:
    targets = [Target(f"t{i}", t) for i, t in enumerate(threats)]
    markers = [Marker(f"m{i}", c, p) for i, (c, p) in enumerate(markers_in)]
    pairs = suggest_marking(targets, markers)
    n = min(len(targets), len(markers))
    assert len(pairs) == n
    assert len({p.marker_id for p in pairs}) == n
    chosen = sorted(targets, key=lambda t: (-t.threat, t.id))[:n]
    best = min(
        sum(pair_cost(t.threat, m.capacity, m.position) for t, m in zip(chosen, perm, strict=False))
        for perm in itertools.permutations(markers, n)
    )
    assert sum(p.cost for p in pairs) == pytest.approx(best, abs=1e-3)
