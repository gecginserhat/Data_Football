"""Tohum şemaları ve bütünlük kontrolleri (SPEC §5.7; assumptions A-02)."""

from pathlib import Path

import pytest
from kurgu_analytics.ingestion.seed import (
    SuperLigSeed,
    check_integrity,
    load_recommendation_rules,
    load_routine_templates,
    load_super_lig,
    recompute_standings,
    render_report,
)
from pydantic import ValidationError

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


@pytest.fixture(scope="module")
def seed() -> SuperLigSeed:
    return load_super_lig(SEED_DIR / "super_lig.json")


def test_seed_files_match_schemas() -> None:
    assert len(load_routine_templates(SEED_DIR / "routine_templates.json").templates) == 7
    assert len(load_recommendation_rules(SEED_DIR / "recommendation_rules.json").rules) == 25


def test_integrity_matches_assumption_a02(seed: SuperLigSeed) -> None:
    report = check_integrity(seed)
    assert report.ok
    deltas = {f.team_id: f.delta for f in report.warnings}
    assert deltas == {"gs": 4, "ibfk": 3, "sam": 3, "fb": 2, "kon": 2, "kas": 2, "gen": 2}


def test_standings_error_stops_load(seed: SuperLigSeed) -> None:
    s26 = seed.seasons.s2026_27
    first = s26.results_weeks_1_6[0]
    broken = s26.model_copy(
        update={
            "results_weeks_1_6": [
                first.model_copy(update={"home_goals": first.home_goals + 5}),
                *s26.results_weeks_1_6[1:],
            ]
        }
    )
    tampered = seed.model_copy(
        update={"seasons": seed.seasons.model_copy(update={"s2026_27": broken})}
    )
    report = check_integrity(tampered)
    assert not report.ok
    assert {f.check for f in report.errors} == {"standings"}


def test_unknown_team_is_an_error(seed: SuperLigSeed) -> None:
    teams = [t for t in seed.teams if t.id != "ts"]
    report = check_integrity(seed.model_copy(update={"teams": teams}))
    assert any(f.check == "references" and f.team_id == "ts" for f in report.errors)


def test_recompute_standings_counts_points(seed: SuperLigSeed) -> None:
    table = recompute_standings(seed.seasons.s2026_27.results_weeks_1_6)
    assert table["amd"]["pts"] == 13
    assert sum(r["played"] for r in table.values()) == 2 * 54


def test_schema_rejects_unknown_fields() -> None:
    raw = (SEED_DIR / "super_lig.json").read_text(encoding="utf-8")
    bad = raw.replace('"in_2026_27"', '"in_2026_27_typo"', 1)
    with pytest.raises(ValidationError):
        SuperLigSeed.model_validate_json(bad)


def test_committed_report_is_current(seed: SuperLigSeed) -> None:
    committed = Path(__file__).resolve().parents[2] / "docs" / "validation" / "seed_integrity.md"
    assert committed.read_text(encoding="utf-8") == render_report(check_integrity(seed), seed)
