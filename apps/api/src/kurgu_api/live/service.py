"""Senkronizasyon kuralları (ADR-0004): kimlikle idempotent, son yazan kazanır, silme kazanır.

Her değişiklik oturumun sıra numarasını bir artırır; çekme `server_seq > since` ile yapılır. Kabul
edilen kayıt aynı kimlikle `set_pieces` satırına dönüşür (A-59).
"""

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.live.schemas import SHOT_OUTCOMES, Change, Rejected, TagPayload

TAG_SQL = """
select id, session_id, device_id, client_ts, deleted, payload
from live_tags where id = any(:ids)
"""
MATCH_SQL = "select home_team_id, away_team_id from matches where id = :id"
ROUTINES_SQL = """
select id, sp_type from routines where id = any(:ids) and archived_at is null
"""
UPSERT_TAG = """
insert into live_tags (id, tenant_id, session_id, device_id, created_at_client, client_ts,
  server_seq, deleted, payload)
values (:id, :tenant, :session, :device, :ts, :ts, :seq, :deleted, cast(:payload as jsonb))
on conflict (id) do update set
  device_id = excluded.device_id, client_ts = excluded.client_ts,
  server_seq = excluded.server_seq, deleted = excluded.deleted,
  payload = case when excluded.deleted then live_tags.payload else excluded.payload end,
  server_received_at = now(), updated_at = now(),
  server_version = live_tags.server_version + 1
"""
UPSERT_SET_PIECE = """
insert into set_pieces (id, tenant_id, match_id, team_id, period, start_time_s, sp_type, side,
  first_contact_team_id, outcome, shots, goal, routine_id, source)
values (:id, :tenant, :match, :team, :period, :clock, :sp_type, :side, :contact, :outcome,
  :shots, :goal, :routine, 'live_tag')
on conflict (id) do update set
  team_id = excluded.team_id, period = excluded.period, start_time_s = excluded.start_time_s,
  sp_type = excluded.sp_type, side = excluded.side,
  first_contact_team_id = excluded.first_contact_team_id, outcome = excluded.outcome,
  shots = excluded.shots, goal = excluded.goal, routine_id = excluded.routine_id
"""


@dataclass(slots=True)
class SyncResult:
    accepted: list[uuid.UUID] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    changed: int = 0


def _newer(ts: dt.datetime, device: str, other_ts: dt.datetime, other_device: str) -> bool:
    """Son yazan kazanır; eşit zamanda cihaz kimliği sözlük sırasıyla (deterministik)."""
    return (ts, device) > (other_ts, other_device)


def _same(existing: Any, ts: dt.datetime, device: str, payload: dict[str, Any]) -> bool:
    return bool(
        existing.client_ts == ts and existing.device_id == device and existing.payload == payload
    )


async def apply_changes(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    match_id: uuid.UUID,
    club_team_id: uuid.UUID | None,
    device_id: str,
    changes: list[Change],
    last_seq: int,
) -> tuple[SyncResult, int]:
    """Değişiklikleri uygular; (sonuç, yeni son sıra) döner. Oturum satırı çağıranda kilitlidir."""
    result = SyncResult()
    match = (await session.execute(text(MATCH_SQL), {"id": match_id})).one()
    teams = {"home": match.home_team_id, "away": match.away_team_id}
    existing: dict[uuid.UUID, Any] = {
        r.id: r for r in await session.execute(text(TAG_SQL), {"ids": [c.id for c in changes]})
    }
    payloads: dict[uuid.UUID, TagPayload] = {}
    for change in changes:
        if change.op == "upsert":
            try:
                payloads[change.id] = TagPayload.model_validate(change.payload or {})
            except ValidationError:
                continue
    routine_ids = [p.routine_id for p in payloads.values() if p.routine_id]
    routines = (
        {r.id: r.sp_type for r in await session.execute(text(ROUTINES_SQL), {"ids": routine_ids})}
        if routine_ids
        else {}
    )
    seq = last_seq
    for change in changes:
        ts = (
            change.client_ts if change.client_ts.tzinfo else change.client_ts.replace(tzinfo=dt.UTC)
        )
        old = existing.get(change.id)
        if old is not None and old.session_id != session_id:
            result.rejected.append(Rejected(id=change.id, reason="session-mismatch"))
            continue
        if change.op == "delete":
            if old is not None and old.deleted:
                result.accepted.append(change.id)
                continue
            seq += 1
            await session.execute(
                text(UPSERT_TAG),
                {
                    "id": change.id,
                    "tenant": tenant_id,
                    "session": session_id,
                    "device": device_id,
                    "ts": ts,
                    "seq": seq,
                    "deleted": True,
                    "payload": json.dumps(old.payload if old else {}),
                },
            )
            await session.execute(
                text("delete from set_pieces where id = :id and source = 'live_tag'"),
                {"id": change.id},
            )
            existing[change.id] = _Row(change.id, session_id, device_id, ts, True, {})
            result.accepted.append(change.id)
            result.changed += 1
            continue

        payload = payloads.get(change.id)
        if payload is None:
            result.rejected.append(Rejected(id=change.id, reason="invalid-payload"))
            continue
        if old is not None and old.deleted:
            result.rejected.append(Rejected(id=change.id, reason="deleted"))
            continue
        data = payload.model_dump(mode="json")
        if old is not None and _same(old, ts, device_id, data):
            result.accepted.append(change.id)
            continue
        if old is not None and not _newer(ts, device_id, old.client_ts, old.device_id):
            result.rejected.append(Rejected(id=change.id, reason="stale"))
            continue
        team_id = teams[payload.team]
        if payload.routine_id is not None:
            sp_type = routines.get(payload.routine_id)
            if sp_type is None:
                result.rejected.append(Rejected(id=change.id, reason="routine-not-found"))
                continue
            if team_id != club_team_id:
                result.rejected.append(Rejected(id=change.id, reason="routine-not-own"))
                continue
            if sp_type != payload.sp_type:
                result.rejected.append(Rejected(id=change.id, reason="routine-type-mismatch"))
                continue
        seq += 1
        await session.execute(
            text(UPSERT_TAG),
            {
                "id": change.id,
                "tenant": tenant_id,
                "session": session_id,
                "device": device_id,
                "ts": ts,
                "seq": seq,
                "deleted": False,
                "payload": json.dumps(data),
            },
        )
        other = teams["away" if payload.team == "home" else "home"]
        contact = {"attack": team_id, "defense": other, None: None}[payload.first_contact]
        await session.execute(
            text(UPSERT_SET_PIECE),
            {
                "id": change.id,
                "tenant": tenant_id,
                "match": match_id,
                "team": team_id,
                "period": payload.period,
                "clock": payload.clock_s,
                "sp_type": payload.sp_type,
                "side": payload.side,
                "contact": contact,
                "outcome": payload.outcome,
                "shots": 1 if payload.outcome in SHOT_OUTCOMES else 0,
                "goal": payload.outcome == "goal",
                "routine": payload.routine_id,
            },
        )
        existing[change.id] = _Row(change.id, session_id, device_id, ts, False, data)
        result.accepted.append(change.id)
        result.changed += 1
    return result, seq


@dataclass(frozen=True, slots=True)
class _Row:
    """Aynı istekte aynı kimlik ikinci kez gelirse son durumu temsil eder."""

    id: uuid.UUID
    session_id: uuid.UUID
    device_id: str
    client_ts: dt.datetime
    deleted: bool
    payload: dict[str, Any]
