"""Lig uçlarının yanıt şemaları. Faz 1'de ham kayıt değerleri döner; türetilmiş metrikler Faz 2."""

import uuid

from pydantic import BaseModel


class CompetitionRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class SeasonOut(BaseModel):
    id: uuid.UUID
    code: str
    label: str
    matches_per_team: int | None
    competition: CompetitionRef


class SeasonPage(BaseModel):
    items: list[SeasonOut]
    next_cursor: str | None


class TeamRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class StandingRowOut(BaseModel):
    position: int
    team: TeamRef
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    pts: int


class StandingsOut(BaseModel):
    season_id: uuid.UUID
    week: int
    source: str
    rows: list[StandingRowOut]


class TeamMetricsOut(BaseModel):
    team: TeamRef
    as_of_week: int | None
    """Sezon sürüyorsa verinin geçerli olduğu hafta; tamamlanmış sezonda boş."""
    source: str
    metrics: dict[str, float]


class TeamMetricsPage(BaseModel):
    season_id: uuid.UUID
    items: list[TeamMetricsOut]
    next_cursor: str | None


class TeamOut(TeamRef):
    official_name: str | None


class TeamProfileOut(BaseModel):
    team: TeamOut
    season: SeasonOut
    as_of_week: int | None
    source: str | None
    metrics: dict[str, float]
    standing: StandingRowOut | None
    standing_week: int | None
