"""RFC 9457 `application/problem+json` hata yanıtları (SPEC §11)."""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"
PROBLEM_BASE = "https://kurgu.app/problems/"


class ProblemError(Exception):
    """Uygulama kodunun fırlattığı, problem+json'a dönüşen hata."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.status = status
        self.code = code
        self.detail = detail
        self.headers = headers
        self.extra = extra or {}


def problem_response(
    request: Request,
    status: int,
    code: str,
    detail: str | None = None,
    *,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE}{code}",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    body.update(extra or {})
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


_STATUS_CODES = {
    400: "bad-request",
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    405: "method-not-allowed",
    409: "conflict",
    422: "validation-error",
    429: "too-many-requests",
}


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(
            request, exc.status, exc.code, exc.detail, headers=exc.headers, extra=exc.extra
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        detail = exc.detail if isinstance(exc.detail, str) else None
        headers = dict(exc.headers) if exc.headers else None
        return problem_response(request, exc.status_code, code, detail, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problem_response(
            request, 422, "validation-error", "Request validation failed", extra={"errors": errors}
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return problem_response(request, 500, "internal-error")
