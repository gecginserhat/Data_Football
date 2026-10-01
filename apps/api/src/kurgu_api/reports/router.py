"""Rapor uçları (SPEC §14, ADR-0012, A-68 … A-71).

Rapor isteği kayıt açar ve worker işini kuyruğa koyar (202). Arayüz durumu sorgulayarak ilerlemeyi
gösterir; hazır raporun dosyası kısa ömürlü imzalı adresle indirilir.
"""

import logging
import uuid
from typing import Annotated, Any

from arq import ArqRedis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.audit import write_audit
from kurgu_api.core.problems import ProblemError
from kurgu_api.core.ratelimit import REPORTS, rate_limit
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.ingestion.router import get_queue
from kurgu_api.prep.facts import load_fixture
from kurgu_api.reports.schemas import ReportCreate, ReportFixture, ReportOut
from kurgu_api.routines.schemas import UserRef
from kurgu_api.video.storage import VideoStore, get_video_store

log = logging.getLogger(__name__)
router = APIRouter(tags=["reports"])

READ = [Depends(require(Permission.READ_ANALYSIS))]
StoreDep = Annotated[VideoStore, Depends(get_video_store)]

REPORT_SQL = """
select r.id, r.type, r.fixture_id, r.status, r.progress, r.size_bytes, r.pages, r.error,
  r.data_as_of, r.created_at, r.finished_at, r.duration_ms, r.storage_key, r.created_by,
  u.display_name as created_by_name, m.week, m.kickoff_at, h.code as home_code,
  a.code as away_code
from reports r
join matches m on m.id = r.fixture_id
join teams h on h.id = m.home_team_id
join teams a on a.id = m.away_team_id
left join users u on u.id = r.created_by
"""


def _out(row: Any, store: VideoStore | None = None) -> ReportOut:
    url = store.read_url(row.storage_key) if store and row.status == "ready" else None
    return ReportOut(
        id=row.id,
        type=row.type,
        fixture=ReportFixture(
            id=row.fixture_id,
            week=row.week,
            kickoff_at=row.kickoff_at,
            home_code=row.home_code,
            away_code=row.away_code,
        ),
        status=row.status,
        progress=row.progress,
        size_bytes=row.size_bytes,
        pages=row.pages,
        error=row.error,
        data_as_of=row.data_as_of,
        created_at=row.created_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        created_by=UserRef(id=row.created_by, name=row.created_by_name) if row.created_by else None,
        download_url=url,
    )


async def _report(session: AsyncSession, report_id: uuid.UUID) -> Any:
    row = (
        await session.execute(text(REPORT_SQL + " where r.id = :id"), {"id": report_id})
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Report not found")
    return row


@router.post(
    "/reports",
    response_model=ReportOut,
    status_code=202,
    operation_id="createReport",
    dependencies=[*READ, Depends(rate_limit(REPORTS))],
)
async def create_report(
    session: SessionDep,
    principal: PrincipalDep,
    queue: Annotated[ArqRedis, Depends(get_queue)],
    body: ReportCreate,
) -> ReportOut:
    """Rapor üretimini başlatır (A-68). Fikstür kulübün maçı olmalıdır."""
    assert principal.tenant is not None
    tenant = principal.tenant.tenant_id
    await load_fixture(session, body.fixture_id)
    report_id = uuid.uuid4()
    await session.execute(
        text(
            "insert into reports (id, tenant_id, type, fixture_id, created_by)"
            " values (:id, :t, :type, :f, :u)"
        ),
        {
            "id": report_id,
            "t": tenant,
            "type": body.type,
            "f": body.fixture_id,
            "u": principal.user_id,
        },
    )
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action="report.requested",
        entity="reports",
        entity_id=report_id,
        after=body.model_dump(mode="json"),
    )
    result = _out(await _report(session, report_id))
    await session.commit()
    try:
        await queue.enqueue_job("generate_report_job", str(report_id), str(tenant))
    except Exception:
        log.warning("report could not be queued: %s", report_id, exc_info=True)
    return result


@router.get(
    "/reports",
    response_model=list[ReportOut],
    operation_id="listReports",
    dependencies=READ,
)
async def list_reports(
    session: SessionDep,
    store: StoreDep,
    fixture_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReportOut]:
    where = " where r.fixture_id = :f" if fixture_id else ""
    rows = await session.execute(
        text(REPORT_SQL + where + " order by r.created_at desc, r.id limit :limit"),
        {"f": fixture_id, "limit": limit},
    )
    return [_out(r, store) for r in rows]


@router.get(
    "/reports/{report_id}",
    response_model=ReportOut,
    operation_id="getReport",
    dependencies=READ,
)
async def get_report(session: SessionDep, store: StoreDep, report_id: uuid.UUID) -> ReportOut:
    """Durum ve ilerleme; hazırsa 10 dakika geçerli indirme adresi (A-70)."""
    return _out(await _report(session, report_id), store)
