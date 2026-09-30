"""Kanonik maçı paylaşılan lig tablolarına yazar (worker rolü; ADR-0002, ADR-0003).

Kimlikler `provider_id_map` üzerinden eşlenir. Sağlayıcı kimlikleri kesin olduğu için güven 1
ve onaylı yazılır (SPEC §5.4). Maç yeniden işlenirse olayları silinip yeniden yazılır; böylece
yükleme idempotenttir.
"""

import json
import uuid
from typing import Any

from kurgu_analytics.canonical.model import CanonicalMatch, Match, Team
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def _map(conn: AsyncConnection, entity: str, provider: str, pid: str) -> uuid.UUID | None:
    return (
        await conn.execute(
            text(
                "select kurgu_id from provider_id_map"
                " where entity_type = :e and provider = :p and provider_id = :pid"
            ),
            {"e": entity, "p": provider, "pid": pid},
        )
    ).scalar_one_or_none()


async def _remember(
    conn: AsyncConnection, entity: str, provider: str, pid: str, kurgu_id: uuid.UUID
) -> None:
    await conn.execute(
        text(
            "insert into provider_id_map (entity_type, provider, provider_id, kurgu_id,"
            " confidence, confirmed_at) values (:e, :p, :pid, :kid, 1, now())"
            " on conflict (entity_type, provider, provider_id) do nothing"
        ),
        {"e": entity, "p": provider, "pid": pid, "kid": kurgu_id},
    )


async def _get_or_create(
    conn: AsyncConnection, entity: str, provider: str, pid: str, insert_sql: str, params: Any
) -> uuid.UUID:
    existing = await _map(conn, entity, provider, pid)
    if existing is not None:
        return existing
    new_id: uuid.UUID = (await conn.execute(text(insert_sql), params)).scalar_one()
    await _remember(conn, entity, provider, pid, new_id)
    return new_id


def _team_code(name: str) -> str:
    letters = [c for c in name.upper() if c.isalpha()]
    return "".join(letters[:3]) or "UNK"


async def upsert_match(conn: AsyncConnection, provider: str, match: Match) -> dict[str, Any]:
    """Yarışma, sezon, takımlar ve maçı yazar; kanonik kimlikleri döner."""
    comp_pid = match.competition_provider_id
    competition = await _get_or_create(
        conn,
        "competition",
        provider,
        comp_pid,
        "insert into competitions (code, name) values (:code, :name)"
        " on conflict (code) do update set name = excluded.name returning id",
        {"code": f"{provider}:{comp_pid}", "name": match.competition_name},
    )
    season_pid = f"{comp_pid}:{match.season_provider_id}"
    season = await _get_or_create(
        conn,
        "season",
        provider,
        season_pid,
        "insert into seasons (competition_id, code, label) values (:c, :code, :label)"
        " on conflict (competition_id, code) do update set label = excluded.label returning id",
        {"c": competition, "code": match.season_provider_id, "label": match.season_name},
    )
    teams: dict[str, uuid.UUID] = {}
    for team in (match.home, match.away):
        teams[team.provider_id] = await _team(conn, provider, team)
    params = {
        "season": season,
        "week": match.week,
        "stage": match.stage,
        "home": teams[match.home.provider_id],
        "away": teams[match.away.provider_id],
        "kickoff": match.kickoff_at,
        "hs": match.home_score,
        "as_": match.away_score,
        "status": "finished" if match.home_score is not None else "scheduled",
        "src": provider,
    }
    match_id = await _map(conn, "match", provider, match.provider_id)
    if match_id is None:
        match_id = (
            await conn.execute(
                text(
                    "insert into matches (season_id, week, stage, home_team_id, away_team_id,"
                    " kickoff_at, home_score, away_score, status, source) values (:season, :week,"
                    " :stage, :home, :away, :kickoff, :hs, :as_, :status, :src) returning id"
                ),
                params,
            )
        ).scalar_one()
        assert match_id is not None
        await _remember(conn, "match", provider, match.provider_id, match_id)
    else:
        await conn.execute(
            text(
                "update matches set week = :week, stage = :stage, kickoff_at = :kickoff,"
                " home_score = :hs, away_score = :as_, status = :status where id = :id"
            ),
            params | {"id": match_id},
        )
    return {"match_id": match_id, "season_id": season, "teams": teams}


async def _team(conn: AsyncConnection, provider: str, team: Team) -> uuid.UUID:
    return await _get_or_create(
        conn,
        "team",
        provider,
        team.provider_id,
        "insert into teams (code, name) values (:code, :name) returning id",
        {"code": _team_code(team.name), "name": team.name},
    )


async def write_canonical(
    conn: AsyncConnection, provider: str, cm: CanonicalMatch, raw_id: uuid.UUID | None
) -> dict[str, Any]:
    ids = await upsert_match(conn, provider, cm.match)
    teams: dict[str, uuid.UUID] = ids["teams"]
    players: dict[str, uuid.UUID] = {}
    for p in cm.players:
        players[p.provider_id] = await _get_or_create(
            conn,
            "player",
            provider,
            p.provider_id,
            "insert into players (name, current_team_id) values (:name, :team) returning id",
            {"name": p.name, "team": teams.get(p.team_provider_id)},
        )

    match_id: uuid.UUID = ids["match_id"]
    await conn.execute(
        text("delete from set_pieces where match_id = :m and source = 'provider'"),
        {"m": match_id},
    )
    await conn.execute(text("delete from events where match_id = :m"), {"m": match_id})
    rows = [
        {
            "match": match_id,
            "idx": a.action_index,
            "period": a.period,
            "time": a.time_s,
            "team": teams[a.team_provider_id],
            "player": players.get(a.player_provider_id) if a.player_provider_id else None,
            "type": a.type,
            "result": a.result,
            "bodypart": a.bodypart,
            "sx": a.start_x,
            "sy": a.start_y,
            "ex": a.end_x,
            "ey": a.end_y,
            "xg": a.xg,
            "xg_source": a.xg_source,
            "provider": provider,
            "peid": a.provider_event_id,
            "raw": raw_id,
            "extra": json.dumps(a.extra),
        }
        for a in cm.actions
    ]
    if rows:
        await conn.execute(
            text(
                "insert into events (match_id, action_index, period, time_s, team_id, player_id,"
                " type, result, bodypart, start_x, start_y, end_x, end_y, xg, xg_source, provider,"
                " provider_event_id, raw_ref, extra) values (:match, :idx, :period, :time, :team,"
                " :player, :type, :result, :bodypart, :sx, :sy, :ex, :ey, :xg, :xg_source,"
                " :provider, :peid, :raw, cast(:extra as jsonb))"
            ),
            rows,
        )
    return {"match_id": match_id, "teams": teams, "players": players, "actions": len(rows)}
