"""Worker işleri ve komut satırı (`kurgu-ingest`) (SPEC §5.2).

API bir yükleme işi açar (`pending`, kiracıya ait) ve `run_ingestion_job` işini kuyruğa
koyar. Worker kendi rolüyle (`kurgu_worker`) bağlanır; paylaşılan lig tablolarına yalnızca bu
rol yazabilir. Komut satırı aynı hattı kiracısız (paylaşılan) bir işle çalıştırır.
"""

import argparse
import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

from kurgu_api.config import get_settings
from kurgu_api.core.db import get_engine
from kurgu_api.ingestion.pipeline import PROVIDERS, run_ingestion
from kurgu_api.ingestion.runs import create_run
from kurgu_api.ingestion.storage import get_object_store


async def run_ingestion_job(
    ctx: dict[str, Any], run_id: str, tenant_id: str | None, provider: str, params: dict[str, Any]
) -> dict[str, Any]:
    return await run_ingestion(
        get_engine(),
        get_object_store(),
        uuid.UUID(run_id),
        tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
        provider=PROVIDERS[provider](),
        params=params,
    )


async def _cli(provider: str, params: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.worker_database_url or settings.database_url)
    try:
        async with engine.begin() as conn:
            run_id = await create_run(
                conn, tenant_id=None, provider=provider, kind="events", params=params
            )
        return await run_ingestion(
            engine,
            get_object_store(settings),
            run_id,
            tenant_id=None,
            provider=PROVIDERS[provider](),
            params=params,
        )
    finally:
        await engine.dispose()


def main() -> None:
    """`kurgu-ingest statsbomb_open --competition 43 --season 106 [--limit N]`."""
    parser = argparse.ArgumentParser(prog="kurgu-ingest")
    parser.add_argument("provider", choices=sorted(PROVIDERS))
    parser.add_argument("--competition", type=int, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    params: dict[str, Any] = {"competition_id": args.competition, "season_id": args.season}
    if args.limit:
        params["limit"] = args.limit
    stats = asyncio.run(_cli(args.provider, params))
    print(f"ingestion finished: {stats}")


if __name__ == "__main__":
    main()
