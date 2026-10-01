"""Yerel depo uçları (yalnızca `KURGU_STORAGE_BACKEND=local`; geliştirme ve test, A-60).

S3 imzalı adreslerinin yerel karşılığıdır: kimlik doğrulama yoktur, yetki HMAC imzasıyla gelir.
"""

import hashlib
import mimetypes
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse

from kurgu_api.config import get_settings
from kurgu_api.core.problems import ProblemError
from kurgu_api.video.storage import LocalVideoStore, verify

router = APIRouter(prefix="/storage/local", tags=["storage"], include_in_schema=False)
MAX_PART_BYTES = 64 * 1024**2
mimetypes.add_type("application/vnd.apple.mpegurl", ".m3u8")
mimetypes.add_type("video/mp2t", ".ts")


def _store() -> LocalVideoStore:
    settings = get_settings()
    if settings.kurgu_storage_backend != "local":
        raise ProblemError(404, "not-found", "Local storage is disabled")
    return LocalVideoStore(settings)


def _check(
    store: LocalVideoStore, method: str, key: str, upload: str, part: int, exp: int, sig: str
) -> None:
    if not verify(store.secret, method, key, upload, part, exp, sig):
        raise ProblemError(403, "invalid-signature", "Invalid or expired signature")


@router.put("/part")
async def put_part(
    request: Request,
    key: Annotated[str, Query()],
    upload: Annotated[str, Query()],
    part: Annotated[int, Query(ge=1, le=10000)],
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query()],
) -> Response:
    """Bir parçayı yazar; S3 gibi ETag (MD5) döner."""
    store = _store()
    _check(store, "PUT", key, upload, part, exp, sig)
    try:
        path = store.part_path(upload, part)
    except ValueError as exc:
        raise ProblemError(400, "invalid-upload", str(exc)) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(usedforsecurity=False)
    size = 0
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as out:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_PART_BYTES:
                tmp.unlink(missing_ok=True)
                raise ProblemError(413, "part-too-large", "Part is too large")
            digest.update(chunk)
            out.write(chunk)
    tmp.replace(path)
    return Response(status_code=200, headers={"ETag": f'"{digest.hexdigest()}"'})


@router.get("/object")
async def get_object(
    key: Annotated[str, Query()],
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query()],
    upload: Annotated[str, Query()] = "",
    part: Annotated[int, Query()] = 0,
) -> FileResponse:
    store = _store()
    _check(store, "GET", key, upload, part, exp, sig)
    try:
        path = store.path(key)
    except ValueError as exc:
        raise ProblemError(400, "invalid-key", str(exc)) from exc
    if not path.is_file():
        raise ProblemError(404, "not-found", "Object not found")
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "private, max-age=600"})
