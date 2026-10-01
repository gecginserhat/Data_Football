"""Güvenlik başlıkları, istek kimliği, hız sınırı ve MFA kiracı ayarı (ADR-0016, A-88 … A-90)."""

import time
import uuid
from typing import Any

import asyncpg
import pytest
from kurgu_api.config import get_settings
from kurgu_api.core.ratelimit import REPORTS, Limit, hit
from redis.asyncio import Redis

from .conftest import Seeded, TokenFactory, add_member


async def test_api_responses_carry_security_headers(client: Any) -> None:
    for path in ("/healthz", "/api/v1/does-not-exist"):
        response = await client.get(path)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["content-security-policy"].startswith("default-src 'none'")
        # Yerel ve test ortamında HTTPS yok; HSTS yalnız staging ve production'da.
        assert "strict-transport-security" not in response.headers


async def test_docs_page_gets_its_own_policy(client: Any) -> None:
    response = await client.get("/api/v1/docs")
    assert response.status_code == 200
    assert "cdn.jsdelivr.net" in response.headers["content-security-policy"]


async def test_hsts_is_sent_in_hardened_environments(monkeypatch: Any, signing_key: Any) -> None:
    import httpx
    from kurgu_api.main import create_app

    monkeypatch.setattr(get_settings(), "kurgu_env", "staging")
    monkeypatch.setattr(get_settings(), "kurgu_data_keys", "k1:" + "A" * 43 + "=")
    from kurgu_api.core.crypto import get_keyring

    get_keyring.cache_clear()
    try:
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            response = await http.get("/healthz")
        assert response.headers["strict-transport-security"].startswith("max-age=31536000")
    finally:
        get_keyring.cache_clear()


async def test_request_id_is_echoed_or_generated(client: Any) -> None:
    given = await client.get("/healthz", headers={"X-Request-ID": "trace-12345678"})
    assert given.headers["x-request-id"] == "trace-12345678"
    generated = await client.get("/healthz", headers={"X-Request-ID": "bad id\n"})
    assert generated.headers["x-request-id"] != "bad id\n"
    assert len(generated.headers["x-request-id"]) == 32


async def test_fixed_window_counter() -> None:
    client: Redis = Redis.from_url(get_settings().redis_url)
    rule = Limit(f"test-{uuid.uuid4().hex}", 3, 60)
    now = 1_000_020.0  # pencere 1_000_020 // 60 = 16667; bitişi 1_000_080
    try:
        assert [await hit(client, "u", rule, now) for _ in range(3)] == [None, None, None]
        assert await hit(client, "u", rule, now) == 60
        assert await hit(client, "other", rule, now) is None
        # Sonraki pencerede sayaç sıfırdan başlar.
        assert await hit(client, "u", rule, now + 60) is None
    finally:
        await client.aclose()


async def test_rate_limited_endpoint_returns_problem_with_retry_after(
    client: Any, make_token: TokenFactory, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    subject = f"analyst-{uuid.uuid4()}"
    user_id = await add_member(superuser, subject, tenants.tenant_a, "analyst")
    redis: Redis = Redis.from_url(get_settings().redis_url)
    window = int(time.time() // REPORTS.window_s)
    await redis.set(f"rl:{REPORTS.bucket}:{user_id}:{window}", REPORTS.limit, ex=REPORTS.window_s)
    await redis.aclose()

    response = await client.post(
        "/api/v1/reports",
        json={},
        headers={"Authorization": f"Bearer {make_token(subject)}"},
    )
    assert response.status_code == 429
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("/rate-limited")
    assert 1 <= int(response.headers["retry-after"]) <= REPORTS.window_s


async def test_rate_limit_fails_open_without_redis(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    tenants: Seeded,
    monkeypatch: Any,
    app: Any,
) -> None:
    subject = f"analyst-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, "analyst")
    app.state.ratelimit_redis = Redis.from_url("redis://localhost:1/0", socket_timeout=0.2)
    response = await client.post(
        "/api/v1/reports", json={}, headers={"Authorization": f"Bearer {make_token(subject)}"}
    )
    # Sınır atlanır; istek doğrulamaya kadar ilerler.
    assert response.status_code == 422


@pytest.mark.parametrize(("role", "blocked"), [("performance", True), ("analyst", False)])
async def test_tenant_setting_turns_on_mfa_in_development(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    tenants: Seeded,
    role: str,
    blocked: bool,
) -> None:
    await superuser.execute(
        """update tenants set settings = settings || '{"mfa_required": true}' where id = $1""",
        tenants.tenant_a,
    )
    subject = f"{role}-{uuid.uuid4()}"
    await add_member(superuser, subject, tenants.tenant_a, role)
    response = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {make_token(subject)}"}
    )
    assert (response.status_code == 403) is blocked
    stepped_up = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {make_token(subject, acr='2')}"}
    )
    assert stepped_up.status_code == 200


async def test_mfa_cannot_be_disabled_in_production(monkeypatch: Any) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "kurgu_require_mfa", False)
    monkeypatch.setattr(settings, "kurgu_env", "production")
    assert settings.mfa_enforced
    monkeypatch.setattr(settings, "kurgu_env", "development")
    assert not settings.mfa_enforced
