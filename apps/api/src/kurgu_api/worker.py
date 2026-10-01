"""Arq worker. Çalıştırma: `arq kurgu_api.worker.WorkerSettings`.

API ile aynı paketten çalışır (ADR-0001). Uzun işler (yükleme, MV yenileme, PDF, HLS)
sonraki fazlarda buraya eklenir. Faz 1: sağlayıcı yükleme işi. Faz 2: metrik görünümü yenileme.
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from kurgu_api.config import get_settings
from kurgu_api.core.db import get_engine
from kurgu_api.ingestion.jobs import run_ingestion_job
from kurgu_api.league.views import refresh_metric_views


async def ping(ctx: dict[str, Any], value: str = "pong") -> str:
    """Kuyruğun uçtan uca çalıştığını gösteren basit iş."""
    return value


async def refresh_metric_views_job(ctx: dict[str, Any]) -> str:
    """Metrik görünümlerini yeniler (ADR-0007). Yükleme işleri bunu kendisi de çağırır."""
    async with get_engine().begin() as conn:
        await refresh_metric_views(conn)
    return "refreshed"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping, run_ingestion_job, refresh_metric_views_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 600
