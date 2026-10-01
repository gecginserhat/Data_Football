"""Öneri motoru: kural şeması, değerlendirici, güven, metinler (SPEC §7, ADR-0009)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from kurgu_analytics.recs import (
    Fact,
    Rule,
    RuleSet,
    Subject,
    confidence,
    evaluate,
    evaluate_rule,
    format_value,
    recommendations,
    render,
)
from pydantic import ValidationError

SEED = Path(__file__).resolve().parents[2] / "seed" / "recommendation_rules.json"


def seed_rules() -> RuleSet:
    return RuleSet.model_validate(json.loads(SEED.read_text(encoding="utf-8")))


def rule(**changes: object) -> Rule:
    base: dict[str, object] = {
        "id": "T_RULE",
        "scope": "fixture",
        "area": "attack",
        "priority": 1,
        "when": {"all": [{"subject": "opponent", "metric": "m", "op": "rank_lte", "value": 6}]},
        "title": "Başlık",
        "why": "Rakip {opponent.m|dec1} ({opponent.rank.m}.).",
        "action": "Yapın.",
        "enabled": True,
    }
    base.update(changes)
    return Rule.model_validate(base)


def opp(**metrics: Fact) -> dict[str, Subject]:
    return {"opponent": Subject(metrics=metrics, matches=34)}


# --- Şema --------------------------------------------------------------------------------------


def test_seed_rules_parse() -> None:
    rules = seed_rules().rules
    assert len(rules) == 25
    assert sum(r.per_routine for r in rules) == 2
    assert {r.scope for r in rules} == {"fixture", "season"}


@pytest.mark.parametrize(
    "changes",
    [
        {"why": "{__import__('os').system('x')}"},
        {"why": "Değer {opponent.m|exec}"},
        {"why": "Değer {secret.m}"},
        {"why": "Değer {opponent.rank.m|pct}"},
        {"why": "Açık { parantez"},
        {"when": {"all": [{"subject": "opponent", "metric": "m", "op": "eval", "value": 1}]}},
        {"when": {"all": [{"subject": "anyone", "metric": "m", "op": "gte", "value": 1}]}},
        {"when": {"all": [{"subject": "opponent", "metric": "m", "op": "rank_lte", "value": 2.5}]}},
        {"when": {"all": []}},
        {"when": {"all": [{"subject": "opponent", "metric": "m", "op": "gte"}]}},
        {"id": "lower_case"},
    ],
)
def test_rejects_unsafe_or_malformed_rules(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        rule(**changes)


def test_rule_ids_are_unique() -> None:
    r = rule().model_dump(by_alias=True)
    with pytest.raises(ValidationError):
        RuleSet.model_validate({"rules": [r, r]})


# --- Operatörler ve üç değerli mantık ---------------------------------------------------------


def test_rank_lte_fires_with_strength_and_text() -> None:
    result = evaluate_rule(rule(), opp(m=Fact(value=14.43, rank=4, teams=18)))
    assert result.fired
    assert result.strength == pytest.approx(0.4)
    assert result.confidence == "medium"
    assert result.why == "Rakip 14,4 (4.)."
    assert result.evidence[0]["rank"] == 4


def test_not_met_and_missing_data() -> None:
    assert evaluate_rule(rule(), opp(m=Fact(value=1, rank=9, teams=18))).status == "not_met"
    missing = evaluate_rule(rule(), opp())
    assert missing.status == "missing_data"
    assert missing.why == "Rakip — (—.)."


@pytest.mark.parametrize(
    ("op", "value", "fact", "passed"),
    [
        ("gte", 2, Fact(value=2), True),
        ("gt", 2, Fact(value=2), False),
        ("lte", -2, Fact(value=-2.4), True),
        ("lt", 0.5, Fact(value=0.6), False),
        ("eq", 0, Fact(value=0.0), True),
        ("rank_gte", 12, Fact(value=0.4, rank=18, teams=18), True),
        ("pctl_gte", 80, Fact(value=1, percentile=90), True),
        ("pctl_lte", 20, Fact(value=1, percentile=30), False),
    ],
)
def test_operators(op: str, value: float, fact: Fact, passed: bool) -> None:
    r = rule(when={"all": [{"subject": "opponent", "metric": "m", "op": op, "value": value}]})
    assert evaluate_rule(r, opp(m=fact)).fired is passed


def test_exists_and_not() -> None:
    exists = rule(when={"all": [{"subject": "opponent", "metric": "m", "op": "exists"}]})
    assert evaluate_rule(exists, opp(m=Fact(value=0))).fired
    assert evaluate_rule(exists, opp()).status == "not_met"
    negated = rule(
        when={"not": {"subject": "opponent", "metric": "m", "op": "gte", "value": 5}},
    )
    assert evaluate_rule(negated, opp(m=Fact(value=3))).fired
    assert evaluate_rule(negated, opp()).status == "missing_data"


def test_any_takes_strongest_hit_and_all_the_weakest() -> None:
    conds = [
        {"subject": "opponent", "metric": "a", "op": "rank_lte", "value": 5},
        {"subject": "opponent", "metric": "b", "op": "rank_lte", "value": 5},
    ]
    facts = opp(a=Fact(value=1, rank=1, teams=18), b=Fact(value=1, rank=4, teams=18))
    assert evaluate_rule(rule(when={"any": conds}), facts).strength == 1.0
    assert evaluate_rule(rule(when={"all": conds}), facts).strength == pytest.approx(0.25)
    # Bir koşulun verisi yokken diğeri tetiklenirse `any` yine tetiklenir.
    assert evaluate_rule(rule(when={"any": conds}), opp(a=Fact(value=1, rank=2, teams=18))).fired


def test_confidence_levels_and_low_sample_downgrade() -> None:
    assert confidence(0.6, False) == "high"
    assert confidence(0.6, True) == "medium"
    assert confidence(0.2, False) == "medium"
    assert confidence(0.1, True) == "low"
    facts = opp(m=Fact(value=1, rank=1, teams=18, low_sample=True))
    assert evaluate_rule(rule(), facts).confidence == "medium"


def test_min_sample_blocks_small_samples() -> None:
    r = rule(min_sample={"matches": 5})
    facts = {"opponent": Subject(metrics={"m": Fact(value=1, rank=1, teams=18)}, matches=3)}
    assert evaluate_rule(r, facts).status == "low_sample"


def test_disabled_rules_are_skipped_unless_asked() -> None:
    rs = RuleSet(rules=[rule(enabled=False)])
    facts = opp(m=Fact(value=1, rank=1, teams=18))
    assert evaluate(rs, facts, scope="fixture") == []
    assert evaluate(rs, facts, scope="fixture", include_disabled=True)[0].status == "disabled"


# --- Biçimler ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "fmt", "text"),
    [
        (0.2044, "pct", "%20,4"),
        (56.4, "pct100", "%56,4"),
        (0.564, "pct100", "%56,4"),
        (5.66, "dec1", "5,7"),
        (15.0, "int", "15"),
        (2.84, "signed", "+2,8"),
        (-2.84, "signed", "-2,8"),
        (1234.5, "dec1", "1.234,5"),
        (3.0, None, "3"),
    ],
)
def test_turkish_formats(value: float, fmt: str | None, text: str) -> None:
    assert format_value(value, fmt) == text


def test_render_labels_and_aliases() -> None:
    routine = Subject(
        metrics={"uses": Fact(value=6), "shot_rate_posterior": Fact(value=0.55)},
        labels={"name": "Arka direk"},
    )
    text = render(
        '"{routine.name}" {routine.uses|int} kullanımda {routine.shot_rate_posterior|pct}',
        {"own_log.routine": routine},
    )
    assert text == '"Arka direk" 6 kullanımda %55,0'


# --- Rutin kuralları, sıralama ve tekilleştirme ----------------------------------------------


def test_routine_rules_run_per_routine() -> None:
    rules = RuleSet(rules=[r for r in seed_rules().rules if r.id == "LOG_ROUTINE_WORKS"])
    hot = Subject(
        metrics={"uses": Fact(value=6), "shot_rate_posterior": Fact(value=0.6)},
        labels={"name": "Arka"},
        key="r1",
    )
    cold = Subject(
        metrics={"uses": Fact(value=6), "shot_rate_posterior": Fact(value=0.1)},
        labels={"name": "Kısa"},
        key="r2",
    )
    results = evaluate(rules, {}, scope="fixture", routines=[hot, cold])
    assert [(r.subject_key, r.fired) for r in results] == [("r1", True), ("r2", False)]
    assert results[0].title == '"Arka" çalışıyor; plana alın'
    # Rutin yoksa tek sonuç: veri yok.
    assert evaluate(rules, {}, scope="fixture")[0].status == "missing_data"


def test_recommendations_sort_and_dedup_by_template() -> None:
    facts = opp(m=Fact(value=1, rank=1, teams=18), n=Fact(value=1, rank=5, teams=18))
    a = rule(id="A", priority=2, template="tpl-x")
    b = rule(id="B", priority=1, template="tpl-x")
    c = rule(
        id="C",
        priority=1,
        when={"all": [{"subject": "opponent", "metric": "n", "op": "rank_lte", "value": 6}]},
    )
    out = recommendations(evaluate(RuleSet(rules=[a, b, c]), facts, scope="fixture"))
    assert [r.rule.id for r in out] == ["B", "C"]


def test_acceptance_example_rules_fire_on_samsunspor_ranks() -> None:
    """Kabul örneği (SPEC §19 Faz 4): faulde 4., korner/maçta 2. sıradaki rakip."""
    rs = seed_rules()
    facts = {
        "opponent": Subject(
            metrics={
                "fouls_committed_per_match": Fact(value=14.4, rank=4, teams=18, matches=34),
                "corners_per_match": Fact(value=6.1, rank=2, teams=18, matches=34),
            },
            matches=34,
        )
    }
    fired = {r.rule.id: r for r in evaluate(rs, facts, scope="fixture") if r.fired}
    assert fired["ATK_WIN_FOULS"].title == "Ceza sahası çevresinde faul kazanın"
    assert fired["DEF_CORNER_PRIORITY"].title == "Korner savunması haftanın öncelikli çalışması"
    assert "ligde 4." in fired["ATK_WIN_FOULS"].why
