"""Yükleme işi kayıtları (`ingestion_runs`) ve durum makinesi (SPEC §5.2, §5.6).

Durumlar: `pending → running → succeeded | quarantined | failed`. Karantinadaki bir iş
düzeltilmiş veriyle yeniden kuyruğa alınabilir (`quarantined → pending`); başarısız iş de
yeniden denenebilir (`failed → pending`). Başka geçiş yoktur.
"""

import json
import uuid
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from kurgu_api.ingestion.storage import ObjectStore

RunStatus = Literal["pending", "running", "succeeded", "quarantined", "failed"]

TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    "pending": frozenset({"running", "failed"}),
    "running": frozenset({"succeeded", "quarantined", "failed"}),
    "quarantined": frozenset({"pending"}),
    "failed": frozenset({"pending"}),
    "succeeded": frozenset(),
}


class InvalidTransitionError(ValueError):
    pass


def check_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise InvalidTransitionError(f"{current} → {target} geçişi yok")


Conn = AsyncConnection | AsyncSession


async def create_run(
    conn: Conn,
    *,
    tenant_id: uuid.UUID | None,
    provider: str,
    kind: str,
    params: dict[str, Any],
    created_by: uuid.UUID | None = None,
) -> uuid.UUID:
    run_id: uuid.UUID = (
        await conn.execute(
            text(
                "insert into ingestion_runs (tenant_id, provider, kind, params, created_by)"
                " values (:tenant, :provider, :kind, cast(:params as jsonb), :by) returning id"
            ),
            {
                "tenant": tenant_id,
                "provider": provider,
                "kind": kind,
                "params": json.dumps(params),
                "by": created_by,
            },
        )
    ).scalar_one()
    return run_id


async def transition(
    conn: Conn,
    run_id: uuid.UUID,
    target: RunStatus,
    *,
    stats: dict[str, Any] | None = None,
    quality_report: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Durumu değiştirir; geçersiz geçişte `InvalidTransitionError`. Satır kilitlenir."""
    current: RunStatus = (
        await conn.execute(
            text("select status from ingestion_runs where id = :id for update"), {"id": run_id}
        )
    ).scalar_one()
    check_transition(current, target)
    await conn.execute(
        text(
            """
            update ingestion_runs set
              status = cast(:target as varchar),
              stats = coalesce(cast(:stats as jsonb), stats),
              quality_report = coalesce(cast(:quality as jsonb), quality_report),
              error = :error,
              started_at = case when cast(:target as varchar) = 'running'
                                then now() else started_at end,
              finished_at = case
                when cast(:target as varchar) in ('succeeded', 'quarantined', 'failed')
                then now() else null end
            where id = :id
            """
        ),
        {
            "id": run_id,
            "target": target,
            "stats": json.dumps(stats) if stats is not None else None,
            "quality": json.dumps(quality_report) if quality_report is not None else None,
            "error": error,
        },
    )


async def store_raw(
    conn: Conn,
    store: ObjectStore,
    *,
    tenant_id: uuid.UUID | None,
    provider: str,
    kind: str,
    content: bytes,
    source_hash: str,
    content_type: str,
    run_id: uuid.UUID | None,
) -> tuple[uuid.UUID, bool]:
    """Ham yükü depoya ve `raw_payloads` tablosuna yazar. Döner: (kimlik, yeni mi).

    Aynı `source_hash` daha önce yüklendiyse var olan kayıt döner ve hiçbir şey yazılmaz.
    """
    owner = str(tenant_id) if tenant_id else "shared"
    key = f"raw/{owner}/{provider}/{source_hash}"
    await store.put(key, content, content_type)
    inserted = (
        await conn.execute(
            text(
                "insert into raw_payloads (tenant_id, provider, kind, source_hash, storage_key,"
                " content_type, size_bytes, ingestion_run_id) values (:tenant, :provider, :kind,"
                " :hash, :key, :ctype, :size, :run)"
                " on conflict on constraint uq_raw_payloads_source do nothing returning id"
            ),
            {
                "tenant": tenant_id,
                "provider": provider,
                "kind": kind,
                "hash": source_hash,
                "key": key,
                "ctype": content_type,
                "size": len(content),
                "run": run_id,
            },
        )
    ).scalar_one_or_none()
    if inserted is not None:
        return inserted, True
    existing: uuid.UUID = (
        await conn.execute(
            text(
                "select id from raw_payloads where tenant_id is not distinct from :tenant"
                " and provider = :provider and source_hash = :hash"
            ),
            {"tenant": tenant_id, "provider": provider, "hash": source_hash},
        )
    ).scalar_one()
    return existing, False
