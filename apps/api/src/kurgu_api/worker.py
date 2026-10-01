"""Arq worker. Çalıştırma: `arq kurgu_api.worker.WorkerSettings`.

API ile aynı paketten çalışır (ADR-0001). Uzun işler (yükleme, MV yenileme, PDF, HLS)
sonraki fazlarda buraya eklenir.
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from kurgu_api.config import get_settings


async def ping(ctx: dict[str, Any], value: str = "pong") -> str:
    """Kuyruğun uçtan uca çalıştığını gösteren basit iş."""
    return value


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 600
