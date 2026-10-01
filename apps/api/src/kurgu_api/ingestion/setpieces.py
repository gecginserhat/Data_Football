"""Olaylardan çıkarılan duran top dizilerini yazar (SPEC §5.5).

Sağlayıcı dizileri (`source='provider'`) paylaşılır (`tenant_id` boş) ve lisanslı maçlarda
okunur; kiracının içe aktardığı maçların dizileri (`source='import'`) kiracıya aittir. Dizideki
olaylar `events.set_piece_id` ile diziye bağlanır.
"""

import uuid
from collections.abc import Sequence
from typing import Any, Literal

from kurgu_analytics.canonical.model import Action, CanonicalMatch
from kurgu_analytics.setpieces.extract import extract
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, INTEGER
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

INSERT = text(
    """
    insert into set_pieces (match_id, team_id, period, start_time_s, sp_type, sp_subtype, side,
      taker_id, start_x, start_y, end_x, end_y, target_zone, first_contact_team_id,
      first_contact_player_id, outcome, shots, xg_total, xg_phase1, xg_phase2, goal,
      phase_of_goal, source, tenant_id)
    values (:match, :team, :period, :t, :type, :subtype, :side, :taker, :sx, :sy, :ex, :ey,
      :zone, :fc_team, :fc_player, :outcome, :shots, :xg, :xg1, :xg2, :goal, :pog, :source,
      :tenant)
    returning id
    """
)
LINK = text(
    "update events set set_piece_id = :sp where match_id = :match and action_index = any(:indices)"
).bindparams(bindparam("indices", type_=ARRAY(INTEGER)))


async def write_set_pieces(
    conn: AsyncConnection, provider: str, cm: CanonicalMatch, written: dict[str, Any]
) -> int:
    """Sağlayıcı hattının yazma sonrası kancası (paylaşılan diziler)."""
    return await insert_set_pieces(
        conn, written["match_id"], cm.actions, written["teams"], written["players"]
    )


async def insert_set_pieces(
    conn: AsyncConnection | AsyncSession,
    match_id: uuid.UUID,
    actions: Sequence[Action],
    teams: dict[str, uuid.UUID],
    players: dict[str, uuid.UUID],
    *,
    tenant_id: uuid.UUID | None = None,
    source: Literal["provider", "import"] = "provider",
) -> int:
    """Dizileri çıkarır ve yazar. `teams`/`players`: aksiyondaki kimlik → kanonik kimlik."""
    sequences = extract(actions)
    for sp in sequences:
        sp_id: uuid.UUID = (
            await conn.execute(
                INSERT,
                {
                    "match": match_id,
                    "team": teams[sp.team],
                    "period": sp.period,
                    "t": sp.start_time_s,
                    "type": sp.sp_type,
                    "subtype": sp.sp_subtype,
                    "side": sp.side,
                    "taker": players.get(sp.taker) if sp.taker else None,
                    "sx": sp.start_x,
                    "sy": sp.start_y,
                    "ex": sp.end_x,
                    "ey": sp.end_y,
                    "zone": sp.target_zone,
                    "fc_team": teams.get(sp.first_contact_team) if sp.first_contact_team else None,
                    "fc_player": (
                        players.get(sp.first_contact_player) if sp.first_contact_player else None
                    ),
                    "outcome": sp.outcome,
                    "shots": len(sp.shots),
                    "xg": sp.xg_total,
                    "xg1": sp.xg_phase1,
                    "xg2": sp.xg_phase2,
                    "goal": sp.goal,
                    "pog": sp.phase_of_goal,
                    "source": source,
                    "tenant": tenant_id,
                },
            )
        ).scalar_one()
        await conn.execute(LINK, {"sp": sp_id, "match": match_id, "indices": sp.action_indices})
    return len(sequences)
