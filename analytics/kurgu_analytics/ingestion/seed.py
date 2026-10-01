"""Tohum dosyalarının şemaları ve bütünlük kontrolleri (SPEC §5.7, Ek A; assumptions A-02).

Bu modül saf doğrulama yapar; veritabanına yazmaz. Yükleme `kurgu_api.league.seed`
içindedir.

Bütünlük kontrolleri (`super_lig.json` → `meta.integrity_checks`):
1. `open_play + fast_break + penalty + set_piece = goals` (0-1 kendi kalesine gol farkı).
   Kaynaklar arası tanım farkı nedeniyle 7 takımda tutmuyor; **uyarı** üretir (A-02).
2. Sonuçlardan yeniden hesaplanan puan tablosu, tohumdaki tabloyla birebir aynı. **Hata.**
3. 2025/26 toplam duran top golü 166, toplam gol 812, pay %20,4. **Hata.**
Ek olarak referans bütünlüğü (bilinmeyen takım kimliği) **hata** sayılır.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt

SEED_SOURCE = "seed:super_lig.json"
GOAL_BREAKDOWN_TOLERANCE = 1
EXPECTED_SET_PIECE_GOALS = 166
EXPECTED_GOALS = 812


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SeedTeam(_Strict):
    id: str = Field(pattern=r"^[a-z]{2,5}$")
    code: str = Field(min_length=2, max_length=5)
    name: str
    official_name: str
    in_2026_27: bool
    promoted_2026_27: bool
    relegated_2025_26: bool


class TeamSeasonStats(_Strict):
    """2025/26 takım-sezon özeti. Birimler `meta.definitions` alanında."""

    team_id: str
    matches: NonNegativeInt
    goals: NonNegativeInt
    goals_against: NonNegativeInt
    xg: NonNegativeFloat
    xga: NonNegativeFloat
    penalty_goals: NonNegativeInt
    penalty_attempts: NonNegativeInt
    open_play_goals: NonNegativeInt
    fast_break_goals: NonNegativeInt
    direct_fk_goals: NonNegativeInt
    headed_goals: NonNegativeInt
    corners_per_match: NonNegativeFloat
    aerials_won_per_match: NonNegativeFloat
    aerial_win_pct: float = Field(ge=0, le=100)
    clearances_per_match: NonNegativeFloat
    fouls_committed: NonNegativeInt
    fouls_won: NonNegativeInt
    accurate_crosses_per_match: NonNegativeFloat
    set_piece_goals: NonNegativeInt
    set_piece_xg: NonNegativeFloat

    def metrics(self) -> dict[str, float]:
        """`team_id` dışındaki tüm alanlar metrik olarak."""
        return {k: float(v) for k, v in self.model_dump().items() if k != "team_id"}


class Season2025(_Strict):
    competition: str
    matches_per_team: int
    total_matches: int
    team_stats: list[TeamSeasonStats]


class SetPieceToDate(_Strict):
    team_id: str
    set_piece_goals: NonNegativeInt
    set_piece_xg: NonNegativeFloat


class StandingRow(_Strict):
    pos: int = Field(ge=1)
    team_id: str
    played: NonNegativeInt
    won: NonNegativeInt
    drawn: NonNegativeInt
    lost: NonNegativeInt
    gf: NonNegativeInt
    ga: NonNegativeInt
    pts: NonNegativeInt


class Result(_Strict):
    week: int = Field(ge=1)
    home: str
    away: str
    home_goals: NonNegativeInt
    away_goals: NonNegativeInt


class Fixture(_Strict):
    week: int = Field(ge=1)
    home: str
    away: str
    date: dt.date | None = None
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    tz: str | None = None
    date_window: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}$")


class Season2026(_Strict):
    competition: str
    as_of_week: int
    set_piece_to_date: list[SetPieceToDate]
    standings_after_week_6: list[StandingRow]
    results_weeks_1_6: list[Result]
    fixtures_weeks_7_12: list[Fixture]


class Seasons(_Strict):
    s2025_26: Season2025 = Field(alias="2025_26")
    s2026_27: Season2026 = Field(alias="2026_27")


class Meta(_Strict):
    compiled_at: dt.date
    license_note: str
    sources: dict[str, str]
    definitions: dict[str, str]
    integrity_checks: list[str]


class Benchmarks(_Strict):
    premier_league_2025_26: dict[str, float]
    super_lig_2025_26: dict[str, float]


class SuperLigSeed(_Strict):
    meta: Meta
    teams: list[SeedTeam]
    seasons: Seasons
    benchmarks: Benchmarks


# --- Diğer tohum dosyaları: Faz 1'de yalnızca şema doğrulaması --------------


class TemplatePlayer(_Strict):
    team: Literal["own", "opponent"]
    role: str
    x: float = Field(ge=0, le=105)
    y: float = Field(ge=0, le=68)
    number: int | None = None


class TemplateLine(_Strict):
    kind: Literal["run", "ball_path"]
    from_: tuple[float, float] = Field(alias="from")
    to: tuple[float, float]
    curve: float


class RoutineTemplate(_Strict):
    id: str
    name: str
    sp_type: Literal["corner", "free_kick", "throw_in"]
    side: Literal["left", "right"] | None = None
    is_defensive: bool
    when_to_use: str
    notes: str
    players: list[TemplatePlayer]
    lines: list[TemplateLine]


class RoutineTemplates(_Strict):
    meta: dict[str, str]
    templates: list[RoutineTemplate]


Op = Literal[
    "gte", "lte", "gt", "lt", "eq", "rank_gte", "rank_lte", "pctl_gte", "pctl_lte", "exists"
]


class Condition(_Strict):
    subject: str
    metric: str
    op: Op
    value: float | str | bool | None = None


class When(_Strict):
    all: list[Condition | When] | None = None
    any: list[Condition | When] | None = None
    not_: Condition | When | None = Field(default=None, alias="not")


class Rule(_Strict):
    id: str = Field(pattern=r"^[A-Z0-9_]+$")
    scope: Literal["fixture", "season"]
    area: Literal["attack", "defense", "balance", "season"]
    priority: int = Field(ge=1)
    when: When
    title: str
    why: str
    action: str
    enabled: bool
    template: str | None = None
    min_sample: dict[str, int] | None = None


class RecommendationRules(_Strict):
    meta: dict[str, object]
    rules: list[Rule]


# --- Bütünlük kontrolleri ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    severity: Literal["warning", "error"]
    message: str
    team_id: str | None = None
    delta: float | None = None


@dataclass(slots=True)
class IntegrityReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def recompute_standings(results: list[Result]) -> dict[str, dict[str, int]]:
    """Sonuçlardan puan tablosu: galibiyet 3, beraberlik 1 puan."""
    table: dict[str, dict[str, int]] = {}
    for r in results:
        for team, gf, ga in (
            (r.home, r.home_goals, r.away_goals),
            (r.away, r.away_goals, r.home_goals),
        ):
            row = table.setdefault(
                team, {"played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "pts": 0}
            )
            row["played"] += 1
            row["gf"] += gf
            row["ga"] += ga
            if gf > ga:
                row["won"] += 1
                row["pts"] += 3
            elif gf == ga:
                row["drawn"] += 1
                row["pts"] += 1
            else:
                row["lost"] += 1
    return table


def check_integrity(seed: SuperLigSeed) -> IntegrityReport:
    report = IntegrityReport()
    team_ids = {t.id for t in seed.teams}
    s25, s26 = seed.seasons.s2025_26, seed.seasons.s2026_27

    referenced = (
        [s.team_id for s in s25.team_stats]
        + [s.team_id for s in s26.set_piece_to_date]
        + [s.team_id for s in s26.standings_after_week_6]
        + [t for r in s26.results_weeks_1_6 for t in (r.home, r.away)]
        + [t for f in s26.fixtures_weeks_7_12 for t in (f.home, f.away)]
    )
    for unknown in sorted(set(referenced) - team_ids):
        report.findings.append(
            Finding("references", "error", f"bilinmeyen takım kimliği: {unknown}", unknown)
        )

    for s in s25.team_stats:
        parts = s.open_play_goals + s.fast_break_goals + s.penalty_goals + s.set_piece_goals
        delta = s.goals - parts
        if not 0 <= delta <= GOAL_BREAKDOWN_TOLERANCE:
            report.findings.append(
                Finding(
                    "goal_breakdown",
                    "warning",
                    f"{s.team_id}: gol kırılımı toplamı {parts}, toplam gol {s.goals}",
                    s.team_id,
                    float(delta),
                )
            )

    recomputed = recompute_standings(s26.results_weeks_1_6)
    for row in s26.standings_after_week_6:
        computed = recomputed.get(row.team_id)
        expected = row.model_dump(exclude={"pos", "team_id"})
        if computed != expected:
            report.findings.append(
                Finding(
                    "standings",
                    "error",
                    f"{row.team_id}: tablo {expected}, sonuçlardan {computed}",
                    row.team_id,
                )
            )
    pts = [r.pts for r in sorted(s26.standings_after_week_6, key=lambda r: r.pos)]
    if pts != sorted(pts, reverse=True):
        report.findings.append(Finding("standings", "error", "sıralama puana göre azalmıyor"))

    sp_goals = sum(s.set_piece_goals for s in s25.team_stats)
    goals = sum(s.goals for s in s25.team_stats)
    bench = seed.benchmarks.super_lig_2025_26
    if (sp_goals, goals) != (EXPECTED_SET_PIECE_GOALS, EXPECTED_GOALS) or (
        bench["set_piece_goals"],
        bench["goals"],
    ) != (sp_goals, goals):
        report.findings.append(
            Finding(
                "totals",
                "error",
                f"duran top golü {sp_goals}, toplam gol {goals}; kıyas {bench}",
            )
        )
    elif abs(bench["set_piece_goal_share"] - sp_goals / goals) > 0.0005:
        report.findings.append(Finding("totals", "error", "duran top payı kıyasla tutmuyor"))
    return report


def load_super_lig(path: Path) -> SuperLigSeed:
    return SuperLigSeed.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_routine_templates(path: Path) -> RoutineTemplates:
    return RoutineTemplates.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_recommendation_rules(path: Path) -> RecommendationRules:
    return RecommendationRules.model_validate(json.loads(path.read_text(encoding="utf-8")))


def render_report(report: IntegrityReport, seed: SuperLigSeed) -> str:
    """`docs/validation/seed_integrity.md` içeriği (Markdown, Türkçe)."""
    s25 = seed.seasons.s2025_26
    lines = [
        "# Tohum bütünlük raporu",
        "",
        f"Kaynak: `seed/super_lig.json` (derlenme {seed.meta.compiled_at.isoformat()}). "
        "Bu dosya `make seed-report` ile üretilir; elle düzenlenmez.",
        "",
        "| Kontrol | Sonuç |",
        "|---|---|",
    ]
    by_check: dict[str, list[Finding]] = {}
    for f in report.findings:
        by_check.setdefault(f.check, []).append(f)
    names = {
        "references": "Referans bütünlüğü (takım kimlikleri)",
        "goal_breakdown": "1. Gol kırılımı = toplam gol (0-1 tolerans)",
        "standings": "2. Sonuçlardan puan tablosu",
        "totals": "3. Duran top golü 166 / toplam gol 812",
    }
    for key, name in names.items():
        found = by_check.get(key, [])
        if not found:
            verdict = "Tuttu"
        else:
            level = "Uyarı" if all(f.severity == "warning" for f in found) else "Hata"
            verdict = f"{level} ({len(found)} bulgu)"
        lines.append(f"| {name} | {verdict} |")
    breakdown = by_check.get("goal_breakdown", [])
    if breakdown:
        stats = {s.team_id: s for s in s25.team_stats}
        lines += [
            "",
            "## Kontrol 1 farkları",
            "",
            "Veri düzeltilmedi (assumptions A-02). Fark büyük olasılıkla kaynaklar arası tanım "
            "farkından ve kendi kalesine gollerden geliyor. Yükleme durmaz; kayıtlar olduğu gibi "
            "yüklenir.",
            "",
            "| Takım | Gol | Akan oyun | Hızlı hücum | Penaltı | Duran top | Fark |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for f in sorted(breakdown, key=lambda f: (-(f.delta or 0), f.team_id or "")):
            s = stats[f.team_id or ""]
            lines.append(
                f"| {s.team_id.upper()} | {s.goals} | {s.open_play_goals} | {s.fast_break_goals} "
                f"| {s.penalty_goals} | {s.set_piece_goals} | {int(f.delta or 0):+d} |"
            )
    errors = report.errors
    if errors:
        lines += ["", "## Hatalar", ""] + [f"- {f.message}" for f in errors]
    return "\n".join(lines) + "\n"
