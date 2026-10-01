"""KVKK iş kuralları: rıza, dışa aktarma, silme ve saklama süreleri (ADR-0019, A-92)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.performance.service import unseal
from kurgu_api.privacy.schemas import ConsentOut, ErasureResult, RequestOut, Retention

ERASED_NAME = "Silinmiş oyuncu"

CONSENT_COLUMNS = "id, text_version, method, reference, given_at, withdrawn_at, is_demo"
REQUEST_SQL = (
    "select r.id, r.squad_player_id, p.name as player_name, r.kind, r.status, r.reason,"
    " r.created_at, r.decided_at, r.note from privacy_requests r"
    " join squad_players p on p.id = r.squad_player_id"
)


def consent_out(row: Any) -> ConsentOut:
    return ConsentOut.model_validate(row, from_attributes=True)


def request_out(row: Any) -> RequestOut:
    return RequestOut.model_validate(row, from_attributes=True)


async def active_consent(session: AsyncSession, player_id: uuid.UUID) -> ConsentOut | None:
    row = (
        await session.execute(
            text(
                f"select {CONSENT_COLUMNS} from health_consents"  # noqa: S608 (sabit sütunlar)
                " where squad_player_id = :p and withdrawn_at is null"
            ),
            {"p": player_id},
        )
    ).first()
    return consent_out(row) if row else None


async def consent_history(session: AsyncSession, player_id: uuid.UUID) -> list[ConsentOut]:
    rows = await session.execute(
        text(
            f"select {CONSENT_COLUMNS} from health_consents"  # noqa: S608 (sabit sütunlar)
            " where squad_player_id = :p order by given_at desc"
        ),
        {"p": player_id},
    )
    return [consent_out(r) for r in rows]


async def retention_for(session: AsyncSession, tenant_id: uuid.UUID) -> Retention:
    raw = (
        await session.execute(
            text("select settings -> 'retention' from tenants where id = :t"), {"t": tenant_id}
        )
    ).scalar_one_or_none()
    return Retention.model_validate(raw or {})


async def export_player(
    session: AsyncSession, tenant_id: uuid.UUID, player_id: uuid.UUID
) -> dict[str, Any]:
    """Oyuncunun kişisel verisinin tamamı; iyi oluş puanları çözülmüş halde."""
    player = (
        (
            await session.execute(
                text(
                    "select id, name, shirt_number, position, height_cm, aerial_win_pct,"
                    " jump_score, active, is_demo, created_at, erased_at"
                    " from squad_players where id = :p"
                ),
                {"p": player_id},
            )
        )
        .mappings()
        .one()
    )
    wellness = []
    for row in await session.execute(
        text(
            "select date, scores, created_at, updated_at from wellness_entries"
            " where squad_player_id = :p order by date"
        ),
        {"p": player_id},
    ):
        scores = unseal(row.scores, tenant_id)
        wellness.append({"date": row.date, **scores, "hooper": sum(scores.values())})
    loads = [
        dict(r)
        for r in (
            await session.execute(
                text(
                    "select s.date, s.md_code, s.title, l.rpe, l.minutes, l.headers, l.jumps"
                    " from session_loads l join training_sessions s on s.id = l.session_id"
                    " where l.squad_player_id = :p order by s.date"
                ),
                {"p": player_id},
            )
        ).mappings()
    ]
    assignments = [
        dict(r)
        for r in (
            await session.execute(
                text(
                    "select fixture_id, routine_id, routine_version, role, assigned_at"
                    " from routine_assignments where squad_player_id = :p order by assigned_at"
                ),
                {"p": player_id},
            )
        ).mappings()
    ]
    requests = [
        request_out(r)
        for r in await session.execute(
            text(REQUEST_SQL + " where r.squad_player_id = :p order by r.created_at"),
            {"p": player_id},
        )
    ]
    return {
        "generated_at": dt.datetime.now(dt.UTC),
        "player": {
            k: (float(v) if k in {"aerial_win_pct", "jump_score"} and v is not None else v)
            for k, v in player.items()
        },
        "consents": await consent_history(session, player_id),
        "wellness": wellness,
        "loads": [{**r, "rpe": float(r["rpe"])} for r in loads],
        "assignments": assignments,
        "requests": requests,
    }


async def erase_player(session: AsyncSession, player_id: uuid.UUID) -> ErasureResult:
    """Silme talebi onayı: sağlık ve yük kayıtlarını siler, kadro kaydını anonimleştirir."""

    async def delete(sql: str) -> int:
        result = await session.execute(text(sql), {"p": player_id})
        return int(getattr(result, "rowcount", 0) or 0)

    erased = ErasureResult(
        wellness=await delete("delete from wellness_entries where squad_player_id = :p"),
        loads=await delete("delete from session_loads where squad_player_id = :p"),
        assignments=await delete("delete from routine_assignments where squad_player_id = :p"),
        consents=await delete("delete from health_consents where squad_player_id = :p"),
    )
    await session.execute(
        text("update memberships set player_id = null where player_id = :p"), {"p": player_id}
    )
    await session.execute(
        text(
            "update squad_players set name = :name, shirt_number = null, height_cm = null,"
            " aerial_win_pct = null, jump_score = null, active = false, erased_at = now(),"
            " updated_at = now() where id = :p"
        ),
        {"p": player_id, "name": ERASED_NAME},
    )
    return erased
