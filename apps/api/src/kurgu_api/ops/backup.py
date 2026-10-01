"""Şifreli veritabanı yedeği ve geri yükleme tatbikatı (ADR-0018, A-95).

`kurgu-backup create`: tutarlı bir anlık görüntüden `pg_dump --format=custom` alır, akış halinde
`age` ile kulübün açık anahtarına şifreler, yanına satır sayılarını taşıyan bir manifest koyar ve
hedefe (yerel dizin ya da `s3://kova/önek`) yazar. Yedek sunucusu özel anahtarı hiç görmez.

`kurgu-backup drill`: son yedeği indirir, özetini doğrular, çözer, boş bir veritabanına açar;
göç sürümünü, tablo satır sayılarını ve bir iyi oluş kaydının `KURGU_DATA_KEYS` ile çözülmesini
denetler; süreyi ve sonucu `docs/runbooks/drills/` altına yazar.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from kurgu_api.config import get_settings
from kurgu_api.core.crypto import DecryptError, KeyConfigError
from kurgu_api.performance.service import unseal

PREFIX = "kurgu-"
DUMP_SUFFIX = ".dump.age"
MANIFEST_SUFFIX = ".json"


class BackupError(RuntimeError):
    pass


def libpq_url(url: str) -> str:
    """SQLAlchemy biçimindeki adresten (`postgresql+asyncpg://`) libpq adresi."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(scheme=parts.scheme.split("+", 1)[0]))


def with_database(url: str, database: str) -> str:
    parts = urlsplit(libpq_url(url))
    return urlunsplit(parts._replace(path=f"/{database}"))


# --- Hedef ---------------------------------------------------------------------------------


class Target(Protocol):
    def put(self, name: str, source: Path) -> None: ...
    def get(self, name: str, dest: Path) -> None: ...
    def names(self) -> list[str]: ...


class LocalTarget:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, name: str, source: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, self.root / name)

    def get(self, name: str, dest: Path) -> None:
        shutil.copyfile(self.root / name, dest)

    def names(self) -> list[str]:
        return sorted(p.name for p in self.root.glob(f"{PREFIX}*")) if self.root.exists() else []


class S3Target:
    def __init__(self, bucket: str, prefix: str) -> None:
        import boto3

        settings = get_settings()
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

    def put(self, name: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, self.prefix + name)

    def get(self, name: str, dest: Path) -> None:
        self.client.download_file(self.bucket, self.prefix + name, str(dest))

    def names(self) -> list[str]:
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=self.prefix + PREFIX
        )
        return sorted(
            obj["Key"][len(self.prefix) :] for page in pages for obj in page.get("Contents", [])
        )


def open_target(spec: str) -> Target:
    if spec.startswith("s3://"):
        bucket, _, prefix = spec[5:].partition("/")
        return S3Target(bucket, prefix)
    return LocalTarget(Path(spec))


# --- Manifest ------------------------------------------------------------------------------


@dataclass
class Manifest:
    name: str
    created_at: str
    database: str
    alembic_version: str
    counts: dict[str, int]
    size_bytes: int
    sha256: str
    pg_dump: str
    seconds: float


def latest_manifest(names: list[str]) -> str:
    manifests = [n for n in names if n.endswith(MANIFEST_SUFFIX)]
    if not manifests:
        raise BackupError("no backups found at the target")
    return manifests[-1]


async def table_counts(conn: asyncpg.Connection) -> dict[str, int]:
    """Şemadaki her tablonun satır sayısı (`alembic_version` hariç)."""
    tables = await conn.fetch(
        "select tablename from pg_tables where schemaname = 'public'"
        " and tablename <> 'alembic_version' order by tablename"
    )
    counts: dict[str, int] = {}
    for row in tables:
        name = row["tablename"]
        # Ad katalogdan gelir, kullanıcı girdisi değildir; çift tırnakla kaçırılır.
        quoted = name.replace('"', '""')
        query = f'select count(*) from public."{quoted}"'  # noqa: S608
        counts[name] = int(await conn.fetchval(query))
    return counts


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise BackupError(f"{args[0]} failed: {err.decode(errors='replace').strip()[-500:]}")
    return out.decode()


async def _pipe(dump: list[str], encrypt: list[str]) -> None:
    """`pg_dump | age` akışı; iki sürecin de hatası yakalanır, düz yedek diske yazılmaz."""
    producer = await asyncio.create_subprocess_exec(
        *dump, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert producer.stdout is not None
    consumer = await asyncio.create_subprocess_exec(
        *encrypt, stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert consumer.stdin is not None
    while chunk := await producer.stdout.read(1024 * 1024):
        consumer.stdin.write(chunk)
        await consumer.stdin.drain()
    consumer.stdin.close()
    dump_err = await producer.stderr.read() if producer.stderr else b""
    enc_err = await consumer.stderr.read() if consumer.stderr else b""
    if await producer.wait() != 0:
        raise BackupError(f"pg_dump failed: {dump_err.decode(errors='replace').strip()[-500:]}")
    if await consumer.wait() != 0:
        raise BackupError(f"age failed: {enc_err.decode(errors='replace').strip()[-500:]}")


async def create_backup(
    database_url: str, recipients_file: Path, target: Target, *, now: datetime | None = None
) -> Manifest:
    """Tutarlı anlık görüntüden şifreli yedek ve manifest üretir, hedefe yazar."""
    started = time.monotonic()
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    name = f"{PREFIX}{stamp}"
    url = libpq_url(database_url)
    conn = await asyncpg.connect(url)
    try:
        # Sayımlar ve döküm aynı anlık görüntüyü görür; tatbikat birebir karşılaştırır.
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            snapshot = str(await conn.fetchval("select pg_export_snapshot()"))
            version = str(await conn.fetchval("select version_num from alembic_version"))
            database = str(await conn.fetchval("select current_database()"))
            counts = await table_counts(conn)
            with tempfile.TemporaryDirectory() as tmp:
                encrypted = Path(tmp) / f"{name}{DUMP_SUFFIX}"
                await _pipe(
                    ["pg_dump", "--format=custom", f"--snapshot={snapshot}", f"--dbname={url}"],
                    ["age", "--encrypt", "-R", str(recipients_file), "-o", str(encrypted)],
                )
                manifest = Manifest(
                    name=name,
                    created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    database=database,
                    alembic_version=version,
                    counts=counts,
                    size_bytes=encrypted.stat().st_size,
                    sha256=sha256_file(encrypted),
                    pg_dump=(await _run("pg_dump", "--version")).strip(),
                    seconds=round(time.monotonic() - started, 2),
                )
                manifest_path = Path(tmp) / f"{name}{MANIFEST_SUFFIX}"
                manifest_path.write_text(json.dumps(asdict(manifest), indent=2) + "\n")
                target.put(encrypted.name, encrypted)
                # Manifest en son yazılır: varsa yedek tamamdır.
                target.put(manifest_path.name, manifest_path)
    finally:
        await conn.close()
    return manifest


# --- Tatbikat ------------------------------------------------------------------------------


@dataclass
class DrillResult:
    backup: str
    started_at: str
    database: str
    alembic_version: str
    expected_version: str
    tables: int
    rows: int
    count_mismatches: dict[str, tuple[int, int]] = field(default_factory=dict)
    wellness_checked: bool = False
    wellness_note: str = ""
    download_s: float = 0.0
    restore_s: float = 0.0
    total_s: float = 0.0
    size_bytes: int = 0

    @property
    def ok(self) -> bool:
        return (
            self.alembic_version == self.expected_version
            and not self.count_mismatches
            and self.wellness_checked
        )


async def _check_wellness(conn: asyncpg.Connection) -> tuple[bool, str]:
    row = await conn.fetchrow("select tenant_id, scores from wellness_entries limit 1")
    if row is None:
        return False, "yedekte iyi oluş kaydı yok; şifre çözme denetlenemedi"
    envelope = row["scores"]
    if isinstance(envelope, str):
        envelope = json.loads(envelope)
    try:
        scores = unseal(envelope, uuid.UUID(str(row["tenant_id"])))
    except (DecryptError, KeyConfigError) as exc:
        return False, f"iyi oluş kaydı çözülemedi: {exc}"
    return True, f"bir iyi oluş kaydı çözüldü ({len(scores)} alan)"


def split_toc(listing: str) -> tuple[str, list[tuple[str, str]]]:
    """`pg_restore -l` çıktısından görünüm verisi girdilerini ayırır.

    Görünümler RLS'li tablolardan beslenir ve sahibinin satır güvenliğiyle yenilenmelidir;
    `pg_restore` ise satır güvenliğini kapatıp çalışır ve FORCE RLS altında hata verir.
    Dönüş: görünüm verisi çıkarılmış liste ve sırasıyla (görünüm, sahip) çiftleri.
    """
    kept: list[str] = []
    views: list[tuple[str, str]] = []
    for line in listing.splitlines():
        if " MATERIALIZED VIEW DATA " in line and not line.startswith(";"):
            parts = line.split()
            views.append((parts[-2], parts[-1]))
            continue
        kept.append(line)
    return "\n".join(kept) + "\n", views


async def restore_dump(dump: Path, database_url: str, workdir: Path) -> None:
    """Yedeği açar; sahiplik ve yetkiler korunur (roller `01-roles.sh` ile hedefte olmalıdır).

    Görünümler sonra, sahiplerinin rolüyle ve satır güvenliği açıkken doldurulur.
    """
    listing, views = split_toc(await _run("pg_restore", "--list", str(dump)))
    toc = workdir / "restore.list"
    toc.write_text(listing)
    await _run(
        "pg_restore", "--exit-on-error", f"--use-list={toc}", f"--dbname={database_url}", str(dump)
    )
    conn = await asyncpg.connect(database_url)
    try:
        for view, owner in views:
            quoted_owner = owner.replace('"', '""')
            quoted_view = view.replace('"', '""')
            await conn.execute(f'set role "{quoted_owner}"')
            await conn.execute(f'refresh materialized view public."{quoted_view}"')
            await conn.execute("reset role")
    finally:
        await conn.close()


async def run_drill(
    admin_url: str, identity_file: Path, target: Target, *, keep: bool = False
) -> DrillResult:
    """Son yedeği boş bir veritabanına açar ve doğrular. Açılan veritabanı sonunda silinir."""
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    manifest_name = latest_manifest(target.names())
    database = f"kurgu_drill_{datetime.now(UTC):%Y%m%d%H%M%S}"
    admin = libpq_url(admin_url)
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / manifest_name
        target.get(manifest_name, manifest_path)
        manifest = Manifest(**json.loads(manifest_path.read_text()))
        encrypted = Path(tmp) / f"{manifest.name}{DUMP_SUFFIX}"
        target.get(encrypted.name, encrypted)
        download_s = time.monotonic() - started
        if sha256_file(encrypted) != manifest.sha256:
            raise BackupError("backup checksum does not match its manifest")
        dump = Path(tmp) / f"{manifest.name}.dump"
        await _run("age", "--decrypt", "-i", str(identity_file), "-o", str(dump), str(encrypted))

        conn = await asyncpg.connect(admin)
        try:
            await conn.execute(f'create database "{database}"')
        finally:
            await conn.close()
        restore_started = time.monotonic()
        try:
            await restore_dump(dump, with_database(admin, database), Path(tmp))
            restore_s = time.monotonic() - restore_started
            restored = await asyncpg.connect(with_database(admin, database))
            try:
                version = str(await restored.fetchval("select version_num from alembic_version"))
                counts = await table_counts(restored)
                wellness_ok, note = await _check_wellness(restored)
            finally:
                await restored.close()
        finally:
            if not keep:
                conn = await asyncpg.connect(admin)
                try:
                    await conn.execute(f'drop database if exists "{database}" with (force)')
                finally:
                    await conn.close()
    mismatches = {
        table: (manifest.counts.get(table, -1), counts.get(table, -1))
        for table in sorted(set(manifest.counts) | set(counts))
        if manifest.counts.get(table) != counts.get(table)
    }
    return DrillResult(
        backup=manifest.name,
        started_at=started_at,
        database=database,
        alembic_version=version,
        expected_version=manifest.alembic_version,
        tables=len(counts),
        rows=sum(counts.values()),
        count_mismatches=mismatches,
        wellness_checked=wellness_ok,
        wellness_note=note,
        download_s=round(download_s, 2),
        restore_s=round(restore_s, 2),
        total_s=round(time.monotonic() - started, 2),
        size_bytes=manifest.size_bytes,
    )


def drill_report(result: DrillResult, *, environment: str) -> str:
    """Tatbikat kaydı (Markdown). Kişisel veri içermez; yalnız sayılar ve süreler."""
    verdict = "BAŞARILI" if result.ok else "BAŞARISIZ"
    lines = [
        f"# Geri yükleme tatbikatı · {result.started_at[:10]}",
        "",
        f"- **Sonuç:** {verdict}",
        f"- **Ortam:** {environment}",
        f"- **Yedek:** `{result.backup}` ({result.size_bytes / 1024 / 1024:.1f} MB, şifreli)",
        f"- **Başlangıç:** {result.started_at}",
        f"- **Göç sürümü:** {result.alembic_version} (beklenen {result.expected_version})",
        f"- **Tablolar / satırlar:** {result.tables} / {result.rows}",
        f"- **Satır sayısı farkı:** {len(result.count_mismatches) or 'yok'}",
        f"- **Şifreli alan:** {result.wellness_note}",
        f"- **Süre:** indirme {result.download_s} sn, açma {result.restore_s} sn,"
        f" toplam {result.total_s} sn (RTO hedefi 4 saat)",
        "",
    ]
    if result.count_mismatches:
        lines += ["| Tablo | Yedekte | Açılan |", "|---|---:|---:|"]
        lines += [f"| {t} | {a} | {b} |" for t, (a, b) in result.count_mismatches.items()]
        lines.append("")
    lines.append("Komut: `make restore-drill` (bkz. `docs/runbooks/backup-restore.md`).")
    return "\n".join(lines) + "\n"


# --- Komut satırı --------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kurgu-backup", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="şifreli yedek al")
    create.add_argument("--database-url", required=True)
    create.add_argument("--recipients", type=Path, required=True, help="age açık anahtar dosyası")
    create.add_argument("--target", required=True, help="dizin ya da s3://kova/önek")
    drill = sub.add_parser("drill", help="son yedeği aç ve doğrula")
    drill.add_argument("--admin-url", required=True, help="veritabanı oluşturabilen rol")
    drill.add_argument("--identity", type=Path, required=True, help="age özel anahtar dosyası")
    drill.add_argument("--target", required=True)
    drill.add_argument("--report-dir", type=Path, default=None)
    drill.add_argument("--environment", default="yerel")
    drill.add_argument("--keep", action="store_true", help="açılan veritabanını silme")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    key_file: Path = args.recipients if args.command == "create" else args.identity
    if not key_file.is_file():
        print(f"kurgu-backup: age key file not found: {key_file}", file=sys.stderr)
        return 1
    try:
        if args.command == "create":
            manifest = asyncio.run(
                create_backup(args.database_url, args.recipients, open_target(args.target))
            )
            print(json.dumps(asdict(manifest) | {"counts": len(manifest.counts)}, indent=2))
            return 0
        result = asyncio.run(
            run_drill(args.admin_url, args.identity, open_target(args.target), keep=args.keep)
        )
    except BackupError as exc:
        print(f"kurgu-backup: {exc}", file=sys.stderr)
        return 1
    report = drill_report(result, environment=args.environment)
    if args.report_dir:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        path = args.report_dir / f"{result.started_at[:10]}-restore-drill.md"
        path.write_text(report)
        print(f"report: {path}")
    print(report)
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
