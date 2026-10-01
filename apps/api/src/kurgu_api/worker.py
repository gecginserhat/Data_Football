"""Arq worker. Çalıştırma: `arq kurgu_api.worker.WorkerSettings`.

API ile aynı paketten çalışır (ADR-0001). Uzun işler (yükleme, MV yenileme, PDF, HLS)
sonraki fazlarda buraya eklenir. Faz 1: sağlayıcı yükleme işi. Faz 2: metrik görünümü yenileme.
Faz 5: video HLS dönüştürme. Faz 6: PDF raporlar.
"""

from typing import Any, ClassVar

from arq import func
from arq.connections import RedisSettings

from kurgu_api.config import get_settings
from kurgu_api.core.db import get_engine
from kurgu_api.ingestion.jobs import run_ingestion_job
from kurgu_api.league.views import refresh_metric_views
from kurgu_api.reports.jobs import generate_report_job
from kurgu_api.video.jobs import transcode_video_job


async def ping(ctx: dict[str, Any], value: str = "pong") -> str:
    """Kuyruğun uçtan uca çalıştığını gösteren basit iş."""
    return value


async def refresh_metric_views_job(ctx: dict[str, Any]) -> str:
    """Metrik görünümlerini yeniler (ADR-0007). Yükleme işleri bunu kendisi de çağırır."""
    async with get_engine().begin() as conn:
        await refresh_metric_views(conn)
    return "refreshed"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        ping,
        run_ingestion_job,
        refresh_metric_views_job,
        # Uzun maç videoları için ayrı süre sınırı (A-61).
        func(transcode_video_job, timeout=4 * 3600, max_tries=1),
        # Rapor tek denemedir; hata kayda yazılır, kullanıcı yeniden ister (A-71).
        func(generate_report_job, timeout=120, max_tries=1),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 600
