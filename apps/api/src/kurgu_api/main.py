"""FastAPI uygulaması. Çalıştırma: `uvicorn kurgu_api.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kurgu_api.config import get_settings
from kurgu_api.core.db import dispose_engine
from kurgu_api.core.logging import configure_logging
from kurgu_api.core.problems import install_problem_handlers
from kurgu_api.health.router import router as health_router
from kurgu_api.identity.router import router as identity_router
from kurgu_api.imports.router import router as imports_router
from kurgu_api.ingestion.router import router as ingestion_router
from kurgu_api.league.router import router as league_router

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    pool = getattr(app.state, "arq", None)
    if pool is not None:
        await pool.aclose()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.kurgu_log_level)
    app = FastAPI(
        title="Kurgu API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_problem_handlers(app)
    app.include_router(health_router)
    app.include_router(identity_router, prefix=API_PREFIX)
    app.include_router(league_router, prefix=API_PREFIX)
    app.include_router(ingestion_router, prefix=API_PREFIX)
    app.include_router(imports_router, prefix=API_PREFIX)
    return app


app = create_app()
