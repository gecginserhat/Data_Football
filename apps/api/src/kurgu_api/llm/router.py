"""Brifing ve LLM ayarı uçları (SPEC §15, ADR-0013, A-75, A-76)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from kurgu_api.config import get_settings
from kurgu_api.core.audit import write_audit
from kurgu_api.identity.deps import PrincipalDep, SessionDep, require
from kurgu_api.identity.roles import Permission
from kurgu_api.llm import service
from kurgu_api.llm.client import LlmClient, configured, get_llm_client
from kurgu_api.llm.schemas import BriefingOut, LlmSettings, LlmSettingsOut
from kurgu_api.prep.facts import load_fixture

router = APIRouter(tags=["llm"])


@router.post(
    "/fixtures/{fixture_id}/briefing",
    response_model=BriefingOut,
    operation_id="generateBriefing",
    dependencies=[Depends(require(Permission.EDIT_ROUTINES))],
)
async def generate_briefing(
    session: SessionDep,
    principal: PrincipalDep,
    client: Annotated[LlmClient, Depends(get_llm_client)],
    fixture_id: uuid.UUID,
) -> BriefingOut:
    """Brifing üretir (A-75). Sayılar girdiyle eşleşmezse bir kez yeniden dener; yine eşleşmezse
    metin döndürülmez (`status = failed`)."""
    assert principal.tenant is not None
    fixture = await load_fixture(session, fixture_id)
    result = await service.generate(
        session, client, fixture, principal.tenant.tenant_id, principal.user_id
    )
    await write_audit(
        session,
        tenant_id=principal.tenant.tenant_id,
        actor_id=principal.user_id,
        action="briefing.generated",
        entity="matches",
        entity_id=fixture_id,
        after={"status": result.status, "attempts": result.attempts, "model": result.model},
    )
    return result


@router.get(
    "/fixtures/{fixture_id}/briefing",
    response_model=BriefingOut,
    operation_id="getBriefing",
    dependencies=[Depends(require(Permission.READ_ANALYSIS))],
)
async def get_briefing(session: SessionDep, fixture_id: uuid.UUID) -> BriefingOut:
    """Son doğrulanmış brifing; yoksa `status = none`."""
    await load_fixture(session, fixture_id)
    return await service.latest(session, fixture_id)


ADMIN = [Depends(require(Permission.USER_ADMIN_AUDIT))]


async def _settings_out(session: SessionDep) -> LlmSettingsOut:
    return LlmSettingsOut(
        settings=await service.tenant_settings(session),
        usage=await service.usage(session),
        configured=configured(get_settings()),
    )


@router.get(
    "/admin/llm-settings",
    response_model=LlmSettingsOut,
    operation_id="getLlmSettings",
    dependencies=ADMIN,
)
async def get_llm_settings(session: SessionDep) -> LlmSettingsOut:
    return await _settings_out(session)


@router.put(
    "/admin/llm-settings",
    response_model=LlmSettingsOut,
    operation_id="updateLlmSettings",
    dependencies=ADMIN,
)
async def update_llm_settings(
    session: SessionDep, principal: PrincipalDep, body: LlmSettings
) -> LlmSettingsOut:
    """Özelliği açar/kapatır ve aylık sınırları değiştirir (A-76)."""
    assert principal.tenant is not None
    before = await service.tenant_settings(session)
    await service.save_settings(session, body)
    await write_audit(
        session,
        tenant_id=principal.tenant.tenant_id,
        actor_id=principal.user_id,
        action="llm.settings_updated",
        entity="tenants",
        entity_id=principal.tenant.tenant_id,
        before=before.model_dump(),
        after=body.model_dump(),
    )
    return await _settings_out(session)
