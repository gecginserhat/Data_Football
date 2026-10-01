"""Güvenli kural değerlendirici (SPEC §7, ADR-0009).

Girdi bir olgular sözlüğüdür (özne → `Subject`); veritabanına dokunulmaz, `eval` yoktur.
Değerlendirme üç değerlidir: koşul doğru, yanlış ya da verisi yok (`None`). Kural yalnızca
`True` ise tetiklenir; deneme modu yanlış ve veri yok durumlarını ayrı gösterir.

Güven (A-48): her koşulun eşikten uzaklığı 0-1'e çekilir; `all` en zayıfı, `any` tetiklenen
en güçlüyü alır. ≥ 0,5 `high`, ≥ 0,2 `medium`, altı `low`; koşul verilerinden biri "az veri"
ise bir basamak düşer.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from kurgu_analytics.recs.rules import (
    PLACEHOLDER_RE,
    ROUTINE_SUBJECT,
    Condition,
    Rule,
    RuleSet,
    When,
    split_path,
)

Confidence = Literal["high", "medium", "low"]
CONFIDENCE_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
HIGH_STRENGTH = 0.5
MEDIUM_STRENGTH = 0.2
MISSING_TEXT = "—"

METRIC_ALIASES = {"set_piece_goals_per_100_corners_approx": "goals_per_100_corners"}
"""Kural dosyasındaki ad → metrik modülündeki ad (A-47)."""


@dataclass(frozen=True, slots=True)
class Fact:
    """Bir öznenin bir metrikteki değeri (oranlar 0-1)."""

    value: float
    rank: int | None = None
    teams: int | None = None
    percentile: float | None = None
    """0-100; 100 = en yüksek değer."""
    matches: float | None = None
    trials: float | None = None
    low_sample: bool = False
    approx: bool = False
    indirect: bool = False
    league_mean: float | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class Subject:
    """Bir öznenin olguları: metrikler, metin etiketleri (ör. rutin adı) ve maç sayısı."""

    metrics: Mapping[str, Fact] = field(default_factory=dict)
    labels: Mapping[str, str] = field(default_factory=dict)
    matches: float | None = None
    key: str | None = None
    """Rutin öznesinde rutin kimliği (öneri kimliğine girer)."""

    def fact(self, metric: str) -> Fact | None:
        return self.metrics.get(METRIC_ALIASES.get(metric, metric))


Facts = Mapping[str, Subject]


@dataclass(frozen=True, slots=True)
class ConditionResult:
    subject: str
    metric: str
    op: str
    threshold: float | bool | None
    value: float | None
    rank: int | None
    teams: int | None
    passed: bool | None
    """None: verisi yok."""
    strength: float


@dataclass(frozen=True, slots=True)
class RuleResult:
    rule: Rule
    status: Literal["fired", "not_met", "missing_data", "low_sample", "disabled"]
    conditions: tuple[ConditionResult, ...]
    strength: float
    confidence: Confidence | None
    title: str
    why: str
    action: str
    evidence: tuple[dict[str, Any], ...]
    subject_key: str | None = None
    """Rutin kuralında rutin kimliği."""

    @property
    def fired(self) -> bool:
        return self.status == "fired"


# --- Operatörler ------------------------------------------------------------------------------


def _relative(x: float, v: float) -> float:
    return min(1.0, abs(x - v) / max(abs(v), 1.0))


def _rank_gte(rank: float, v: float, teams: float) -> float:
    return min(1.0, (rank - v) / max(teams - v, 1.0))


def _rank_lte(rank: float, v: float) -> float:
    return min(1.0, (v - rank) / max(v - 1.0, 1.0))


Check = Callable[[Fact, float], tuple[bool | None, float]]


def _value_op(test: Callable[[float, float], bool]) -> Check:
    def run(fact: Fact, v: float) -> tuple[bool | None, float]:
        ok = test(fact.value, v)
        return ok, _relative(fact.value, v) if ok else 0.0

    return run


def _rank_op(kind: Literal["gte", "lte"]) -> Check:
    def run(fact: Fact, v: float) -> tuple[bool | None, float]:
        if fact.rank is None or fact.teams is None:
            return None, 0.0
        if kind == "gte":
            ok = fact.rank >= v
            return ok, _rank_gte(fact.rank, v, fact.teams) if ok else 0.0
        ok = fact.rank <= v
        return ok, _rank_lte(fact.rank, v) if ok else 0.0

    return run


def _pctl_op(kind: Literal["gte", "lte"]) -> Check:
    def run(fact: Fact, v: float) -> tuple[bool | None, float]:
        if fact.percentile is None:
            return None, 0.0
        p = fact.percentile
        if kind == "gte":
            ok = p >= v
            return ok, min(1.0, (p - v) / max(100.0 - v, 1.0)) if ok else 0.0
        ok = p <= v
        return ok, min(1.0, (v - p) / max(v, 1.0)) if ok else 0.0

    return run


OPS: dict[str, Check] = {
    "gte": _value_op(lambda x, v: x >= v),
    "lte": _value_op(lambda x, v: x <= v),
    "gt": _value_op(lambda x, v: x > v),
    "lt": _value_op(lambda x, v: x < v),
    "eq": lambda fact, v: (math.isclose(fact.value, v, abs_tol=1e-9), 1.0),
    "rank_gte": _rank_op("gte"),
    "rank_lte": _rank_op("lte"),
    "pctl_gte": _pctl_op("gte"),
    "pctl_lte": _pctl_op("lte"),
}
"""Operatör adı → saf karşılaştırma. Yeni operatör ancak buraya eklenerek tanımlanır."""


def _eq_strength(result: tuple[bool | None, float]) -> tuple[bool | None, float]:
    return result[0], 1.0 if result[0] else 0.0


def check_condition(cond: Condition, facts: Facts) -> ConditionResult:
    subject = facts.get(cond.subject)
    fact = subject.fact(cond.metric) if subject else None
    threshold = cond.value
    if cond.op == "exists":
        expected = True if threshold is None else bool(threshold)
        present = fact is not None
        passed: bool | None = present == expected
        strength = 1.0 if passed else 0.0
    elif fact is None or (isinstance(fact.value, float) and math.isnan(fact.value)):
        passed, strength = None, 0.0
    else:
        assert threshold is not None
        assert not isinstance(threshold, bool)
        passed, strength = OPS[cond.op](fact, float(threshold))
        if cond.op == "eq":
            passed, strength = _eq_strength((passed, strength))
    return ConditionResult(
        subject=cond.subject,
        metric=cond.metric,
        op=cond.op,
        threshold=threshold,
        value=fact.value if fact else None,
        rank=fact.rank if fact else None,
        teams=fact.teams if fact else None,
        passed=passed,
        strength=strength,
    )


def _evaluate(
    node: When | Condition, facts: Facts, out: list[ConditionResult]
) -> tuple[bool | None, float]:
    if isinstance(node, Condition):
        r = check_condition(node, facts)
        out.append(r)
        return r.passed, r.strength
    if node.all is not None:
        parts = [_evaluate(c, facts, out) for c in node.all]
        if any(p is False for p, _ in parts):
            return False, 0.0
        if any(p is None for p, _ in parts):
            return None, 0.0
        return True, min(s for _, s in parts)
    if node.any is not None:
        parts = [_evaluate(c, facts, out) for c in node.any]
        hits = [s for p, s in parts if p is True]
        if hits:
            return True, max(hits)
        if any(p is None for p, _ in parts):
            return None, 0.0
        return False, 0.0
    assert node.not_ is not None
    passed, _ = _evaluate(node.not_, facts, out)
    if passed is None:
        return None, 0.0
    return (not passed), 1.0 if not passed else 0.0


def confidence(strength: float, low_sample: bool) -> Confidence:
    """Eşikten uzaklık puanı ve örneklem uyarısından güven düzeyi (A-48)."""
    level = 0 if strength >= HIGH_STRENGTH else 1 if strength >= MEDIUM_STRENGTH else 2
    if low_sample:
        level = min(2, level + 1)
    return ("high", "medium", "low")[level]


# --- Metinler -----------------------------------------------------------------------------------


def _tr_number(x: float, decimals: int) -> str:
    text = f"{abs(x):,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"-{text}" if x < 0 and float(f"{abs(x):.{decimals}f}") != 0 else text


def format_value(value: float, fmt: str | None) -> str:
    """Türkçe sayı biçimi (SPEC §7.2).

    pct %20,4 · pct100 %56,4 · dec1 5,7 · int 15 · signed +2,8.
    """
    if fmt == "pct" or (fmt == "pct100" and abs(value) <= 1):
        return f"%{_tr_number(value * 100, 1)}"
    if fmt == "pct100":
        return f"%{_tr_number(value, 1)}"
    if fmt == "int":
        return _tr_number(round(value), 0)
    if fmt == "signed":
        text = _tr_number(value, 1)
        return text if text.startswith("-") or text == "0,0" else f"+{text}"
    if fmt == "dec1":
        return _tr_number(value, 1)
    return _tr_number(value, 0) if float(value).is_integer() else _tr_number(value, 1)


def render(text: str, facts: Facts) -> str:
    """Yer tutucuları olgularla doldurur; değeri olmayan yer `—` olur."""

    def sub(match: Any) -> str:
        subject_name, rest = split_path(match.group(1))
        subject = facts.get(subject_name)
        if subject is None:
            return MISSING_TEXT
        if rest[0] == "rank":
            fact = subject.fact(rest[1])
            return str(fact.rank) if fact and fact.rank is not None else MISSING_TEXT
        name = rest[0]
        if name in subject.labels:
            return subject.labels[name]
        fact = subject.fact(name)
        if fact is None or math.isnan(fact.value):
            return MISSING_TEXT
        return format_value(fact.value, match.group(2))

    return PLACEHOLDER_RE.sub(sub, text)


# --- Kural ------------------------------------------------------------------------------------


def _evidence(rule: Rule, facts: Facts) -> tuple[dict[str, Any], ...]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for cond in rule.conditions():
        key = (cond.subject, cond.metric)
        if key in seen:
            continue
        seen.add(key)
        subject = facts.get(cond.subject)
        fact = subject.fact(cond.metric) if subject else None
        if fact is None:
            continue
        rows.append(
            {
                "subject": cond.subject,
                "metric": cond.metric,
                "value": fact.value,
                "rank": fact.rank,
                "teams": fact.teams,
                "league_mean": fact.league_mean,
                "matches": fact.matches,
                "trials": fact.trials,
                "low_sample": fact.low_sample,
                "approx": fact.approx,
                "indirect": fact.indirect,
                "source": fact.source,
                "op": cond.op,
                "threshold": cond.value,
            }
        )
    return tuple(rows)


def evaluate_rule(rule: Rule, facts: Facts, subject_key: str | None = None) -> RuleResult:
    """Tek kuralı olgular üzerinde değerlendirir; metinleri her durumda işler."""
    conditions: list[ConditionResult] = []
    passed, strength = _evaluate(rule.when, facts, conditions)
    status: Literal["fired", "not_met", "missing_data", "low_sample", "disabled"]
    if not rule.enabled:
        status = "disabled"
    elif passed is None:
        status = "missing_data"
    elif not passed:
        status = "not_met"
    else:
        status = "fired"
    if status == "fired" and rule.min_sample and rule.min_sample.matches:
        subjects = {c.subject for c in rule.conditions()}
        for name in subjects:
            matches = facts[name].matches if name in facts else None
            if matches is None or matches < rule.min_sample.matches:
                status = "low_sample"
    low = any(
        (s := facts.get(c.subject)) is not None
        and (f := s.fact(c.metric)) is not None
        and f.low_sample
        for c in rule.conditions()
    )
    return RuleResult(
        rule=rule,
        status=status,
        conditions=tuple(conditions),
        strength=strength if passed else 0.0,
        confidence=confidence(strength, low) if status == "fired" else None,
        title=render(rule.title, facts),
        why=render(rule.why, facts),
        action=render(rule.action, facts),
        evidence=_evidence(rule, facts),
        subject_key=subject_key,
    )


def evaluate(
    rule_set: RuleSet,
    facts: Facts,
    *,
    scope: Literal["fixture", "season"],
    routines: Iterable[Subject] = (),
    include_disabled: bool = False,
) -> list[RuleResult]:
    """Kapsamdaki tüm kuralların sonuçları (deneme modu için tetiklenmeyenler dahil).

    Rutin öznesi kullanan kurallar her rutin için ayrı değerlendirilir; rutin yoksa tek sonuç
    "veri yok" olur.
    """
    routines = list(routines)
    out: list[RuleResult] = []
    for rule in rule_set.rules:
        if rule.scope != scope or (not rule.enabled and not include_disabled):
            continue
        if rule.per_routine and routines:
            for routine in routines:
                out.append(evaluate_rule(rule, {**facts, ROUTINE_SUBJECT: routine}, routine.key))
        else:
            out.append(evaluate_rule(rule, facts))
    return out


def recommendations(results: Iterable[RuleResult]) -> list[RuleResult]:
    """Tetiklenenler; öncelik, güven ve güce göre sıralı, aynı şablonda en öndeki kalır."""
    fired = sorted(
        (r for r in results if r.fired),
        key=lambda r: (
            r.rule.priority,
            CONFIDENCE_ORDER[r.confidence or "low"],
            -r.strength,
            r.rule.id,
            r.subject_key or "",
        ),
    )
    seen_templates: set[str] = set()
    kept: list[RuleResult] = []
    for r in fired:
        if r.rule.template:
            if r.rule.template in seen_templates:
                continue
            seen_templates.add(r.rule.template)
        kept.append(r)
    return kept
