"""Video deposu: parçalı yükleme, imzalı adresler, dosya aktarımı (ADR-0010, A-60).

İki uygulama aynı sözleşmeyi sağlar:
- `S3VideoStore`: S3/MinIO çok parçalı yükleme ve imzalı adresler. Tarayıcıya verilen adresler
  `S3_PUBLIC_ENDPOINT_URL` ile imzalanır; worker konteyner içi adresi kullanır.
- `LocalVideoStore`: geliştirme ve test. Adresler API'nin `/storage/local/*` uçlarına gider ve
  HMAC ile imzalanır; imza yöntemi, anahtarı, parçayı ve son kullanma zamanını bağlar.
"""

import asyncio
import hashlib
import hmac
import shutil
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Protocol

from kurgu_api.config import Settings, get_settings

UPLOAD_TTL_S = 6 * 3600
READ_TTL_S = 600
DEV_SIGNING_KEY = "kurgu-dev-storage-signing-key"


class VideoStore(Protocol):
    async def start_upload(self, key: str, content_type: str) -> str: ...

    def part_url(self, key: str, upload_id: str, part: int) -> str: ...

    async def complete(self, key: str, upload_id: str, etags: list[str]) -> None: ...

    async def abort(self, key: str, upload_id: str) -> None: ...

    async def download(self, key: str, path: Path) -> None: ...

    async def read_bytes(self, key: str) -> bytes: ...

    async def upload_file(self, key: str, path: Path, content_type: str) -> None: ...

    def read_url(self, key: str, ttl_s: int = READ_TTL_S) -> str: ...

    async def delete_prefix(self, prefix: str) -> None: ...


def signing_key(settings: Settings) -> bytes:
    if settings.kurgu_storage_signing_key:
        return settings.kurgu_storage_signing_key.encode()
    if settings.kurgu_env in {"development", "test"}:
        return DEV_SIGNING_KEY.encode()
    raise RuntimeError("KURGU_STORAGE_SIGNING_KEY is required outside development")


def sign(secret: bytes, method: str, key: str, upload_id: str, part: int, expires: int) -> str:
    message = f"{method}\n{key}\n{upload_id}\n{part}\n{expires}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify(
    secret: bytes, method: str, key: str, upload_id: str, part: int, expires: int, signature: str
) -> bool:
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(sign(secret, method, key, upload_id, part, expires), signature)


class LocalVideoStore:
    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.kurgu_storage_dir).resolve()
        self.base = settings.kurgu_public_api_url.rstrip("/") + "/api/v1/storage/local"
        self.secret = signing_key(settings)

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("invalid object key")
        return path

    def part_path(self, upload_id: str, part: int) -> Path:
        if not upload_id.isalnum():
            raise ValueError("invalid upload id")
        return self.root / ".uploads" / upload_id / f"{part:05d}"

    def _url(
        self, endpoint: str, method: str, key: str, upload_id: str, part: int, ttl: int
    ) -> str:
        expires = int(time.time()) + ttl
        query = urllib.parse.urlencode(
            {
                "key": key,
                "upload": upload_id,
                "part": part,
                "exp": expires,
                "sig": sign(self.secret, method, key, upload_id, part, expires),
            }
        )
        return f"{self.base}/{endpoint}?{query}"

    async def start_upload(self, key: str, content_type: str) -> str:
        return uuid.uuid4().hex

    def part_url(self, key: str, upload_id: str, part: int) -> str:
        return self._url("part", "PUT", key, upload_id, part, UPLOAD_TTL_S)

    async def complete(self, key: str, upload_id: str, etags: list[str]) -> None:
        def run() -> None:
            target = self.path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".part")
            with tmp.open("wb") as out:
                for n, etag in enumerate(etags, start=1):
                    part = self.part_path(upload_id, n)
                    data = part.read_bytes()
                    if hashlib.md5(data, usedforsecurity=False).hexdigest() != etag.strip('"'):
                        raise ValueError(f"part {n} does not match its etag")
                    out.write(data)
            tmp.replace(target)
            shutil.rmtree(self.part_path(upload_id, 1).parent, ignore_errors=True)

        await asyncio.to_thread(run)

    async def abort(self, key: str, upload_id: str) -> None:
        await asyncio.to_thread(
            shutil.rmtree, self.part_path(upload_id, 1).parent, ignore_errors=True
        )

    async def download(self, key: str, path: Path) -> None:
        await asyncio.to_thread(shutil.copyfile, self.path(key), path)

    async def read_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self.path(key).read_bytes)

    async def upload_file(self, key: str, path: Path, content_type: str) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, path, target)

    def read_url(self, key: str, ttl_s: int = READ_TTL_S) -> str:
        return self._url("object", "GET", key, "", 0, ttl_s)

    async def delete_prefix(self, prefix: str) -> None:
        await asyncio.to_thread(shutil.rmtree, self.path(prefix), ignore_errors=True)


class S3VideoStore:
    """boto3 eşzamanlı olduğu için çağrılar iş parçacığında çalışır."""

    def __init__(self, settings: Settings) -> None:
        import boto3

        def client(endpoint: str | None) -> Any:
            return boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name="us-east-1",
            )

        self.bucket = settings.s3_bucket
        self._client = client(settings.s3_endpoint_url)
        self._public = client(settings.s3_public_endpoint_url or settings.s3_endpoint_url)

    async def start_upload(self, key: str, content_type: str) -> str:
        response = await asyncio.to_thread(
            self._client.create_multipart_upload,
            Bucket=self.bucket,
            Key=key,
            ContentType=content_type,
        )
        upload_id: str = response["UploadId"]
        return upload_id

    def part_url(self, key: str, upload_id: str, part: int) -> str:
        url: str = self._public.generate_presigned_url(
            "upload_part",
            Params={"Bucket": self.bucket, "Key": key, "UploadId": upload_id, "PartNumber": part},
            ExpiresIn=UPLOAD_TTL_S,
        )
        return url

    async def complete(self, key: str, upload_id: str, etags: list[str]) -> None:
        await asyncio.to_thread(
            self._client.complete_multipart_upload,
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [{"ETag": etag, "PartNumber": n} for n, etag in enumerate(etags, 1)]
            },
        )

    async def abort(self, key: str, upload_id: str) -> None:
        await asyncio.to_thread(
            self._client.abort_multipart_upload, Bucket=self.bucket, Key=key, UploadId=upload_id
        )

    async def download(self, key: str, path: Path) -> None:
        await asyncio.to_thread(self._client.download_file, self.bucket, key, str(path))

    async def read_bytes(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def upload_file(self, key: str, path: Path, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.upload_file,
            str(path),
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    def read_url(self, key: str, ttl_s: int = READ_TTL_S) -> str:
        url: str = self._public.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl_s
        )
        return url

    async def delete_prefix(self, prefix: str) -> None:
        def run() -> None:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix.rstrip("/") + "/"):
                keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if keys:
                    self._client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})

        await asyncio.to_thread(run)


_s3_stores: dict[int, S3VideoStore] = {}


def get_video_store() -> VideoStore:
    """Ayarlara göre depo. S3 istemcisi ayar nesnesi başına bir kez kurulur."""
    settings = get_settings()
    if settings.kurgu_storage_backend == "s3":
        store = _s3_stores.get(id(settings))
        if store is None:
            store = _s3_stores.setdefault(id(settings), S3VideoStore(settings))
        return store
    return LocalVideoStore(settings)
