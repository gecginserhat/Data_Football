"""Brifing üretimi: girdi, deneme ve doğrulama, kayıt, kiracı sınırları (ADR-0013, A-73 … A-76)."""

import datetime as dt
import json
import logging
import time
import uuid
from typing import Any, Literal

from kurgu_analytics.reports.briefing import RETRY_NOTE, SYSTEM_PROMPT, briefing_input
from kurgu_analytics.reports.numbers import allowed_keys, extract, verify
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.problems import ProblemError
from kurgu_api.llm.client import LlmClient, LlmError
from kurgu_api.llm.schemas import BriefingOut, LlmSettings, LlmUsage
from kurgu_api.prep.facts import FixtureInfo
from kurgu_api.prep.service import load_plan
from kurgu_api.reports import data

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 2

SETTINGS_SQL = "select settings -> 'llm' as llm from tenants where id = kurgu_current_tenant()"
USAGE_SQL = """
select count(*) as requests, coalesce(sum(input_tokens + output_tokens), 0) as tokens
from llm_runs where created_at >= :start
"""
RUN_SQL = """
insert into llm_runs (tenant_id, kind, fixture_id, attempt, model, status, input, output,
  unmatched, error, input_tokens, output_tokens, duration_ms, created_by)
values (:t, 'briefing', :f, :attempt, :model, :status, cast(:input as jsonb), :output,
  cast(:unmatched as jsonb), :error, :in_t, :out_t, :ms, :u)
returning created_at
"""
LATEST_SQL = """
select output, model, created_at from llm_runs
where fixture_id = :f and kind = 'briefing' and status = 'verified'
order by created_at desc limit 1
"""


def month_start(now: dt.datetime | None = None) -> dt.date:
    now = now or dt.datetime.now(dt.UTC)
    return now.date().replace(day=1)


async def tenant_settings(session: AsyncSession) -> LlmSettings:
    raw = (await session.execute(text(SETTINGS_SQL))).scalar_one_or_none()
    if isinstance(raw, str):
        raw = json.loads(raw)
    return LlmSettings.model_validate(raw or {})


async def usage(session: AsyncSession) -> LlmUsage:
    start = month_start()
    row = (
        await session.execute(
            text(USAGE_SQL), {"start": dt.datetime.combine(start, dt.time(), dt.UTC)}
        )
    ).one()
    return LlmUsage(period_start=start, requests=row.requests, tokens=int(row.tokens))


def within_budget(settings: LlmSettings, used: LlmUsage) -> bool:
    return used.requests < settings.monthly_requests and used.tokens < settings.monthly_tokens


async def check_allowed(session: AsyncSession) -> LlmSettings:
    settings = await tenant_settings(session)
    if not settings.enabled:
        raise ProblemError(403, "llm-disabled", "The briefing feature is turned off for this club")
    if not within_budget(settings, await usage(session)):
        raise ProblemError(429, "llm-budget-exceeded", "Monthly LLM limit reached")
    return settings


async def plan_summary(session: AsyncSession, fixture: FixtureInfo) -> dict[str, Any] | None:
    plan = await load_plan(session, fixture)
    if plan is None:
        return None
    return {
        "done": plan.done,
        "total": plan.total,
        "days": [
            {
                "md": d.md_code,
                "focus": d.focus,
                "items": [i.title for i in plan.items if i.md_code == d.md_code],
            }
            for d in plan.days
        ],
    }


async def build_input(
    session: AsyncSession, fixture: FixtureInfo, tenant_id: uuid.UUID
) -> dict[str, Any]:
    report = await data.opponent_report(session, fixture.id, tenant_id, None)
    return briefing_input(report, await plan_summary(session, fixture))


async def generate(
    session: AsyncSession,
    client: LlmClient,
    fixture: FixtureInfo,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> BriefingOut:
    """En çok iki deneme; her deneme `llm_runs`'a yazılır. Doğrulanmayan metin döndürülmez."""
    settings = await check_allowed(session)
    payload = await build_input(session, fixture, tenant_id)
    allowed = allowed_keys(payload)
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    message = body
    reason: Literal["unverified", "error"] = "unverified"
    made = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1 and not within_budget(settings, await usage(session)):
            break
        made = attempt
        started = time.monotonic()
        row: dict[str, Any] = {
            "t": tenant_id,
            "f": fixture.id,
            "attempt": attempt,
            "model": client.model,
            "input": body,
            "u": user_id,
            "output": None,
            "unmatched": "[]",
            "error": None,
            "in_t": 0,
            "out_t": 0,
        }
        try:
            completion = await client.complete(SYSTEM_PROMPT, message)
        except LlmError as exc:
            log.warning("briefing attempt %s failed: %s", attempt, exc)
            row |= {"status": "error", "error": str(exc)[:2000]}
            row["ms"] = int((time.monotonic() - started) * 1000)
            await session.execute(text(RUN_SQL), row)
            reason = "error"
            break
        check = verify(completion.text, payload, allowed)
        row |= {
            "status": "verified" if check.ok else "rejected",
            "output": completion.text,
            "unmatched": json.dumps(list(check.unmatched), ensure_ascii=False),
            "in_t": completion.input_tokens,
            "out_t": completion.output_tokens,
            "ms": int((time.monotonic() - started) * 1000),
        }
        created_at: dt.datetime = (await session.execute(text(RUN_SQL), row)).scalar_one()
        if check.ok:
            return BriefingOut(
                fixture_id=fixture.id,
                status="verified",
                text=completion.text,
                model=client.model,
                numbers=len(check.numbers),
                attempts=attempt,
                created_at=created_at,
            )
        reason = "unverified"
        message = RETRY_NOTE.format(numbers=", ".join(check.unmatched)) + "\n\n" + body
    return BriefingOut(
        fixture_id=fixture.id,
        status="failed",
        reason=reason,
        model=client.model,
        attempts=made,
    )


async def latest(session: AsyncSession, fixture_id: uuid.UUID) -> BriefingOut:
    row = (await session.execute(text(LATEST_SQL), {"f": fixture_id})).one_or_none()
    if row is None:
        return BriefingOut(fixture_id=fixture_id, status="none")
    return BriefingOut(
        fixture_id=fixture_id,
        status="verified",
        text=row.output,
        model=row.model,
        numbers=len(extract(row.output)),
        created_at=row.created_at,
    )


async def save_settings(session: AsyncSession, settings: LlmSettings) -> None:
    await session.execute(
        text(
            "update tenants set settings = jsonb_set(settings, '{llm}', cast(:v as jsonb))"
            " where id = kurgu_current_tenant()"
        ),
        {"v": settings.model_dump_json()},
    )
