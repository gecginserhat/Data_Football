"""İz takibi ve hata takibi (SPEC §17, ADR-0017, A-91).

İkisi de isteğe bağlıdır: OpenTelemetry yalnız `OTEL_EXPORTER_OTLP_ENDPOINT`, Sentry yalnız
`KURGU_SENTRY_DSN` tanımlıysa başlar. Hata raporlarına kişisel veri ve istek gövdesi gitmez.
"""

import logging
import os
from typing import Any

from fastapi import FastAPI

from kurgu_api.config import Settings

log = logging.getLogger(__name__)
_tracing_started = False


def setup_tracing(service: str, app: FastAPI | None = None) -> bool:
    """OTLP/HTTP dışa aktarıcıyla iz takibini başlatır; uç tanımlı değilse hiçbir şey yapmaz."""
    global _tracing_started
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if not _tracing_started:
        name = os.environ.get("OTEL_SERVICE_NAME", service)
        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        SQLAlchemyInstrumentor().instrument(enable_commenter=False)
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        _tracing_started = True
    if app is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")
    log.info("tracing enabled", extra={"service": service})
    return True


def _scrub(event: Any, _hint: Any) -> Any:
    """Sentry olayından istek gövdesini, çerezleri ve kimlik başlıklarını çıkarır."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for key in list(headers):
                if key.lower() in {"authorization", "cookie", "x-tenant-id"}:
                    headers[key] = "[filtered]"
    event.pop("user", None)
    return event


def setup_sentry(settings: Settings, component: str) -> bool:
    if not settings.kurgu_sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.kurgu_sentry_dsn,
        environment=settings.kurgu_env,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=0.0,
        before_send=_scrub,
    )
    sentry_sdk.set_tag("component", component)
    return True


def current_trace_id() -> str | None:
    """Etkin izin kimliği (loglara eklenir); iz takibi kapalıysa None."""
    if not _tracing_started:
        return None
    from opentelemetry import trace

    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else None
