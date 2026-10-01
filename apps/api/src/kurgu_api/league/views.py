"""Metrik görünümlerinin yenilenmesi (ADR-0007).

`mv_team_setpiece_season` ve `mv_league_benchmarks` yalnızca paylaşılan lig verisinden beslenir;
bu yüzden tohum ve sağlayıcı yüklemesinden sonra yenilenir. Kiracının içe aktardığı satırlar
istek anında okunur ve yenileme gerektirmez.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def refresh_metric_views(conn: AsyncConnection) -> None:
    """Görünümleri `CONCURRENTLY` yeniler; okumalar yenileme sırasında beklemez."""
    await conn.execute(text("select kurgu_refresh_metric_views()"))
