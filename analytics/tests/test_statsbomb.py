"""StatsBomb → SPADL eşleyicisi (Faz 1.6). Sentetik olaylar + (varsa) gerçek bir maç."""

import json
from pathlib import Path

import pytest
from kurgu_analytics.canonical.quality import check_match
from kurgu_analytics.ingestion.statsbomb import (
    StatsBombOpenData,
    events_to_actions,
    match_from_json,
    spadl_type,
)
from kurgu_analytics.testing.statsbomb import SBEvents, match_json


def _types(events: SBEvents) -> list[str]:
    return [a.type for a in events_to_actions(events.events)]


@pytest.mark.parametrize(
    ("pass_type", "height", "cross", "expected"),
    [
        ("Corner", "High Pass", False, "corner_crossed"),
        ("Corner", "Ground Pass", False, "corner_short"),
        ("Free Kick", "High Pass", False, "freekick_crossed"),
        ("Free Kick", "Ground Pass", True, "freekick_crossed"),
        ("Free Kick", "Low Pass", False, "freekick_short"),
        ("Throw-in", "Ground Pass", False, "throw_in"),
        ("Goal Kick", "High Pass", False, "goalkick"),
        (None, "High Pass", True, "cross"),
        (None, "Ground Pass", False, "pass"),
    ],
)
def test_pass_types(pass_type: str | None, height: str, cross: bool, expected: str) -> None:
    ev = SBEvents()
    ev.pass_(10, (100, 70), (110, 40), pass_type=pass_type, height=height, cross=cross)
    assert _types(ev) == [expected]


def test_other_types_and_non_actions_dropped() -> None:
    ev = SBEvents()
    ev.add("Starting XI", 0, location=None, player=None)
    ev.add("Carry", 1, carry={"end_location": [70, 40]})
    ev.add("Dribble", 2, dribble={"outcome": {"name": "Complete"}})
    ev.add("Ball Receipt*", 3)
    ev.add("Pressure", 4)
    ev.add("Duel", 5, duel={"type": {"name": "Tackle"}, "outcome": {"name": "Lost In Play"}})
    ev.add("Duel", 6, duel={"type": {"name": "Aerial Lost"}})
    ev.add("Foul Committed", 7, foul_committed={"card": {"name": "Yellow Card"}})
    ev.add("Clearance", 8, clearance={"body_part": {"name": "Head"}})
    ev.add("Goal Keeper", 9, goalkeeper={"type": {"name": "Keeper Sweeper"}})
    ev.add("Miscontrol", 10)
    actions = events_to_actions(ev.events)
    assert [(a.type, a.result) for a in actions] == [
        ("dribble", "success"),
        ("take_on", "success"),
        ("tackle", "fail"),
        ("foul", "yellow_card"),
        ("clearance", "success"),
        ("keeper_claim", "success"),
        ("bad_touch", "fail"),
    ]
    assert actions[4].bodypart == "head"
    assert [a.action_index for a in actions] == list(range(7))


def test_shots_results_and_xg() -> None:
    ev = SBEvents()
    ev.shot(10, (108, 40), outcome="Goal", xg=0.76, shot_type="Penalty")
    ev.shot(20, (95, 45), outcome="Saved", xg=0.05, shot_type="Free Kick", body_part="Left Foot")
    ev.shot(30, (110, 38), outcome="Goal", xg=0.4, body_part="Head")
    ev.add("Own Goal Against", 40, location=(5, 40))
    actions = events_to_actions(ev.events)
    assert [(a.type, a.result, a.bodypart) for a in actions] == [
        ("shot_penalty", "success", "foot_right"),
        ("shot_freekick", "fail", "foot_left"),
        ("shot", "success", "head"),
        ("bad_touch", "owngoal", "foot"),
    ]
    assert actions[0].xg == pytest.approx(0.76)
    assert actions[0].xg_source == "statsbomb"
    assert actions[3].xg is None


def test_pass_outcomes() -> None:
    ev = SBEvents()
    ev.pass_(1, (60, 40), (70, 40))
    ev.pass_(2, (60, 40), (70, 40), outcome="Incomplete")
    ev.pass_(3, (60, 40), (70, 40), outcome="Pass Offside")
    ev.pass_(4, (60, 40), (70, 40), outcome="Unknown")
    ev.pass_(5, (60, 40), (70, 40), outcome="Injury Clearance")
    assert [a.result for a in events_to_actions(ev.events)] == ["success", "fail", "offside"]


def test_coordinates_and_time() -> None:
    ev = SBEvents()
    ev.pass_(545.417, (120, 80), (114, 30), pass_type="Corner", height="High Pass")
    (corner,) = events_to_actions(ev.events)
    assert corner.time_s == pytest.approx(545.417)
    assert (corner.start_x, corner.start_y) == pytest.approx((105, 0))
    assert (corner.end_x, corner.end_y) == pytest.approx((99.5, 43.16))
    assert corner.extra["pass_type"] == "Corner"
    assert corner.extra["play_pattern"] == "Regular Play"


def test_penalty_shootout_and_throw_in_bodypart() -> None:
    ev = SBEvents()
    ev.pass_(1, (100, 80), (110, 50), pass_type="Throw-in")
    ev.shot(5, (108, 40), shot_type="Penalty", period=5)
    actions = events_to_actions(ev.events)
    assert [a.type for a in actions] == ["throw_in"]
    assert actions[0].bodypart == "other"


def test_unknown_type_is_non_action() -> None:
    assert spadl_type({"type": {"name": "Tactical Shift"}}) == "non_action"


def test_match_metadata() -> None:
    m = match_from_json(match_json())
    assert (m.home.name, m.away.name, m.home_score, m.away_score) == ("Home FC", "Away FC", 1, 0)
    assert m.kickoff_at is not None
    assert m.kickoff_at.isoformat() == "2022-12-01T15:00:00+00:00"


# --- Gerçek maç: Kanada 1-2 Fas, Dünya Kupası 2022 (önbellekte yoksa indirilir) ----------

CACHE = Path(__file__).resolve().parents[2] / "data" / "statsbomb"
CANADA_MOROCCO = "3857276"


@pytest.fixture(scope="module")
def canada_morocco():  # type: ignore[no-untyped-def]
    provider = StatsBombOpenData(CACHE)
    try:
        matches = provider.list_matches({"competition_id": 43, "season_id": 106})
        match = next(m for m in matches if m.provider_id == CANADA_MOROCCO)
        return provider.to_canonical(match, provider.fetch_events(match))
    except OSError as exc:  # ağ yoksa (ör. çevrimdışı geliştirme) atlanır
        pytest.skip(f"StatsBomb Open Data erişilemedi: {exc}")


def test_known_match(canada_morocco) -> None:  # type: ignore[no-untyped-def]
    cm = canada_morocco
    assert (cm.match.home.name, cm.match.away.name) == ("Canada", "Morocco")
    goals = [
        a for a in cm.actions if (a.is_shot and a.result == "success") or a.result == "owngoal"
    ]
    assert len(goals) == cm.match.home_score + cm.match.away_score == 3
    assert 1700 <= len(cm.actions) <= 2300
    assert not [i for i in check_match(cm) if i.severity == "critical"]
    corner = next(
        a for a in cm.actions if a.provider_event_id == "d89366d1-154f-45f6-89c2-6e4bd007fdbb"
    )
    assert corner.type == "corner_crossed"
    assert (corner.start_x, corner.start_y) == pytest.approx((105, 0))
    assert corner.extra["technique"] == "Inswinging"


def test_raw_payload_hash_is_stable() -> None:
    raw = json.dumps(match_json()).encode()
    from kurgu_analytics.ingestion.base import RawPayload

    assert (
        RawPayload("p", "events", "1", raw).source_hash
        == RawPayload("p", "events", "1", raw).source_hash
    )
