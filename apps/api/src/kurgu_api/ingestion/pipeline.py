"""Sağlayıcı yükleme hattı: ham yük → kanonik → kalite → yazım (SPEC §5.2, §5.6).

Her maç kendi işleminde yazılır; bir maçın hatası öncekileri geri almaz. Kritik kalite
bulgusu olan maç yazılmaz ve iş sonunda `quarantined` olur. Aynı ham yük (aynı `source_hash`)
daha önce işlenmişse maç atlanır; `params.reprocess` verilirse (ör. çıkarım algoritması
değiştiğinde) kanonik olaylar ve diziler yeniden yazılır.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from kurgu_analytics.canonical.model import CanonicalMatch
from kurgu_analytics.canonical.quality import check_match, report
from kurgu_analytics.ingestion.base import Provider
from kurgu_analytics.ingestion.statsbomb import StatsBombOpenData
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kurgu_api.config import get_settings
from kurgu_api.ingestion.runs import RunStatus, store_raw, transition
from kurgu_api.ingestion.setpieces import write_set_pieces
from kurgu_api.ingestion.storage import ObjectStore
from kurgu_api.ingestion.writer import write_canonical
from kurgu_api.league.views import refresh_metric_views

ProviderFactory = Callable[[], Provider]


def _statsbomb() -> Provider:
    settings = get_settings()
    # Geliştirme dışında internetten indirme yapılmaz; önbellek `make statsbomb-fetch` ile dolar.
    return StatsBombOpenData(
        Path(settings.kurgu_statsbomb_dir),
        allow_download=settings.kurgu_env in {"development", "test"},
    )


PROVIDERS: dict[str, ProviderFactory] = {"statsbomb_open": _statsbomb}

# Maç yazıldıktan sonra aynı işlemde çalışan adımlar: duran top çıkarımı (Faz 1.7).
PostWriteHook = Callable[[AsyncConnection, str, CanonicalMatch, dict[str, Any]], Awaitable[Any]]
POST_WRITE_HOOKS: list[PostWriteHook] = [write_set_pieces]


async def _context(conn: AsyncConnection, tenant_id: uuid.UUID | None) -> None:
    await conn.execute(
        text("select set_config('app.tenant_id', :t, true), set_config('app.user_id', '', true)"),
        {"t": str(tenant_id) if tenant_id else ""},
    )


async def _already_loaded(conn: AsyncConnection, raw_id: uuid.UUID) -> bool:
    found = await conn.execute(
        text("select 1 from events where raw_ref = :r limit 1"), {"r": raw_id}
    )
    return found.first() is not None


async def run_ingestion(
    engine: AsyncEngine,
    store: ObjectStore,
    run_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID | None,
    provider: Provider,
    params: dict[str, Any],
) -> dict[str, Any]:
    stats: dict[str, Any] = {"matches": 0, "loaded": 0, "skipped": 0, "quarantined": 0}
    quality: dict[str, Any] = {}
    async with engine.begin() as conn:
        await _context(conn, tenant_id)
        await transition(conn, run_id, "running")
    try:
        matches = await asyncio.to_thread(provider.list_matches, params)
        stats["matches"] = len(matches)
        for match in matches:
            raw = await asyncio.to_thread(provider.fetch_events, match)
            async with engine.begin() as conn:
                # Ham ve kanonik lig verisi paylaşılır (tenant_id boş); iş kaydı kiracınındır.
                await _context(conn, None)
                raw_id, new = await store_raw(
                    conn,
                    store,
                    tenant_id=None,
                    provider=provider.name,
                    kind=raw.kind,
                    content=raw.content,
                    source_hash=raw.source_hash,
                    content_type=raw.content_type,
                    run_id=run_id,
                )
                reprocess = bool(params.get("reprocess"))
                if not new and not reprocess and await _already_loaded(conn, raw_id):
                    stats["skipped"] += 1
                    continue
                cm = await asyncio.to_thread(provider.to_canonical, match, raw)
                issues = check_match(cm)
                if any(i.severity == "critical" for i in issues) or any(
                    i.severity == "warning" for i in issues
                ):
                    quality[match.provider_id] = report(issues)
                if any(i.severity == "critical" for i in issues):
                    stats["quarantined"] += 1
                    continue
                written = await write_canonical(conn, provider.name, cm, raw_id)
                for hook in POST_WRITE_HOOKS:
                    await hook(conn, provider.name, cm, written)
                stats["loaded"] += 1
    except Exception as exc:
        async with engine.begin() as conn:
            await _context(conn, tenant_id)
            await transition(conn, run_id, "failed", stats=stats, error=str(exc)[:2000])
        raise
    final: RunStatus = "quarantined" if stats["quarantined"] else "succeeded"
    async with engine.begin() as conn:
        if stats["loaded"]:
            await refresh_metric_views(conn)
        await _context(conn, tenant_id)
        await transition(conn, run_id, final, stats=stats, quality_report=quality)
    return stats
