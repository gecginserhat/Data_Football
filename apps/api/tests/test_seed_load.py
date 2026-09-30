"""`make seed` yükleyicisi: idempotentlik, tohum değerleri ve lisanslar (Faz 1.3)."""

import json
from pathlib import Path

import asyncpg
import pytest
from kurgu_api.dev_identities import DEMO_TENANT_ID, SECOND_TENANT_ID
from kurgu_api.league.seed import SeedIntegrityError, run_seed, validate_files

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
COUNTED = (
    "competitions",
    "seasons",
    "teams",
    "matches",
    "standings_snapshots",
    "team_season_stats",
    "season_stats",
    "provider_id_map",
    "data_licenses",
    "memberships",
)


async def _counts(conn: asyncpg.Connection) -> dict[str, int]:
    return {t: await conn.fetchval(f"select count(*) from {t}") for t in COUNTED}  # noqa: S608


async def test_seed_is_idempotent_and_loads_values(superuser: asyncpg.Connection) -> None:
    await run_seed(seed_dir=SEED_DIR)
    first = await _counts(superuser)
    await run_seed(seed_dir=SEED_DIR)
    assert await _counts(superuser) == first

    assert await superuser.fetchval("select count(*) from teams where country = 'TR'") >= 21
    ts_goals = await superuser.fetchval(
        """
        select v.value from team_season_stats v
        join teams t on t.id = v.team_id join seasons s on s.id = v.season_id
        where t.code = 'TS' and s.code = '2025_26' and v.metric = 'set_piece_goals'
          and v.tenant_id is null
        """
    )
    assert ts_goals == 15
    leader = await superuser.fetchrow(
        """
        select t.code, st.pts from standings_snapshots st join teams t on t.id = st.team_id
        join seasons s on s.id = st.season_id
        where s.code = '2026_27' and st.week = 6 and st.position = 1
        """
    )
    assert (leader["code"], leader["pts"]) == ("AMD", 13)
    finished = await superuser.fetchval(
        "select count(*) from matches where status = 'finished' and source = 'seed:super_lig.json'"
    )
    scheduled = await superuser.fetchval(
        "select count(*) from matches where status = 'scheduled' and source = 'seed:super_lig.json'"
    )
    assert (finished, scheduled) == (54, 54)
    kickoff = await superuser.fetchval(
        """
        select m.kickoff_at at time zone 'Europe/Istanbul' from matches m
        join teams h on h.id = m.home_team_id join teams a on a.id = m.away_team_id
        where h.code = 'GS' and a.code = 'KAS' and m.week = 7
        """
    )
    assert kickoff.isoformat() == "2026-10-09T20:00:00"
    assert (
        await superuser.fetchval(
            "select count(*) from season_stats where metric = 'set_piece_goals_per_match'"
        )
        == 2
    )


async def test_seed_licenses_and_club(superuser: asyncpg.Connection) -> None:
    await run_seed(seed_dir=SEED_DIR)
    licensed = {
        r["tenant_id"]
        for r in await superuser.fetch(
            "select tenant_id from data_licenses where provider = 'seed'"
        )
    }
    assert {DEMO_TENANT_ID, SECOND_TENANT_ID} <= licensed
    club = await superuser.fetchval(
        "select t.code from tenants x join teams t on t.id = x.club_team_id where x.id = $1",
        DEMO_TENANT_ID,
    )
    assert club == "TS"


async def test_seed_data_visible_to_licensed_tenant(
    superuser: asyncpg.Connection, app_conn: asyncpg.Connection
) -> None:
    await run_seed(seed_dir=SEED_DIR)
    await app_conn.execute("select set_config('app.tenant_id', $1, false)", str(SECOND_TENANT_ID))
    assert await app_conn.fetchval("select count(*) from standings_snapshots") >= 18


def test_integrity_error_stops_before_writing(tmp_path: Path) -> None:
    for name in ("routine_templates.json", "recommendation_rules.json"):
        (tmp_path / name).write_text((SEED_DIR / name).read_text(encoding="utf-8"))
    data = json.loads((SEED_DIR / "super_lig.json").read_text(encoding="utf-8"))
    data["seasons"]["2026_27"]["standings_after_week_6"][0]["pts"] += 1
    (tmp_path / "super_lig.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SeedIntegrityError):
        validate_files(tmp_path)
