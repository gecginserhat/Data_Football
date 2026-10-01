"""KVKK uçları: rıza, envanter ve saklama, veri sahibi talepleri (SPEC §12.3, ADR-0019, A-92).

Erişim: oyuncu yalnız kendi kaydı için rıza verir, geri çeker, verisini indirir ve silme talebi
açar. Performans ve sağlık ekibi (`load_wellness` tam) kâğıt rızayı kaydeder, rızayı geri çeker,
dışa aktarır ve oyuncu adına talep açar. Yönetici (`user_admin_audit`) envanteri ve saklama
sürelerini yönetir, talepleri karara bağlar; iyi oluş puanlarını görmez. Her yazma ve dışa
aktarma denetim kaydına girer.
"""

import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from kurgu_api.core.audit import write_audit
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission, scope_for
from kurgu_api.identity.service import Principal
from kurgu_api.privacy.consent import CONSENT_TEXT, CONSENT_VERSION
from kurgu_api.privacy.inventory import INVENTORY
from kurgu_api.privacy.schemas import (
    ConsentIn,
    ConsentOut,
    ConsentStatusOut,
    ConsentTextOut,
    DecisionIn,
    InventoryItemOut,
    PlayerExport,
    PrivacySettingsOut,
    RequestDecisionOut,
    RequestIn,
    RequestOut,
    Retention,
)
from kurgu_api.privacy.service import (
    REQUEST_SQL,
    active_consent,
    consent_history,
    consent_out,
    erase_player,
    export_player,
    request_out,
    retention_for,
)

router = APIRouter(tags=["privacy"])

admin = [Depends(require(Permission.USER_ADMIN_AUDIT))]

Access = Literal["own", "staff", "admin"]


def _tenant(principal: Principal) -> uuid.UUID:
    if principal.tenant is None:
        raise ProblemError(400, "tenant-required", "Select a tenant")
    return principal.tenant.tenant_id


def _access(principal: Principal, player_id: uuid.UUID) -> Access:
    _tenant(principal)
    assert principal.tenant is not None
    wellness = scope_for(principal.roles, Permission.LOAD_WELLNESS)
    if wellness == "all":
        return "staff"
    if wellness == "own" and principal.tenant.player_id == player_id:
        return "own"
    if scope_for(principal.roles, Permission.USER_ADMIN_AUDIT) == "all":
        return "admin"
    raise ProblemError(403, "forbidden", "No access to this player's privacy records")


async def _player_name(session: SessionDep, player_id: uuid.UUID) -> str:
    name = (
        await session.execute(
            text("select name from squad_players where id = :p"), {"p": player_id}
        )
    ).scalar_one_or_none()
    if name is None:
        raise ProblemError(404, "not-found", "Squad player not found")
    return str(name)


async def _audit(
    session: SessionDep,
    principal: Principal,
    action: str,
    entity: str,
    entity_id: uuid.UUID,
    after: dict[str, object],
) -> None:
    await write_audit(
        session,
        tenant_id=_tenant(principal),
        actor_id=principal.user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        after=after,
    )


@router.get("/privacy/consent-text", response_model=ConsentTextOut, operation_id="getConsentText")
async def consent_text(principal: PrincipalDep) -> ConsentTextOut:
    _tenant(principal)
    return ConsentTextOut(version=CONSENT_VERSION, text=CONSENT_TEXT)


async def _status(
    session: SessionDep, principal: Principal, player_id: uuid.UUID, access: Access
) -> ConsentStatusOut:
    name = await _player_name(session, player_id)
    return ConsentStatusOut(
        squad_player_id=player_id,
        player_name=name,
        active=await active_consent(session, player_id),
        history=await consent_history(session, player_id),
        current_version=CONSENT_VERSION,
        can_record_paper=access == "staff",
        can_give_self=access == "own",
    )


@router.get(
    "/squad/{player_id}/consent", response_model=ConsentStatusOut, operation_id="getConsent"
)
async def get_consent(
    session: SessionDep, principal: PrincipalDep, player_id: uuid.UUID
) -> ConsentStatusOut:
    return await _status(session, principal, player_id, _access(principal, player_id))


@router.post(
    "/squad/{player_id}/consent",
    response_model=ConsentStatusOut,
    status_code=201,
    operation_id="giveConsent",
)
async def give_consent(
    session: SessionDep, principal: PrincipalDep, player_id: uuid.UUID, body: ConsentIn
) -> ConsentStatusOut:
    access = _access(principal, player_id)
    if access == "admin":
        raise ProblemError(403, "forbidden", "Administrators cannot record health consent")
    if access == "own" and body.method != "self":
        raise ProblemError(422, "invalid-method", "Players give consent themselves")
    if access == "staff" and body.method != "paper":
        raise ProblemError(422, "invalid-method", "Staff record signed paper consent")
    if body.text_version != CONSENT_VERSION:
        raise ProblemError(409, "consent-text-outdated", "The consent text has changed")
    await _player_name(session, player_id)
    if await active_consent(session, player_id) is not None:
        raise ProblemError(409, "consent-exists", "An active consent already exists")
    row = (
        await session.execute(
            text(
                "insert into health_consents (tenant_id, squad_player_id, text_version, method,"
                " reference, recorded_by) values (:t, :p, :v, :m, :r, :u)"
                " returning id, text_version, method, reference, given_at, withdrawn_at, is_demo"
            ),
            {
                "t": _tenant(principal),
                "p": player_id,
                "v": body.text_version,
                "m": body.method,
                "r": body.reference if body.method == "paper" else None,
                "u": principal.user_id,
            },
        )
    ).one()
    await _audit(
        session,
        principal,
        "consent.give",
        "health_consents",
        row.id,
        {"squad_player_id": str(player_id), "method": body.method, "version": body.text_version},
    )
    return await _status(session, principal, player_id, access)


@router.delete(
    "/squad/{player_id}/consent", response_model=ConsentStatusOut, operation_id="withdrawConsent"
)
async def withdraw_consent(
    session: SessionDep, principal: PrincipalDep, player_id: uuid.UUID
) -> ConsentStatusOut:
    access = _access(principal, player_id)
    if access == "admin":
        raise ProblemError(403, "forbidden", "Administrators cannot change health consent")
    current = await active_consent(session, player_id)
    if current is None:
        raise ProblemError(404, "not-found", "No active consent")
    await session.execute(
        text("update health_consents set withdrawn_at = now(), withdrawn_by = :u where id = :id"),
        {"id": current.id, "u": principal.user_id},
    )
    await _audit(
        session,
        principal,
        "consent.withdraw",
        "health_consents",
        current.id,
        {"squad_player_id": str(player_id)},
    )
    return await _status(session, principal, player_id, access)


@router.get(
    "/squad/{player_id}/export",
    response_model=PlayerExport,
    operation_id="exportPlayerData",
)
async def export_data(
    session: SessionDep, principal: PrincipalDep, player_id: uuid.UUID
) -> Response:
    """Veri sahibinin verisinin kopyası (KVKK m.11); dosya olarak indirilir."""
    access = _access(principal, player_id)
    if access == "admin":
        raise ProblemError(403, "forbidden", "Administrators cannot read wellness scores")
    await _player_name(session, player_id)
    tenant = _tenant(principal)
    data = PlayerExport.model_validate(await export_player(session, tenant, player_id))
    await _audit(
        session,
        principal,
        "privacy.export",
        "squad_players",
        player_id,
        {"wellness": len(data.wellness), "loads": len(data.loads)},
    )
    return Response(
        data.model_dump_json(indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="kurgu-veri-{player_id}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/privacy/settings",
    response_model=PrivacySettingsOut,
    operation_id="getPrivacySettings",
    dependencies=admin,
)
async def privacy_settings(session: SessionDep, principal: PrincipalDep) -> PrivacySettingsOut:
    tenant = _tenant(principal)
    retention = await retention_for(session, tenant)
    region: str = (
        await session.execute(text("select data_region from tenants where id = :t"), {"t": tenant})
    ).scalar_one()
    days = retention.model_dump()
    return PrivacySettingsOut(
        retention=retention,
        data_region=region,
        inventory=[
            InventoryItemOut(
                key=item.key,
                title=item.title,
                tables=list(item.tables),
                fields=list(item.fields),
                subjects=item.subjects,
                purpose=item.purpose,
                legal_basis=item.legal_basis,
                special_category=item.special_category,
                encrypted=item.encrypted,
                retention=item.retention,
                retention_days=days[item.retention_key] if item.retention_key else None,
            )
            for item in INVENTORY
        ],
    )


@router.put(
    "/privacy/retention",
    response_model=Retention,
    operation_id="updateRetention",
    dependencies=admin,
)
async def update_retention(
    session: SessionDep, principal: PrincipalDep, body: Retention
) -> Retention:
    tenant = _tenant(principal)
    before = await retention_for(session, tenant)
    await session.execute(
        text(
            "update tenants set settings = settings || jsonb_build_object('retention',"
            " cast(:r as jsonb)) where id = :t"
        ),
        {"t": tenant, "r": json.dumps(body.model_dump())},
    )
    await write_audit(
        session,
        tenant_id=tenant,
        actor_id=principal.user_id,
        action="privacy.retention",
        entity="tenants",
        entity_id=tenant,
        before=before.model_dump(),
        after=body.model_dump(),
    )
    return body


@router.get(
    "/privacy/requests", response_model=list[RequestOut], operation_id="listPrivacyRequests"
)
async def list_requests(session: SessionDep, principal: PrincipalDep) -> list[RequestOut]:
    _tenant(principal)
    assert principal.tenant is not None
    roles = principal.roles
    if (
        scope_for(roles, Permission.USER_ADMIN_AUDIT) == "all"
        or scope_for(roles, Permission.LOAD_WELLNESS) == "all"
    ):
        rows = await session.execute(text(REQUEST_SQL + " order by r.created_at desc"))
    elif scope_for(roles, Permission.LOAD_WELLNESS) == "own" and principal.tenant.player_id:
        rows = await session.execute(
            text(REQUEST_SQL + " where r.squad_player_id = :p order by r.created_at desc"),
            {"p": principal.tenant.player_id},
        )
    else:
        raise ProblemError(403, "forbidden", "No access to privacy requests")
    return [request_out(r) for r in rows]


@router.post(
    "/privacy/requests",
    response_model=RequestOut,
    status_code=201,
    operation_id="createPrivacyRequest",
)
async def create_request(
    session: SessionDep, principal: PrincipalDep, body: RequestIn
) -> RequestOut:
    access = _access(principal, body.squad_player_id)
    if access == "admin":
        raise ProblemError(403, "forbidden", "Requests come from the player or the staff")
    await _player_name(session, body.squad_player_id)
    existing = (
        await session.execute(
            text(
                "select 1 from privacy_requests where squad_player_id = :p and kind = :k"
                " and status = 'open'"
            ),
            {"p": body.squad_player_id, "k": body.kind},
        )
    ).first()
    if existing:
        raise ProblemError(409, "request-exists", "An open request already exists")
    request_id: uuid.UUID = (
        await session.execute(
            text(
                "insert into privacy_requests (tenant_id, squad_player_id, kind, reason,"
                " requested_by) values (:t, :p, :k, :r, :u) returning id"
            ),
            {
                "t": _tenant(principal),
                "p": body.squad_player_id,
                "k": body.kind,
                "r": body.reason,
                "u": principal.user_id,
            },
        )
    ).scalar_one()
    await _audit(
        session,
        principal,
        "privacy.request",
        "privacy_requests",
        request_id,
        {"squad_player_id": str(body.squad_player_id), "kind": body.kind},
    )
    row = (await session.execute(text(REQUEST_SQL + " where r.id = :id"), {"id": request_id})).one()
    return request_out(row)


@router.post(
    "/privacy/requests/{request_id}/decision",
    response_model=RequestDecisionOut,
    operation_id="decidePrivacyRequest",
    dependencies=admin,
)
async def decide_request(
    session: SessionDep, principal: PrincipalDep, request_id: uuid.UUID, body: DecisionIn
) -> RequestDecisionOut:
    row = (
        await session.execute(
            text(REQUEST_SQL + " where r.id = :id for update of r"), {"id": request_id}
        )
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "Request not found")
    if row.status != "open":
        raise ProblemError(409, "request-closed", "The request is already decided")
    erased = await erase_player(session, row.squad_player_id) if body.approve else None
    await session.execute(
        text(
            "update privacy_requests set status = :s, decided_by = :u, decided_at = now(),"
            " note = :n where id = :id"
        ),
        {
            "id": request_id,
            "s": "completed" if body.approve else "rejected",
            "u": principal.user_id,
            "n": body.note,
        },
    )
    await _audit(
        session,
        principal,
        "privacy.erasure" if body.approve else "privacy.reject",
        "privacy_requests",
        request_id,
        {
            "squad_player_id": str(row.squad_player_id),
            **(erased.model_dump() if erased else {}),
        },
    )
    updated = (
        await session.execute(text(REQUEST_SQL + " where r.id = :id"), {"id": request_id})
    ).one()
    return RequestDecisionOut(request=request_out(updated), erased=erased)


__all__ = ["ConsentOut", "consent_out", "router"]
