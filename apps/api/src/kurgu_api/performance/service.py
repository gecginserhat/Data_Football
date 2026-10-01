"""Yük ve iyi oluş kayıtlarını okur, hesapları `kurgu_analytics.metrics.load` ile yapar.

İyi oluş puanları şifreli zarflardır (ADR-0014); yalnız burada çözülür.
"""

import datetime as dt
import math
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from kurgu_analytics.metrics.load import (
    HOOPER_ITEMS,
    daily_loads,
    hooper_trend,
    load_trend,
    srpe,
    weekly_alerts,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.crypto import decrypt, encrypt
from kurgu_api.performance.schemas import AlertOut, PlayerRef

TZ = ZoneInfo("Europe/Istanbul")
WELLNESS_TABLE = "wellness_entries"
WELLNESS_FIELD = "scores"
CHRONIC_DAYS = 28

LOADS_SQL = """
select sl.squad_player_id as player_id, ts.date, ts.title, ts.md_code, sl.rpe, sl.minutes,
       sl.headers, sl.jumps
from session_loads sl join training_sessions ts on ts.id = sl.session_id
where ts.date <= :until and (cast(:player as uuid) is null or sl.squad_player_id = :player)
order by ts.date, ts.created_at
"""

WELLNESS_SQL = """
select squad_player_id as player_id, date, scores from wellness_entries
where date <= :until and (cast(:player as uuid) is null or squad_player_id = :player)
order by date
"""

PLAYERS_SQL = """
select id, name, shirt_number, position, is_demo from squad_players
where active or id = cast(:player as uuid)
order by position = 'GK' desc, shirt_number nulls last, name
"""


def today() -> dt.date:
    return dt.datetime.now(TZ).date()


def num(value: Any) -> float | None:
    """NaN ve sonsuzu boşa çevirir, 4 basamağa yuvarlar."""
    if value is None:
        return None
    f = float(value)
    return None if math.isnan(f) or math.isinf(f) else round(f, 4)


def seal(scores: dict[str, int], tenant_id: uuid.UUID) -> dict[str, Any]:
    return encrypt(scores, tenant_id=tenant_id, table=WELLNESS_TABLE, field=WELLNESS_FIELD)


def unseal(envelope: dict[str, Any], tenant_id: uuid.UUID) -> dict[str, int]:
    value: dict[str, int] = decrypt(
        envelope, tenant_id=tenant_id, table=WELLNESS_TABLE, field=WELLNESS_FIELD
    )
    return value


@dataclass
class LoadData:
    players: dict[uuid.UUID, PlayerRef]
    sessions: pd.DataFrame
    """player_id, date, title, md_code, rpe, minutes, srpe, headers, jumps."""
    wellness: pd.DataFrame
    """player_id, date, sleep, stress, fatigue, soreness."""


async def load_data(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    until: dt.date,
    player: uuid.UUID | None = None,
) -> LoadData:
    players = {
        r.id: PlayerRef(
            id=r.id,
            name=r.name,
            shirt_number=r.shirt_number,
            position=r.position,
            is_demo=r.is_demo,
        )
        for r in await session.execute(text(PLAYERS_SQL), {"player": player})
    }
    rows = (await session.execute(text(LOADS_SQL), {"until": until, "player": player})).all()
    sessions = pd.DataFrame(
        [
            {
                "player_id": r.player_id,
                "date": r.date,
                "title": r.title,
                "md_code": r.md_code,
                "rpe": float(r.rpe),
                "minutes": r.minutes,
                "srpe": srpe(float(r.rpe), r.minutes),
                "headers": r.headers,
                "jumps": r.jumps,
            }
            for r in rows
        ],
        columns=[
            "player_id",
            "date",
            "title",
            "md_code",
            "rpe",
            "minutes",
            "srpe",
            "headers",
            "jumps",
        ],
    )
    entries = (await session.execute(text(WELLNESS_SQL), {"until": until, "player": player})).all()
    wellness = pd.DataFrame(
        [
            {"player_id": r.player_id, "date": r.date, **unseal(r.scores, tenant_id)}
            for r in entries
        ],
        columns=["player_id", "date", *HOOPER_ITEMS],
    )
    return LoadData(players, sessions, wellness)


def trends(data: LoadData, until: dt.date) -> pd.DataFrame:
    return load_trend(daily_loads(data.sessions[["player_id", "date", "srpe"]], until))


def alerts(data: LoadData, until: dt.date, since: dt.date | None = None) -> list[AlertOut]:
    """Sıçrama ve kafa vuruşu uyarıları; `since` verilirse o haftadan sonrakiler."""
    out: list[AlertOut] = []
    for metric in ("jumps", "headers"):
        frame = weekly_alerts(data.sessions, metric, until)
        for r in frame.itertuples(index=False):
            if since is not None and r.week < since:
                continue
            player = data.players.get(r.player_id)
            if player is None:
                continue
            out.append(
                AlertOut(
                    player=player,
                    metric=metric,
                    week=r.week,
                    total=int(r.total),
                    mean=round(float(r.mean), 2),
                    sd=round(float(r.sd), 2),
                    threshold=round(float(r.threshold), 2),
                    weeks=int(r.weeks),
                )
            )
    return sorted(out, key=lambda a: (-a.week.toordinal(), a.player.name, a.metric))


def hooper(data: LoadData) -> pd.DataFrame:
    return hooper_trend(data.wellness)
