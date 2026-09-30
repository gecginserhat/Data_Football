"""Yükleme işi uçları: başlat, listele, durum (SPEC §5.2, §11 `/admin/data-sources`).

İş kaydı isteyen kiracıya aittir; yazılan lig verisi paylaşılır ve lisansla okunur.
"""

import uuid
from typing import Annotated, Any, Literal

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from kurgu_api.config import get_settings
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.ingestion.runs import create_run

router = APIRouter(tags=["ingestion"], dependencies=[Depends(require(Permission.USER_ADMIN_AUDIT))])


class StatsBombParams(BaseModel):
    competition_id: int
    season_id: int
    limit: int | None = Field(default=None, ge=1, le=500)
    reprocess: bool | None = None


class IngestionRunCreate(BaseModel):
    provider: Literal["statsbomb_open"]
    params: StatsBombParams


class IngestionRunOut(BaseModel):
    id: uuid.UUID
    provider: str
    kind: str
    status: str
    params: dict[str, Any]
    stats: dict[str, Any]
    quality_report: dict[str, Any] | None
    error: str | None


async def get_queue(request: Request) -> ArqRedis:
    """Uygulama başına tek arq bağlantısı (ilk kullanımda açılır)."""
    pool: ArqRedis | None = getattr(request.app.state, "arq", None)
    if pool is None:
        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        request.app.state.arq = pool
    return pool


RUN_COLUMNS = "id, provider, kind, status, params, stats, quality_report, error"


@router.post(
    "/ingestion-runs",
    response_model=IngestionRunOut,
    status_code=202,
    operation_id="createIngestionRun",
)
async def create_ingestion_run(
    body: IngestionRunCreate,
    session: SessionDep,
    principal: PrincipalDep,
    queue: Annotated[ArqRedis, Depends(get_queue)],
) -> IngestionRunOut:
    assert principal.tenant is not None
    params = body.params.model_dump(exclude_none=True)
    run_id = await create_run(
        session,
        tenant_id=principal.tenant.tenant_id,
        provider=body.provider,
        kind="events",
        params=params,
        created_by=principal.user_id,
    )
    row = (
        await session.execute(
            text(f"select {RUN_COLUMNS} from ingestion_runs where id = :id"),  # noqa: S608
            {"id": run_id},
        )
    ).one()
    # İş, kayıt işlemi tamamlandıktan sonra görünür olsun diye commit edilir.
    await session.commit()
    await queue.enqueue_job(
        "run_ingestion_job", str(run_id), str(principal.tenant.tenant_id), body.provider, params
    )
    return IngestionRunOut.model_validate(row._asdict())


@router.get(
    "/ingestion-runs/{run_id}", response_model=IngestionRunOut, operation_id="getIngestionRun"
)
async def get_ingestion_run(run_id: uuid.UUID, session: SessionDep) -> IngestionRunOut:
    row = (
        await session.execute(
            text(f"select {RUN_COLUMNS} from ingestion_runs where id = :id"),  # noqa: S608
            {"id": run_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "Ingestion run not found")
    return IngestionRunOut.model_validate(row._asdict())


@router.get(
    "/ingestion-runs", response_model=list[IngestionRunOut], operation_id="listIngestionRuns"
)
async def list_ingestion_runs(session: SessionDep) -> list[IngestionRunOut]:
    rows = (
        await session.execute(
            text(
                f"select {RUN_COLUMNS} from ingestion_runs"  # noqa: S608
                " order by created_at desc limit 50"
            )
        )
    ).all()
    return [IngestionRunOut.model_validate(r._asdict()) for r in rows]
