"""Veri anahtarı yönetimi (ADR-0014, `docs/runbooks/keys.md`).

`kurgu-keys generate <kid>`: `KURGU_DATA_KEYS` için yeni anahtar girdisi yazdırır.
`kurgu-keys rewrap --admin-url ...`: birincil olmayan anahtarla sarılmış tüm iyi oluş zarflarını
birincil anahtarla yeniden sarar ve kiracı başına denetim kaydı yazar. Ardından eski anahtar
`KURGU_DATA_KEYS` listesinden çıkarılabilir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections import Counter

import asyncpg

from kurgu_api.core.crypto import DecryptError, KeyConfigError, generate_key, get_keyring, rewrap
from kurgu_api.ops.backup import libpq_url
from kurgu_api.performance.service import WELLNESS_FIELD, WELLNESS_TABLE

BATCH = 500


async def rewrap_all(
    admin_url: str, *, dry_run: bool = False, tenant: uuid.UUID | None = None
) -> dict[uuid.UUID, int]:
    """Eski anahtarlı zarfları yeniden sarar; kiracı başına yeniden sarılan kayıt sayısı.

    Bağlantı RLS'yi atlayabilen bir operatör rolüyle kurulur (tüm kiracılar tek geçişte).
    """
    ring = get_keyring()
    done: Counter[uuid.UUID] = Counter()
    conn = await asyncpg.connect(libpq_url(admin_url))
    try:
        while True:
            rows = await conn.fetch(
                f"select id, tenant_id, {WELLNESS_FIELD} as envelope from {WELLNESS_TABLE}"  # noqa: S608
                f" where {WELLNESS_FIELD}->>'kid' <> $1 and ($3::uuid is null or tenant_id = $3)"
                " order by id limit $2",
                ring.primary,
                BATCH,
                tenant,
            )
            if not rows:
                break
            async with conn.transaction():
                for row in rows:
                    envelope = row["envelope"]
                    if isinstance(envelope, str):
                        envelope = json.loads(envelope)
                    tenant = uuid.UUID(str(row["tenant_id"]))
                    fresh = rewrap(
                        envelope,
                        tenant_id=tenant,
                        table=WELLNESS_TABLE,
                        field=WELLNESS_FIELD,
                        keyring=ring,
                    )
                    if not dry_run:
                        await conn.execute(
                            f"update {WELLNESS_TABLE} set {WELLNESS_FIELD} = $1::jsonb"  # noqa: S608
                            " where id = $2",
                            json.dumps(fresh),
                            row["id"],
                        )
                    done[tenant] += 1
            if dry_run:
                break
        if not dry_run:
            for tenant, count in done.items():
                await conn.execute(
                    "insert into audit_log (tenant_id, action, entity, after)"
                    " values ($1, 'keys.rewrap', $2, $3::jsonb)",
                    tenant,
                    WELLNESS_TABLE,
                    json.dumps({"records": count, "kid": ring.primary}),
                )
    finally:
        await conn.close()
    return dict(done)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kurgu-keys", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="yeni anahtar girdisi yazdır")
    gen.add_argument("kid")
    rw = sub.add_parser("rewrap", help="zarfları birincil anahtarla yeniden sar")
    rw.add_argument("--admin-url", required=True)
    rw.add_argument("--dry-run", action="store_true", help="yalnız ilk parti; yazmaz")
    rw.add_argument("--tenant", type=uuid.UUID, default=None, help="yalnız bu kulüp")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            print(generate_key(args.kid))
            return 0
        counts = asyncio.run(rewrap_all(args.admin_url, dry_run=args.dry_run, tenant=args.tenant))
    except (KeyConfigError, DecryptError) as exc:
        print(f"kurgu-keys: {exc}", file=sys.stderr)
        return 1
    total = sum(counts.values())
    verb = "yeniden sarılacak (deneme)" if args.dry_run else "yeniden sarıldı"
    print(f"{total} kayıt {verb}; {len(counts)} kiracı")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
