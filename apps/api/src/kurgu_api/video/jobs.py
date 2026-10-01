"""Worker işi: videoyu HLS'ye çevirir ve varlığın durumunu günceller (ADR-0010, A-61)."""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kurgu_api.core.db import get_engine
from kurgu_api.video.hls import PLAYLIST, transcode
from kurgu_api.video.storage import VideoStore, get_video_store

log = logging.getLogger(__name__)


async def _context(conn: AsyncConnection, tenant_id: str) -> None:
    await conn.execute(
        text("select set_config('app.tenant_id', :t, true), set_config('app.user_id', '', true)"),
        {"t": tenant_id},
    )


async def _set(conn: AsyncConnection, asset_id: str, **fields: Any) -> None:
    columns = ", ".join(f"{k} = :{k}" for k in fields)
    await conn.execute(
        text(f"update video_assets set {columns}, updated_at = now() where id = :id"),  # noqa: S608
        {"id": asset_id, **fields},
    )


async def run_transcode(asset_id: str, tenant_id: str, store: VideoStore | None = None) -> str:
    """Kaynağı indirir, dönüştürür, parçaları yükler. Sonuç durumu döner (`ready`/`failed`)."""
    store = store or get_video_store()
    engine = get_engine()
    async with engine.begin() as conn:
        await _context(conn, tenant_id)
        row = (
            await conn.execute(
                text("select storage_key, status from video_assets where id = :id"),
                {"id": asset_id},
            )
        ).one_or_none()
    if row is None or row.status != "processing":
        return row.status if row else "missing"
    prefix = row.storage_key.rsplit("/", 1)[0] + "/hls"
    try:
        with tempfile.TemporaryDirectory(prefix="kurgu-hls-") as tmp:
            work = Path(tmp)
            source = work / "source"
            await store.download(row.storage_key, source)
            out = work / "hls"
            duration = await transcode(source, out)
            for path in sorted(out.iterdir()):
                kind = "application/vnd.apple.mpegurl" if path.name == PLAYLIST else "video/mp2t"
                await store.upload_file(f"{prefix}/{path.name}", path, kind)
    except Exception as exc:
        log.warning("transcode failed for %s", asset_id, exc_info=True)
        async with engine.begin() as conn:
            await _context(conn, tenant_id)
            await _set(conn, asset_id, status="failed", error=str(exc)[-2000:])
        return "failed"
    async with engine.begin() as conn:
        await _context(conn, tenant_id)
        await _set(
            conn,
            asset_id,
            status="ready",
            error=None,
            duration_s=duration,
            hls_key=f"{prefix}/{PLAYLIST}",
        )
    return "ready"


async def transcode_video_job(ctx: dict[str, Any], asset_id: str, tenant_id: str) -> str:
    uuid.UUID(asset_id)
    return await run_transcode(asset_id, tenant_id)
