"""Gözlem: `/metrics`, iş sayaçları, log alanları ve Sentry süzgeci (ADR-0017, A-91)."""

import contextlib
import json
import logging
import uuid
from typing import Any

from kurgu_api.config import get_settings
from kurgu_api.core.logging import JsonFormatter
from kurgu_api.core.metrics import JOBS_KEY, render, tracked
from kurgu_api.core.observability import _scrub, setup_sentry, setup_tracing
from kurgu_api.core.security import request_id_var
from redis.asyncio import Redis


async def test_metrics_endpoint_is_hidden_without_token(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(get_settings(), "kurgu_metrics_token", None)
    assert (await client.get("/metrics")).status_code == 404


async def test_metrics_endpoint_requires_the_token(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(get_settings(), "kurgu_metrics_token", "scrape-token-123")
    assert (await client.get("/metrics")).status_code == 401
    wrong = await client.get("/metrics", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401

    await client.get("/api/v1/me")  # 401, ama sayılır
    response = await client.get("/metrics", headers={"Authorization": "Bearer scrape-token-123"})
    assert response.status_code == 200
    body = response.text
    assert 'kurgu_http_requests_total{method="GET",route="/api/v1/me",status="401"}' in body
    assert "kurgu_http_request_duration_seconds_bucket" in body
    assert "kurgu_queue_depth" in body
    # Kimlik içeren yollar etiket olmaz; şablon kullanılır.
    assert str(uuid.UUID(int=0)) not in body


async def test_tracked_jobs_are_counted_across_processes() -> None:
    redis: Redis = Redis.from_url(get_settings().redis_url)
    await redis.delete(JOBS_KEY)

    async def sample_job(ctx: dict[str, Any], fail: bool = False) -> str:
        if fail:
            raise RuntimeError("boom")
        return "done"

    wrapped = tracked(sample_job)
    assert wrapped.__name__ == "sample_job"
    assert await wrapped({"redis": redis}) == "done"
    with contextlib.suppress(RuntimeError):
        await wrapped({"redis": redis}, fail=True)
    text = await render(redis)
    await redis.delete(JOBS_KEY)
    await redis.aclose()
    assert 'kurgu_jobs_total{job="sample_job",outcome="ok"} 1' in text
    assert 'kurgu_jobs_total{job="sample_job",outcome="failed"} 1' in text
    assert 'kurgu_job_seconds_total{job="sample_job"}' in text


def test_json_log_carries_request_id() -> None:
    token = request_id_var.set("req-abcdef12")
    try:
        record = logging.LogRecord("kurgu", logging.INFO, __file__, 1, "hello", (), None)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-abcdef12"
    assert payload["msg"] == "hello"


def test_optional_integrations_stay_off_without_configuration(monkeypatch: Any) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert setup_tracing("kurgu-api") is False
    monkeypatch.setattr(get_settings(), "kurgu_sentry_dsn", None)
    assert setup_sentry(get_settings(), "api") is False


def test_sentry_events_are_scrubbed_of_personal_data() -> None:
    event = {
        "request": {
            "data": {"sleep": 3},
            "cookies": {"session": "x"},
            "headers": {"Authorization": "Bearer t", "X-Tenant-Id": "t", "Accept": "json"},
        },
        "user": {"email": "player@kurgu.test"},
    }
    cleaned = _scrub(event, None)
    assert "data" not in cleaned["request"]
    assert "cookies" not in cleaned["request"]
    assert cleaned["request"]["headers"]["Authorization"] == "[filtered]"
    assert cleaned["request"]["headers"]["X-Tenant-Id"] == "[filtered]"
    assert cleaned["request"]["headers"]["Accept"] == "json"
    assert "user" not in cleaned


def test_frame_memo_reuses_results_only_for_identical_tables() -> None:
    import pandas as pd
    from kurgu_api.core.memo import FrameMemo

    calls: list[int] = []

    def double(frame: pd.DataFrame) -> pd.DataFrame:
        calls.append(len(frame))
        return frame * 2

    memo = FrameMemo(double, size=2)
    first = memo(pd.DataFrame({"a": [1, 2]}))
    first.loc[0, "a"] = 99  # çağıranın değişikliği önbelleğe sızmaz
    assert memo(pd.DataFrame({"a": [1, 2]}))["a"].tolist() == [2, 4]
    assert len(calls) == 1
    assert memo(pd.DataFrame({"a": [1, 3]}))["a"].tolist() == [2, 6]
    assert memo(pd.DataFrame({"b": [1, 2]}))["b"].tolist() == [2, 4]
    assert len(calls) == 3
    memo(pd.DataFrame({"a": [1, 2]}))  # en eski girdi düştü, yeniden hesaplanır
    assert len(calls) == 4
