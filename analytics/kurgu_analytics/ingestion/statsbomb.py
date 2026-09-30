"""StatsBomb Open Data adaptörü ve SPADL eşleyicisi (SPEC §5.3; ADR-0003; assumptions A-06, A-16).

Veri: https://github.com/statsbomb/open-data. Lisans ve atıf koşulları geçerlidir; veriler
repoya eklenmez, `data/statsbomb/` önbelleğine indirilir (`make statsbomb-fetch`).

SPADL dönüşümü socceraction'ın StatsBomb dönüştürücüsünün kurallarını izler (tür, sonuç ve
vücut bölgesi eşlemesi). socceraction 1.5 numpy<2 ve pandera<0.18 sabitlediği için doğrudan
bağımlılık olarak kullanılmaz; uyum ayrı bir karşılaştırma betiğiyle ölçülür (A-16).
Farklar: socceraction'ın sonradan eklediği sentetik `dribble` aksiyonları üretilmez; StatsBomb
`Carry` olayları zaten `dribble` olarak gelir.

Koordinatlar StatsBomb'da olayı yapan takımın hücum yönündedir; kanoniğe
`kurgu_analytics.canonical.coords.statsbomb_to_canonical` ile çevrilir.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from kurgu_analytics.canonical.coords import statsbomb_to_canonical
from kurgu_analytics.canonical.model import Action, CanonicalMatch, Match, Player, Team
from kurgu_analytics.ingestion.base import RawPayload

PROVIDER = "statsbomb_open"
BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
ATTRIBUTION = "Data: StatsBomb Open Data (https://github.com/statsbomb/open-data)"

# Doğrulama için varsayılan yarışmalar (A-06): (competition_id, season_id).
DEFAULT_COMPETITIONS: tuple[tuple[int, int], ...] = (
    (43, 106),  # FIFA Dünya Kupası 2022
    (55, 282),  # UEFA Euro 2024
    (9, 281),  # 1. Bundesliga 2023/24
)

_KEEPER_TYPES = {
    "Shot Saved": "keeper_save",
    "Shot Saved Off Target": "keeper_save",
    "Shot Saved to Post": "keeper_save",
    "Penalty Saved": "keeper_save",
    "Penalty Saved to Post": "keeper_save",
    "Save": "keeper_save",
    "Smother": "keeper_save",
    "Collected": "keeper_claim",
    "Punch": "keeper_punch",
    "Keeper Sweeper": "keeper_claim",
}
_FAIL_OUTCOMES = {
    "Incomplete",
    "Out",
    "Unknown",
    "Injury Clearance",
    "Lost",
    "Lost In Play",
    "Lost Out",
    "Fail",
    "No Touch",
    "In Play Danger",
}


def _name(obj: Any) -> str | None:
    return obj.get("name") if isinstance(obj, dict) else None


def spadl_type(event: dict[str, Any]) -> str:
    """StatsBomb olay türü → SPADL aksiyon türü."""
    etype = event["type"]["name"]
    if etype == "Pass":
        p = event.get("pass", {})
        if _name(p.get("outcome")) in {"Unknown", "Injury Clearance"}:
            return "non_action"  # oyun dışı ya da belirsiz pas (socceraction ile aynı)
        ptype = _name(p.get("type"))
        crossed = _name(p.get("height")) == "High Pass" or bool(p.get("cross"))
        if ptype == "Free Kick":
            return "freekick_crossed" if crossed else "freekick_short"
        if ptype == "Corner":
            return "corner_crossed" if crossed else "corner_short"
        if ptype == "Goal Kick":
            return "goalkick"
        if ptype == "Throw-in":
            return "throw_in"
        return "cross" if p.get("cross") else "pass"
    if etype == "Dribble":
        return "take_on"
    if etype == "Carry":
        return "dribble"
    if etype == "Foul Committed":
        return "foul"
    if etype == "Duel" and _name(event.get("duel", {}).get("type")) == "Tackle":
        return "tackle"
    if etype == "Interception":
        return "interception"
    if etype == "Shot":
        stype = _name(event.get("shot", {}).get("type"))
        if stype == "Free Kick":
            return "shot_freekick"
        if stype == "Penalty":
            return "shot_penalty"
        return "shot"
    if etype == "Own Goal Against":
        return "bad_touch"  # sonuç `owngoal` (socceraction ile aynı)
    if etype == "Goal Keeper":
        return _KEEPER_TYPES.get(_name(event.get("goalkeeper", {}).get("type")) or "", "non_action")
    if etype == "Clearance":
        return "clearance"
    if etype == "Miscontrol":
        return "bad_touch"
    return "non_action"


def spadl_result(event: dict[str, Any], action_type: str) -> str:
    """StatsBomb sonucu → SPADL sonucu."""
    etype = event["type"]["name"]
    if etype == "Own Goal Against":
        return "owngoal"
    if etype == "Pass":
        outcome = _name(event.get("pass", {}).get("outcome"))
        if outcome is None:
            return "success"
        return "offside" if outcome == "Pass Offside" else "fail"
    if etype == "Shot":
        return "success" if _name(event.get("shot", {}).get("outcome")) == "Goal" else "fail"
    if etype == "Dribble":
        return "success" if _name(event.get("dribble", {}).get("outcome")) == "Complete" else "fail"
    if etype == "Foul Committed":
        card = _name(event.get("foul_committed", {}).get("card")) or ""
        if card in {"Red Card", "Second Yellow"}:
            return "red_card"
        return "yellow_card" if card == "Yellow Card" else "fail"
    if action_type == "bad_touch":
        return "fail"  # kendi kalesine gol yukarıda `owngoal` olarak döndü
    section = {"Duel": "duel", "Interception": "interception", "Goal Keeper": "goalkeeper"}.get(
        etype
    )
    if section:
        outcome = _name(event.get(section, {}).get("outcome"))
        return "fail" if outcome in _FAIL_OUTCOMES else "success"
    return "success"


def spadl_bodypart(event: dict[str, Any], action_type: str) -> str:
    if action_type == "throw_in":
        return "other"
    section = {
        "Pass": "pass",
        "Shot": "shot",
        "Clearance": "clearance",
        "Goal Keeper": "goalkeeper",
    }.get(event["type"]["name"])
    part = _name(event.get(section, {}).get("body_part")) if section else None
    if part is None:
        return "foot"
    if part == "Head":
        return "head"
    if part == "Left Foot":
        return "foot_left"
    if part == "Right Foot":
        return "foot_right"
    if part in {"Drop Kick"}:
        return "foot"
    return "other"


def _end_location(event: dict[str, Any]) -> list[float] | None:
    for section in ("pass", "carry", "shot", "goalkeeper"):
        end = event.get(section, {}).get("end_location")
        if end:
            return list(end[:2])
    return None


def _seconds(timestamp: str) -> float:
    h, m, s = timestamp.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _extra(event: dict[str, Any]) -> dict[str, Any]:
    """SPADL'ın taşımadığı, doğrulama ve alt tür için gereken StatsBomb alanları."""
    extra: dict[str, Any] = {
        "sb_type": event["type"]["name"],
        "play_pattern": _name(event.get("play_pattern")),
        "possession": event.get("possession"),
    }
    p = event.get("pass")
    if p:
        extra["pass_type"] = _name(p.get("type"))
        extra["pass_height"] = _name(p.get("height"))
        technique = _name(p.get("technique"))
        if technique:
            extra["technique"] = technique
    s = event.get("shot")
    if s:
        extra["shot_type"] = _name(s.get("type"))
    return extra


def events_to_actions(events: Iterable[dict[str, Any]]) -> list[Action]:
    """StatsBomb olay listesi → sıralı SPADL aksiyonları (`non_action` atılır)."""
    actions: list[Action] = []
    ordered = sorted(events, key=lambda e: (e["period"], e["index"]))
    for event in ordered:
        if event["period"] > 4 or "location" not in event:
            continue  # penaltı atışları (period 5) ve konumsuz olaylar dışarıda
        atype = spadl_type(event)
        if atype == "non_action":
            continue
        sx, sy = statsbomb_to_canonical(*event["location"][:2])
        end = _end_location(event)
        ex, ey = statsbomb_to_canonical(*end) if end else (sx, sy)
        xg = event.get("shot", {}).get("statsbomb_xg")
        actions.append(
            Action(
                action_index=len(actions),
                period=event["period"],
                time_s=_seconds(event["timestamp"]),
                team_provider_id=str(event["team"]["id"]),
                player_provider_id=str(event["player"]["id"]) if "player" in event else None,
                type=atype,
                result=spadl_result(event, atype),
                bodypart=spadl_bodypart(event, atype),
                start_x=sx,
                start_y=sy,
                end_x=ex,
                end_y=ey,
                xg=float(xg) if xg is not None else None,
                xg_source="statsbomb" if xg is not None else None,
                provider_event_id=event["id"],
                extra=_extra(event),
            )
        )
    return actions


def players_from_events(events: Iterable[dict[str, Any]]) -> list[Player]:
    seen: dict[str, Player] = {}
    for event in events:
        player = event.get("player")
        if player and str(player["id"]) not in seen:
            seen[str(player["id"])] = Player(
                provider_id=str(player["id"]),
                name=player["name"],
                team_provider_id=str(event["team"]["id"]),
            )
        for line in event.get("tactics", {}).get("lineup", []):
            pid = str(line["player"]["id"])
            if pid not in seen:
                seen[pid] = Player(pid, line["player"]["name"], str(event["team"]["id"]))
    return list(seen.values())


def match_from_json(raw: dict[str, Any]) -> Match:
    kickoff = None
    if raw.get("match_date"):
        time = (raw.get("kick_off") or "00:00:00.000")[:8]
        # StatsBomb saat dilimi vermez; yerel saat UTC kabul edilir (yalnız sıralama için).
        kickoff = dt.datetime.fromisoformat(f"{raw['match_date']}T{time}+00:00")
    home, away = raw["home_team"], raw["away_team"]
    return Match(
        provider_id=str(raw["match_id"]),
        competition_provider_id=str(raw["competition"]["competition_id"]),
        competition_name=raw["competition"]["competition_name"],
        season_provider_id=str(raw["season"]["season_id"]),
        season_name=raw["season"]["season_name"],
        home=Team(str(home["home_team_id"]), home["home_team_name"]),
        away=Team(str(away["away_team_id"]), away["away_team_name"]),
        kickoff_at=kickoff,
        home_score=raw.get("home_score"),
        away_score=raw.get("away_score"),
        week=raw.get("match_week"),
        stage=_name(raw.get("competition_stage")),
    )


class StatsBombOpenData:
    """StatsBomb Open Data sağlayıcısı: önce yerel önbellek, yoksa (izin varsa) indirme."""

    name = PROVIDER

    def __init__(
        self, cache_dir: Path, *, base_url: str = BASE_URL, allow_download: bool = True
    ) -> None:
        self.cache_dir = cache_dir
        self.base_url = base_url
        self.allow_download = allow_download

    def _read(self, relative: str) -> bytes:
        path = self.cache_dir / relative
        if path.is_file():
            return path.read_bytes()
        if not self.allow_download:
            raise FileNotFoundError(f"{path} yok; önce `make statsbomb-fetch` çalıştırın")
        url = f"{self.base_url}/{relative}"
        if not url.startswith("https://"):
            raise ValueError("only https sources are allowed")
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 (https zorunlu)
            content: bytes = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return content

    def list_matches(self, params: dict[str, Any]) -> list[Match]:
        raw = json.loads(
            self._read(f"matches/{params['competition_id']}/{params['season_id']}.json")
        )
        matches = [match_from_json(m) for m in raw]
        limit = params.get("limit")
        return matches[: int(limit)] if limit else matches

    def fetch_events(self, match: Match) -> RawPayload:
        content = self._read(f"events/{match.provider_id}.json")
        return RawPayload(PROVIDER, "events", match.provider_id, content)

    def to_canonical(self, match: Match, raw: RawPayload) -> CanonicalMatch:
        events = json.loads(raw.content)
        return CanonicalMatch(
            match=match,
            players=tuple(players_from_events(events)),
            actions=tuple(events_to_actions(events)),
        )


def fetch_all(
    cache_dir: Path,
    competitions: Iterable[tuple[int, int]] = DEFAULT_COMPETITIONS,
    *,
    workers: int = 8,
) -> int:
    """Seçili yarışmaların maç listelerini ve olay dosyalarını önbelleğe indirir."""
    from concurrent.futures import ThreadPoolExecutor

    provider = StatsBombOpenData(cache_dir)
    matches = [
        m
        for competition_id, season_id in competitions
        for m in provider.list_matches({"competition_id": competition_id, "season_id": season_id})
    ]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(provider.fetch_events, matches))
    return len(matches)


def main() -> None:
    """`python -m kurgu_analytics.ingestion.statsbomb [önbellek]` (`make statsbomb-fetch`)."""
    import sys

    cache = Path(sys.argv[1] if len(sys.argv) > 1 else "data/statsbomb")
    count = fetch_all(cache)
    print(f"{count} matches cached in {cache}. {ATTRIBUTION}")


if __name__ == "__main__":
    main()
