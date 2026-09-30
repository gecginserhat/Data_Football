"""HTTP yardımcıları: imleç sayfalama ve ETag (SPEC §11).

İmleç, son öğenin sıralama anahtarının base64url ile kodlanmış JSON'udur; istemci için opaktır.
ETag, yanıt gövdesinin SHA-256 özetidir (zayıf değil, güçlü). `If-None-Match` tutarsa 304 döner.
"""

import base64
import hashlib
import json
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from kurgu_api.core.problems import ProblemError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def encode_cursor(key: list[Any]) -> str:
    raw = json.dumps(key, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, size: int) -> list[Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        key = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProblemError(400, "invalid-cursor", "Invalid cursor") from exc
    if not isinstance(key, list) or len(key) != size:
        raise ProblemError(400, "invalid-cursor", "Invalid cursor")
    return key


def etag_response(request: Request, model: BaseModel) -> Response:
    """Gövdeyi ETag ile döner; istemcinin ETag'i aynıysa 304 (gövdesiz)."""
    body = jsonable_encoder(model)
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    etag = f'"{digest[:32]}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    candidates = {t.strip() for t in request.headers.get("if-none-match", "").split(",")}
    if etag in candidates or "*" in candidates:
        return Response(status_code=304, headers=headers)
    return JSONResponse(body, headers=headers)
