"""Maç hazırlığının iş mantığı: kural seti, öneriler, plan (ADR-0009).

Öneriler her istekte güncel kural setiyle hesaplanır; kayıtlı kararlar üstüne bindirilir (A-50).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from kurgu_analytics.recs import RuleResult, RuleSet, evaluate, recommendations
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.roles import Permission, Role, scope_for
from kurgu_api.league.metrics import SeasonMetrics
from kurgu_api.prep.facts import FixtureInfo, MetricsCache, fixture_facts, md_date
from kurgu_api.prep.plans import DAYS, MD_OFFSET, md_rank
from kurgu_api.prep.schemas import (
    EvidenceOut,
    MatchupRow,
    PlanDay,
    PlanItemOut,
    PlanOut,
    RecommendationOut,
    RoutineRef,
    RuleSetRef,
    SideValue,
    TemplateRef,
)
from kurgu_api.routines.schemas import UserRef

REC_NAMESPACE = uuid.UUID("6f1c2d8e-5b7a-4c39-9e0f-4b1d2a7c8e51")
"""Öneri kimliklerinin `uuid5` ad alanı (A-50)."""

RULE_SET_SQL = """
select rs.version, rs.label, rs.message, rs.published_at, rs.published_by, rs.rules,
       rs.tenant_id is null as is_default, u.display_name as published_by_name
from rule_sets rs left join users u on u.id = rs.published_by
order by rs.tenant_id is null, rs.version desc
limit 1
"""
STORED_SQL = """
select r.*, u.display_name as decided_by_name
from recommendations r left join users u on u.id = r.decided_by
where r.fixture_id = :fixture and r.status in ('accepted', 'rejected')
"""
TEMPLATES_SQL = "select id, name from routine_templates"
ROUTINE_NAMES_SQL = "select id, name from routines where archived_at is null order by name, id"
MEMBERS_SQL = """
select distinct m.user_id, m.role, u.display_name, u.email
from memberships m join users u on u.id = m.user_id
where m.tenant_id = kurgu_current_tenant()
"""
PLAN_SQL = "select id, template from fixture_plans where fixture_id = :fixture"
ITEMS_SQL = """
select i.*, a.display_name as assignee_name, d.display_name as done_by_name, r.name as routine_name
from plan_items i
left join users a on a.id = i.assignee_id
left join users d on d.id = i.done_by
left join routines r on r.id = i.routine_id
where i.plan_id = :plan
"""

MATCHUP_METRICS = (
    "set_piece_goals",
    "set_piece_xg",
    "set_piece_goal_share",
    "corners_per_match",
    "headed_goals",
    "aerial_win_pct",
    "fouls_committed_per_match",
    "fouls_won_per_match",
    "set_piece_goals_against",
    "direct_fk_goals",
)
"""Eşleşme notlarında gösterilen metrikler (SPEC §13.1 maç hazırlığı)."""


@dataclass(frozen=True, slots=True)
class LoadedRuleSet:
    version: int
    label: str | None
    is_default: bool
    message: str | None
    published_at: Any
    published_by: UserRef | None
    raw: list[dict[str, Any]]
    rules: RuleSet

    @property
    def ref(self) -> RuleSetRef:
        return RuleSetRef(version=self.version, label=self.label, is_default=self.is_default)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def user_ref(user_id: uuid.UUID | None, name: str | None) -> UserRef | None:
    return UserRef(id=user_id, name=name) if user_id else None


def parse_rules(raw: list[dict[str, Any]]) -> RuleSet:
    """Kural listesini şemayla doğrular; hatada 422 problem."""
    try:
        return RuleSet.model_validate({"rules": raw})
    except ValidationError as exc:
        errors = [
            {"loc": [str(p) for p in e["loc"]], "msg": e["msg"]}
            for e in exc.errors(include_url=False, include_context=False)
        ]
        raise ProblemError(
            422, "invalid-rules", "The rule set is not valid", extra={"errors": errors[:20]}
        ) from exc


async def current_rule_set(session: AsyncSession) -> LoadedRuleSet:
    """Kulübün son sürümü; yoksa varsayılan set (A-51)."""
    row = (await session.execute(text(RULE_SET_SQL))).one_or_none()
    if row is None:
        raise ProblemError(503, "rules-not-loaded", "Default rule set is not loaded")
    doc = _json(row.rules)
    raw = doc["rules"] if isinstance(doc, dict) else doc
    return LoadedRuleSet(
        version=row.version,
        label=row.label,
        is_default=row.is_default,
        message=row.message,
        published_at=row.published_at,
        published_by=user_ref(row.published_by, row.published_by_name),
        raw=raw,
        rules=parse_rules(raw),
    )


def recommendation_id(
    tenant_id: uuid.UUID, fixture_id: uuid.UUID, rule_id: str, subject_key: str | None
) -> uuid.UUID:
    return uuid.uuid5(REC_NAMESPACE, f"{tenant_id}:{fixture_id}:{rule_id}:{subject_key or ''}")


def evidence_out(rows: Any) -> list[EvidenceOut]:
    return [EvidenceOut.model_validate(r) for r in rows]


@dataclass(slots=True)
class Evaluation:
    fixture: FixtureInfo
    rule_set: LoadedRuleSet
    results: list[RuleResult]
    shown: list[RuleResult]
    routines: dict[str, str]
    """Rutin kimliği → ad."""
    templates: dict[str, str]
    cache: MetricsCache


async def evaluate_fixture(
    session: AsyncSession,
    fixture: FixtureInfo,
    rule_set: LoadedRuleSet | None = None,
    *,
    include_disabled: bool = False,
    scope: str = "fixture",
) -> Evaluation:
    rule_set = rule_set or await current_rule_set(session)
    cache = MetricsCache()
    facts, routines = await fixture_facts(session, fixture, cache)
    results = evaluate(
        rule_set.rules,
        facts,
        scope=scope,  # type: ignore[arg-type]
        routines=routines,
        include_disabled=include_disabled,
    )
    templates = {r.id: r.name for r in await session.execute(text(TEMPLATES_SQL))}
    return Evaluation(
        fixture=fixture,
        rule_set=rule_set,
        results=results,
        shown=recommendations(results),
        routines={s.key: s.labels["name"] for s in routines if s.key},
        templates=templates,
        cache=cache,
    )


def live_recommendation(
    ev: Evaluation, tenant_id: uuid.UUID, result: RuleResult
) -> RecommendationOut:
    rule = result.rule
    routine = (
        RoutineRef(id=uuid.UUID(result.subject_key), name=ev.routines[result.subject_key])
        if result.subject_key and result.subject_key in ev.routines
        else None
    )
    return RecommendationOut(
        id=recommendation_id(tenant_id, ev.fixture.id, rule.id, result.subject_key),
        rule_id=rule.id,
        rule_set_version=ev.rule_set.version,
        area=rule.area,
        priority=rule.priority,
        confidence=result.confidence or "low",
        title=result.title,
        why=result.why,
        action=result.action,
        template=(
            TemplateRef(id=rule.template, name=ev.templates[rule.template])
            if rule.template and rule.template in ev.templates
            else None
        ),
        routine=routine,
        evidence=evidence_out(result.evidence),
        status="suggested",
        reason=None,
        decided_by=None,
        decided_at=None,
        active=True,
    )


def stored_recommendation(
    row: Any, templates: dict[str, str], routines: dict[str, str], *, active: bool
) -> RecommendationOut:
    rid = str(row.routine_id) if row.routine_id else None
    return RecommendationOut(
        id=row.id,
        rule_id=row.rule_id,
        rule_set_version=row.rule_set_version,
        area=row.area,
        priority=row.priority,
        confidence=row.confidence,
        title=row.title,
        why=row.why,
        action=row.action,
        template=(
            TemplateRef(id=row.template_id, name=templates.get(row.template_id, row.template_id))
            if row.template_id
            else None
        ),
        routine=RoutineRef(id=row.routine_id, name=routines.get(rid, "—")) if rid else None,
        evidence=evidence_out(_json(row.evidence)),
        status=row.status,
        reason=row.reason,
        decided_by=user_ref(row.decided_by, row.decided_by_name),
        decided_at=row.decided_at,
        active=active,
    )


async def merged_recommendations(
    session: AsyncSession, ev: Evaluation, tenant_id: uuid.UUID
) -> list[RecommendationOut]:
    """Canlı öneriler + kayıtlı kararlar (A-50).

    Kararı verilmiş ama artık tetiklenmeyenler sonda.
    """
    stored = {r.id: r for r in await session.execute(text(STORED_SQL), {"fixture": ev.fixture.id})}
    out: list[RecommendationOut] = []
    for result in ev.shown:
        live = live_recommendation(ev, tenant_id, result)
        row = stored.pop(live.id, None)
        out.append(
            stored_recommendation(row, ev.templates, ev.routines, active=True) if row else live
        )
    leftovers = sorted(stored.values(), key=lambda r: (r.priority, r.rule_id))
    out.extend(stored_recommendation(r, ev.templates, ev.routines, active=False) for r in leftovers)
    return out


def _side(metrics: SeasonMetrics | None, team: uuid.UUID, metric: str) -> SideValue | None:
    if metrics is None:
        return None
    v = metrics.values.get(team, {}).get(metric)
    if v is None:
        return None
    return SideValue(
        value=v.value, rank=v.rank, teams=v.teams, low_sample=v.low_sample, approx=v.approx
    )


async def matchup(session: AsyncSession, ev: Evaluation) -> list[MatchupRow]:
    fx = ev.fixture
    current = await ev.cache.get(session, fx.out.season.id)
    previous = (
        await ev.cache.get(session, fx.out.previous_season.id) if fx.out.previous_season else None
    )
    rows: list[MatchupRow] = []
    for metric in MATCHUP_METRICS:
        opp = _side(previous, fx.opponent_id, metric)
        opp_now = _side(current, fx.opponent_id, metric)
        club = _side(previous, fx.club_id, metric)
        if opp is None and opp_now is None and club is None:
            continue
        sample = next(
            (
                m.values[t][metric]
                for m in (previous, current)
                if m is not None
                for t in (fx.opponent_id, fx.club_id)
                if metric in m.values.get(t, {})
            ),
            None,
        )
        bench = previous.benchmarks.get(metric) if previous else None
        rows.append(
            MatchupRow(
                metric=metric,
                indirect=bool(sample and sample.indirect),
                opponent=opp,
                opponent_current=opp_now,
                club=club,
                league_mean=bench.mean if bench else None,
            )
        )
    return rows


async def assignees(session: AsyncSession) -> list[UserRef]:
    """Plan maddesi işaretleme izni olan kulüp üyeleri."""
    seen: dict[uuid.UUID, UserRef] = {}
    for row in await session.execute(text(MEMBERS_SQL)):
        try:
            role = Role(row.role)
        except ValueError:
            continue
        if scope_for(frozenset({role}), Permission.MARK_PLAN_ITEMS) is None:
            continue
        seen.setdefault(row.user_id, UserRef(id=row.user_id, name=row.display_name or row.email))
    return sorted(seen.values(), key=lambda u: (u.name or "", str(u.id)))


async def routine_refs(session: AsyncSession) -> list[RoutineRef]:
    return [
        RoutineRef(id=r.id, name=r.name) for r in await session.execute(text(ROUTINE_NAMES_SQL))
    ]


async def load_plan(session: AsyncSession, fixture: FixtureInfo) -> PlanOut | None:
    plan = (await session.execute(text(PLAN_SQL), {"fixture": fixture.id})).one_or_none()
    if plan is None:
        return None
    rows = (await session.execute(text(ITEMS_SQL), {"plan": plan.id})).all()
    items = sorted(
        (
            PlanItemOut(
                id=r.id,
                md_code=r.md_code,
                position=r.position,
                title=r.title,
                detail=r.detail,
                status=r.status,
                assignee=user_ref(r.assignee_id, r.assignee_name),
                done_by=user_ref(r.done_by, r.done_by_name),
                done_at=r.done_at,
                recommendation_id=r.recommendation_id,
                routine=RoutineRef(id=r.routine_id, name=r.routine_name) if r.routine_id else None,
            )
            for r in rows
        ),
        key=lambda i: (md_rank(i.md_code), i.position, i.title),
    )
    days = [
        PlanDay(md_code=code, date=md_date(fixture.out.kickoff_at, MD_OFFSET[code]), focus=focus)
        for code, focus in DAYS[plan.template]
    ]
    done = sum(1 for i in items if i.status == "done")
    return PlanOut(
        id=plan.id, template=plan.template, days=days, items=items, done=done, total=len(items)
    )
