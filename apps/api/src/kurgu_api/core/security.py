"""Güvenlik başlıkları ve istek kimliği ara katmanı (SPEC §12.2, §17; ADR-0016, ADR-0017).

Saf ASGI ara katmanıdır; akış yanıtlarını (HLS, dosya) tamponlamaz.
"""

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"
# Swagger UI CDN betikleri ve satır içi başlatıcı kullanır; yalnız belge sayfasında gevşetilir.
DOCS_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;"
    " style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:"
    " https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'"
)
HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool, docs_path: str) -> None:
        self.app = app
        self.hsts = hsts
        self.docs_path = docs_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(REQUEST_ID_HEADER.encode(), b"").decode()
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        csp = DOCS_CSP if scope.get("path", "") == self.docs_path else API_CSP

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in BASE_HEADERS.items():
                    headers.setdefault(key, value)
                headers.setdefault("Content-Security-Policy", csp)
                # Kişisel veri taşıyabilir: kendi önbellek kuralı olmayan yanıt saklanmaz.
                headers.setdefault("Cache-Control", "no-store")
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", HSTS)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)
