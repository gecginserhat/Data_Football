"""LLM brifingi (Faz 6, ADR-0013): sayı denetimi, yeniden deneme, kayıt, kiracı ayarı ve sınırlar.

Kabul (SPEC §19 Faz 6): brifing sayı eşleştirme denetiminden geçer; geçmezse gösterilmez.
Gerçek model çağrılmaz; istemci sahte ya da enjekte edilir.
"""

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest
from kurgu_api.config import get_settings
from kurgu_api.core.db import get_sessionmaker, set_request_context
from kurgu_api.llm.client import AnthropicClient, Completion, LlmError, get_llm_client
from kurgu_api.reports import data

from .conftest import Seeded, TokenFactory
from .test_prep import _headers, club, fixture_id, seeded

__all__ = ["club", "fixture_id", "seeded"]


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("KURGU_LLM_BACKEND", "fake")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class ScriptedClient:
    """Sırayla verilen yanıtları döner; istemleri saklar."""

    model = "scripted"

    def __init__(self, *outputs: str | Exception) -> None:
        self.outputs = list(outputs)
        self.messages: list[str] = []

    async def complete(self, system: str, user: str) -> Completion:
        self.messages.append(user)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return Completion(out, 1000, 200)


def _use(app: Any, client: ScriptedClient) -> None:
    app.dependency_overrides[get_llm_client] = lambda: client


@pytest.fixture
async def coach(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "sp_coach")


@pytest.fixture
async def admin(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "admin")


@pytest.fixture
async def viewer(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "viewer")


@pytest.fixture
async def other(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_b, "head_coach")


async def _generate(client: Any, headers: dict[str, str], fixture: str) -> Any:
    return await client.post(f"/api/v1/fixtures/{fixture}/briefing", headers=headers)


async def _runs(superuser: asyncpg.Connection, tenant: uuid.UUID) -> list[asyncpg.Record]:
    rows: list[asyncpg.Record] = await superuser.fetch(
        "select attempt, status, model, output, unmatched, input_tokens, output_tokens,"
        " duration_ms from llm_runs where tenant_id = $1 order by created_at, attempt",
        tenant,
    )
    return rows


async def test_fake_briefing_is_verified_and_logged(
    client: Any,
    coach: dict[str, str],
    viewer: dict[str, str],
    fixture_id: str,
    club: Seeded,
    superuser: asyncpg.Connection,
) -> None:
    response = await _generate(client, coach, fixture_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "verified"
    assert body["attempts"] == 1
    assert body["model"] == "fake"
    assert body["numbers"] > 3
    assert "Samsunspor" in body["text"]

    stored = (await client.get(f"/api/v1/fixtures/{fixture_id}/briefing", headers=viewer)).json()
    assert stored["status"] == "verified"
    assert stored["text"] == body["text"]

    runs = await _runs(superuser, club.tenant_a)
    assert [(r["attempt"], r["status"]) for r in runs] == [(1, "verified")]
    assert runs[0]["input_tokens"] > 0
    assert runs[0]["duration_ms"] is not None

    # Rakip raporu son doğrulanmış brifingi taşır.
    async with get_sessionmaker()() as session, session.begin():
        await set_request_context(session, user_id=None, tenant_id=club.tenant_a)
        report = await data.opponent_report(session, uuid.UUID(fixture_id), club.tenant_a, None)
    assert report.briefing is not None
    assert report.briefing.text == body["text"]


async def test_fabricated_numbers_are_never_shown(
    app: Any,
    client: Any,
    coach: dict[str, str],
    fixture_id: str,
    club: Seeded,
    superuser: asyncpg.Connection,
) -> None:
    scripted = ScriptedClient(
        "Rakip maç başına 7,1 korner kullanıyor.", "Rakip 93 kez kafa vuruşu denedi."
    )
    _use(app, scripted)
    body = (await _generate(client, coach, fixture_id)).json()
    assert body["status"] == "failed"
    assert body["reason"] == "unverified"
    assert body["text"] is None
    assert body["attempts"] == 2
    assert "7,1" in scripted.messages[1].split("\n\n", 1)[0]

    runs = await _runs(superuser, club.tenant_a)
    assert [(r["attempt"], r["status"]) for r in runs] == [(1, "rejected"), (2, "rejected")]
    assert runs[0]["unmatched"] == '["7,1"]'
    stored = (await client.get(f"/api/v1/fixtures/{fixture_id}/briefing", headers=coach)).json()
    assert stored == {**stored, "status": "none", "text": None}


async def test_retry_can_succeed(
    app: Any, client: Any, coach: dict[str, str], fixture_id: str
) -> None:
    _use(app, ScriptedClient("Rakip 7,1 korner kullanıyor.", "Rakip 7. haftada deplasmanda."))
    body = (await _generate(client, coach, fixture_id)).json()
    assert body["status"] == "verified"
    assert body["attempts"] == 2
    assert body["text"] == "Rakip 7. haftada deplasmanda."


async def test_model_error_is_logged_and_hidden(
    app: Any,
    client: Any,
    coach: dict[str, str],
    fixture_id: str,
    club: Seeded,
    superuser: asyncpg.Connection,
) -> None:
    _use(app, ScriptedClient(LlmError("refusal")))
    body = (await _generate(client, coach, fixture_id)).json()
    assert body["status"] == "failed"
    assert body["reason"] == "error"
    runs = await _runs(superuser, club.tenant_a)
    assert [(r["attempt"], r["status"]) for r in runs] == [(1, "error")]


async def test_not_configured(
    client: Any, coach: dict[str, str], fixture_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KURGU_LLM_BACKEND", "anthropic")
    monkeypatch.delenv("KURGU_LLM_MODEL", raising=False)
    monkeypatch.delenv("KURGU_ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    response = await _generate(client, coach, fixture_id)
    assert response.status_code == 503
    assert response.json()["type"].endswith("llm-not-configured")


async def test_fake_backend_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from kurgu_api.core.problems import ProblemError

    monkeypatch.setenv("KURGU_ENV", "production")
    get_settings.cache_clear()
    with pytest.raises(ProblemError):
        get_llm_client()


async def test_settings_disable_and_budget(
    client: Any,
    admin: dict[str, str],
    coach: dict[str, str],
    other: dict[str, str],
    fixture_id: str,
) -> None:
    settings = (await client.get("/api/v1/admin/llm-settings", headers=admin)).json()
    assert settings["settings"] == {
        "enabled": True,
        "monthly_requests": 200,
        "monthly_tokens": 2_000_000,
    }
    assert settings["configured"] is True
    assert settings["usage"]["requests"] == 0

    off = await client.put(
        "/api/v1/admin/llm-settings",
        headers=admin,
        json={"enabled": False, "monthly_requests": 1, "monthly_tokens": 2_000_000},
    )
    assert off.status_code == 200, off.text
    disabled = await _generate(client, coach, fixture_id)
    assert disabled.status_code == 403
    assert disabled.json()["type"].endswith("llm-disabled")

    await client.put(
        "/api/v1/admin/llm-settings",
        headers=admin,
        json={"enabled": True, "monthly_requests": 1, "monthly_tokens": 2_000_000},
    )
    assert (await _generate(client, coach, fixture_id)).json()["status"] == "verified"
    limited = await _generate(client, coach, fixture_id)
    assert limited.status_code == 429
    usage = (await client.get("/api/v1/admin/llm-settings", headers=admin)).json()["usage"]
    assert usage["requests"] == 1
    # Diğer kiracının sayacı ve brifingi ayrıdır.
    assert (await _generate(client, other, fixture_id)).json()["status"] == "verified"


async def test_budget_stops_the_retry(
    app: Any,
    client: Any,
    admin: dict[str, str],
    coach: dict[str, str],
    fixture_id: str,
) -> None:
    await client.put(
        "/api/v1/admin/llm-settings",
        headers=admin,
        json={"enabled": True, "monthly_requests": 1, "monthly_tokens": 2_000_000},
    )
    _use(app, ScriptedClient("Rakip 7,1 korner kullanıyor.", "kullanılmaz"))
    body = (await _generate(client, coach, fixture_id)).json()
    assert body["status"] == "failed"
    assert body["attempts"] == 1


async def test_permissions_and_isolation(
    client: Any,
    coach: dict[str, str],
    viewer: dict[str, str],
    other: dict[str, str],
    fixture_id: str,
) -> None:
    assert (await _generate(client, viewer, fixture_id)).status_code == 403
    assert (await client.get("/api/v1/admin/llm-settings", headers=coach)).status_code == 403
    assert (await _generate(client, coach, fixture_id)).json()["status"] == "verified"
    other_view = await client.get(f"/api/v1/fixtures/{fixture_id}/briefing", headers=other)
    assert other_view.json()["status"] == "none"


async def test_anthropic_client_reads_text_and_rejects_refusal() -> None:
    client = AnthropicClient("model-from-env", "key-from-env")

    def response(stop: str, *texts: str) -> Any:
        return SimpleNamespace(
            stop_reason=stop,
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
            content=[SimpleNamespace(type="text", text=t) for t in texts],
        )

    calls: list[dict[str, Any]] = []
    replies = [response("end_turn", "Merhaba ", "dünya"), response("refusal")]

    async def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return replies.pop(0)

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))  # type: ignore[assignment]
    done = await client.complete("sistem", "girdi")
    assert done == Completion("Merhaba dünya", 11, 7)
    assert calls[0]["model"] == "model-from-env"
    assert "thinking" not in calls[0]
    assert "temperature" not in calls[0]
    with pytest.raises(LlmError):
        await client.complete("sistem", "girdi")
