"""Şifreli yedek ve geri yükleme tatbikatı (ADR-0018, A-95)."""

import datetime as dt
import json
import subprocess
from pathlib import Path

import asyncpg
import pytest
from kurgu_api.ops.backup import (
    BackupError,
    DrillResult,
    LocalTarget,
    create_backup,
    drill_report,
    latest_manifest,
    libpq_url,
    run_drill,
    split_toc,
    with_database,
)
from kurgu_api.performance.service import seal

from .conftest import ADMIN_URL, DB_NAME, Seeded


def _keypair(directory: Path, name: str) -> tuple[Path, Path]:
    identity = directory / f"{name}.txt"
    subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
    recipient = subprocess.run(
        ["age-keygen", "-y", str(identity)], check=True, capture_output=True, text=True
    ).stdout
    recipients = directory / f"{name}.pub"
    recipients.write_text(recipient)
    return identity, recipients


def test_urls_are_converted_for_libpq() -> None:
    assert libpq_url("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert with_database("postgresql://u:p@h:5432/db", "other") == "postgresql://u:p@h:5432/other"


def test_view_data_is_split_from_the_restore_list() -> None:
    listing = "\n".join(
        [
            "; Archive created at 2026-10-01",
            "215; 1259 16500 TABLE public set_pieces kurgu_owner",
            "4100; 0 16700 MATERIALIZED VIEW DATA public mv_team_setpiece_season kurgu_owner",
            "4101; 0 16710 MATERIALIZED VIEW DATA public mv_league_benchmarks kurgu_owner",
        ]
    )
    kept, views = split_toc(listing)
    assert "MATERIALIZED VIEW DATA" not in kept
    assert "TABLE public set_pieces" in kept
    assert views == [
        ("mv_team_setpiece_season", "kurgu_owner"),
        ("mv_league_benchmarks", "kurgu_owner"),
    ]


def test_latest_manifest_needs_a_backup() -> None:
    with pytest.raises(BackupError):
        latest_manifest(["kurgu-1.dump.age"])
    assert latest_manifest(["kurgu-1.json", "kurgu-2.dump.age", "kurgu-2.json"]) == "kurgu-2.json"


def test_failed_drill_report_lists_mismatches() -> None:
    result = DrillResult(
        backup="kurgu-x",
        started_at="2026-10-01T00:00:00+00:00",
        database="d",
        alembic_version="0009",
        expected_version="0009",
        tables=2,
        rows=10,
        count_mismatches={"squad_players": (5, 4)},
        wellness_checked=True,
        wellness_note="ok",
    )
    assert not result.ok
    report = drill_report(result, environment="test")
    assert "BAŞARISIZ" in report
    assert "| squad_players | 5 | 4 |" in report


async def test_backup_is_encrypted_and_restores_with_matching_counts(
    tmp_path: Path, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    player = await superuser.fetchval(
        "insert into squad_players (tenant_id, name, shirt_number, position, height_cm)"
        " values ($1, 'Yedek Oyuncu', 31, 'MID', 180) returning id",
        tenants.tenant_a,
    )
    scores = {"sleep": 3, "stress": 2, "fatigue": 4, "soreness": 3}
    await superuser.execute(
        "insert into wellness_entries (tenant_id, squad_player_id, date, scores)"
        " values ($1, $2, $3, $4::jsonb)",
        tenants.tenant_a,
        player,
        dt.date(2026, 9, 30),
        json.dumps(seal(scores, tenants.tenant_a)),
    )
    identity, recipients = _keypair(tmp_path, "club")
    target = LocalTarget(tmp_path / "store")
    source = with_database(ADMIN_URL, DB_NAME)

    manifest = await create_backup(source, recipients, target)
    dump = (tmp_path / "store" / f"{manifest.name}.dump.age").read_bytes()
    assert dump.startswith(b"age-encryption.org/v1")
    assert b"Yedek Oyuncu" not in dump
    assert manifest.counts["wellness_entries"] >= 1

    result = await run_drill(ADMIN_URL, identity, target)
    assert result.ok, drill_report(result, environment="test")
    assert result.count_mismatches == {}
    assert result.alembic_version == manifest.alembic_version
    assert result.wellness_checked

    left = await superuser.fetchval(
        "select count(*) from pg_database where datname = $1", result.database
    )
    assert left == 0

    # Başka bir anahtar yedeği açamaz; bozulmuş dosya özet denetimine takılır.
    other, _ = _keypair(tmp_path, "other")
    with pytest.raises(BackupError, match="age failed"):
        await run_drill(ADMIN_URL, other, target)
    path = tmp_path / "store" / f"{manifest.name}.dump.age"
    path.write_bytes(dump[:-10] + b"0123456789")
    with pytest.raises(BackupError, match="checksum"):
        await run_drill(ADMIN_URL, identity, target)
