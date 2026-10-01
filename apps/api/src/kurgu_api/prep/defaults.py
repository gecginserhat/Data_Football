"""Varsayılan kural setinin yüklenmesi (A-51).

`seed/recommendation_rules.json` öneri motorunun şemasıyla doğrulanır ve kiracısız 0. sürüm
olarak `rule_sets` tablosuna yazılır (idempotent; içerik değişmediyse dokunulmaz). Kulüplerin
kendi sürümleri etkilenmez.
"""

import json
from pathlib import Path

from kurgu_analytics.recs import RuleSet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

UPSERT = """
insert into rule_sets (tenant_id, version, label, rules, message, published_at)
values (null, 0, :label, cast(:rules as jsonb), 'Varsayılan kural seti', now())
on conflict on constraint uq_rule_sets_tenant_version do update set
  label = excluded.label, rules = excluded.rules, published_at = now()
where (rule_sets.label, rule_sets.rules) is distinct from (excluded.label, excluded.rules)
"""


def read_default_rules(path: Path) -> RuleSet:
    """Dosyayı öneri motoru şemasıyla doğrular."""
    return RuleSet.model_validate(json.loads(path.read_text(encoding="utf-8")))


async def load_default_rules(conn: AsyncConnection, rule_set: RuleSet) -> int:
    """Varsayılan seti yükler; kural sayısını döner."""
    label = rule_set.meta.get("version")
    await conn.execute(
        text(UPSERT),
        {
            "label": str(label) if label is not None else None,
            "rules": json.dumps(rule_set.model_dump(mode="json", by_alias=True)),
        },
    )
    return len(rule_set.rules)
