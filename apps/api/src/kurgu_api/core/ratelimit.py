"""Kullanıcı başına sabit pencereli hız sınırı (SPEC §12.2, ADR-0016, A-89).

Sayaç Redis'te `INCR` + `EXPIRE` ile tutulur. Redis erişilemezse istek geçer (açık başarısız) ve
uyarı loglanır: sınır kötüye kullanımı yavaşlatmak içindir, erişilebilirliği düşürmemelidir.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from kurgu_api.config import get_settings
from kurgu_api.core.problems import ProblemError
from kurgu_api.identity.deps import PrincipalDep

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limit:
    bucket: str
    limit: int
    window_s: int


UPLOADS = Limit("uploads", 20, 600)
VIDEO_UPLOADS = Limit("video-uploads", 20, 3600)
REPORTS = Limit("reports", 30, 600)
BRIEFINGS = Limit("briefings", 10, 600)


def _redis(request: Request) -> Redis:
    client: Redis | None = getattr(request.app.state, "ratelimit_redis", None)
    if client is None:
        client = Redis.from_url(get_settings().redis_url, socket_timeout=0.5)
        request.app.state.ratelimit_redis = client
    return client


async def hit(client: Redis, key: str, rule: Limit, now: float | None = None) -> int | None:
    """Sayacı artırır.

    Sınır aşıldıysa pencerenin bitmesine kalan saniyeyi, aşılmadıysa None döner.
    """
    now = time.time() if now is None else now
    window = int(now // rule.window_s)
    redis_key = f"rl:{rule.bucket}:{key}:{window}"
    async with client.pipeline(transaction=True) as pipe:
        pipe.incr(redis_key)
        pipe.expire(redis_key, rule.window_s + 1)
        count, _ = await pipe.execute()
    if int(count) > rule.limit:
        return max(1, int((window + 1) * rule.window_s - now))
    return None


def rate_limit(rule: Limit) -> Callable[[Request, PrincipalDep], Awaitable[None]]:
    async def _dependency(request: Request, principal: PrincipalDep) -> None:
        if not get_settings().kurgu_rate_limit_enabled:
            return
        try:
            retry_after = await hit(_redis(request), str(principal.user_id), rule)
        except (RedisError, OSError) as exc:
            log.warning("rate limit skipped", extra={"bucket": rule.bucket, "error": str(exc)})
            return
        if retry_after is not None:
            raise ProblemError(
                429,
                "rate-limited",
                f"Too many requests; at most {rule.limit} per {rule.window_s} seconds",
                headers={"Retry-After": str(retry_after)},
                extra={"retry_after": retry_after},
            )

    return _dependency
