"""Duran top çıkarımı: her dal için el yapımı diziler ve hypothesis değişmezleri (Faz 1.7)."""

from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from kurgu_analytics.canonical.model import Action
from kurgu_analytics.setpieces.extract import Config, extract

ATT, DEF = "A", "D"


class Seq:
    def __init__(self) -> None:
        self.actions: list[Action] = []

    def add(
        self,
        t: float,
        type_: str,
        team: str = ATT,
        start: tuple[float, float] = (60, 34),
        end: tuple[float, float] | None = None,
        *,
        result: str = "success",
        xg: float | None = None,
        bodypart: str = "foot",
        period: int = 1,
        player: str = "p",
        **extra: str,
    ) -> "Seq":
        self.actions.append(
            Action(
                action_index=len(self.actions),
                period=period,
                time_s=t,
                team_provider_id=team,
                player_provider_id=player,
                type=type_,
                result=result,
                bodypart=bodypart,
                start_x=start[0],
                start_y=start[1],
                end_x=(end or start)[0],
                end_y=(end or start)[1],
                xg=xg,
                extra=dict(extra),
            )
        )
        return self


def corner(seq: Seq, t: float = 100.0) -> Seq:
    return seq.add(t, "corner_crossed", start=(105, 0.5), end=(100, 25), bodypart="foot_right")


def test_corner_header_goal_in_first_phase() -> None:
    s = corner(Seq())
    s.add(
        101.5,
        "shot",
        start=(100, 25),
        end=(105, 33),
        result="success",
        xg=0.3,
        bodypart="head",
        player="h",
    )
    (sp,) = extract(s.actions)
    assert (sp.sp_type, sp.sp_subtype, sp.side, sp.target_zone) == (
        "corner",
        "outswing",
        "right",
        "NP",
    )
    assert (sp.first_contact_team, sp.first_contact_player) == (ATT, "h")
    assert sp.goal
    assert sp.phase_of_goal == 1
    assert sp.outcome == "goal"
    assert sp.xg_phase1 == pytest.approx(0.3)


def test_inswing_from_left_side_and_provider_technique() -> None:
    s = Seq().add(10, "corner_crossed", start=(105, 67.5), end=(101, 40), bodypart="foot_right")
    s.add(40, "corner_crossed", start=(105, 0.5), end=(101, 30), technique="Inswinging")
    first, second = extract(s.actions)
    assert (first.side, first.sp_subtype, first.target_zone) == ("left", "inswing", "NP")
    assert second.sp_subtype == "inswing"


def test_long_throw_filter() -> None:
    s = Seq().add(10, "throw_in", start=(60, 0), end=(75, 10))
    s.add(40, "throw_in", start=(85, 0), end=(96, 30))
    s.add(80, "throw_in", start=(75, 68), end=(78, 64))
    sps = extract(s.actions)
    assert [sp.start_time_s for sp in sps] == [40]
    assert sps[0].sp_type == "throw_in"
    assert len(extract(s.actions, Config(all_throw_ins=True))) == 3


def test_phase_two_by_time_and_by_passes() -> None:
    s = corner(Seq())
    s.add(101, "clearance", DEF, start=(5, 35), end=(20, 30))
    s.add(107, "shot", start=(85, 30), end=(105, 34), xg=0.05)  # 7 sn: ikinci faz
    s.add(130, "corner_crossed", start=(105, 0.5), end=(100, 30))
    s.add(131, "pass", start=(100, 30), end=(95, 35))
    s.add(132, "pass", start=(95, 35), end=(99, 33))  # ikinci pas: ikinci faz
    s.add(132.5, "shot", start=(99, 33), end=(105, 34), xg=0.2)
    first, second = extract(s.actions)
    assert [x.phase for x in first.shots] == [2]
    assert first.first_contact_team == DEF
    assert [x.phase for x in second.shots] == [2]
    assert second.xg_phase2 == pytest.approx(0.2)


def test_window_ends_after_twenty_seconds() -> None:
    s = corner(Seq())
    s.add(110, "pass", start=(80, 30), end=(85, 40))
    s.add(121, "shot", start=(90, 34), end=(105, 34), xg=0.1)
    (sp,) = extract(s.actions)
    assert sp.shots == []
    assert extract(s.actions, Config(window_s=25))[0].shots != []


def test_new_restart_cuts_the_sequence() -> None:
    s = corner(Seq())
    s.add(103, "clearance", DEF, start=(3, 30), end=(1, 40))
    corner(s, t=110)
    s.add(111, "shot", start=(100, 30), end=(105, 34), xg=0.4)
    first, second = extract(s.actions)
    assert first.shots == []
    assert first.outcome == "cleared"
    assert len(second.shots) == 1


def test_direct_free_kick_shot() -> None:
    s = Seq().add(50, "shot_freekick", start=(82, 30), end=(105, 33), result="success", xg=0.07)
    (sp,) = extract(s.actions)
    assert (sp.sp_type, sp.sp_subtype) == ("free_kick", "direct_shot")
    assert [(x.phase, x.goal) for x in sp.shots] == [(1, True)]
    assert sp.outcome == "goal"


def test_turnover_out_of_final_third_and_counter() -> None:
    s = corner(Seq())
    s.add(101, "keeper_claim", DEF, start=(2, 30))
    s.add(103, "pass", DEF, start=(5, 30), end=(50, 40))  # rakip topu üçte birden çıkarıyor
    s.add(104, "shot", ATT, start=(100, 30), end=(105, 34), xg=0.3)  # dizi bitti; sayılmaz
    s.add(110, "shot", DEF, start=(95, 30), end=(105, 34), xg=0.1)
    (sp,) = extract(s.actions)
    assert sp.ended_by_turnover
    assert sp.shots == []
    assert sp.outcome == "counter_conceded"


def test_penalty_and_kickoff_break_sequences() -> None:
    s = corner(Seq())
    s.add(102, "foul", DEF, start=(10, 34))
    s.add(150 - 45, "shot_penalty", start=(94, 34), end=(105, 34), result="success", xg=0.78)
    (sp,) = extract(s.actions)
    assert sp.shots == []
    assert not sp.goal

    s = corner(Seq())
    s.add(101, "shot", start=(100, 30), end=(105, 34), result="success", xg=0.3)
    s.add(110, "pass", DEF, start=(52.5, 34), end=(40, 30))  # başlama vuruşu
    s.add(112, "shot", start=(90, 34), end=(105, 34), xg=0.2)
    (sp,) = extract(s.actions)
    assert len(sp.shots) == 1


def test_own_goal_counts_as_set_piece_goal() -> None:
    s = corner(Seq())
    s.add(101, "bad_touch", DEF, start=(2, 36), result="owngoal")
    (sp,) = extract(s.actions)
    assert sp.goal
    assert sp.phase_of_goal == 1
    assert sp.outcome == "goal"


def test_shot_outcomes() -> None:
    s = corner(Seq())
    s.add(101, "shot", start=(100, 30), end=(103, 34), xg=0.2, result="fail")
    s.add(101.2, "keeper_save", DEF, start=(1, 34))
    assert extract(s.actions)[0].outcome == "shot_on_target"
    s = corner(Seq()).add(101, "shot", start=(100, 30), end=(105, 50), xg=0.1, result="fail")
    assert extract(s.actions)[0].outcome == "shot_off_target"
    s = corner(Seq()).add(101, "shot", start=(90, 30), end=(92, 31), xg=0.1, result="fail")
    assert extract(s.actions)[0].outcome == "shot_blocked"


def test_short_corner_retained_and_no_contact() -> None:
    s = Seq().add(10, "corner_short", start=(105, 0.5), end=(100, 5))
    s.add(11, "pass", start=(100, 5), end=(95, 20))
    (sp,) = extract(s.actions)
    assert (sp.sp_subtype, sp.target_zone, sp.outcome) == ("short", "SH", "possession_retained")
    s = corner(Seq()).add(101, "shot", start=(100, 30), end=(105, 34), period=2)
    assert extract(s.actions)[0].first_contact_team is None


def test_attacker_first_contact_without_shot() -> None:
    s = corner(Seq()).add(101, "pass", start=(100, 25), end=(90, 30))
    assert extract(s.actions)[0].outcome == "first_contact_no_shot"


# --- Değişmezler ----------------------------------------------------------

TYPES = [
    "pass",
    "cross",
    "shot",
    "clearance",
    "dribble",
    "corner_crossed",
    "corner_short",
    "freekick_crossed",
    "shot_freekick",
    "throw_in",
    "keeper_claim",
    "shot_penalty",
    "goalkick",
    "foul",
    "tackle",
]


@st.composite
def action_lists(draw: st.DrawFn) -> list[Action]:
    n = draw(st.integers(min_value=1, max_value=60))
    t = 0.0
    out: list[Action] = []
    for i in range(n):
        t += draw(st.floats(min_value=0, max_value=8))
        x1, x2 = draw(st.floats(0, 105)), draw(st.floats(0, 105))
        y1, y2 = draw(st.floats(0, 68)), draw(st.floats(0, 68))
        type_ = draw(st.sampled_from(TYPES))
        out.append(
            Action(
                action_index=i,
                period=1,
                time_s=t,
                team_provider_id=draw(st.sampled_from([ATT, DEF])),
                player_provider_id="p",
                type=type_,
                result=draw(st.sampled_from(["success", "fail"])),
                bodypart=draw(st.sampled_from(["foot_left", "foot_right", "head"])),
                start_x=x1,
                start_y=y1,
                end_x=x2,
                end_y=y2,
                xg=draw(st.floats(0, 1))
                if type_ in {"shot", "shot_freekick", "shot_penalty"}
                else None,
            )
        )
    return out


@given(action_lists())
@settings(max_examples=300, deadline=None)
def test_invariants(actions: list[Action]) -> None:
    sps = extract(actions)
    owner: Counter[int] = Counter()
    for sp in sps:
        assert sp.xg_phase1 + sp.xg_phase2 == pytest.approx(sp.xg_total)
        assert sp.goal == (sp.phase_of_goal is not None)
        for shot in sp.shots:
            owner[shot.action_index] += 1
            assert shot.action_index in sp.action_indices
            assert actions[shot.action_index].type != "shot_penalty"
        assert all(actions[k].time_s - sp.start_time_s <= 20 for k in sp.action_indices)
    assert all(count == 1 for count in owner.values())
