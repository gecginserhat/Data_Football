"""Rutin uçları (SPEC §11): şablonlar, kütüphane, sürümler ve dışa aktarım.

Okuma analiz okuma iznine, yazma rutin düzenleme iznine bağlıdır (SPEC §12.1). Rutinler
kiracıya aittir (RLS). Her kayıt değişmez bir sürüm açar; silme yoktur, arşiv vardır (A-41).
"""

import datetime as dt
import json
import math
import unicodedata
import uuid
from typing import Annotated, Any
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from kurgu_analytics.metrics import routine_metrics
from kurgu_analytics.reports.diagram import Diagram
from kurgu_analytics.reports.routine_sheet import build_meta, render_pdf, render_png
from sqlalchemy import text

from kurgu_api.core.audit import write_audit
from kurgu_api.core.http import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    decode_cursor,
    encode_cursor,
    etag_response,
)
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.routines.schemas import (
    RateOut,
    RoutineCreate,
    RoutineFromTemplate,
    RoutineOut,
    RoutinePage,
    RoutinePatch,
    RoutineStatsOut,
    RoutineSummary,
    RoutineUpdate,
    SpType,
    TemplateList,
    TemplateOut,
    UserRef,
    VersionOut,
    VersionSummary,
)

read = [Depends(require(Permission.READ_ANALYSIS))]
write = [Depends(require(Permission.EDIT_ROUTINES))]
router = APIRouter(tags=["routines"])
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]

ROUTINE_SQL = """
select r.id, r.name, r.sp_type, r.side, r.is_defensive, r.from_template, r.current_version,
       r.archived_at, r.created_at, r.updated_at, r.updated_by, u.display_name as updated_by_name,
       v.diagram
from routines r
join routine_versions v on v.routine_id = r.id and v.version = r.current_version
left join users u on u.id = r.updated_by
"""

VERSION_SQL = """
select v.version, v.name, v.message, v.created_at, v.created_by,
       u.display_name as created_by_name, v.side, v.notes, v.when_to_use, v.diagram
from routine_versions v left join users u on u.id = v.created_by
"""


def _tenant(principal: PrincipalDep) -> uuid.UUID:
    assert principal.tenant is not None
    return principal.tenant.tenant_id


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _user(user_id: uuid.UUID | None, name: str | None) -> UserRef | None:
    return UserRef(id=user_id, name=name) if user_id else None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    f = float(value)
    return None if math.isnan(f) else f


EMPTY_STATS = RoutineStatsOut(
    uses=0,
    matches=0,
    goals=0,
    xg=0.0,
    xg_per_use=None,
    first_contact=RateOut(value=None, shrunk=None, low=None, high=None, trials=0),
    shot=RateOut(value=None, shrunk=None, low=None, high=None, trials=0),
    low_sample=True,
)


async def _stats(session: SessionDep) -> dict[uuid.UUID, RoutineStatsOut]:
    """Kiracının tüm rutinleri; önsel kulübün rutinlerinden kestirildiği için hep birlikte."""
    rows = (await session.execute(text("select * from v_routine_stats"))).mappings().all()
    if not rows:
        return {}
    metrics = routine_metrics(pd.DataFrame([dict(r) for r in rows]))
    out: dict[uuid.UUID, RoutineStatsOut] = {}
    for m in metrics.to_dict("records"):
        out[m["routine_id"]] = RoutineStatsOut(
            uses=m["uses"],
            matches=m["matches"],
            goals=m["goals"],
            xg=float(m["xg"]),
            xg_per_use=_num(m["xg_per_use"]),
            first_contact=RateOut(
                value=_num(m["first_contact_rate"]),
                shrunk=_num(m["first_contact_shrunk"]),
                low=_num(m["first_contact_low"]),
                high=_num(m["first_contact_high"]),
                trials=m["first_contact_trials"],
            ),
            shot=RateOut(
                value=_num(m["shot_rate"]),
                shrunk=_num(m["shot_shrunk"]),
                low=_num(m["shot_low"]),
                high=_num(m["shot_high"]),
                trials=m["uses"],
            ),
            low_sample=bool(m["low_sample"]),
        )
    return out


def _summary(row: Any, stats: dict[uuid.UUID, RoutineStatsOut]) -> RoutineSummary:
    return RoutineSummary(
        id=row.id,
        name=row.name,
        sp_type=row.sp_type,
        side=row.side,
        is_defensive=row.is_defensive,
        from_template=row.from_template,
        current_version=row.current_version,
        archived=row.archived_at is not None,
        updated_at=row.updated_at,
        updated_by=_user(row.updated_by, row.updated_by_name),
        diagram=Diagram.model_validate(_json(row.diagram)),
        stats=stats.get(row.id, EMPTY_STATS),
    )


def _version(row: Any) -> VersionOut:
    return VersionOut(
        version=row.version,
        name=row.name,
        message=row.message,
        created_at=row.created_at,
        created_by=_user(row.created_by, row.created_by_name),
        side=row.side,
        notes=row.notes,
        when_to_use=row.when_to_use,
        diagram=Diagram.model_validate(_json(row.diagram)),
    )


async def _routine_row(session: SessionDep, routine_id: uuid.UUID, lock: bool = False) -> Any:
    sql = ROUTINE_SQL + " where r.id = :id" + (" for update of r" if lock else "")
    row = (await session.execute(text(sql), {"id": routine_id})).first()
    if row is None:
        raise ProblemError(404, "not-found", "Routine not found")
    return row


async def _version_row(session: SessionDep, routine_id: uuid.UUID, version: int) -> Any:
    row = (
        await session.execute(
            text(VERSION_SQL + " where v.routine_id = :id and v.version = :v"),
            {"id": routine_id, "v": version},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "Routine version not found")
    return row


async def _out(session: SessionDep, routine_id: uuid.UUID) -> RoutineOut:
    row = await _routine_row(session, routine_id)
    stats = await _stats(session)
    current = _version(await _version_row(session, routine_id, row.current_version))
    return RoutineOut(
        id=row.id,
        name=row.name,
        sp_type=row.sp_type,
        side=row.side,
        is_defensive=row.is_defensive,
        from_template=row.from_template,
        current_version=row.current_version,
        archived=row.archived_at is not None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=current,
        stats=stats.get(row.id, EMPTY_STATS),
    )


async def _insert_version(
    session: SessionDep,
    *,
    tenant_id: uuid.UUID,
    routine_id: uuid.UUID,
    version: int,
    name: str,
    side: str | None,
    notes: str,
    when_to_use: str,
    diagram: Diagram,
    message: str | None,
    user_id: uuid.UUID,
) -> None:
    await session.execute(
        text(
            "insert into routine_versions (tenant_id, routine_id, version, name, side, notes,"
            " when_to_use, diagram, message, created_by) values (:tenant, :routine, :version,"
            " :name, :side, :notes, :when, cast(:diagram as jsonb), :message, :user)"
        ),
        {
            "tenant": tenant_id,
            "routine": routine_id,
            "version": version,
            "name": name,
            "side": side,
            "notes": notes,
            "when": when_to_use,
            "diagram": json.dumps(diagram.dump()),
            "message": message,
            "user": user_id,
        },
    )


async def _create(
    session: SessionDep,
    principal: PrincipalDep,
    body: RoutineCreate,
    from_template: str | None,
) -> uuid.UUID:
    tenant_id = _tenant(principal)
    routine_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into routines (tenant_id, name, sp_type, side, is_defensive, from_template,"
                " created_by, updated_by) values (:tenant, :name, :sp_type, :side, :defensive,"
                " :tpl, :user, :user) returning id"
            ),
            {
                "tenant": tenant_id,
                "name": body.name.strip(),
                "sp_type": body.sp_type,
                "side": body.side,
                "defensive": body.is_defensive,
                "tpl": from_template,
                "user": principal.user_id,
            },
        )
    ).scalar_one()
    await _insert_version(
        session,
        tenant_id=tenant_id,
        routine_id=routine_id,
        version=1,
        name=body.name.strip(),
        side=body.side,
        notes=body.notes,
        when_to_use=body.when_to_use,
        diagram=body.diagram,
        message=None,
        user_id=principal.user_id,
    )
    await write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=principal.user_id,
        action="routine.create",
        entity="routines",
        entity_id=routine_id,
        after={"name": body.name.strip(), "sp_type": body.sp_type, "from_template": from_template},
    )
    return routine_id


@router.get(
    "/routine-templates",
    response_model=list[TemplateOut],
    operation_id="listRoutineTemplates",
    dependencies=read,
)
async def list_templates(request: Request, session: SessionDep) -> Response:
    rows = (
        await session.execute(
            text(
                "select id, name, sp_type, side, is_defensive, when_to_use, notes, diagram"
                " from routine_templates order by sort_order, id"
            )
        )
    ).all()
    items = [TemplateOut.model_validate({**r._asdict(), "diagram": _json(r.diagram)}) for r in rows]
    return etag_response(request, TemplateList(items))


@router.get("/routines", response_model=RoutinePage, operation_id="listRoutines", dependencies=read)
async def list_routines(
    session: SessionDep,
    sp_type: Annotated[SpType | None, Query(alias="type")] = None,
    archived: bool = False,
    q: Annotated[str | None, Query(max_length=120)] = None,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> RoutinePage:
    where = ["(r.archived_at is not null) = :archived"]
    params: dict[str, Any] = {"archived": archived, "limit": limit + 1}
    if sp_type:
        where.append("r.sp_type = :sp_type")
        params["sp_type"] = sp_type
    if q:
        where.append("r.name ilike :q")
        params["q"] = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
    key = decode_cursor(cursor, 2)
    if key:
        where.append("(r.updated_at, r.id) < (cast(:k_at as timestamptz), cast(:k_id as uuid))")
        params["k_at"] = dt.datetime.fromisoformat(key[0])
        params["k_id"] = key[1]
    sql = ROUTINE_SQL + " where " + " and ".join(where) + " order by r.updated_at desc, r.id desc"
    rows = (await session.execute(text(sql + " limit :limit"), params)).all()
    stats = await _stats(session)
    items = [_summary(r, stats) for r in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor([last.updated_at.isoformat(), str(last.id)])
    return RoutinePage(items=items, next_cursor=next_cursor)


@router.post(
    "/routines",
    response_model=RoutineOut,
    status_code=201,
    operation_id="createRoutine",
    dependencies=write,
)
async def create_routine(
    body: RoutineCreate, session: SessionDep, principal: PrincipalDep
) -> RoutineOut:
    return await _out(session, await _create(session, principal, body, None))


@router.post(
    "/routines/from-template/{template_id}",
    response_model=RoutineOut,
    status_code=201,
    operation_id="createRoutineFromTemplate",
    dependencies=write,
)
async def create_from_template(
    template_id: str,
    session: SessionDep,
    principal: PrincipalDep,
    body: RoutineFromTemplate | None = None,
) -> RoutineOut:
    row = (
        await session.execute(
            text("select * from routine_templates where id = :id"), {"id": template_id}
        )
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "Routine template not found")
    create = RoutineCreate(
        name=(body.name if body and body.name else row.name),
        sp_type=row.sp_type,
        side=row.side,
        is_defensive=row.is_defensive,
        notes=row.notes,
        when_to_use=row.when_to_use,
        diagram=Diagram.model_validate(_json(row.diagram)),
    )
    return await _out(session, await _create(session, principal, create, template_id))


@router.get(
    "/routines/{routine_id}",
    response_model=RoutineOut,
    operation_id="getRoutine",
    dependencies=read,
)
async def get_routine(routine_id: uuid.UUID, request: Request, session: SessionDep) -> Response:
    return etag_response(request, await _out(session, routine_id))


def _same_content(row: Any, body: RoutineUpdate) -> bool:
    current = Diagram.model_validate(_json(row.diagram)).dump()
    return (
        current == body.diagram.dump()
        and row.name == body.name.strip()
        and row.side == body.side
        and row.notes == body.notes
        and row.when_to_use == body.when_to_use
    )


@router.put(
    "/routines/{routine_id}",
    response_model=RoutineOut,
    operation_id="updateRoutine",
    dependencies=write,
    responses={409: {"description": "`base_version` is not the current version"}},
)
async def update_routine(
    routine_id: uuid.UUID, body: RoutineUpdate, session: SessionDep, principal: PrincipalDep
) -> RoutineOut:
    routine = await _routine_row(session, routine_id, lock=True)
    if routine.archived_at is not None:
        raise ProblemError(409, "archived", "Archived routines cannot be edited")
    if body.base_version != routine.current_version:
        raise ProblemError(
            409,
            "version-conflict",
            "Routine was changed by someone else",
            extra={"current_version": routine.current_version},
        )
    current = await _version_row(session, routine_id, routine.current_version)
    if _same_content(current, body):
        return await _out(session, routine_id)
    version = routine.current_version + 1
    tenant_id = _tenant(principal)
    await _insert_version(
        session,
        tenant_id=tenant_id,
        routine_id=routine_id,
        version=version,
        name=body.name.strip(),
        side=body.side,
        notes=body.notes,
        when_to_use=body.when_to_use,
        diagram=body.diagram,
        message=body.message.strip() if body.message and body.message.strip() else None,
        user_id=principal.user_id,
    )
    await session.execute(
        text(
            "update routines set name = :name, side = :side, current_version = :version,"
            " updated_by = :user, updated_at = now() where id = :id"
        ),
        {
            "name": body.name.strip(),
            "side": body.side,
            "version": version,
            "user": principal.user_id,
            "id": routine_id,
        },
    )
    await write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=principal.user_id,
        action="routine.version",
        entity="routines",
        entity_id=routine_id,
        before={"version": routine.current_version},
        after={"version": version, "name": body.name.strip(), "message": body.message},
    )
    return await _out(session, routine_id)


@router.patch(
    "/routines/{routine_id}",
    response_model=RoutineOut,
    operation_id="patchRoutine",
    dependencies=write,
)
async def patch_routine(
    routine_id: uuid.UUID, body: RoutinePatch, session: SessionDep, principal: PrincipalDep
) -> RoutineOut:
    routine = await _routine_row(session, routine_id, lock=True)
    if (routine.archived_at is not None) != body.archived:
        await session.execute(
            text(
                "update routines set archived_at = case when :archived then now() end,"
                " updated_by = :user, updated_at = now() where id = :id"
            ),
            {"archived": body.archived, "user": principal.user_id, "id": routine_id},
        )
        await write_audit(
            session,
            tenant_id=_tenant(principal),
            actor_id=principal.user_id,
            action="routine.archive" if body.archived else "routine.unarchive",
            entity="routines",
            entity_id=routine_id,
            after={"archived": body.archived},
        )
    return await _out(session, routine_id)


@router.get(
    "/routines/{routine_id}/versions",
    response_model=list[VersionSummary],
    operation_id="listRoutineVersions",
    dependencies=read,
)
async def list_versions(routine_id: uuid.UUID, session: SessionDep) -> list[VersionSummary]:
    await _routine_row(session, routine_id)
    rows = (
        await session.execute(
            text(VERSION_SQL + " where v.routine_id = :id order by v.version desc"),
            {"id": routine_id},
        )
    ).all()
    return [
        VersionSummary(
            version=r.version,
            name=r.name,
            message=r.message,
            created_at=r.created_at,
            created_by=_user(r.created_by, r.created_by_name),
        )
        for r in rows
    ]


@router.get(
    "/routines/{routine_id}/versions/{version}",
    response_model=VersionOut,
    operation_id="getRoutineVersion",
    dependencies=read,
)
async def get_version(
    routine_id: uuid.UUID, version: int, request: Request, session: SessionDep
) -> Response:
    return etag_response(request, _version(await _version_row(session, routine_id, version)))


EXPORT_TYPES = {"pdf": "application/pdf", "png": "image/png"}
TR_ASCII = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")


def _filename(name: str, version: int, ext: str) -> str:
    """ASCII dosya adı: `arka-direk-v3.pdf` (Türkçe harfler sadeleştirilir)."""
    ascii_name = (
        unicodedata.normalize("NFKD", name.translate(TR_ASCII)).encode("ascii", "ignore").decode()
    )
    slug = "-".join("".join(c if c.isalnum() else " " for c in ascii_name).lower().split())
    return f"{slug or 'rutin'}-v{version}.{ext}"


@router.get(
    "/routines/{routine_id}/versions/{version}/export",
    operation_id="exportRoutineVersion",
    dependencies=read,
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}, "image/png": {}},
            "description": "Rutin sayfası (PDF, A4) ya da saha görseli (PNG)",
        }
    },
)
async def export_version(
    routine_id: uuid.UUID,
    version: int,
    session: SessionDep,
    principal: PrincipalDep,
    export_format: Annotated[str, Query(alias="format", pattern="^(pdf|png)$")] = "pdf",
    lang: Annotated[str, Query(pattern="^(tr|en)$")] = "tr",
) -> Response:
    routine = await _routine_row(session, routine_id)
    row = await _version_row(session, routine_id, version)
    diagram = Diagram.model_validate(_json(row.diagram))
    assert principal.tenant is not None
    meta = build_meta(
        name=row.name,
        sp_type=routine.sp_type,
        side=row.side,
        is_defensive=routine.is_defensive,
        version=row.version,
        saved_at=row.created_at.astimezone(dt.UTC),
        saved_by=row.created_by_name,
        club=principal.tenant.tenant_name,
        notes=row.notes,
        when_to_use=row.when_to_use,
        lang=lang,
    )
    renderer = render_pdf if export_format == "pdf" else render_png
    content = await run_in_threadpool(renderer, diagram, meta)
    filename = _filename(row.name, row.version, export_format)
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=EXPORT_TYPES[export_format],
        headers={"Content-Disposition": disposition, "Cache-Control": "private, max-age=300"},
    )
