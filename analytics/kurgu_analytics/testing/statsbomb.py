"""Sentetik StatsBomb olayları üreten test yardımcıları (gerçek veri repoya eklenmez, A-06)."""

from typing import Any


class SBEvents:
    """Sıralı StatsBomb olay listesi kurar. Zaman saniye, konum StatsBomb 120 × 80."""

    def __init__(self, home: int = 1, away: int = 2) -> None:
        self.home, self.away = home, away
        self.events: list[dict[str, Any]] = []

    def add(
        self,
        type_name: str,
        t: float,
        *,
        team: int | None = None,
        player: int | None = 10,
        location: tuple[float, float] | None = (60.0, 40.0),
        period: int = 1,
        play_pattern: str = "Regular Play",
        **sections: Any,
    ) -> dict[str, Any]:
        minutes, seconds = divmod(t, 60)
        event: dict[str, Any] = {
            "id": f"ev-{len(self.events)}",
            "index": len(self.events) + 1,
            "period": period,
            "timestamp": f"00:{int(minutes):02d}:{seconds:06.3f}",
            "type": {"name": type_name},
            "possession": 1,
            "play_pattern": {"name": play_pattern},
            "team": {"id": team or self.home, "name": f"Team {team or self.home}"},
        }
        if player is not None:
            event["player"] = {"id": player, "name": f"Player {player}"}
        if location is not None:
            event["location"] = list(location)
        event.update(sections)
        self.events.append(event)
        return event

    def pass_(
        self,
        t: float,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        pass_type: str | None = None,
        height: str = "Ground Pass",
        outcome: str | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        section: dict[str, Any] = {"end_location": list(end), "height": {"name": height}}
        if pass_type:
            section["type"] = {"name": pass_type}
        if outcome:
            section["outcome"] = {"name": outcome}
        for key in ("cross", "technique", "body_part"):
            if key in kw:
                value = kw.pop(key)
                section[key] = (
                    {"name": value} if isinstance(value, str) and key != "cross" else value
                )
        kw["pass"] = section
        return self.add("Pass", t, location=start, **kw)

    def shot(
        self,
        t: float,
        start: tuple[float, float],
        *,
        outcome: str = "Off T",
        xg: float = 0.1,
        shot_type: str = "Open Play",
        body_part: str = "Right Foot",
        **kw: Any,
    ) -> dict[str, Any]:
        section = {
            "end_location": [120.0, 40.0, 1.0],
            "outcome": {"name": outcome},
            "statsbomb_xg": xg,
            "type": {"name": shot_type},
            "body_part": {"name": body_part},
        }
        return self.add("Shot", t, location=start, shot=section, **kw)


def match_json(match_id: int = 99, home: int = 1, away: int = 2) -> dict[str, Any]:
    return {
        "match_id": match_id,
        "match_date": "2022-12-01",
        "kick_off": "15:00:00.000",
        "competition": {"competition_id": 43, "competition_name": "FIFA World Cup"},
        "season": {"season_id": 106, "season_name": "2022"},
        "home_team": {"home_team_id": home, "home_team_name": "Home FC"},
        "away_team": {"away_team_id": away, "away_team_name": "Away FC"},
        "home_score": 1,
        "away_score": 0,
        "match_week": 1,
        "competition_stage": {"name": "Group Stage"},
    }
