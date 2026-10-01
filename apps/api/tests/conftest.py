"""Test altyapısı: ayrı bir test veritabanı, gerçek roller ve RLS ile çalışır.

Gerekenler: yerel ya da CI'da çalışan PostgreSQL 16 ve Redis. Bağlantı adresleri
ortam değişkenleriyle değiştirilebilir (bkz. `TEST_ADMIN_DATABASE_URL`).
"""

import os
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import anyio
import asyncpg
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)
DB_NAME = os.environ.get("TEST_DATABASE_NAME", "kurgu_test")
PG_HOSTPORT = ADMIN_URL.split("@", 1)[1].rsplit("/", 1)[0]
PASSWORDS = {"kurgu_owner": "test-owner", "kurgu_app": "test-app", "kurgu_worker": "test-worker"}
ISSUER = "https://issuer.test/realms/kurgu"
AUDIENCE = "kurgu-api"


def _url(role: str, driver: str = "postgresql+asyncpg") -> str:
    return f"{driver}://{role}:{PASSWORDS[role]}@{PG_HOSTPORT}/{DB_NAME}"


os.environ.update(
    {
        "KURGU_ENV": "test",
        "DATABASE_URL": _url("kurgu_app"),
        "MIGRATIONS_DATABASE_URL": _url("kurgu_owner"),
        "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"),
        "OIDC_ISSUER": ISSUER,
        "OIDC_AUDIENCE": AUDIENCE,
        "KURGU_REQUIRE_MFA": "false",
    }
)


async def _prepare_database() -> None:
    admin = await asyncpg.connect(ADMIN_URL)
    try:
        for role, password in PASSWORDS.items():
            exists = await admin.fetchval("select 1 from pg_roles where rolname = $1", role)
            bypass = "" if role == "kurgu_owner" else " nobypassrls"
            verb = "alter" if exists else "create"
            await admin.execute(f"{verb} role {role} login password '{password}'{bypass}")
        await admin.execute(f'drop database if exists "{DB_NAME}" with (force)')
        await admin.execute(f'create database "{DB_NAME}" owner kurgu_owner')
    finally:
        await admin.close()
    db = await asyncpg.connect(ADMIN_URL.rsplit("/", 1)[0] + f"/{DB_NAME}")
    try:
        await db.execute("alter schema public owner to kurgu_owner")
        await db.execute("grant usage on schema public to kurgu_app, kurgu_worker")
    finally:
        await db.close()


def _migrate(target: str = "head") -> None:
    from alembic import command
    from alembic.config import Config

    here = os.path.dirname(os.path.dirname(__file__))
    config = Config(os.path.join(here, "alembic.ini"))
    config.set_main_option("sqlalchemy.url", _url("kurgu_owner"))
    command.upgrade(config, target)


@pytest.fixture(scope="session", autouse=True)
async def database() -> None:
    await _prepare_database()
    # Alembic env.py kendi olay döngüsünü açar; bu yüzden ayrı bir iş parçacığında çalışır.
    await anyio.to_thread.run_sync(_migrate)


@pytest.fixture
async def superuser() -> AsyncIterator[asyncpg.Connection]:
    """RLS'yi atlayan bağlantı; yalnızca test verisi hazırlamak için."""
    conn = await asyncpg.connect(ADMIN_URL.rsplit("/", 1)[0] + f"/{DB_NAME}")
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def app_conn() -> AsyncIterator[asyncpg.Connection]:
    """Uygulama rolüyle (RLS'ye tabi) bağlantı."""
    conn = await asyncpg.connect(_url("kurgu_app", "postgresql"))
    try:
        yield conn
    finally:
        await conn.close()


# --- Token üretimi -------------------------------------------------------


@dataclass
class TokenFactory:
    key: rsa.RSAPrivateKey

    def __call__(self, subject: str | None = None, **claims: Any) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": subject or str(uuid.uuid4()),
            "iat": now,
            "exp": now + 300,
            "email": claims.pop("email", "user@kurgu.test"),
            "name": claims.pop("name", "Test Kullanıcı"),
        }
        payload.update(claims)
        return jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": "test"})


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def make_token(signing_key: rsa.RSAPrivateKey) -> TokenFactory:
    return TokenFactory(signing_key)


class StaticKeyVerifier:
    """JWKS yerine sabit açık anahtarla doğrulayan test doğrulayıcısı."""

    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self._public = key.public_key()

    async def verify(self, token: str) -> Any:
        from kurgu_api.identity.tokens import InvalidTokenError, claims_from_payload

        try:
            payload = jwt.decode(
                token, self._public, algorithms=["RS256"], audience=AUDIENCE, issuer=ISSUER
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc
        return claims_from_payload(payload)


@pytest.fixture
def app(signing_key: rsa.RSAPrivateKey) -> Any:
    from kurgu_api.identity.deps import get_token_verifier
    from kurgu_api.main import create_app

    application = create_app()
    application.dependency_overrides[get_token_verifier] = lambda: StaticKeyVerifier(signing_key)
    return application


@pytest.fixture
async def client(app: Any) -> AsyncIterator[Any]:
    import httpx
    from asgi_lifespan import LifespanManager

    async with (
        LifespanManager(app) as manager,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=manager.app), base_url="http://test"
        ) as http,
    ):
        yield http


# --- Veri yardımcıları ---------------------------------------------------


@dataclass
class Seeded:
    tenant_a: uuid.UUID
    tenant_b: uuid.UUID


@pytest.fixture
async def tenants(superuser: asyncpg.Connection) -> Seeded:
    a = await superuser.fetchval("insert into tenants (name) values ('Kulüp A') returning id")
    b = await superuser.fetchval("insert into tenants (name) values ('Kulüp B') returning id")
    return Seeded(tenant_a=a, tenant_b=b)


async def add_member(
    superuser: asyncpg.Connection, subject: str, tenant_id: uuid.UUID, *roles: str
) -> uuid.UUID:
    user_id: uuid.UUID = await superuser.fetchval(
        """
        insert into users (issuer, subject, email) values ($1, $2, $3)
        on conflict (issuer, subject) do update set email = excluded.email
        returning id
        """,
        ISSUER,
        subject,
        f"{subject}@kurgu.test",
    )
    for role in roles:
        await superuser.execute(
            "insert into memberships (user_id, tenant_id, role) values ($1, $2, $3)",
            user_id,
            tenant_id,
            role,
        )
    return user_id
