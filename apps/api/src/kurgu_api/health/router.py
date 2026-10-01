"""`/healthz` (canlılık) ve `/readyz` (bağımlılıklar hazır mı) uçları (SPEC §17)."""

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from kurgu_api.config import get_settings
from kurgu_api.core.db import get_sessionmaker

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool] = {}


@router.get("/healthz", response_model=HealthStatus)
async def healthz() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/readyz", response_model=HealthStatus, responses={503: {"model": HealthStatus}})
async def readyz() -> JSONResponse:
    checks = {"database": await _check_db(), "redis": await _check_redis()}
    ok = all(checks.values())
    body = HealthStatus(status="ok" if ok else "degraded", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)


async def _check_db() -> bool:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("select 1"))
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    client: Redis = Redis.from_url(get_settings().redis_url)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()
