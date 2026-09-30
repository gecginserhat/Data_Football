"""Arq worker. Çalıştırma: `arq kurgu_api.worker.WorkerSettings`.

API ile aynı paketten çalışır (ADR-0001). Uzun işler (yükleme, MV yenileme, PDF, HLS)
sonraki fazlarda buraya eklenir. Faz 1: sağlayıcı yükleme işi.
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from kurgu_api.config import get_settings
from kurgu_api.ingestion.jobs import run_ingestion_job


async def ping(ctx: dict[str, Any], value: str = "pong") -> str:
    """Kuyruğun uçtan uca çalıştığını gösteren basit iş."""
    return value


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping, run_ingestion_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 600
