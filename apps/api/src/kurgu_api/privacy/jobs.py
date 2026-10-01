"""Gecelik saklama görevi (SPEC §12.3, ADR-0019, A-92).

Her kiracı için ayarlı süreleri aşan iyi oluş, yük ve denetim kayıtlarını siler; silme sayısını
denetim kaydına yazar. Worker rolü kiracıları yalnız okuyabilir (`worker_list` politikası).
"""

import datetime as dt
import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kurgu_api.core.db import get_engine
from kurgu_api.privacy.schemas import Retention

log = logging.getLogger(__name__)


async def purge_tenant(
    conn: AsyncConnection, tenant_id: uuid.UUID, retention: Retention, today: dt.date
) -> dict[str, int]:
    await conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    wellness_cutoff = today - dt.timedelta(days=retention.wellness_days)
    loads_cutoff = today - dt.timedelta(days=retention.loads_days)
    audit_cutoff = dt.datetime.combine(
        today - dt.timedelta(days=retention.audit_days), dt.time(), dt.UTC
    )

    async def count(sql: str, params: dict[str, Any]) -> int:
        result = await conn.execute(text(sql), params)
        return int(getattr(result, "rowcount", 0) or 0)

    removed = {
        "wellness": await count(
            "delete from wellness_entries where date < :d", {"d": wellness_cutoff}
        ),
        "loads": await count(
            "delete from session_loads where session_id in"
            " (select id from training_sessions where date < :d)",
            {"d": loads_cutoff},
        ),
        "sessions": await count(
            "delete from training_sessions where date < :d", {"d": loads_cutoff}
        ),
        "audit": int(
            (
                await conn.execute(
                    text("select kurgu_purge_audit(:t, :before)"),
                    {"t": tenant_id, "before": audit_cutoff},
                )
            ).scalar_one()
        ),
    }
    await conn.execute(
        text(
            "insert into audit_log (tenant_id, actor_id, action, entity, entity_id, after)"
            " values (:t, null, 'privacy.retention_run', 'tenants', :id, cast(:after as jsonb))"
        ),
        {"t": tenant_id, "id": str(tenant_id), "after": json.dumps(removed)},
    )
    return removed


async def retention_job(ctx: dict[str, Any], today: dt.date | None = None) -> dict[str, Any]:
    """Tüm kiracılarda saklama sürelerini uygular (worker, her gece)."""
    today = today or dt.date.today()
    report: dict[str, Any] = {}
    async with get_engine().connect() as conn:
        tenants = (
            await conn.execute(text("select id, settings -> 'retention' from tenants order by id"))
        ).all()
        await conn.commit()
        for tenant_id, raw in tenants:
            async with conn.begin():
                report[str(tenant_id)] = await purge_tenant(
                    conn, tenant_id, Retention.model_validate(raw or {}), today
                )
    log.info("retention run", extra={"tenants": len(report)})
    return report
