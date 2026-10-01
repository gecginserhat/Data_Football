"""Canlı kayıt uçları (SPEC §11): oturum, toplu senkronizasyon, değişiklik çekme (ADR-0004)."""

import logging
import uuid
from typing import Annotated

from arq import ArqRedis
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text

from kurgu_api.core.audit import write_audit
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.ingestion.router import get_queue
from kurgu_api.live.schemas import (
    MatchSetPieceOut,
    SessionCreate,
    SessionOut,
    SyncIn,
    SyncOut,
    TagOut,
    TagsOut,
)
from kurgu_api.live.service import apply_changes

log = logging.getLogger(__name__)
router = APIRouter(tags=["live"])
TAG = [Depends(require(Permission.LIVE_TAGGING_VIDEO))]
READ = [Depends(require(Permission.READ_ANALYSIS))]

SESSION_COLUMNS = "id, match_id, last_seq, server_received_at as created_at"
OPEN_SQL = f"""
insert into tagging_sessions (id, tenant_id, match_id, device_id, created_by, created_at_client)
values (:id, :t, :m, :d, :u, now())
on conflict (tenant_id, match_id) where not deleted and match_id is not null do nothing
returning {SESSION_COLUMNS}
"""  # noqa: S608
CLUB_SQL = "select club_team_id from tenants where id = kurgu_current_tenant()"


def _tenant(principal: PrincipalDep) -> uuid.UUID:
    assert principal.tenant is not None
    return principal.tenant.tenant_id


async def _visible_match(session: SessionDep, match_id: uuid.UUID) -> None:
    found = (
        await session.execute(text("select 1 from matches where id = :id"), {"id": match_id})
    ).first()
    if not found:
        raise ProblemError(404, "not-found", "Match not found")


@router.post(
    "/tagging-sessions",
    response_model=SessionOut,
    operation_id="openTaggingSession",
    dependencies=TAG,
)
async def open_session(
    session: SessionDep, principal: PrincipalDep, body: SessionCreate
) -> SessionOut:
    """Maçın kayıt oturumunu döner; yoksa açar. Aynı maçı kaydeden cihazlar paylaşır (A-56)."""
    await _visible_match(session, body.match_id)
    tenant = _tenant(principal)
    row = (
        await session.execute(
            text(OPEN_SQL),
            {
                "id": uuid.uuid4(),
                "t": tenant,
                "m": body.match_id,
                "d": body.device_id,
                "u": principal.user_id,
            },
        )
    ).one_or_none()
    if row is None:
        row = (
            await session.execute(
                text(
                    f"select {SESSION_COLUMNS} from tagging_sessions"  # noqa: S608
                    " where match_id = :m and not deleted"
                ),
                {"m": body.match_id},
            )
        ).one()
    else:
        await write_audit(
            session,
            tenant_id=tenant,
            actor_id=principal.user_id,
            action="tagging_session.open",
            entity="tagging_sessions",
            entity_id=row.id,
            after={"match_id": str(body.match_id), "device_id": body.device_id},
        )
    return SessionOut.model_validate(row._asdict())


@router.post(
    "/tagging-sessions/{session_id}/sync",
    response_model=SyncOut,
    operation_id="syncTaggingSession",
    dependencies=TAG,
)
async def sync(
    session: SessionDep,
    principal: PrincipalDep,
    session_id: uuid.UUID,
    body: SyncIn,
    queue: Annotated[ArqRedis, Depends(get_queue)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> SyncOut:
    """Toplu, idempotent senkronizasyon. Yanıtta sunucu sırası ve reddedilen kayıtlar (ADR-0004)."""
    if not idempotency_key:
        raise ProblemError(400, "idempotency-key-required", "Idempotency-Key header is required")
    row = (
        await session.execute(
            text(
                "select id, match_id, last_seq from tagging_sessions"
                " where id = :id and not deleted for update"
            ),
            {"id": session_id},
        )
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Tagging session not found")
    club = (await session.execute(text(CLUB_SQL))).scalar_one_or_none()
    result, seq = await apply_changes(
        session,
        tenant_id=_tenant(principal),
        session_id=row.id,
        match_id=row.match_id,
        club_team_id=club,
        device_id=body.device_id,
        changes=body.changes,
        last_seq=row.last_seq,
    )
    if seq != row.last_seq:
        await session.execute(
            text("update tagging_sessions set last_seq = :seq where id = :id"),
            {"seq": seq, "id": row.id},
        )
    if result.changed:
        await write_audit(
            session,
            tenant_id=_tenant(principal),
            actor_id=principal.user_id,
            action="tagging_session.sync",
            entity="tagging_sessions",
            entity_id=row.id,
            after={
                "device_id": body.device_id,
                "changed": result.changed,
                "rejected": len(result.rejected),
                "server_seq": seq,
            },
        )
        await session.commit()
        try:
            await queue.enqueue_job("refresh_metric_views_job")
        except Exception:  # Kuyruk düşükse kayıt yine de alınmıştır (A-59).
            log.warning("metric view refresh could not be queued", exc_info=True)
    return SyncOut(server_seq=seq, accepted=result.accepted, rejected=result.rejected)


@router.get(
    "/tagging-sessions/{session_id}/tags",
    response_model=TagsOut,
    operation_id="listSessionTags",
    dependencies=TAG,
)
async def list_tags(
    session: SessionDep,
    session_id: uuid.UUID,
    since: Annotated[int, Query(ge=0)] = 0,
) -> TagsOut:
    """`since` sırasından sonraki değişiklikler (mezar taşları dahil)."""
    last = (
        await session.execute(
            text("select last_seq from tagging_sessions where id = :id and not deleted"),
            {"id": session_id},
        )
    ).scalar_one_or_none()
    if last is None:
        raise ProblemError(404, "not-found", "Tagging session not found")
    rows = await session.execute(
        text(
            "select id, device_id, client_ts, server_seq, deleted, payload from live_tags"
            " where session_id = :id and server_seq > :since order by server_seq"
        ),
        {"id": session_id, "since": since},
    )
    return TagsOut(server_seq=last, tags=[TagOut.model_validate(r._asdict()) for r in rows])


@router.get(
    "/fixtures/{fixture_id}/set-pieces",
    response_model=list[MatchSetPieceOut],
    operation_id="listFixtureSetPieces",
    dependencies=READ,
)
async def fixture_set_pieces(session: SessionDep, fixture_id: uuid.UUID) -> list[MatchSetPieceOut]:
    """Maçın görünen duran topları, saate göre (klip bağlama ve kayıt listesi için)."""
    await _visible_match(session, fixture_id)
    rows = await session.execute(
        text(
            "select p.id, p.team_id, t.code as team_code, p.period, p.start_time_s, p.sp_type,"
            " p.outcome, p.routine_id, p.source from set_pieces p join teams t on t.id = p.team_id"
            " where p.match_id = :m order by p.period, p.start_time_s, p.id"
        ),
        {"m": fixture_id},
    )
    return [MatchSetPieceOut.model_validate(r._asdict()) for r in rows]
