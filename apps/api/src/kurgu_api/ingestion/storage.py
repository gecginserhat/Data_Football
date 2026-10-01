"""Nesne deposu: ham yükler (bronze) ve içe aktarılan dosyalar (SPEC §5.2).

İki uygulama vardır: S3 uyumlu depo (yerelde MinIO) ve testler için yerel klasör. Anahtarlar
içerik özetini taşır (`raw/<sağlayıcı>/<sha256>`); aynı içerik aynı anahtara yazılır, bu yüzden
yazma idempotenttir. Ham yükler değişmez: var olan anahtarın üzerine yazılmaz.
"""

import asyncio
from pathlib import Path
from typing import Any, Protocol

from kurgu_api.config import Settings, get_settings


class ObjectStore(Protocol):
    async def put(self, key: str, content: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def exists(self, key: str) -> bool: ...


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("invalid object key")
        return path

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        path = self._path(key)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(content)
        tmp.replace(path)

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3ObjectStore:
    """boto3 istemcisi eşzamanlı olduğu için çağrılar iş parçacığında çalışır."""

    def __init__(self, settings: Settings) -> None:
        import boto3

        self.bucket = settings.s3_bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        if await self.exists(key):
            return
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True


def get_object_store(settings: Settings | None = None) -> ObjectStore:
    settings = settings or get_settings()
    if settings.kurgu_storage_backend == "s3":
        return S3ObjectStore(settings)
    return LocalObjectStore(Path(settings.kurgu_storage_dir))
