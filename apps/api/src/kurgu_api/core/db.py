"""Async SQLAlchemy motoru ve istek başına işlem.

Her istek tek bir işlem içinde çalışır. Kiracı ve kullanıcı bağlamı `SET LOCAL` ile
işleme yazılır; RLS politikaları bu ayarları okur (ADR-0002). İşlem dışında sorgu atılmaz.
"""

import uuid
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kurgu_api.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """İstek başına oturum; başarıda commit, hatada rollback."""
    async with get_sessionmaker()() as session, session.begin():
        yield session


async def set_request_context(
    session: AsyncSession, *, user_id: uuid.UUID | None, tenant_id: uuid.UUID | None
) -> None:
    """RLS bağlamını işlem süresince ayarlar (`set_config(..., is_local => true)`)."""
    await session.execute(
        text(
            "select set_config('app.user_id', :user_id, true),"
            " set_config('app.tenant_id', :tenant_id, true)"
        ),
        {
            "user_id": str(user_id) if user_id else "",
            "tenant_id": str(tenant_id) if tenant_id else "",
        },
    )
