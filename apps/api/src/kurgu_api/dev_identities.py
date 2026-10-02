"""Yerel geliştirme kimlikleri: demo kiracı ve Keycloak test kullanıcılarının üyelikleri.

`infra/keycloak/kurgu-realm.json` içindeki kullanıcı kimlikleri sabittir; burada aynı
kimliklerle (iss, sub) kullanıcı ve üyelik kaydı açılır. İşlem idempotenttir.
Yalnızca `development` ve `test` ortamlarında çalışır (assumptions A-09, A-10).
Çalıştırma: `kurgu-dev-identities` (göç rolüyle bağlanır).
"""

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from kurgu_api.config import get_settings
from kurgu_api.identity.roles import Role
from kurgu_api.squad.demo import seed_demo_consents, seed_demo_squad

DEMO_TENANT_ID = uuid.UUID("00000000-0000-4000-9000-000000000001")
DEMO_TENANT_NAME = "Trabzonspor (demo)"
SECOND_TENANT_ID = uuid.UUID("00000000-0000-4000-9000-000000000002")
SECOND_TENANT_NAME = "Test Kulübü"

# Keycloak realm dosyasındaki kullanıcı kimlikleri (sıra rollerle aynı).
DEV_USERS: list[tuple[uuid.UUID, str, Role]] = [
    (uuid.UUID(f"00000000-0000-4000-8000-{i:012d}"), role.value.replace("_", "-"), role)
    for i, role in enumerate(Role, start=1)
]

# MFA test kullanıcısı: yalnız ikinci kiracıda performans rolünde; o kiracıda MFA açıktır (A-90).
MFA_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000009")
MFA_USERNAME = "mfa-performance"


async def seed_dev_identities(database_url: str | None = None) -> None:
    settings = get_settings()
    if settings.kurgu_env not in {"development", "test"}:
        raise SystemExit("dev identities are only for development and test environments")
    engine = create_async_engine(database_url or settings.migrations_database_url)
    issuer = settings.oidc_issuer.rstrip("/")
    async with engine.begin() as conn:
        tenants = ((DEMO_TENANT_ID, DEMO_TENANT_NAME), (SECOND_TENANT_ID, SECOND_TENANT_NAME))
        for tenant_id, name in tenants:
            await conn.execute(
                text("select set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
            )
            await conn.execute(
                text(
                    "insert into tenants (id, name) values (:id, :name) on conflict (id) do nothing"
                ),
                {"id": tenant_id, "name": name},
            )
        await conn.execute(
            text(
                "update tenants set settings = settings || '{\"mfa_required\": true}'::jsonb"
                " where id = :id"
            ),
            {"id": SECOND_TENANT_ID},
        )
        await _member(conn, issuer, MFA_USER_ID, MFA_USERNAME, SECOND_TENANT_ID, Role.PERFORMANCE)
        await conn.execute(
            text("select set_config('app.tenant_id', :tid, true)"), {"tid": str(DEMO_TENANT_ID)}
        )
        for subject, username, role in DEV_USERS:
            await _member(conn, issuer, subject, username, DEMO_TENANT_ID, role)
        squad = await seed_demo_squad(conn, DEMO_TENANT_ID)
        await seed_demo_consents(conn, DEMO_TENANT_ID)
    await engine.dispose()
    print(f"dev identities ready: {len(DEV_USERS)} users in '{DEMO_TENANT_NAME}'")
    if squad:
        print("demo squad, sessions and wellness added (is_demo)")


async def _member(
    conn: AsyncConnection,
    issuer: str,
    subject: uuid.UUID,
    username: str,
    tenant_id: uuid.UUID,
    role: Role,
) -> None:
    await conn.execute(
        text("select set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
    )
    user_id: uuid.UUID = (
        await conn.execute(
            text("select kurgu_resolve_user(:iss, :sub, :email, :name)"),
            {"iss": issuer, "sub": str(subject), "email": f"{username}@kurgu.local", "name": None},
        )
    ).scalar_one()
    await conn.execute(
        text(
            "insert into memberships (user_id, tenant_id, role) values (:uid, :tid, :role)"
            " on conflict (user_id, tenant_id, role) do nothing"
        ),
        {"uid": user_id, "tid": tenant_id, "role": role.value},
    )


def main() -> None:
    asyncio.run(seed_dev_identities())


if __name__ == "__main__":
    main()
