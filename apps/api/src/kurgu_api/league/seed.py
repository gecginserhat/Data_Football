"""Tohum yükleyici (`make seed`; SPEC §5.7, assumptions A-02, A-03, A-09).

Sıra: dosyaları doğrula → bütünlük kontrolleri (hata varsa dur, uyarıları yaz) → geliştirme
kimlikleri → lig verisi → kiracı lisansları ve kulüp bağlantısı. Tek işlemdir; yarıda kalırsa
hiçbir şey yazılmaz. İdempotenttir: ikinci çalıştırma satır sayısını değiştirmez.

Kimlikler: tohumdaki kısa kimlikler (`gs`, `ts`…) `provider_id_map` içinde `provider='seed'`
ile tutulur (A-04). Maçların kimliği `sezon:hafta:ev-deplasman` biçimindedir.
Göç rolüyle bağlanır; paylaşılan tablolar bu rol için RLS'ye tabi değildir. Yalnızca
`development` ve `test` ortamlarında çalışır.
"""

import asyncio
import datetime as dt
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from kurgu_analytics.ingestion.seed import (
    SEED_SOURCE,
    IntegrityReport,
    SuperLigSeed,
    check_integrity,
    load_recommendation_rules,
    load_routine_templates,
    load_super_lig,
    render_report,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from kurgu_api.config import get_settings
from kurgu_api.dev_identities import DEMO_TENANT_ID, SECOND_TENANT_ID, seed_dev_identities

PROVIDER = "seed"
SUPER_LIG = ("TR-SL", "Süper Lig", "TR")
PREMIER_LEAGUE = ("ENG-PL", "Premier League", "GB-ENG")
SEASON_LABELS = {"2025_26": "2025/26", "2026_27": "2026/27"}
CLUB_TEAM = {DEMO_TENANT_ID: "ts"}
LICENSE_NOTE = "Tohum verisi: yalnızca geliştirme ve demo (seed/super_lig.json meta.license_note)."


class SeedIntegrityError(RuntimeError):
    pass


@dataclass
class SeedResult:
    report: IntegrityReport
    teams: dict[str, uuid.UUID] = field(default_factory=dict)
    seasons: dict[str, uuid.UUID] = field(default_factory=dict)


async def _map_id(conn: AsyncConnection, entity: str, provider_id: str) -> uuid.UUID | None:
    row = await conn.execute(
        text(
            "select kurgu_id from provider_id_map"
            " where entity_type = :e and provider = :p and provider_id = :pid"
        ),
        {"e": entity, "p": PROVIDER, "pid": provider_id},
    )
    return row.scalar_one_or_none()


async def _remember(
    conn: AsyncConnection, entity: str, provider_id: str, kurgu_id: uuid.UUID
) -> None:
    await conn.execute(
        text(
            "insert into provider_id_map (entity_type, provider, provider_id, kurgu_id,"
            " confidence, confirmed_at) values (:e, :p, :pid, :kid, 1, now())"
            " on conflict (entity_type, provider, provider_id) do nothing"
        ),
        {"e": entity, "p": PROVIDER, "pid": provider_id, "kid": kurgu_id},
    )


async def _competition(conn: AsyncConnection, code: str, name: str, country: str) -> uuid.UUID:
    row = await conn.execute(
        text(
            "insert into competitions (code, name, country) values (:c, :n, :k)"
            " on conflict (code) do update set name = excluded.name, country = excluded.country"
            " returning id"
        ),
        {"c": code, "n": name, "k": country},
    )
    return row.scalar_one()


async def _season(
    conn: AsyncConnection, competition_id: uuid.UUID, code: str, matches_per_team: int | None
) -> uuid.UUID:
    row = await conn.execute(
        text(
            "insert into seasons (competition_id, code, label, matches_per_team)"
            " values (:cid, :code, :label, :mpt)"
            " on conflict (competition_id, code) do update set label = excluded.label,"
            " matches_per_team = excluded.matches_per_team returning id"
        ),
        {
            "cid": competition_id,
            "code": code,
            "label": SEASON_LABELS[code],
            "mpt": matches_per_team,
        },
    )
    return row.scalar_one()


async def _teams(conn: AsyncConnection, seed: SuperLigSeed) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for team in seed.teams:
        existing = await _map_id(conn, "team", team.id)
        params = {"code": team.code, "name": team.name, "official": team.official_name}
        if existing is None:
            new_id: uuid.UUID = (
                await conn.execute(
                    text(
                        "insert into teams (code, name, official_name, country)"
                        " values (:code, :name, :official, 'TR') returning id"
                    ),
                    params,
                )
            ).scalar_one()
            await _remember(conn, "team", team.id, new_id)
            ids[team.id] = new_id
        else:
            await conn.execute(
                text(
                    "update teams set code = :code, name = :name, official_name = :official"
                    " where id = :id"
                ),
                {**params, "id": existing},
            )
            ids[team.id] = existing
    return ids


async def _stat(
    conn: AsyncConnection,
    season_id: uuid.UUID,
    team_id: uuid.UUID,
    metric: str,
    value: float,
    as_of_week: int | None,
) -> None:
    await conn.execute(
        text(
            "insert into team_season_stats (season_id, team_id, metric, value, as_of_week, source)"
            " values (:s, :t, :m, :v, :w, :src)"
            " on conflict on constraint uq_team_season_stats_key"
            " do update set value = excluded.value"
        ),
        {
            "s": season_id,
            "t": team_id,
            "m": metric,
            "v": value,
            "w": as_of_week,
            "src": SEED_SOURCE,
        },
    )


async def _season_stat(
    conn: AsyncConnection, season_id: uuid.UUID, metric: str, value: float
) -> None:
    await conn.execute(
        text(
            "insert into season_stats (season_id, metric, value, source) values (:s, :m, :v, :src)"
            " on conflict on constraint uq_season_stats_key do update set value = excluded.value"
        ),
        {"s": season_id, "m": metric, "v": value, "src": SEED_SOURCE},
    )


async def _match(
    conn: AsyncConnection,
    season_code: str,
    season_id: uuid.UUID,
    week: int,
    home: uuid.UUID,
    away: uuid.UUID,
    key: str,
    *,
    score: tuple[int, int] | None,
    kickoff_at: dt.datetime | None,
    extra: str,
) -> None:
    provider_id = f"{season_code}:{week}:{key}"
    params = {
        "season": season_id,
        "week": week,
        "home": home,
        "away": away,
        "hs": score[0] if score else None,
        "as_": score[1] if score else None,
        "status": "finished" if score else "scheduled",
        "kickoff": kickoff_at,
        "extra": extra,
        "src": SEED_SOURCE,
    }
    existing = await _map_id(conn, "match", provider_id)
    if existing is None:
        new_id: uuid.UUID = (
            await conn.execute(
                text(
                    "insert into matches (season_id, week, home_team_id, away_team_id, home_score,"
                    " away_score, status, kickoff_at, extra, source) values (:season, :week,"
                    " :home, :away, :hs, :as_, :status, :kickoff, cast(:extra as jsonb), :src)"
                    " returning id"
                ),
                params,
            )
        ).scalar_one()
        await _remember(conn, "match", provider_id, new_id)
    else:
        await conn.execute(
            text(
                "update matches set season_id = :season, week = :week, home_team_id = :home,"
                " away_team_id = :away, home_score = :hs, away_score = :as_, status = :status,"
                " kickoff_at = :kickoff, extra = cast(:extra as jsonb), source = :src"
                " where id = :id"
            ),
            {**params, "id": existing},
        )


async def load_league(conn: AsyncConnection, seed: SuperLigSeed) -> SeedResult:
    result = SeedResult(report=IntegrityReport())
    s25, s26 = seed.seasons.s2025_26, seed.seasons.s2026_27

    sl = await _competition(conn, *SUPER_LIG)
    pl = await _competition(conn, *PREMIER_LEAGUE)
    result.seasons["2025_26"] = await _season(conn, sl, "2025_26", s25.matches_per_team)
    result.seasons["2026_27"] = await _season(conn, sl, "2026_27", 34)
    pl_season = await _season(conn, pl, "2025_26", None)
    teams = result.teams = await _teams(conn, seed)

    season25, season26 = result.seasons["2025_26"], result.seasons["2026_27"]
    for stats in s25.team_stats:
        for metric, value in stats.metrics().items():
            await _stat(conn, season25, teams[stats.team_id], metric, value, None)
    for sp in s26.set_piece_to_date:
        for metric in ("set_piece_goals", "set_piece_xg"):
            value = float(getattr(sp, metric))
            await _stat(conn, season26, teams[sp.team_id], metric, value, s26.as_of_week)

    for row in s26.standings_after_week_6:
        await conn.execute(
            text(
                "insert into standings_snapshots (season_id, week, team_id, position, played, won,"
                " drawn, lost, gf, ga, pts, source) values (:s, :w, :t, :pos, :pl, :won, :dr,"
                " :lost, :gf, :ga, :pts, :src)"
                " on conflict (season_id, week, team_id) do update"
                " set position = excluded.position, played = excluded.played,"
                " won = excluded.won, drawn = excluded.drawn,"
                " lost = excluded.lost, gf = excluded.gf, ga = excluded.ga, pts = excluded.pts,"
                " source = excluded.source"
            ),
            {
                "s": season26,
                "w": s26.as_of_week,
                "t": teams[row.team_id],
                "pos": row.pos,
                "pl": row.played,
                "won": row.won,
                "dr": row.drawn,
                "lost": row.lost,
                "gf": row.gf,
                "ga": row.ga,
                "pts": row.pts,
                "src": SEED_SOURCE,
            },
        )

    for r in s26.results_weeks_1_6:
        await _match(
            conn,
            "2026_27",
            season26,
            r.week,
            teams[r.home],
            teams[r.away],
            f"{r.home}-{r.away}",
            score=(r.home_goals, r.away_goals),
            kickoff_at=None,
            extra="{}",
        )
    for f in s26.fixtures_weeks_7_12:
        kickoff = None
        if f.date and f.time:
            hour, minute = (int(p) for p in f.time.split(":"))
            kickoff = dt.datetime.combine(
                f.date, dt.time(hour, minute), tzinfo=ZoneInfo(f.tz or "Europe/Istanbul")
            )
        extra = json.dumps({"date_window": f.date_window} if f.date_window else {})
        await _match(
            conn,
            "2026_27",
            season26,
            f.week,
            teams[f.home],
            teams[f.away],
            f"{f.home}-{f.away}",
            score=None,
            kickoff_at=kickoff,
            extra=extra,
        )

    for metric, value in seed.benchmarks.super_lig_2025_26.items():
        await _season_stat(conn, season25, metric, value)
    for metric, value in seed.benchmarks.premier_league_2025_26.items():
        await _season_stat(conn, pl_season, metric, value)
    return result


async def link_tenants(conn: AsyncConnection, teams: dict[str, uuid.UUID]) -> None:
    """Geliştirme kiracılarına tohum lisansı ve kulüp bağlantısı (A-09)."""
    for tenant_id in (DEMO_TENANT_ID, SECOND_TENANT_ID):
        await conn.execute(
            text("select set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
        )
        await conn.execute(
            text(
                "insert into data_licenses (tenant_id, provider, terms_note)"
                " select cast(:tid as uuid), cast(:p as varchar), :note"
                " where not exists (select 1 from data_licenses"
                " where tenant_id = :tid and provider = :p and competition_id is null)"
            ),
            {"tid": tenant_id, "p": PROVIDER, "note": LICENSE_NOTE},
        )
        club = CLUB_TEAM.get(tenant_id)
        await conn.execute(
            text("update tenants set club_team_id = :club where id = :tid"),
            {"club": teams[club] if club else None, "tid": tenant_id},
        )


def validate_files(seed_dir: Path) -> tuple[SuperLigSeed, IntegrityReport]:
    seed = load_super_lig(seed_dir / "super_lig.json")
    # Faz 3 ve 4'te yüklenecek; şimdilik yalnızca şema doğrulaması.
    load_routine_templates(seed_dir / "routine_templates.json")
    load_recommendation_rules(seed_dir / "recommendation_rules.json")
    report = check_integrity(seed)
    if not report.ok:
        messages = "; ".join(f.message for f in report.errors)
        raise SeedIntegrityError(f"tohum bütünlük kontrolü başarısız: {messages}")
    return seed, report


async def run_seed(database_url: str | None = None, seed_dir: Path | None = None) -> SeedResult:
    settings = get_settings()
    if settings.kurgu_env not in {"development", "test"}:
        raise SystemExit("seed data is only for development and test environments")
    seed, report = validate_files(seed_dir or Path(settings.kurgu_seed_dir))
    await seed_dev_identities(database_url)
    engine = create_async_engine(database_url or settings.migrations_database_url)
    try:
        async with engine.begin() as conn:
            result = await load_league(conn, seed)
            await link_tenants(conn, result.teams)
    finally:
        await engine.dispose()
    result.report = report
    return result


def main() -> None:
    """`kurgu-seed`: yükler; `kurgu-seed --report DOSYA`: yalnızca bütünlük raporunu yazar."""
    settings = get_settings()
    if len(sys.argv) == 3 and sys.argv[1] == "--report":
        seed = load_super_lig(Path(settings.kurgu_seed_dir) / "super_lig.json")
        Path(sys.argv[2]).write_text(render_report(check_integrity(seed), seed), encoding="utf-8")
        print(f"report written: {sys.argv[2]}")
        return
    result = asyncio.run(run_seed())
    for warning in result.report.warnings:
        print(f"warning [{warning.check}] {warning.message}")
    print(
        f"seed loaded: {len(result.teams)} teams, {len(result.seasons)} seasons,"
        f" {len(result.report.warnings)} integrity warnings (see docs/validation/seed_integrity.md)"
    )


if __name__ == "__main__":
    main()
