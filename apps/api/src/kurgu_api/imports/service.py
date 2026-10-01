"""İçe aktarım: dosyayı çözümle, takımları eşle, onaylanınca kiracının tablolarına yaz (SPEC §5.6).

Akış: `uploaded` (eşleştirme onay bekliyor) → `validated` ya da `quarantined` → `committed`.
Dosya nesne deposunda değişmeden durur; eşleştirme her değiştiğinde dosya yeniden okunup
doğrulanır. Yazılan satırlar yalnızca içe aktaran kiracıya aittir (`tenant_id`, RLS).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
from kurgu_analytics.canonical.model import SHOT_TYPES, Action
from kurgu_analytics.ingestion.imports import (
    AUTO_MATCH_SCORE,
    TEAM_STATS_METRICS,
    Issue,
    Kind,
    apply_mapping,
    match_names,
    read_table,
    suggest_mapping,
    validate,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kurgu_api.core.audit import write_audit
from kurgu_api.ingestion.setpieces import insert_set_pieces

Status = Literal["uploaded", "validated", "quarantined", "committed", "failed"]
TEAM_COLUMNS: dict[Kind, tuple[str, ...]] = {
    "team_season_stats": ("team",),
    "events": ("home_team", "away_team"),
}
SOURCE = "import"
SAMPLE_ROWS = 5
UNKNOWN_BODYPART = "other"
"""Dosyada vücut bölgesi yoksa SPADL `other` yazılır (A-33)."""


@dataclass(slots=True)
class Analysis:
    file_columns: list[str]
    sample: list[dict[str, str]]
    columns: dict[str, str | None]
    teams: dict[str, dict[str, Any]]
    report: dict[str, Any]
    status: Status
    typed: pd.DataFrame | None

    def mapping_json(self) -> dict[str, Any]:
        return {
            "file_columns": self.file_columns,
            "sample": self.sample,
            "columns": self.columns,
            "teams": self.teams,
        }


async def team_candidates(
    session: AsyncSession, season_id: uuid.UUID
) -> list[tuple[str, str, str]]:
    """Sezonda görünen takımlar; sezonda hiç kayıt yoksa görülebilen tüm takımlar."""
    rows = (
        await session.execute(
            text(
                """
                select t.id, t.name, t.code from teams t where t.id in (
                  select home_team_id from matches where season_id = :s
                  union select away_team_id from matches where season_id = :s
                  union select team_id from team_season_stats where season_id = :s
                  union select team_id from standings_snapshots where season_id = :s)
                order by t.name
                """
            ),
            {"s": season_id},
        )
    ).all()
    if not rows:
        rows = (await session.execute(text("select id, name, code from teams order by name"))).all()
    return [(str(r.id), r.name, r.code) for r in rows]


def analyze(
    content: bytes,
    filename: str,
    kind: Kind,
    candidates: list[tuple[str, str, str]],
    columns: dict[str, str | None] | None = None,
    team_choices: dict[str, str | None] | None = None,
) -> Analysis:
    """Dosyayı okur, sütunları eşler, doğrular ve takım isimlerini adaylarla eşleştirir.

    `team_choices`: kullanıcının elle seçtiği takımlar (isim → takım kimliği ya da `None`).
    Puanı `AUTO_MATCH_SCORE` altındaki öneriler onay bekler. `UnreadableFileError` fırlatabilir.
    """
    frame = read_table(content, filename)
    file_columns = [str(c) for c in frame.columns]
    if columns is None:
        columns = suggest_mapping(file_columns, kind)
    mapped = apply_mapping(frame, columns)
    report, typed = validate(mapped, kind)

    names = sorted(
        {
            str(v).strip()
            for col in TEAM_COLUMNS[kind]
            if col in mapped.columns
            for v in mapped[col]
            if str(v).strip()
        }
    )
    scores = match_names(names, candidates)
    choices = team_choices or {}
    teams: dict[str, dict[str, Any]] = {}
    for name in names:
        suggested, score = scores[name]
        entry: dict[str, Any] = {"suggested": suggested, "score": round(score, 3)}
        if name in choices:
            entry |= {"team_id": choices[name], "manual": True}
        else:
            auto = suggested is not None and score >= AUTO_MATCH_SCORE
            entry |= {"team_id": suggested if auto else None, "manual": False}
        entry["confirmed"] = entry["team_id"] is not None
        teams[name] = entry

    for issue in _team_mapping_issues(mapped, kind, teams):
        report.issues.append(issue)
        typed = None

    if report.critical:
        status: Status = "quarantined"
    elif all(t["confirmed"] for t in teams.values()):
        status = "validated"
    else:
        status = "uploaded"
    sample = frame.head(SAMPLE_ROWS).astype(str).to_dict(orient="records")
    return Analysis(
        file_columns=file_columns,
        sample=[{str(k): v for k, v in row.items()} for row in sample],
        columns=columns,
        teams=teams,
        report=report.to_dict(),
        status=status,
        typed=typed if status != "quarantined" else None,
    )


def _team_mapping_issues(
    mapped: pd.DataFrame, kind: Kind, teams: dict[str, dict[str, Any]]
) -> list[Issue]:
    """İki farklı ismin aynı takıma eşlenmesi: istatistikte yineleme, maçta aynı takım."""
    chosen = {name: t["team_id"] for name, t in teams.items() if t["team_id"]}
    if kind == "team_season_stats":
        by_team: dict[str, list[str]] = {}
        for name, team_id in chosen.items():
            by_team.setdefault(team_id, []).append(name)
        clashes = [names for names in by_team.values() if len(names) > 1]
        if not clashes:
            return []
        listed = "; ".join(" / ".join(n) for n in clashes)
        return [Issue("team_mapping", "critical", f"aynı takıma eşlenen isimler: {listed}", "team")]
    if not {"home_team", "away_team"} <= set(mapped.columns):
        return []
    home = mapped["home_team"].map(lambda n: chosen.get(str(n).strip()))
    away = mapped["away_team"].map(lambda n: chosen.get(str(n).strip()))
    same = mapped[home.notna() & (home == away)]
    if not len(same):
        return []
    return [
        Issue(
            "team_mapping",
            "critical",
            "ev sahibi ve deplasman aynı takıma eşlendi",
            "home_team",
            len(same),
            tuple(int(i) for i in same.index[:5]),
        )
    ]


# --- Yazma --------------------------------------------------------------------


async def commit_team_stats(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    season_id: uuid.UUID,
    typed: pd.DataFrame,
    teams: dict[str, uuid.UUID],
) -> dict[str, int]:
    """Takım × metrik satırlarını yazar; aynı kaynaktaki eski değerin üzerine yazar."""
    rows = [
        {
            "tenant": tenant_id,
            "season": season_id,
            "team": teams[str(r["team"]).strip()],
            "metric": metric,
            "value": float(r[metric]),
            "source": SOURCE,
        }
        for _, r in typed.iterrows()
        for metric in TEAM_STATS_METRICS
        if metric in typed.columns and not pd.isna(r[metric])
    ]
    if rows:
        await session.execute(
            text(
                "insert into team_season_stats (tenant_id, season_id, team_id, metric, value,"
                " source) values (:tenant, :season, :team, :metric, :value, :source)"
                " on conflict on constraint uq_team_season_stats_key"
                " do update set value = excluded.value, created_at = now()"
            ),
            rows,
        )
    return {"teams": len(typed), "values": len(rows)}


async def commit_events(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    season_id: uuid.UUID,
    typed: pd.DataFrame,
    teams: dict[str, uuid.UUID],
    import_id: uuid.UUID,
) -> dict[str, int]:
    """Maç başına: maçı (varsa aynı referanslı eskisinin yerine) ve olaylarını yazar, duran top
    dizilerini çıkarır. Skor dosyadaki gollerden hesaplanır."""
    stats = {"matches": 0, "replaced": 0, "events": 0, "set_pieces": 0}
    frame = typed.sort_index().sort_values(["period", "time_s"], kind="stable")
    for ref, group in frame.groupby("match_ref", sort=False):
        first = group.iloc[0]
        home = teams[str(first["home_team"]).strip()]
        away = teams[str(first["away_team"]).strip()]
        stats["replaced"] += await _drop_previous(session, tenant_id, season_id, str(ref))
        actions = [_action(i, r, teams) for i, (_, r) in enumerate(group.iterrows())]
        score = {home: 0, away: 0}
        for a in actions:
            scorer = uuid.UUID(a.team_provider_id)
            if a.type in SHOT_TYPES and a.result == "success":
                score[scorer] += 1
            elif a.result == "owngoal":
                score[away if scorer == home else home] += 1
        match_id: uuid.UUID = (
            await session.execute(
                text(
                    "insert into matches (tenant_id, season_id, home_team_id, away_team_id,"
                    " kickoff_at, home_score, away_score, status, source, extra) values (:tenant,"
                    " :season, :home, :away, :kickoff, :hs, :as_, 'finished', :source,"
                    " cast(:extra as jsonb)) returning id"
                ),
                {
                    "tenant": tenant_id,
                    "season": season_id,
                    "home": home,
                    "away": away,
                    "kickoff": pd.Timestamp(first["match_date"]).to_pydatetime(),
                    "hs": score[home],
                    "as_": score[away],
                    "source": SOURCE,
                    "extra": json.dumps({"import_ref": str(ref), "import_id": str(import_id)}),
                },
            )
        ).scalar_one()
        await session.execute(
            text(
                "insert into events (tenant_id, match_id, action_index, period, time_s, team_id,"
                " type, result, bodypart, start_x, start_y, end_x, end_y, xg, xg_source, provider,"
                " extra) values (:tenant, :match, :idx, :period, :time, :team, :type, :result,"
                " :bodypart, :sx, :sy, :ex, :ey, :xg, :xg_source, :provider,"
                " cast(:extra as jsonb))"
            ),
            [
                {
                    "tenant": tenant_id,
                    "match": match_id,
                    "idx": a.action_index,
                    "period": a.period,
                    "time": a.time_s,
                    "team": uuid.UUID(a.team_provider_id),
                    "type": a.type,
                    "result": a.result,
                    "bodypart": a.bodypart,
                    "sx": a.start_x,
                    "sy": a.start_y,
                    "ex": a.end_x,
                    "ey": a.end_y,
                    "xg": a.xg,
                    "xg_source": a.xg_source,
                    "provider": SOURCE,
                    "extra": json.dumps(a.extra),
                }
                for a in actions
            ],
        )
        team_ids = {str(home): home, str(away): away}
        stats["set_pieces"] += await insert_set_pieces(
            session, match_id, actions, team_ids, {}, tenant_id=tenant_id, source="import"
        )
        stats["matches"] += 1
        stats["events"] += len(actions)
    return stats


def _action(index: int, r: pd.Series, teams: dict[str, uuid.UUID]) -> Action:
    player = r.get("player")
    has_player = isinstance(player, str) and player.strip() != ""
    xg = r.get("xg")
    has_xg = xg is not None and not pd.isna(xg)
    bodypart = r.get("bodypart")
    return Action(
        action_index=index,
        period=int(r["period"]),
        time_s=float(r["time_s"]),
        team_provider_id=str(teams[str(r["team"]).strip()]),
        player_provider_id=player.strip() if has_player else None,
        type=str(r["type"]),
        result=str(r["result"]),
        bodypart=str(bodypart) if isinstance(bodypart, str) and bodypart else UNKNOWN_BODYPART,
        start_x=float(r["start_x"]),
        start_y=float(r["start_y"]),
        end_x=float(r["end_x"]),
        end_y=float(r["end_y"]),
        xg=float(xg) if has_xg else None,
        xg_source=SOURCE if has_xg else None,
        extra={"player": player.strip()} if has_player else {},
    )


async def _drop_previous(
    session: AsyncSession, tenant_id: uuid.UUID, season_id: uuid.UUID, ref: str
) -> int:
    """Aynı kiracının aynı sezonda aynı referansla içe aktardığı maçı kaldırır (yeniden yükleme)."""
    ids: list[uuid.UUID] = list(
        (
            await session.execute(
                text(
                    "select id from matches where tenant_id = :tenant and season_id = :season"
                    " and source = :source and extra ->> 'import_ref' = :ref"
                ),
                {"tenant": tenant_id, "season": season_id, "source": SOURCE, "ref": ref},
            )
        )
        .scalars()
        .all()
    )
    for match_id in ids:
        await session.execute(text("delete from set_pieces where match_id = :m"), {"m": match_id})
        await session.execute(text("delete from matches where id = :m"), {"m": match_id})
    return len(ids)


async def audit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    entity_id: uuid.UUID,
    after: dict[str, Any],
) -> None:
    await write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity="imports",
        entity_id=entity_id,
        after=after,
    )
