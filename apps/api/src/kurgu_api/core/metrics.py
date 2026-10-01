"""Prometheus metrikleri (SPEC §17, ADR-0017, A-91): istek sayısı ve süresi, iş kuyruğu.

İş sayaçları worker sürecinde üretilir; API'den okunabilsin diye Redis'te bir karma tabloda
tutulur (`kurgu:metrics:jobs`, alanlar `<iş>:ok`, `<iş>:failed`, `<iş>:seconds`).
"""

import functools
import re
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from redis.asyncio import Redis
from starlette.types import ASGIApp, Message, Receive, Scope, Send

JOBS_KEY = "kurgu:metrics:jobs"
QUEUE_KEY = "arq:queue"

REGISTRY = CollectorRegistry()
REQUESTS = Counter(
    "kurgu_http_requests_total",
    "HTTP istekleri",
    ["method", "route", "status"],
    registry=REGISTRY,
)
LATENCY = Histogram(
    "kurgu_http_request_duration_seconds",
    "HTTP istek süresi",
    ["method", "route"],
    buckets=(0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10),
    registry=REGISTRY,
)


class MetricsMiddleware:
    """Rota şablonuna göre (kimlikler etiket olmaz) istek sayısı ve süresi.

    Şablonlar OpenAPI yollarından derlenir; böylece etiket sayısı uç sayısıyla sınırlı kalır.
    """

    def __init__(self, app: ASGIApp, paths: Callable[[], Iterable[str]]) -> None:
        self.app = app
        self._paths = paths
        self._patterns: list[tuple[re.Pattern[str], str]] | None = None

    def template(self, path: str) -> str:
        if self._patterns is None:
            self._patterns = [
                (re.compile("^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(p)) + "$"), p)
                for p in self._paths()
            ]
        for pattern, template in self._patterns:
            if pattern.match(path):
                return template
        return "unmatched"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            template = self.template(scope.get("path", ""))
            if template not in ("/metrics", "/healthz", "/readyz"):
                method = scope.get("method", "")
                REQUESTS.labels(method, template, str(status)).inc()
                LATENCY.labels(method, template).observe(time.perf_counter() - start)


def tracked[**P, R](job: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Worker işinin sonucunu ve süresini Redis'teki sayaçlara yazar."""

    @functools.wraps(job)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        ctx: dict[str, Any] = args[0] if args and isinstance(args[0], dict) else {}
        redis: Redis | None = ctx.get("redis")
        start = time.perf_counter()
        outcome = "failed"
        try:
            result = await job(*args, **kwargs)
            outcome = "ok"
            return result
        finally:
            if redis is not None:
                name = job.__name__
                async with redis.pipeline(transaction=False) as pipe:
                    pipe.hincrby(JOBS_KEY, f"{name}:{outcome}", 1)
                    pipe.hincrbyfloat(JOBS_KEY, f"{name}:seconds", time.perf_counter() - start)
                    await pipe.execute()

    return wrapper


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def render(redis: Redis) -> str:
    """İstek metrikleri ile kuyruk ve iş metriklerini Prometheus metin biçiminde döner."""
    lines = [generate_latest(REGISTRY).decode()]
    depth = await redis.zcard(QUEUE_KEY)
    lines += [
        "# HELP kurgu_queue_depth Kuyrukta bekleyen iş sayısı",
        "# TYPE kurgu_queue_depth gauge",
        f"kurgu_queue_depth {depth}",
    ]
    raw: dict[bytes, bytes] = await redis.hgetall(JOBS_KEY)  # type: ignore[misc]
    counts: list[str] = []
    seconds: list[str] = []
    for field, value in sorted(raw.items()):
        name, _, kind = field.decode().rpartition(":")
        label = _escape(name)
        if kind in ("ok", "failed"):
            counts.append(f'kurgu_jobs_total{{job="{label}",outcome="{kind}"}} {int(value)}')
        elif kind == "seconds":
            seconds.append(f'kurgu_job_seconds_total{{job="{label}"}} {float(value)}')
    lines += [
        "# HELP kurgu_jobs_total Tamamlanan işler",
        "# TYPE kurgu_jobs_total counter",
        *counts,
    ]
    lines += [
        "# HELP kurgu_job_seconds_total İşlerde geçen toplam süre",
        "# TYPE kurgu_job_seconds_total counter",
        *seconds,
    ]
    return "\n".join(lines) + "\n"
