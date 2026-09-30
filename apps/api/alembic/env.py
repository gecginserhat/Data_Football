"""Alembic ortamı. Göçler tablo sahibi rolüyle (`kurgu_owner`) çalışır (ADR-0002)."""

import asyncio

from alembic import context
from kurgu_api.config import get_settings
from kurgu_api.core.models import Base
from kurgu_api.identity import models as _identity_models  # noqa: F401
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

target_metadata = Base.metadata


def _url() -> str:
    return (
        context.config.get_main_option("sqlalchemy.url") or get_settings().migrations_database_url
    )


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
