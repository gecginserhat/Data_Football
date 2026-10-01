"""Denetim kaydı (SPEC §10 `audit_log`). Yalnızca ekleme; uygulama rolleri güncelleyemez."""

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def write_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    entity: str,
    entity_id: uuid.UUID,
    after: dict[str, Any],
    before: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            "insert into audit_log (tenant_id, actor_id, action, entity, entity_id, before, after)"
            " values (:tenant, :actor, :action, :entity, :entity_id, cast(:before as jsonb),"
            " cast(:after as jsonb))"
        ),
        {
            "tenant": tenant_id,
            "actor": actor_id,
            "action": action,
            "entity": entity,
            "entity_id": str(entity_id),
            "before": json.dumps(before) if before is not None else None,
            "after": json.dumps(after),
        },
    )
