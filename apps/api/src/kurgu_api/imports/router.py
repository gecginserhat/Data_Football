"""İçe aktarım uçları (SPEC §11: `POST /imports`, `GET /imports/{id}`, `POST /imports/{id}/commit`).

Yalnızca yöneticiler içe aktarır (`/admin/imports`). Yükleme `Idempotency-Key` başlığı ister:
aynı anahtar ve aynı dosya aynı kaydı döner, aynı anahtarla farklı dosya 409 alır.
"""

import datetime as dt
import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from kurgu_analytics.ingestion.imports import TEMPLATES, Kind, UnreadableFileError
from pydantic import BaseModel, Field
from sqlalchemy import text

from kurgu_api.core.problems import ProblemError
from kurgu_api.core.ratelimit import UPLOADS, rate_limit
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.imports import service
from kurgu_api.ingestion.storage import ObjectStore, get_object_store

router = APIRouter(tags=["imports"], dependencies=[Depends(require(Permission.USER_ADMIN_AUDIT))])

MAX_BYTES = 20 * 1024 * 1024
EXTENSIONS = {
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
}


def get_store() -> ObjectStore:
    return get_object_store()


StoreDep = Annotated[ObjectStore, Depends(get_store)]


class FieldOut(BaseModel):
    name: str
    required: bool


class TeamMatchOut(BaseModel):
    name: str
    team_id: uuid.UUID | None
    suggested: uuid.UUID | None
    score: float
    confirmed: bool
    manual: bool


class TeamOption(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class ImportSummary(BaseModel):
    id: uuid.UUID
    kind: Kind
    filename: str
    status: str
    season_id: uuid.UUID | None
    size_bytes: int
    created_at: dt.datetime
    committed_at: dt.datetime | None


class ImportOut(ImportSummary):
    file_columns: list[str]
    sample: list[dict[str, str]]
    fields: list[FieldOut]
    columns: dict[str, str | None]
    teams: list[TeamMatchOut]
    team_options: list[TeamOption]
    report: dict[str, Any]
    result: dict[str, Any] | None


class MappingUpdate(BaseModel):
    columns: dict[str, str | None] | None = Field(
        default=None, description="Dosya sütunu → şablon alanı (`null`: yok say)"
    )
    teams: dict[str, uuid.UUID | None] | None = Field(
        default=None, description="Dosyadaki takım adı → takım kimliği (`null`: seçimi kaldır)"
    )


COLUMNS = (
    "id, kind, filename, status, season_id, size_bytes, created_at, committed_at, mapping,"
    " quality_report, storage_key, source_hash, content_type"
)


async def _load(session: SessionDep, import_id: uuid.UUID, lock: bool = False) -> Any:
    sql = f"select {COLUMNS} from imports where id = :id"  # noqa: S608
    row = (
        await session.execute(text(sql + (" for update" if lock else "")), {"id": import_id})
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "Import not found")
    return row


def _tenant(principal: PrincipalDep) -> uuid.UUID:
    assert principal.tenant is not None
    return principal.tenant.tenant_id


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def _out(session: SessionDep, row: Any) -> ImportOut:
    mapping = _json(row.mapping) or {}
    report = _json(row.quality_report) or {}
    options = await service.team_candidates(session, row.season_id)
    return ImportOut(
        id=row.id,
        kind=row.kind,
        filename=row.filename,
        status=row.status,
        season_id=row.season_id,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
        committed_at=row.committed_at,
        file_columns=mapping.get("file_columns", []),
        sample=mapping.get("sample", []),
        fields=[FieldOut(name=f.name, required=f.required) for f in TEMPLATES[row.kind]],
        columns=mapping.get("columns", {}),
        teams=[TeamMatchOut(name=n, **t) for n, t in mapping.get("teams", {}).items()],
        team_options=[TeamOption(id=uuid.UUID(i), name=n, code=c) for i, n, c in options],
        report={k: v for k, v in report.items() if k != "result"},
        result=report.get("result"),
    )


def _analyze(
    content: bytes,
    filename: str,
    kind: Kind,
    candidates: list[tuple[str, str, str]],
    columns: dict[str, str | None] | None = None,
    team_choices: dict[str, str | None] | None = None,
) -> service.Analysis:
    try:
        return service.analyze(content, filename, kind, candidates, columns, team_choices)
    except UnreadableFileError as exc:
        raise ProblemError(422, "unreadable-file", f"File could not be read: {exc}") from exc


@router.post(
    "/imports",
    response_model=ImportOut,
    status_code=201,
    operation_id="createImport",
    dependencies=[Depends(rate_limit(UPLOADS))],
)
async def create_import(
    session: SessionDep,
    principal: PrincipalDep,
    store: StoreDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[Kind, Form()],
    season_id: Annotated[uuid.UUID, Form()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> ImportOut:
    tenant_id = _tenant(principal)
    filename = (file.filename or "upload.csv").rsplit("/", 1)[-1][:255]
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in EXTENSIONS:
        raise ProblemError(415, "unsupported-file-type", "Only CSV, TSV and XLSX files")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ProblemError(413, "file-too-large", f"Maximum size is {MAX_BYTES} bytes")
    digest = hashlib.sha256(content).hexdigest()

    existing = (
        await session.execute(
            text(f"select {COLUMNS} from imports where idempotency_key = :k"),  # noqa: S608
            {"k": idempotency_key},
        )
    ).first()
    if existing is not None:
        if existing.source_hash != digest or existing.kind != kind:
            raise ProblemError(409, "idempotency-key-reused", "Key was used for another upload")
        return await _out(session, existing)

    visible = await session.execute(text("select 1 from seasons where id = :s"), {"s": season_id})
    if visible.first() is None:
        raise ProblemError(422, "unknown-season", "Season not found or not licensed")

    candidates = await service.team_candidates(session, season_id)
    analysis = _analyze(content, filename, kind, candidates)
    key = f"imports/{tenant_id}/{digest}"
    await store.put(key, content, EXTENSIONS[extension])
    import_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into imports (tenant_id, kind, filename, content_type, size_bytes,"
                " source_hash, storage_key, status, mapping, quality_report, season_id,"
                " idempotency_key, created_by) values (:tenant, :kind, :filename, :ctype, :size,"
                " :hash, :key, :status, cast(:mapping as jsonb), cast(:report as jsonb), :season,"
                " :idem, :user) returning id"
            ),
            {
                "tenant": tenant_id,
                "kind": kind,
                "filename": filename,
                "ctype": EXTENSIONS[extension],
                "size": len(content),
                "hash": digest,
                "key": key,
                "status": analysis.status,
                "mapping": json.dumps(analysis.mapping_json()),
                "report": json.dumps(analysis.report),
                "season": season_id,
                "idem": idempotency_key,
                "user": principal.user_id,
            },
        )
    ).scalar_one()
    await service.audit(
        session,
        tenant_id,
        principal.user_id,
        "import.upload",
        import_id,
        {"kind": kind, "filename": filename, "status": analysis.status},
    )
    return await _out(session, await _load(session, import_id))


@router.get("/imports", response_model=list[ImportSummary], operation_id="listImports")
async def list_imports(session: SessionDep) -> list[ImportSummary]:
    rows = (
        await session.execute(
            text(f"select {COLUMNS} from imports order by created_at desc limit 50")  # noqa: S608
        )
    ).all()
    return [ImportSummary.model_validate(r._asdict()) for r in rows]


@router.get("/imports/{import_id}", response_model=ImportOut, operation_id="getImport")
async def get_import(import_id: uuid.UUID, session: SessionDep) -> ImportOut:
    return await _out(session, await _load(session, import_id))


@router.put(
    "/imports/{import_id}/mapping", response_model=ImportOut, operation_id="updateImportMapping"
)
async def update_mapping(
    import_id: uuid.UUID,
    body: MappingUpdate,
    session: SessionDep,
    principal: PrincipalDep,
    store: StoreDep,
) -> ImportOut:
    """Sütun ya da takım eşleştirmesini değiştirir; dosya yeniden doğrulanır."""
    row = await _load(session, import_id, lock=True)
    if row.status in ("committed", "failed"):
        raise ProblemError(409, "import-closed", f"Import is {row.status}")
    mapping = _json(row.mapping) or {}
    kind: Kind = row.kind

    columns = body.columns if body.columns is not None else mapping.get("columns")
    if body.columns is not None:
        allowed = {f.name for f in TEMPLATES[kind]}
        targets = [t for t in body.columns.values() if t]
        unknown = sorted(set(targets) - allowed)
        if unknown:
            raise ProblemError(422, "unknown-field", f"Unknown fields: {', '.join(unknown)}")
        if len(targets) != len(set(targets)):
            raise ProblemError(422, "duplicate-field", "A field can be mapped only once")

    candidates = await service.team_candidates(session, row.season_id)
    choices: dict[str, str | None] = {
        name: t["team_id"] for name, t in mapping.get("teams", {}).items() if t.get("manual")
    }
    if body.teams is not None:
        valid = {c[0] for c in candidates}
        for name, team_id in body.teams.items():
            if team_id is not None and str(team_id) not in valid:
                raise ProblemError(422, "unknown-team", f"Team not available: {name}")
            choices[name] = str(team_id) if team_id else None

    content = await store.get(row.storage_key)
    analysis = _analyze(content, row.filename, kind, candidates, columns, choices)
    await session.execute(
        text(
            "update imports set status = :status, mapping = cast(:mapping as jsonb),"
            " quality_report = cast(:report as jsonb) where id = :id"
        ),
        {
            "id": import_id,
            "status": analysis.status,
            "mapping": json.dumps(analysis.mapping_json()),
            "report": json.dumps(analysis.report),
        },
    )
    await service.audit(
        session,
        _tenant(principal),
        principal.user_id,
        "import.mapping",
        import_id,
        {"status": analysis.status},
    )
    return await _out(session, await _load(session, import_id))


@router.post("/imports/{import_id}/commit", response_model=ImportOut, operation_id="commitImport")
async def commit_import(
    import_id: uuid.UUID, session: SessionDep, principal: PrincipalDep, store: StoreDep
) -> ImportOut:
    """Doğrulanmış içe aktarımı kiracının tablolarına yazar. Karantinadaki ya da takım onayı
    bekleyen içe aktarım 409 alır."""
    row = await _load(session, import_id, lock=True)
    if row.status != "validated":
        raise ProblemError(
            409, "import-not-ready", f"Import is {row.status}", extra={"status": row.status}
        )
    tenant_id = _tenant(principal)
    mapping = _json(row.mapping) or {}
    kind: Kind = row.kind
    candidates = await service.team_candidates(session, row.season_id)
    choices = {n: t["team_id"] for n, t in mapping.get("teams", {}).items() if t.get("manual")}
    content = await store.get(row.storage_key)
    analysis = _analyze(content, row.filename, kind, candidates, mapping.get("columns"), choices)
    if analysis.status != "validated" or analysis.typed is None:
        # Dosya değişmez; burada ancak takım listesi değiştiyse (örneğin lisans) kalınır.
        raise ProblemError(409, "import-not-ready", "Validation no longer passes")
    teams = {n: uuid.UUID(t["team_id"]) for n, t in analysis.teams.items()}
    if kind == "team_season_stats":
        result = await service.commit_team_stats(
            session, tenant_id, row.season_id, analysis.typed, teams
        )
    else:
        result = await service.commit_events(
            session, tenant_id, row.season_id, analysis.typed, teams, import_id
        )
    report = analysis.report | {"result": result}
    await session.execute(
        text(
            "update imports set status = 'committed', committed_at = now(),"
            " quality_report = cast(:report as jsonb) where id = :id"
        ),
        {"id": import_id, "report": json.dumps(report)},
    )
    await service.audit(
        session, tenant_id, principal.user_id, "import.commit", import_id, {"result": result}
    )
    return await _out(session, await _load(session, import_id))
