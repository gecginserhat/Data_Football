"""FastAPI uygulaması. Çalıştırma: `uvicorn kurgu_api.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kurgu_api.config import get_settings
from kurgu_api.core.crypto import get_keyring
from kurgu_api.core.db import dispose_engine
from kurgu_api.core.logging import configure_logging
from kurgu_api.core.metrics import MetricsMiddleware
from kurgu_api.core.observability import setup_sentry, setup_tracing
from kurgu_api.core.problems import install_problem_handlers
from kurgu_api.core.security import SecurityHeadersMiddleware
from kurgu_api.health.router import router as health_router
from kurgu_api.identity.router import router as identity_router
from kurgu_api.imports.router import router as imports_router
from kurgu_api.ingestion.router import router as ingestion_router
from kurgu_api.league.router import router as league_router
from kurgu_api.live.router import router as live_router
from kurgu_api.llm.router import router as llm_router
from kurgu_api.performance.router import router as performance_router
from kurgu_api.prep.router import router as prep_router
from kurgu_api.reports.router import router as reports_router
from kurgu_api.routines.router import router as routines_router
from kurgu_api.squad.router import router as squad_router
from kurgu_api.video.local_router import router as local_storage_router
from kurgu_api.video.router import router as video_router

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
    setup_sentry(settings, "api")
    # Şifreleme anahtarı yoksa (üretim) uygulama başlamaz (ADR-0014).
    get_keyring()
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
        expose_headers=["ETag", "X-Request-ID", "Retry-After"],
    )
    app.add_middleware(MetricsMiddleware, paths=lambda: list(app.openapi()["paths"]))
    # En dışta: CORS ve hata yanıtları dahil her yanıta başlık ekler.
    app.add_middleware(
        SecurityHeadersMiddleware, hsts=settings.hardened, docs_path=f"{API_PREFIX}/docs"
    )
    install_problem_handlers(app)
    app.include_router(health_router)
    app.include_router(identity_router, prefix=API_PREFIX)
    app.include_router(league_router, prefix=API_PREFIX)
    app.include_router(routines_router, prefix=API_PREFIX)
    app.include_router(prep_router, prefix=API_PREFIX)
    app.include_router(reports_router, prefix=API_PREFIX)
    app.include_router(squad_router, prefix=API_PREFIX)
    app.include_router(performance_router, prefix=API_PREFIX)
    app.include_router(llm_router, prefix=API_PREFIX)
    app.include_router(live_router, prefix=API_PREFIX)
    app.include_router(video_router, prefix=API_PREFIX)
    app.include_router(local_storage_router, prefix=API_PREFIX)
    app.include_router(ingestion_router, prefix=API_PREFIX)
    app.include_router(imports_router, prefix=API_PREFIX)
    setup_tracing("kurgu-api", app)
    return app


app = create_app()
