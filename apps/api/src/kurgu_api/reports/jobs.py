"""Worker işi: rapor verisini toplar, HTML'i ve PDF'i üretir, depoya yükler (ADR-0012, A-71)."""

import datetime as dt
import json
import logging
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from kurgu_analytics.reports.documents import MatchPlanReport, OpponentReport
from kurgu_analytics.reports.render import (
    footer_html,
    render_match_plan_html,
    render_opponent_html,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.db import get_sessionmaker, set_request_context
from kurgu_api.reports import data
from kurgu_api.reports.pdf import page_count, render_pdf
from kurgu_api.video.storage import VideoStore, get_video_store

log = logging.getLogger(__name__)
Renderer = Callable[[str, str], Awaitable[bytes]]


def storage_key(tenant_id: str, report_id: str) -> str:
    return f"reports/{tenant_id}/{report_id}.pdf"


async def _set(session: AsyncSession, report_id: str, **fields: Any) -> None:
    columns = ", ".join(f"{k} = :{k}" for k in fields)
    await session.execute(
        text(f"update reports set {columns} where id = :id"),  # noqa: S608
        {"id": report_id, **fields},
    )


async def _step(tenant_id: str, report_id: str, **fields: Any) -> None:
    """Durum güncellemesi kendi işleminde yazılır; arayüz ilerlemeyi hemen görür."""
    async with get_sessionmaker()() as session, session.begin():
        await set_request_context(session, user_id=None, tenant_id=uuid.UUID(tenant_id))
        await _set(session, report_id, **fields)


def _as_of(report: OpponentReport | MatchPlanReport) -> dict[str, Any]:
    meta = report.meta
    return {
        "season": meta.season,
        "profile_season": meta.profile_season,
        "week": meta.data_week,
        "sources": meta.sources,
    }


async def run_report(
    report_id: str,
    tenant_id: str,
    store: VideoStore | None = None,
    renderer: Renderer = render_pdf,
) -> str:
    """Raporu üretir. Sonuç durumu döner (`ready`/`failed`; kayıt yoksa `missing`)."""
    store = store or get_video_store()
    tenant = uuid.UUID(tenant_id)
    async with get_sessionmaker()() as session, session.begin():
        await set_request_context(session, user_id=None, tenant_id=tenant)
        row = (
            await session.execute(
                text("select type, fixture_id, status, created_by from reports where id = :id"),
                {"id": report_id},
            )
        ).one_or_none()
        if row is None or row.status not in {"queued", "running"}:
            return row.status if row else "missing"
        await _set(
            session, report_id, status="running", progress=10, started_at=dt.datetime.now(dt.UTC)
        )
    started = time.monotonic()
    try:
        async with get_sessionmaker()() as session, session.begin():
            await set_request_context(session, user_id=row.created_by, tenant_id=tenant)
            document: OpponentReport | MatchPlanReport
            if row.type == "opponent":
                document = await data.opponent_report(
                    session, row.fixture_id, tenant, row.created_by
                )
                html = render_opponent_html(document)
            else:
                document = await data.match_plan_report(
                    session, row.fixture_id, tenant, row.created_by
                )
                html = render_match_plan_html(document)
        await _step(tenant_id, report_id, progress=50)
        pdf = await renderer(html, footer_html(document))
        await _step(tenant_id, report_id, progress=85)
        key = storage_key(tenant_id, report_id)
        with tempfile.TemporaryDirectory(prefix="kurgu-report-") as tmp:
            path = Path(tmp) / "report.pdf"
            path.write_bytes(pdf)
            await store.upload_file(key, path, "application/pdf")
    except Exception as exc:
        log.warning("report %s failed", report_id, exc_info=True)
        await _step(
            tenant_id,
            report_id,
            status="failed",
            error=str(exc)[-2000:] or type(exc).__name__,
            finished_at=dt.datetime.now(dt.UTC),
        )
        return "failed"
    async with get_sessionmaker()() as session, session.begin():
        await set_request_context(session, user_id=None, tenant_id=tenant)
        await session.execute(
            text(
                "update reports set status = 'ready', progress = 100, storage_key = :key,"
                " size_bytes = :size, pages = :pages, error = null,"
                " data_as_of = cast(:as_of as jsonb), finished_at = now(),"
                " duration_ms = (extract(epoch from (now() - created_at)) * 1000)::int"
                " where id = :id"
            ),
            {
                "id": report_id,
                "key": key,
                "size": len(pdf),
                "pages": page_count(pdf),
                "as_of": json.dumps(_as_of(document)),
            },
        )
    log.info("report %s ready in %.1fs", report_id, time.monotonic() - started)
    return "ready"


async def generate_report_job(ctx: dict[str, Any], report_id: str, tenant_id: str) -> str:
    uuid.UUID(report_id)
    return await run_report(report_id, tenant_id)
