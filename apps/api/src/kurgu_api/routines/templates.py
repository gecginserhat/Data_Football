"""Rutin şablonlarının yüklenmesi (A-40).

Şablonlar `seed/routine_templates.json` dosyasından okunur, v1 diyagramına çevrilir ve
paylaşılan `routine_templates` tablosuna yazılır (idempotent). Dosyadan kalkan bir şablon
silinmez: ona bağlı rutinler olabilir.
"""

import json
from pathlib import Path
from typing import Any

from kurgu_analytics.ingestion.seed import load_routine_templates
from kurgu_analytics.reports.diagram import from_template
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

UPSERT = """
insert into routine_templates (id, name, sp_type, side, is_defensive, when_to_use, notes, diagram,
                               sort_order, updated_at)
values (:id, :name, :sp_type, :side, :is_defensive, :when_to_use, :notes, cast(:diagram as jsonb),
        :sort_order, now())
on conflict (id) do update set
  name = excluded.name, sp_type = excluded.sp_type, side = excluded.side,
  is_defensive = excluded.is_defensive, when_to_use = excluded.when_to_use,
  notes = excluded.notes, diagram = excluded.diagram, sort_order = excluded.sort_order,
  updated_at = now()
where (routine_templates.name, routine_templates.sp_type, routine_templates.side,
       routine_templates.is_defensive, routine_templates.when_to_use, routine_templates.notes,
       routine_templates.diagram, routine_templates.sort_order)
  is distinct from (excluded.name, excluded.sp_type, excluded.side, excluded.is_defensive,
                    excluded.when_to_use, excluded.notes, excluded.diagram, excluded.sort_order)
"""


def read_templates(path: Path) -> list[dict[str, Any]]:
    """Dosyayı şemaya göre doğrular ve şablon listesini döner."""
    load_routine_templates(path)
    templates: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["templates"]
    return templates


async def load_templates(conn: AsyncConnection, templates: list[dict[str, Any]]) -> int:
    """Şablonları yükler (upsert); şablon sayısını döner."""
    for order, tpl in enumerate(templates):
        await conn.execute(
            text(UPSERT),
            {
                "id": tpl["id"],
                "name": tpl["name"],
                "sp_type": tpl["sp_type"],
                "side": tpl.get("side"),
                "is_defensive": tpl["is_defensive"],
                "when_to_use": tpl["when_to_use"],
                "notes": tpl["notes"],
                "diagram": json.dumps(from_template(tpl).dump()),
                "sort_order": order,
            },
        )
    return len(templates)
