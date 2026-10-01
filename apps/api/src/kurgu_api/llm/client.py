"""Model istemcisi (ADR-0013).

Model adı `KURGU_LLM_MODEL`, anahtar `KURGU_ANTHROPIC_API_KEY` değişkeninden okunur; kodda
varsayılan model yoktur. `thinking` ve örnekleme parametreleri gönderilmez.
`KURGU_LLM_BACKEND=fake` girdiden belirlenimci metin üretir ve üretim ortamında kullanılamaz.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from kurgu_analytics.reports.briefing import fake_briefing

from kurgu_api.config import Settings, get_settings
from kurgu_api.core.problems import ProblemError

MAX_TOKENS = 2048


class LlmError(Exception):
    """Model yanıt vermedi ya da yanıt kullanılamaz (ret, boş metin)."""


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class LlmClient(Protocol):
    model: str

    async def complete(self, system: str, user: str) -> Completion: ...


class AnthropicClient:
    def __init__(self, model: str, api_key: str) -> None:
        from anthropic import AsyncAnthropic

        self.model = model
        self._client = AsyncAnthropic(api_key=api_key, timeout=90.0, max_retries=2)

    async def complete(self, system: str, user: str) -> Completion:
        import anthropic

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIStatusError as exc:
            raise LlmError(f"API error {exc.status_code}") from exc
        except anthropic.APIError as exc:
            raise LlmError(type(exc).__name__) from exc
        usage = response.usage
        if response.stop_reason == "refusal":
            raise LlmError("refusal")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LlmError(f"empty response ({response.stop_reason})")
        return Completion(text, usage.input_tokens, usage.output_tokens)


class FakeClient:
    """Girdiden metin üretir; token sayımı karakter sayısından yaklaşık hesaplanır."""

    model = "fake"

    async def complete(self, system: str, user: str) -> Completion:
        data: dict[str, Any] = json.loads(user[user.index("{") :])
        text = fake_briefing(data)
        return Completion(text, (len(system) + len(user)) // 4, len(text) // 4)


_clients: dict[tuple[str, str], AnthropicClient] = {}


def configured(settings: Settings) -> bool:
    if settings.kurgu_llm_backend == "fake":
        return settings.kurgu_env != "production"
    return bool(settings.kurgu_llm_model and settings.kurgu_anthropic_api_key)


def get_llm_client() -> LlmClient:
    settings = get_settings()
    if not configured(settings):
        raise ProblemError(
            503, "llm-not-configured", "KURGU_LLM_MODEL and KURGU_ANTHROPIC_API_KEY are required"
        )
    if settings.kurgu_llm_backend == "fake":
        return FakeClient()
    key = (settings.kurgu_llm_model or "", settings.kurgu_anthropic_api_key or "")
    client = _clients.get(key)
    if client is None:
        client = _clients.setdefault(key, AnthropicClient(*key))
    return client
