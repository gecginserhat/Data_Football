"""Lig uçlarının yanıt şemaları (SPEC §11). Türetilmiş değerler `kurgu_analytics.metrics`'ten."""

import datetime as dt
import uuid
from typing import Literal

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


class MetricValueOut(BaseModel):
    """Bir takımın bir metrikteki değeri (SPEC §6.1, §6.4)."""

    value: float
    """Kayıttan hesaplanan ham değer; oranlar 0-1."""
    rank: int
    """Lig sırası: 1 = en yüksek değer; eşitler aynı sırayı alır."""
    percentile: float | None
    teams: int
    """Bu metrikte değeri olan takım sayısı."""
    trials: float | None
    """Oran metriklerinde deneme sayısı."""
    matches: float | None
    shrunk: float | None
    """Beta-binom ya da gamma-Poisson sonsal ortalaması (A-35)."""
    shrunk_low: float | None
    shrunk_high: float | None
    low_sample: bool
    """Deneme < 8 ya da maç < 5: "Az veri"."""
    approx: bool
    """Yaklaşık değer (A-37)."""
    indirect: bool
    """Savunma için dolaylı gösterge."""
    source: str
    """Değerin kaynağı: tohum, sağlayıcı, `events` (olay verisi) ya da `import` (kulüp kaydı)."""


class TeamMetricsOut(BaseModel):
    team: TeamRef
    as_of_week: int | None
    """Sezon sürüyorsa verinin geçerli olduğu hafta; tamamlanmış sezonda boş."""
    values: dict[str, MetricValueOut]
    inputs: dict[str, float]
    """Metriklerin hesaplandığı ham kayıt değerleri (tohum alanları, olay toplamları)."""


class TeamMetricsPage(BaseModel):
    season_id: uuid.UUID
    club_team_id: uuid.UUID | None
    """Aktif kiracının kulübü ("sizin kulübünüz" işareti için)."""
    items: list[TeamMetricsOut]
    next_cursor: str | None


class BenchmarkOut(BaseModel):
    min: float
    max: float
    mean: float
    """Takım değerlerinin ağırlıksız ortalaması (lig ortalaması)."""
    teams: int


class ReferenceOut(BaseModel):
    competition: CompetitionRef
    season_code: str
    metric: str
    value: float
    source: str


class BenchmarksOut(BaseModel):
    season_id: uuid.UUID
    metrics: dict[str, BenchmarkOut]
    totals: dict[str, float]
    """Lig toplamları: goals, set_piece_goals, matches, set_piece_goal_share, …"""
    references: list[ReferenceOut]
    """Kayıttaki referans kıyaslar (ör. Premier League 2025/26 duran top golü / maç)."""


class TeamOut(TeamRef):
    official_name: str | None


class FormOut(BaseModel):
    match_id: uuid.UUID
    week: int | None
    opponent: TeamRef
    home: bool
    goals_for: int
    goals_against: int
    result: Literal["W", "D", "L"]


class TeamProfileOut(BaseModel):
    team: TeamOut
    season: SeasonOut
    as_of_week: int | None
    values: dict[str, MetricValueOut]
    benchmarks: dict[str, BenchmarkOut]
    club: TeamRef | None
    """Aktif kiracının kulübü; profil çubuklarında işaretlenir."""
    club_values: dict[str, MetricValueOut]
    standing: StandingRowOut | None
    standing_week: int | None
    form: list[FormOut]
    """Son 5 maç, yeniden eskiye."""


class SetPieceOut(BaseModel):
    id: uuid.UUID
    match_id: uuid.UUID
    week: int | None
    opponent: TeamRef
    period: int
    start_time_s: float
    sp_type: str
    sp_subtype: str | None
    side: str | None
    target_zone: str | None
    first_contact_team_id: uuid.UUID | None
    outcome: str | None
    shots: int
    xg_total: float
    goal: bool
    phase_of_goal: int | None
    source: str


class SetPiecePage(BaseModel):
    items: list[SetPieceOut]
    next_cursor: str | None


class FixtureOut(BaseModel):
    id: uuid.UUID
    season_id: uuid.UUID
    week: int | None
    kickoff_at: dt.datetime | None
    status: str
    home: TeamRef
    away: TeamRef
    home_score: int | None
    away_score: int | None


class FixturePage(BaseModel):
    items: list[FixtureOut]
    next_cursor: str | None
