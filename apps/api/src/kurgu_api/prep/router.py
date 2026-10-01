"""Maç hazırlığı uçları (SPEC §11 Hazırlık ve Kurallar, ADR-0009).

İzinler (SPEC §12.1): okuma `read_analysis`, öneri kararı `decide_recommendations`, plan
maddeleri `mark_plan_items`, kural ayarları `rule_settings`. Her yazma denetim kaydına girer.
"""

import dataclasses
import datetime as dt
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text

from kurgu_api.core.audit import write_audit
from kurgu_api.core.http import etag_response
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.prep.facts import MetricsCache, club_team_id, load_fixture
from kurgu_api.prep.plans import ACCEPT_DAY, ITEMS
from kurgu_api.prep.schemas import (
    ConditionOut,
    DecisionIn,
    DryRunIn,
    DryRunOut,
    DryRunRule,
    OverviewRecsOut,
    PlanCreate,
    PlanItemCreate,
    PlanItemPatch,
    PlanOut,
    PrepOut,
    RecommendationOut,
    RoutineRef,
    RuleSetOut,
    RuleSetUpdate,
    RuleSetVersionOut,
    ThreatOut,
    UpcomingThreats,
)
from kurgu_api.prep.service import (
    Evaluation,
    LoadedRuleSet,
    assignees,
    current_rule_set,
    evaluate_fixture,
    live_recommendation,
    load_plan,
    matchup,
    merged_recommendations,
    parse_rules,
    recommendation_id,
    routine_refs,
    user_ref,
)

read = [Depends(require(Permission.READ_ANALYSIS))]
decide = [Depends(require(Permission.DECIDE_RECOMMENDATIONS))]
mark = [Depends(require(Permission.MARK_PLAN_ITEMS))]
rules_admin = [Depends(require(Permission.RULE_SETTINGS))]
router = APIRouter(tags=["prep"])

UPCOMING_SQL = """
select m.id from matches m
where m.status = 'scheduled' and (m.home_team_id = :club or m.away_team_id = :club)
order by m.kickoff_at nulls last, m.week, m.id
limit :limit
"""


def _tenant(principal: PrincipalDep) -> uuid.UUID:
    assert principal.tenant is not None
    return principal.tenant.tenant_id


# --- Hazırlık ------------------------------------------------------------------------------------


@router.get(
    "/fixtures/{fixture_id}/prep",
    response_model=PrepOut,
    operation_id="getFixturePrep",
    dependencies=read,
)
async def get_prep(
    request: Request, session: SessionDep, principal: PrincipalDep, fixture_id: uuid.UUID
) -> Response:
    """Öneriler (kanıt ve güvenle), eşleşme notları, MD planı, sorumlu adayları (SPEC §13.2)."""
    fixture = await load_fixture(session, fixture_id)
    ev = await evaluate_fixture(session, fixture)
    out = PrepOut(
        fixture=fixture.out,
        rule_set=ev.rule_set.ref,
        recommendations=await merged_recommendations(session, ev, _tenant(principal)),
        matchup=await matchup(session, ev),
        plan=await load_plan(session, fixture),
        assignees=await assignees(session),
        routines=await routine_refs(session),
    )
    return etag_response(request, out)


async def _ensure_plan(
    session: SessionDep, principal: PrincipalDep, fixture_id: uuid.UUID, template: str
) -> tuple[uuid.UUID, str, bool]:
    """Planı döner; yoksa şablonla oluşturur. (plan, şablon, yeni mi)."""
    row = (
        await session.execute(
            text("select id, template from fixture_plans where fixture_id = :f"), {"f": fixture_id}
        )
    ).one_or_none()
    if row:
        return row.id, row.template, False
    tenant = _tenant(principal)
    plan_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into fixture_plans (tenant_id, fixture_id, template, created_by)"
                " values (:t, :f, :tpl, :u) returning id"
            ),
            {"t": tenant, "f": fixture_id, "tpl": template, "u": principal.user_id},
        )
    ).scalar_one()
    for position, (code, title, detail) in enumerate(ITEMS[template]):  # type: ignore[index]
        await session.execute(
            text(
                "insert into plan_items (tenant_id, plan_id, md_code, position, title, detail,"
                " created_by) values (:t, :p, :md, :pos, :title, :detail, :u)"
            ),
            {
                "t": tenant,
                "p": plan_id,
                "md": code,
                "pos": position,
                "title": title,
                "detail": detail,
                "u": principal.user_id,
            },
        )
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action="plan.create",
        entity="fixture_plans",
        entity_id=plan_id,
        after={"fixture_id": str(fixture_id), "template": template},
    )
    return plan_id, template, True


async def _add_recommendation_item(
    session: SessionDep,
    principal: PrincipalDep,
    plan_id: uuid.UUID,
    template: str,
    rec: RecommendationOut,
) -> None:
    exists = (
        await session.execute(
            text("select 1 from plan_items where plan_id = :p and recommendation_id = :r"),
            {"p": plan_id, "r": rec.id},
        )
    ).first()
    if exists:
        return
    md = ACCEPT_DAY[template][rec.area]  # type: ignore[index]
    position: int = (
        await session.execute(
            text("select coalesce(max(position), -1) + 1 from plan_items where plan_id = :p"),
            {"p": plan_id},
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into plan_items (tenant_id, plan_id, md_code, position, title, detail,"
            " recommendation_id, routine_id, created_by)"
            " values (:t, :p, :md, :pos, :title, :detail, :r, :routine, :u)"
        ),
        {
            "t": _tenant(principal),
            "p": plan_id,
            "md": md,
            "pos": position,
            "title": rec.title[:200],
            "detail": rec.action,
            "r": rec.id,
            "routine": rec.routine.id if rec.routine else None,
            "u": principal.user_id,
        },
    )


async def _accepted_into_plan(
    session: SessionDep, principal: PrincipalDep, plan_id: uuid.UUID, template: str, ev: Evaluation
) -> None:
    for rec in await merged_recommendations(session, ev, _tenant(principal)):
        if rec.status == "accepted":
            await _add_recommendation_item(session, principal, plan_id, template, rec)


@router.post(
    "/recommendations/{recommendation_id}/decision",
    response_model=RecommendationOut,
    operation_id="decideRecommendation",
    dependencies=decide,
)
async def decide_recommendation(
    session: SessionDep, principal: PrincipalDep, recommendation_id: uuid.UUID, body: DecisionIn
) -> RecommendationOut:
    """Kabul, gerekçeli red ya da geri alma (A-50). Kabul plana madde ekler (A-52)."""
    tenant = _tenant(principal)
    reason = (body.reason or "").strip() or None
    if body.decision == "rejected" and not reason:
        raise ProblemError(422, "reason-required", "A reason is required to reject")
    fixture = await load_fixture(session, body.fixture_id)
    ev = await evaluate_fixture(session, fixture)
    recs = {r.id: r for r in await merged_recommendations(session, ev, tenant)}
    current = recs.get(recommendation_id)
    if current is None:
        raise ProblemError(404, "not-found", "Recommendation not found for this fixture")
    live = next(
        (
            live_recommendation(ev, tenant, r)
            for r in ev.shown
            if recommendation_id_of(ev, tenant, r) == recommendation_id
        ),
        None,
    )
    # Kararı verilmiş öneride anlık görüntü korunur; yeni kararda güncel kanıt yazılır.
    snapshot = live if current.status == "suggested" and live else current
    before = {"status": current.status, "reason": current.reason}
    now = dt.datetime.now(dt.UTC)
    decided = body.decision != "suggested"
    await session.execute(
        text(
            """
insert into recommendations (id, tenant_id, fixture_id, rule_id, routine_id, rule_set_version,
  area, priority, confidence, title, why, action, template_id, evidence, status, reason,
  decided_by, decided_at)
values (:id, :tenant, :fixture, :rule, :routine, :version, :area, :priority, :confidence,
  :title, :why, :action, :template, cast(:evidence as jsonb), :status, :reason, :by, :at)
on conflict (id) do update set
  rule_set_version = excluded.rule_set_version, area = excluded.area,
  priority = excluded.priority, confidence = excluded.confidence, title = excluded.title,
  why = excluded.why, action = excluded.action, template_id = excluded.template_id,
  evidence = excluded.evidence, status = excluded.status, reason = excluded.reason,
  decided_by = excluded.decided_by, decided_at = excluded.decided_at, updated_at = now()
"""
        ),
        {
            "id": recommendation_id,
            "tenant": tenant,
            "fixture": fixture.id,
            "rule": snapshot.rule_id,
            "routine": snapshot.routine.id if snapshot.routine else None,
            "version": snapshot.rule_set_version,
            "area": snapshot.area,
            "priority": snapshot.priority,
            "confidence": snapshot.confidence,
            "title": snapshot.title,
            "why": snapshot.why,
            "action": snapshot.action,
            "template": snapshot.template.id if snapshot.template else None,
            "evidence": json.dumps([e.model_dump(mode="json") for e in snapshot.evidence]),
            "status": body.decision,
            "reason": reason if decided else None,
            "by": principal.user_id if decided else None,
            "at": now if decided else None,
        },
    )
    if body.decision == "accepted":
        plan_id, template, created = await _ensure_plan(session, principal, fixture.id, "standard")
        if created:
            await _accepted_into_plan(session, principal, plan_id, template, ev)
        else:
            accepted = snapshot.model_copy(update={"id": recommendation_id})
            await _add_recommendation_item(session, principal, plan_id, template, accepted)
    else:
        # Red ya da geri almada, henüz yapılmamış bağlı plan maddesi kalkar (A-52).
        await session.execute(
            text("delete from plan_items where recommendation_id = :r and status = 'todo'"),
            {"r": recommendation_id},
        )
    action = {"accepted": "accept", "rejected": "reject", "suggested": "undo"}[body.decision]
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action=f"recommendation.{action}",
        entity="recommendations",
        entity_id=recommendation_id,
        before=before,
        after={
            "status": body.decision,
            "reason": reason,
            "rule_id": snapshot.rule_id,
            "rule_set_version": snapshot.rule_set_version,
            "fixture_id": str(fixture.id),
        },
    )
    refreshed = {r.id: r for r in await merged_recommendations(session, ev, tenant)}
    result = refreshed.get(recommendation_id)
    if result is None:  # Geri alınan ve artık tetiklenmeyen öneri.
        return snapshot.model_copy(
            update={"status": "suggested", "reason": None, "decided_by": None, "decided_at": None}
        )
    return result


def recommendation_id_of(ev: Evaluation, tenant: uuid.UUID, result: Any) -> uuid.UUID:
    return recommendation_id(tenant, ev.fixture.id, result.rule.id, result.subject_key)


# --- Plan --------------------------------------------------------------------------------------


@router.post(
    "/fixtures/{fixture_id}/plan",
    response_model=PlanOut,
    status_code=201,
    operation_id="createFixturePlan",
    dependencies=mark,
)
async def create_plan(
    session: SessionDep, principal: PrincipalDep, fixture_id: uuid.UUID, body: PlanCreate
) -> PlanOut:
    """Şablondan MD planı (A-52). Plan zaten varsa 409. Kabul edilmiş öneriler eklenir."""
    fixture = await load_fixture(session, fixture_id)
    plan_id, template, created = await _ensure_plan(session, principal, fixture.id, body.template)
    if not created:
        raise ProblemError(409, "plan-exists", "This fixture already has a plan")
    ev = await evaluate_fixture(session, fixture)
    await _accepted_into_plan(session, principal, plan_id, template, ev)
    plan = await load_plan(session, fixture)
    assert plan is not None
    return plan


async def _check_assignee(session: SessionDep, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    if user_id not in {u.id for u in await assignees(session)}:
        raise ProblemError(422, "invalid-assignee", "Assignee cannot mark plan items")


async def _check_routine(session: SessionDep, routine_id: uuid.UUID | None) -> None:
    if routine_id is None:
        return
    if routine_id not in {r.id for r in await routine_refs(session)}:
        raise ProblemError(422, "invalid-routine", "Routine not found or archived")


@router.post(
    "/fixtures/{fixture_id}/plan/items",
    response_model=PlanOut,
    status_code=201,
    operation_id="addPlanItem",
    dependencies=mark,
)
async def add_plan_item(
    session: SessionDep, principal: PrincipalDep, fixture_id: uuid.UUID, body: PlanItemCreate
) -> PlanOut:
    fixture = await load_fixture(session, fixture_id)
    plan = (
        await session.execute(
            text("select id from fixture_plans where fixture_id = :f"), {"f": fixture.id}
        )
    ).one_or_none()
    if plan is None:
        raise ProblemError(409, "plan-missing", "Create a plan from a template first")
    await _check_assignee(session, body.assignee_id)
    await _check_routine(session, body.routine_id)
    item_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into plan_items (tenant_id, plan_id, md_code, position, title, detail,"
                " routine_id, assignee_id, created_by)"
                " values (:t, :p, :md,"
                " (select coalesce(max(position), -1) + 1 from plan_items where plan_id = :p),"
                " :title, :detail, :routine, :assignee, :u) returning id"
            ),
            {
                "t": _tenant(principal),
                "p": plan.id,
                "md": body.md_code,
                "title": body.title.strip(),
                "detail": body.detail.strip(),
                "routine": body.routine_id,
                "assignee": body.assignee_id,
                "u": principal.user_id,
            },
        )
    ).scalar_one()
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="plan_item.create",
        entity="plan_items",
        entity_id=item_id,
        after=body.model_dump(mode="json"),
    )
    out = await load_plan(session, fixture)
    assert out is not None
    return out


ITEM_SQL = """
select i.id, i.status, i.assignee_id, i.title, i.detail, i.md_code, p.fixture_id
from plan_items i join fixture_plans p on p.id = i.plan_id where i.id = :id
"""


@router.patch(
    "/plan-items/{item_id}",
    response_model=PlanOut,
    operation_id="updatePlanItem",
    dependencies=mark,
)
async def update_plan_item(
    session: SessionDep, principal: PrincipalDep, item_id: uuid.UUID, body: PlanItemPatch
) -> PlanOut:
    """Durum (tamamlandı / yapılacak), sorumlu, başlık, açıklama ya da gün."""
    row = (await session.execute(text(ITEM_SQL), {"id": item_id})).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Plan item not found")
    changes = body.model_dump(exclude_unset=True)
    if "assignee_id" in changes:
        await _check_assignee(session, changes["assignee_id"])
    sets: list[str] = []
    params: dict[str, Any] = {"id": item_id}
    for key in ("assignee_id", "title", "detail", "md_code"):
        if key in changes:
            if key in ("title", "md_code") and changes[key] is None:
                raise ProblemError(422, "invalid-field", f"{key} cannot be empty")
            value = changes[key].strip() if isinstance(changes[key], str) else changes[key]
            sets.append(f"{key} = :{key}")
            params[key] = value
    if changes.get("status") is not None and changes["status"] != row.status:
        done = changes["status"] == "done"
        sets += ["status = :status", "done_by = :done_by", "done_at = :done_at"]
        params |= {
            "status": changes["status"],
            "done_by": principal.user_id if done else None,
            "done_at": dt.datetime.now(dt.UTC) if done else None,
        }
    if sets:
        await session.execute(
            # Sütun adları yukarıdaki sabit listeden gelir.
            text(f"update plan_items set {', '.join(sets)}, updated_at = now() where id = :id"),  # noqa: S608
            params,
        )
        await write_audit(
            session,
            tenant_id=_tenant(principal),
            actor_id=principal.user_id,
            action="plan_item.update",
            entity="plan_items",
            entity_id=item_id,
            before={
                "status": row.status,
                "assignee_id": str(row.assignee_id) if row.assignee_id else None,
                "title": row.title,
                "md_code": row.md_code,
            },
            after={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in changes.items()},
        )
    fixture = await load_fixture(session, row.fixture_id)
    out = await load_plan(session, fixture)
    assert out is not None
    return out


@router.delete(
    "/plan-items/{item_id}",
    response_model=PlanOut,
    operation_id="deletePlanItem",
    dependencies=mark,
)
async def delete_plan_item(
    session: SessionDep, principal: PrincipalDep, item_id: uuid.UUID
) -> PlanOut:
    row = (await session.execute(text(ITEM_SQL), {"id": item_id})).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Plan item not found")
    await session.execute(text("delete from plan_items where id = :id"), {"id": item_id})
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="plan_item.delete",
        entity="plan_items",
        entity_id=item_id,
        before={"title": row.title, "md_code": row.md_code, "status": row.status},
        after={},
    )
    fixture = await load_fixture(session, row.fixture_id)
    out = await load_plan(session, fixture)
    assert out is not None
    return out


# --- Genel bakış -------------------------------------------------------------------------------


@router.get(
    "/prep/overview",
    response_model=OverviewRecsOut,
    operation_id="getPrepOverview",
    dependencies=read,
)
async def prep_overview(
    request: Request, session: SessionDep, principal: PrincipalDep, limit: int = 5
) -> Response:
    """Sezon önerileri ve yaklaşan maçların tehdit etiketleri (SPEC §13.1, A-38)."""
    rule_set = await current_rule_set(session)
    club = await club_team_id(session)
    upcoming_ids = (
        [
            r.id
            for r in await session.execute(
                text(UPCOMING_SQL), {"club": club, "limit": max(1, min(limit, 10))}
            )
        ]
        if club
        else []
    )
    season_recs: list[RecommendationOut] = []
    season = None
    upcoming: list[UpcomingThreats] = []
    cache = MetricsCache()
    for index, fixture_id in enumerate(upcoming_ids):
        fixture = await load_fixture(session, fixture_id)
        ev = await evaluate_fixture(session, fixture, rule_set, cache=cache)
        threats = [
            ThreatOut(rule_id=r.rule.id, title=r.title, confidence=r.confidence or "low")
            for r in ev.shown
            if r.rule.area == "defense"
        ][:2]
        upcoming.append(
            UpcomingThreats(fixture=fixture.out, threats=threats, recommendations=len(ev.shown))
        )
        if index == 0:
            season = fixture.out.season
            season_ev = await evaluate_fixture(
                session, fixture, rule_set, scope="season", cache=cache
            )
            season_recs = [
                live_recommendation(season_ev, _tenant(principal), r) for r in season_ev.shown
            ]
    return etag_response(
        request,
        OverviewRecsOut(
            season=season,
            rule_set=rule_set.ref,
            recommendations=season_recs,
            upcoming=upcoming,
        ),
    )


# --- Kural setleri -----------------------------------------------------------------------------


def _rule_set_out(rs: LoadedRuleSet) -> RuleSetOut:
    return RuleSetOut(
        version=rs.version,
        label=rs.label,
        is_default=rs.is_default,
        message=rs.message,
        published_at=rs.published_at,
        published_by=rs.published_by,
        rules=[r.model_dump(mode="json", by_alias=True, exclude_none=True) for r in rs.rules.rules],
    )


@router.get(
    "/rule-sets/current",
    response_model=RuleSetOut,
    operation_id="getCurrentRuleSet",
    dependencies=read,
)
async def get_current_rule_set(request: Request, session: SessionDep) -> Response:
    """Kulübün güncel kural seti; kulüp henüz değiştirmediyse varsayılan set (A-51)."""
    return etag_response(request, _rule_set_out(await current_rule_set(session)))


@router.put(
    "/rule-sets/current",
    response_model=RuleSetOut,
    operation_id="updateCurrentRuleSet",
    dependencies=rules_admin,
)
async def update_rule_set(
    session: SessionDep, principal: PrincipalDep, body: RuleSetUpdate
) -> RuleSetOut:
    """Yeni kulüp sürümü yayımlar. `base_version` güncel değilse 409; içerik aynıysa sürüm açmaz."""
    current = await current_rule_set(session)
    if body.base_version != current.version:
        raise ProblemError(
            409,
            "version-conflict",
            "The rule set changed since you loaded it",
            extra={"current_version": current.version},
        )
    parsed = parse_rules(body.rules)
    dumped = [r.model_dump(mode="json", by_alias=True, exclude_none=True) for r in parsed.rules]
    if dumped == _rule_set_out(current).rules:
        return _rule_set_out(current)
    tenant = _tenant(principal)
    version = current.version + 1  # varsayılan set 0; ilk kulüp sürümü 1 (A-51)
    rule_set_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into rule_sets (tenant_id, version, label, rules, message, published_by)"
                " values (:t, :v, :label, cast(:rules as jsonb), :message, :u) returning id"
            ),
            {
                "t": tenant,
                "v": version,
                "label": current.label,
                "rules": json.dumps({"rules": dumped}),
                "message": (body.message or "").strip() or None,
                "u": principal.user_id,
            },
        )
    ).scalar_one()
    before = {r["id"]: r for r in _rule_set_out(current).rules}
    changed = sorted(r["id"] for r in dumped if before.get(r["id"]) != r) + sorted(
        set(before) - {r["id"] for r in dumped}
    )
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action="rule_set.publish",
        entity="rule_sets",
        entity_id=rule_set_id,
        before={"version": current.version},
        after={"version": version, "changed_rules": changed, "message": body.message},
    )
    return _rule_set_out(await current_rule_set(session))


@router.get(
    "/rule-sets/versions",
    response_model=list[RuleSetVersionOut],
    operation_id="listRuleSetVersions",
    dependencies=read,
)
async def list_rule_set_versions(session: SessionDep) -> list[RuleSetVersionOut]:
    rows = await session.execute(
        text(
            "select rs.version, rs.label, rs.message, rs.published_at, rs.published_by,"
            " rs.tenant_id is null as is_default, u.display_name"
            " from rule_sets rs left join users u on u.id = rs.published_by"
            " order by rs.tenant_id is null, rs.version desc"
        )
    )
    return [
        RuleSetVersionOut(
            version=r.version,
            label=r.label,
            is_default=r.is_default,
            message=r.message,
            published_at=r.published_at,
            published_by=user_ref(r.published_by, r.display_name),
        )
        for r in rows
    ]


@router.post(
    "/rule-sets/dry-run",
    response_model=DryRunOut,
    operation_id="dryRunRuleSet",
    dependencies=rules_admin,
)
async def dry_run(session: SessionDep, body: DryRunIn) -> DryRunOut:
    """Bir fikstürde hangi kuralların tetiklendiği ve nedeni; taslak setle de çalışır, kaydetmez."""
    fixture = await load_fixture(session, body.fixture_id)
    current = await current_rule_set(session)
    rule_set = (
        dataclasses.replace(current, raw=body.rules, rules=parse_rules(body.rules))
        if body.rules is not None
        else current
    )
    results: list[DryRunRule] = []
    for scope in ("fixture", "season"):
        ev = await evaluate_fixture(session, fixture, rule_set, include_disabled=True, scope=scope)
        shown = {(r.rule.id, r.subject_key) for r in ev.shown}
        by_rule: dict[str, list[Any]] = {}
        for r in ev.results:
            by_rule.setdefault(r.rule.id, []).append(r)
        for rule_id, group in by_rule.items():
            fired = [r for r in group if r.fired]
            # Rutin kurallarında tetiklenen her rutin; hiçbiri tetiklenmediyse tek satır.
            for r in fired or group[:1]:
                results.append(
                    DryRunRule(
                        rule_id=rule_id,
                        scope=r.rule.scope,
                        area=r.rule.area,
                        priority=r.rule.priority,
                        enabled=r.rule.enabled,
                        status=r.status,
                        shown=(rule_id, r.subject_key) in shown,
                        confidence=r.confidence,
                        strength=round(r.strength, 3),
                        title=r.title,
                        why=r.why,
                        routine=(
                            RoutineRef(id=uuid.UUID(r.subject_key), name=ev.routines[r.subject_key])
                            if fired and r.subject_key in ev.routines
                            else None
                        ),
                        conditions=[
                            ConditionOut(
                                subject=c.subject,
                                metric=c.metric,
                                op=c.op,
                                threshold=c.threshold,
                                value=c.value,
                                rank=c.rank,
                                teams=c.teams,
                                passed=c.passed,
                            )
                            for c in r.conditions
                        ],
                    )
                )
    return DryRunOut(fixture=fixture.out, results=results)
