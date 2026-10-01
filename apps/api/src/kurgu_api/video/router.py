"""Video ve klip uçları (SPEC §11 Video, ADR-0010).

Yükleme doğrudan depoya parçalı yapılır; API yalnızca imzalı adres verir ve tamamlanınca HLS işini
kuyruğa koyar. Oynatma listesi API'den geçer, parça adresleri kısa ömürlü imzalı adreslerdir.
"""

import logging
import math
import uuid
from typing import Annotated, Any

from arq import ArqRedis
from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.audit import write_audit
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.ingestion.router import get_queue
from kurgu_api.routines.schemas import UserRef
from kurgu_api.video.hls import TranscodeError, rewrite_playlist
from kurgu_api.video.schemas import (
    PART_SIZE,
    AssetOut,
    AssetPatch,
    ClipCreate,
    ClipOut,
    ClipPatch,
    ClipSetPiece,
    CompleteIn,
    PartUrl,
    UploadCreate,
    UploadOut,
)
from kurgu_api.video.storage import VideoStore, get_video_store

log = logging.getLogger(__name__)
router = APIRouter(tags=["video"])

READ = [Depends(require(Permission.READ_ANALYSIS))]
WRITE = [Depends(require(Permission.LIVE_TAGGING_VIDEO))]
StoreDep = Annotated[VideoStore, Depends(get_video_store)]

ASSET_SQL = """
select a.id, a.title, a.filename, a.content_type, a.size_bytes, a.match_id, a.offset_s, a.status,
  a.error, a.duration_s, a.created_at, a.created_by, u.display_name as created_by_name,
  a.storage_key, a.upload_id, a.parts, a.part_size, a.hls_key
from video_assets a left join users u on u.id = a.created_by
"""
CLIP_SQL = """
select c.id, c.asset_id, a.title as asset_title, a.match_id, c.start_s, c.end_s, c.title,
  c.created_at, p.id as sp_id, p.sp_type, t.code as team_code, p.period, p.start_time_s,
  p.outcome, p.routine_id
from video_clips c
join video_assets a on a.id = c.asset_id
left join set_pieces p on p.id = c.set_piece_id
left join teams t on t.id = p.team_id
"""


def _tenant(principal: PrincipalDep) -> uuid.UUID:
    assert principal.tenant is not None
    return principal.tenant.tenant_id


def _asset_out(row: Any) -> AssetOut:
    data = row._asdict()
    data["created_by"] = (
        UserRef(id=row.created_by, name=row.created_by_name) if row.created_by else None
    )
    return AssetOut.model_validate(data)


def _clip_out(row: Any) -> ClipOut:
    data = row._asdict()
    data["set_piece"] = (
        ClipSetPiece(
            id=row.sp_id,
            sp_type=row.sp_type,
            team_code=row.team_code,
            period=row.period,
            start_time_s=row.start_time_s,
            outcome=row.outcome,
            routine_id=row.routine_id,
        )
        if row.sp_id
        else None
    )
    return ClipOut.model_validate(data)


async def _asset(session: AsyncSession, asset_id: uuid.UUID, *, lock: bool = False) -> Any:
    sql = ASSET_SQL + " where a.id = :id" + (" for update of a" if lock else "")
    row = (await session.execute(text(sql), {"id": asset_id})).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Video not found")
    return row


async def _visible_match(session: AsyncSession, match_id: uuid.UUID) -> None:
    found = (
        await session.execute(text("select 1 from matches where id = :id"), {"id": match_id})
    ).first()
    if not found:
        raise ProblemError(404, "not-found", "Match not found")


# --- Yükleme ve varlıklar ---------------------------------------------------------------------


@router.post(
    "/video/uploads",
    response_model=UploadOut,
    operation_id="createVideoUpload",
    dependencies=WRITE,
)
async def create_upload(
    session: SessionDep,
    principal: PrincipalDep,
    store: StoreDep,
    body: UploadCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> UploadOut:
    """Parçalı yükleme başlatır; parça başına imzalı PUT adresi döner (A-60)."""
    if not idempotency_key:
        raise ProblemError(400, "idempotency-key-required", "Idempotency-Key header is required")
    if body.match_id:
        await _visible_match(session, body.match_id)
    tenant = _tenant(principal)
    existing = (
        await session.execute(
            text(ASSET_SQL + " where a.idempotency_key = :k"), {"k": idempotency_key}
        )
    ).one_or_none()
    if existing is None:
        asset_id = uuid.uuid4()
        key = f"{tenant}/videos/{asset_id}/source"
        parts = math.ceil(body.size_bytes / PART_SIZE)
        upload_id = await store.start_upload(key, body.content_type)
        await session.execute(
            text(
                "insert into video_assets (id, tenant_id, match_id, title, filename, content_type,"
                " size_bytes, part_size, parts, storage_key, upload_id, offset_s, idempotency_key,"
                " created_by) values (:id, :t, :m, :title, :fn, :ct, :size, :ps, :parts, :key,"
                " :up, :off, :idem, :u)"
            ),
            {
                "id": asset_id,
                "t": tenant,
                "m": body.match_id,
                "title": body.title,
                "fn": body.filename,
                "ct": body.content_type,
                "size": body.size_bytes,
                "ps": PART_SIZE,
                "parts": parts,
                "key": key,
                "up": upload_id,
                "off": body.offset_s,
                "idem": idempotency_key,
                "u": principal.user_id,
            },
        )
        await write_audit(
            session,
            tenant_id=tenant,
            actor_id=principal.user_id,
            action="video.upload_started",
            entity="video_assets",
            entity_id=asset_id,
            after=body.model_dump(mode="json"),
        )
        existing = await _asset(session, asset_id)
    if existing.status != "uploading":
        return UploadOut(asset=_asset_out(existing), part_size=existing.part_size, parts=[])
    urls = [
        PartUrl(number=n, url=store.part_url(existing.storage_key, existing.upload_id, n))
        for n in range(1, existing.parts + 1)
    ]
    return UploadOut(asset=_asset_out(existing), part_size=existing.part_size, parts=urls)


@router.post(
    "/video/assets/{asset_id}/complete",
    response_model=AssetOut,
    operation_id="completeVideoUpload",
    dependencies=WRITE,
)
async def complete_upload(
    session: SessionDep,
    principal: PrincipalDep,
    store: StoreDep,
    queue: Annotated[ArqRedis, Depends(get_queue)],
    asset_id: uuid.UUID,
    body: CompleteIn,
) -> AssetOut:
    """Parçaları birleştirir ve HLS dönüştürmeyi kuyruğa koyar. Tekrar çağrı zararsızdır."""
    row = await _asset(session, asset_id, lock=True)
    if row.status != "uploading":
        return _asset_out(row)
    if len(body.etags) != row.parts:
        raise ProblemError(
            422, "parts-mismatch", f"Expected {row.parts} parts, got {len(body.etags)}"
        )
    try:
        await store.complete(row.storage_key, row.upload_id, body.etags)
    except (ValueError, FileNotFoundError) as exc:
        raise ProblemError(409, "upload-incomplete", str(exc)) from exc
    await session.execute(
        text(
            "update video_assets set status = 'processing', upload_id = null, updated_at = now()"
            " where id = :id"
        ),
        {"id": asset_id},
    )
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="video.upload_completed",
        entity="video_assets",
        entity_id=asset_id,
        after={"parts": row.parts},
    )
    result = _asset_out(await _asset(session, asset_id))
    # İş, kayıt görünür olduktan sonra kuyruğa girmeli; işlem bağlamı commit ile kapanır.
    await session.commit()
    try:
        await queue.enqueue_job("transcode_video_job", str(asset_id), str(_tenant(principal)))
    except Exception:
        log.warning("transcode could not be queued for %s", asset_id, exc_info=True)
    return result


@router.get(
    "/video/assets",
    response_model=list[AssetOut],
    operation_id="listVideoAssets",
    dependencies=READ,
)
async def list_assets(
    session: SessionDep, match_id: Annotated[uuid.UUID | None, Query()] = None
) -> list[AssetOut]:
    where = " where a.match_id = :m" if match_id else ""
    rows = await session.execute(
        text(ASSET_SQL + where + " order by a.created_at desc"), {"m": match_id}
    )
    return [_asset_out(r) for r in rows]


@router.get(
    "/video/assets/{asset_id}",
    response_model=AssetOut,
    operation_id="getVideoAsset",
    dependencies=READ,
)
async def get_asset(session: SessionDep, asset_id: uuid.UUID) -> AssetOut:
    return _asset_out(await _asset(session, asset_id))


@router.patch(
    "/video/assets/{asset_id}",
    response_model=AssetOut,
    operation_id="updateVideoAsset",
    dependencies=WRITE,
)
async def update_asset(
    session: SessionDep, principal: PrincipalDep, asset_id: uuid.UUID, body: AssetPatch
) -> AssetOut:
    row = await _asset(session, asset_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is None:
        raise ProblemError(422, "invalid-title", "Title cannot be empty")
    if "offset_s" in changes and changes["offset_s"] is None:
        changes["offset_s"] = 0
    if changes.get("match_id"):
        await _visible_match(session, changes["match_id"])
        linked: int = (
            await session.execute(
                text(
                    "select count(*) from video_clips c join set_pieces p on p.id = c.set_piece_id"
                    " where c.asset_id = :a and p.match_id <> :m"
                ),
                {"a": asset_id, "m": changes["match_id"]},
            )
        ).scalar_one()
        if linked:
            raise ProblemError(409, "clips-linked", "Clips are linked to another match")
    if changes:
        columns = ", ".join(f"{k} = :{k}" for k in changes)
        await session.execute(
            text(f"update video_assets set {columns}, updated_at = now() where id = :id"),  # noqa: S608
            {"id": asset_id, **changes},
        )
        await write_audit(
            session,
            tenant_id=_tenant(principal),
            actor_id=principal.user_id,
            action="video.updated",
            entity="video_assets",
            entity_id=asset_id,
            before={k: _jsonable(getattr(row, k)) for k in changes},
            after={k: _jsonable(v) for k, v in changes.items()},
        )
    return _asset_out(await _asset(session, asset_id))


@router.delete(
    "/video/assets/{asset_id}",
    status_code=204,
    operation_id="deleteVideoAsset",
    dependencies=WRITE,
)
async def delete_asset(
    session: SessionDep, principal: PrincipalDep, store: StoreDep, asset_id: uuid.UUID
) -> Response:
    """Videoyu, kliplerini ve depodaki dosyalarını (kaynak ve HLS) siler."""
    row = await _asset(session, asset_id, lock=True)
    if row.status == "uploading" and row.upload_id:
        try:
            await store.abort(row.storage_key, row.upload_id)
        except Exception:
            log.warning("abort failed for %s", asset_id, exc_info=True)
    await session.execute(text("delete from video_assets where id = :id"), {"id": asset_id})
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="video.deleted",
        entity="video_assets",
        entity_id=asset_id,
        before={"title": row.title, "storage_key": row.storage_key},
        after={},
    )
    await session.commit()
    try:
        await store.delete_prefix(row.storage_key.rsplit("/", 1)[0])
    except Exception:
        log.warning("objects could not be deleted for %s", asset_id, exc_info=True)
    return Response(status_code=204)


@router.get(
    "/video/assets/{asset_id}/playlist",
    operation_id="getVideoPlaylist",
    dependencies=READ,
    responses={200: {"content": {"application/vnd.apple.mpegurl": {}}}},
)
async def playlist(session: SessionDep, store: StoreDep, asset_id: uuid.UUID) -> Response:
    """HLS oynatma listesi; parça satırları 10 dk geçerli imzalı adreslerle değiştirilir (A-61)."""
    row = await _asset(session, asset_id)
    if row.status != "ready" or not row.hls_key:
        raise ProblemError(409, "not-ready", "Video is not ready")
    prefix = row.hls_key.rsplit("/", 1)[0]
    raw = (await store.read_bytes(row.hls_key)).decode()
    try:
        body = rewrite_playlist(raw, lambda name: store.read_url(f"{prefix}/{name}"))
    except TranscodeError as exc:
        raise ProblemError(500, "invalid-playlist", str(exc)) from exc
    return Response(
        body,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "private, max-age=60"},
    )


def _jsonable(value: Any) -> Any:
    return str(value) if isinstance(value, uuid.UUID) else value


# --- Klipler ----------------------------------------------------------------------------------


async def _check_clip(
    session: AsyncSession,
    asset: Any,
    start_s: float,
    end_s: float,
    set_piece_id: uuid.UUID | None,
) -> None:
    if end_s <= start_s:
        raise ProblemError(422, "invalid-range", "Clip end must be after its start")
    if asset.duration_s is not None and end_s > asset.duration_s + 0.5:
        raise ProblemError(422, "invalid-range", "Clip ends after the video")
    if set_piece_id is None:
        return
    match = (
        await session.execute(
            text("select match_id from set_pieces where id = :id"), {"id": set_piece_id}
        )
    ).scalar_one_or_none()
    if match is None:
        raise ProblemError(404, "set-piece-not-found", "Set piece not found")
    if asset.match_id is None or match != asset.match_id:
        raise ProblemError(
            422, "set-piece-match-mismatch", "Set piece belongs to another match than the video"
        )


@router.get("/clips", response_model=list[ClipOut], operation_id="listClips", dependencies=READ)
async def list_clips(
    session: SessionDep,
    asset_id: Annotated[uuid.UUID | None, Query()] = None,
    set_piece_id: Annotated[uuid.UUID | None, Query()] = None,
    routine_id: Annotated[uuid.UUID | None, Query()] = None,
    match_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ClipOut]:
    """Klipler; video, duran top, rutin ya da maça göre süzülebilir."""
    filters = {
        "c.asset_id = :asset": asset_id,
        "c.set_piece_id = :sp": set_piece_id,
        "p.routine_id = :routine": routine_id,
        "a.match_id = :match": match_id,
    }
    where = [clause for clause, value in filters.items() if value is not None]
    sql = CLIP_SQL + (" where " + " and ".join(where) if where else "")
    rows = await session.execute(
        text(sql + " order by a.created_at desc, c.start_s"),
        {"asset": asset_id, "sp": set_piece_id, "routine": routine_id, "match": match_id},
    )
    return [_clip_out(r) for r in rows]


async def _clip(session: AsyncSession, clip_id: uuid.UUID) -> ClipOut:
    row = (
        await session.execute(text(CLIP_SQL + " where c.id = :id"), {"id": clip_id})
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "not-found", "Clip not found")
    return _clip_out(row)


@router.post(
    "/clips", response_model=ClipOut, status_code=201, operation_id="createClip", dependencies=WRITE
)
async def create_clip(session: SessionDep, principal: PrincipalDep, body: ClipCreate) -> ClipOut:
    asset = await _asset(session, body.asset_id)
    await _check_clip(session, asset, body.start_s, body.end_s, body.set_piece_id)
    clip_id = uuid.uuid4()
    await session.execute(
        text(
            "insert into video_clips (id, tenant_id, asset_id, start_s, end_s, title, set_piece_id,"
            " created_by) values (:id, :t, :a, :s, :e, :title, :sp, :u)"
        ),
        {
            "id": clip_id,
            "t": _tenant(principal),
            "a": body.asset_id,
            "s": body.start_s,
            "e": body.end_s,
            "title": body.title,
            "sp": body.set_piece_id,
            "u": principal.user_id,
        },
    )
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="clip.created",
        entity="video_clips",
        entity_id=clip_id,
        after=body.model_dump(mode="json"),
    )
    return await _clip(session, clip_id)


@router.patch(
    "/clips/{clip_id}", response_model=ClipOut, operation_id="updateClip", dependencies=WRITE
)
async def update_clip(
    session: SessionDep, principal: PrincipalDep, clip_id: uuid.UUID, body: ClipPatch
) -> ClipOut:
    current = await _clip(session, clip_id)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is None:
        changes["title"] = ""
    for field in ("start_s", "end_s"):
        if field in changes and changes[field] is None:
            del changes[field]
    start = changes.get("start_s", current.start_s)
    end = changes.get("end_s", current.end_s)
    link = changes.get("set_piece_id", current.set_piece.id if current.set_piece else None)
    asset = await _asset(session, current.asset_id)
    await _check_clip(session, asset, start, end, link if "set_piece_id" in changes else None)
    if changes:
        columns = ", ".join(f"{k} = :{k}" for k in changes)
        await session.execute(
            text(f"update video_clips set {columns}, updated_at = now() where id = :id"),  # noqa: S608
            {"id": clip_id, **changes},
        )
        await write_audit(
            session,
            tenant_id=_tenant(principal),
            actor_id=principal.user_id,
            action="clip.updated",
            entity="video_clips",
            entity_id=clip_id,
            before=current.model_dump(mode="json", include=set(changes) - {"set_piece_id"})
            | (
                {"set_piece_id": str(current.set_piece.id) if current.set_piece else None}
                if "set_piece_id" in changes
                else {}
            ),
            after={k: _jsonable(v) for k, v in changes.items()},
        )
    return await _clip(session, clip_id)


@router.delete("/clips/{clip_id}", status_code=204, operation_id="deleteClip", dependencies=WRITE)
async def delete_clip(session: SessionDep, principal: PrincipalDep, clip_id: uuid.UUID) -> Response:
    current = await _clip(session, clip_id)
    await session.execute(text("delete from video_clips where id = :id"), {"id": clip_id})
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action="clip.deleted",
        entity="video_clips",
        entity_id=clip_id,
        before=current.model_dump(mode="json", include={"asset_id", "start_s", "end_s", "title"}),
        after={},
    )
    return Response(status_code=204)
