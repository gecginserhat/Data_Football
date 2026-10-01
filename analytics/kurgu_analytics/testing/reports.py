"""Test ve önizleme için örnek rapor girdileri (gerçek kayıt değildir; yalnız testlerde)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from kurgu_analytics.reports.diagram import Diagram, from_template
from kurgu_analytics.reports.documents import (
    Briefing,
    ClipLink,
    Evidence,
    FixtureLabel,
    MatchPlanReport,
    MetricRow,
    OpponentReport,
    PlanDay,
    PlanItem,
    Recommendation,
    ReportMeta,
    RoutineBlock,
    TeamLabel,
    ZoneCount,
)

CLUB = TeamLabel(code="TS", name="Trabzonspor")
OPPONENT = TeamLabel(code="SAM", name="Samsunspor")
NOW = dt.datetime(2026, 10, 5, 9, 30, tzinfo=dt.UTC)


def meta() -> ReportMeta:
    return ReportMeta(
        club=CLUB,
        generated_at=NOW,
        generated_by="Analist",
        season="2026/27",
        profile_season="2025/26",
        data_week=6,
        sources=["seed:super_lig"],
    )


def fixture() -> FixtureLabel:
    return FixtureLabel(
        week=7,
        kickoff_at=dt.datetime(2026, 10, 10, 17, 0, tzinfo=dt.UTC),
        is_home=False,
        club=CLUB,
        opponent=OPPONENT,
    )


def recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            area="attack",
            priority=1,
            confidence="high",
            title="Ceza sahası çevresinde faul kazanın",
            why="Samsunspor maç başına 14,82 faul yapıyor; ligde 4.",
            action="Ceza sahası önünde bire bir ve kombinasyon çalışın.",
            status="accepted",
            evidence=[
                Evidence(
                    subject="opponent",
                    metric="fouls_committed_per_match",
                    value=14.82,
                    rank=4,
                    teams=18,
                )
            ],
        ),
        Recommendation(
            area="defense",
            priority=1,
            confidence="medium",
            title="Korner savunması haftanın öncelikli çalışması",
            why="Samsunspor maç başına 6,40 korner kullanıyor; ligde 2.",
            action="Bölge ve adam karışık korner savunmasını MD-2'de prova edin.",
            status="accepted",
            routine="Karma korner savunması",
            evidence=[
                Evidence(
                    subject="opponent", metric="corners_per_match", value=6.4, rank=2, teams=18
                )
            ],
        ),
    ]


def opponent_report(briefing: bool = True) -> OpponentReport:
    metrics = [
        MetricRow(
            metric="set_piece_goals",
            value=12,
            rank=3,
            teams=18,
            league_mean=9.4,
            club_value=15,
            club_rank=1,
        ),
        MetricRow(
            metric="set_piece_xg",
            value=10.2,
            rank=5,
            teams=18,
            league_mean=9.9,
            club_value=13.1,
            club_rank=2,
        ),
        MetricRow(metric="set_piece_goal_share", value=0.24, rank=6, teams=18, league_mean=0.204),
        MetricRow(metric="set_piece_goals_minus_xg", value=1.8, rank=4, teams=18, league_mean=-0.5),
        MetricRow(
            metric="corners_per_match",
            value=6.4,
            rank=2,
            teams=18,
            league_mean=5.1,
            current_value=5.5,
            current_rank=6,
            current_teams=18,
            current_low_sample=True,
        ),
        MetricRow(
            metric="first_contact_win_pct",
            value=0.31,
            rank=12,
            teams=18,
            league_mean=0.33,
            low_sample=True,
        ),
        MetricRow(metric="set_piece_goals_against", value=11, rank=7, teams=18, league_mean=9.4),
        MetricRow(
            metric="aerial_win_pct", value=0.47, rank=16, teams=18, league_mean=0.5, indirect=True
        ),
        MetricRow(
            metric="fouls_committed_per_match",
            value=14.82,
            rank=4,
            teams=18,
            league_mean=13.2,
            indirect=True,
        ),
        MetricRow(metric="fouls_won_per_match", value=12.1, rank=10, teams=18, league_mean=12.6),
    ]
    return OpponentReport(
        meta=meta(),
        fixture=fixture(),
        standing="Samsunspor 34 maçta 52 puanla 6. sırada (34. hafta).",
        form=["W", "D", "L", "W", "W"],
        metrics=metrics,
        recommendations=recommendations(),
        zones=[
            ZoneCount(zone="NP", count=14),
            ZoneCount(zone="FP", count=9),
            ZoneCount(zone="C6", count=6),
            ZoneCount(zone="PS", count=4),
            ZoneCount(zone="SH", count=3),
        ],
        set_pieces=41,
        clips=[
            ClipLink(
                title="Arka direk golü",
                detail="7. hafta · korner 23:05",
                url="http://localhost:3000/video/x?clip=y",
            )
        ],
        briefing=Briefing(
            text="Samsunspor maç başına 6,40 korner kullanıyor ve bu metrikte ligde 2.",
            created_at=NOW,
        )
        if briefing
        else None,
    )


def template_diagram(index: int = 0) -> Diagram:
    root = Path(__file__).resolve().parents[3] / "seed" / "routine_templates.json"
    templates = json.loads(root.read_text(encoding="utf-8"))["templates"]
    return from_template(templates[index])


def match_plan_report() -> MatchPlanReport:
    days = [
        PlanDay(
            md_code="MD-2",
            date=dt.date(2026, 10, 8),
            focus="Duran top provası",
            items=[
                PlanItem(
                    title="Korner savunması provası",
                    done=True,
                    assignee="Duran Top",
                    routine="Karma korner savunması",
                ),
                PlanItem(title="Serbest vuruş hücumu", done=False),
            ],
        ),
        PlanDay(md_code="MD-1", date=dt.date(2026, 10, 9), focus="Hafif tekrar", items=[]),
    ]
    return MatchPlanReport(
        meta=meta(),
        fixture=fixture(),
        recommendations=recommendations(),
        routines=[
            RoutineBlock(
                name="Yakın direkte sıçratma",
                sp_type="corner",
                side="right",
                is_defensive=False,
                version=2,
                notes="Perdeleme zamanlaması önemli.",
                when_to_use="Rakip yakın direği alanla savunuyorsa.",
                diagram=template_diagram(0),
            ),
        ],
        days=days,
        plan_done=1,
        plan_total=2,
    )
