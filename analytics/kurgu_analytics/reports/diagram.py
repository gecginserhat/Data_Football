"""Rutin diyagramı v1: doğrulama ve geometri (ADR-0008, A-39).

Koordinatlar kanonik metredir (SPEC §4). TS karşılığı `@kurgu/pitch` (`src/diagram.ts`); iki
taraf `packages/pitch/diagram.vectors.json` test vektörleriyle aynı sonucu verir.

Kavis: ikinci dereceden Bézier kontrol noktası = orta nokta + curve × (−dy, dx). Pozitif kavis
gidiş yönünün soluna (+90°) bükülür. Ayna `y → 68 − y` yapar ve kavisin işaretini çevirir.
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
DEFAULT_FRAME_MS = 1000
MAX_PLAYERS = 30
MAX_LINES = 80
MAX_ZONES = 12
MAX_FRAMES = 20

ROLES_ENV = "KURGU_ROLES_PATH"
_ROLES_RELATIVE = Path("packages") / "pitch" / "roles.json"

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
X = Annotated[float, Field(ge=0, le=PITCH_LENGTH)]
Y = Annotated[float, Field(ge=0, le=PITCH_WIDTH)]
Point = tuple[float, float]


def _check_point(p: Point) -> None:
    if not (0 <= p[0] <= PITCH_LENGTH and 0 <= p[1] <= PITCH_WIDTH):
        raise ValueError(f"point {p} is outside the 105 x 68 pitch")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DiagramPlayer(_Model):
    id: Id
    team: Literal["own", "opponent"]
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    number: int | None = Field(default=None, ge=1, le=99)
    label: str | None = Field(default=None, max_length=40)
    x: X
    y: Y


class DiagramLine(_Model):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: Id
    kind: Literal["run", "ball_path", "screen"]
    from_: Point = Field(alias="from")
    to: Point
    curve: float = Field(default=0.0, ge=-1, le=1)
    player_id: str | None = None

    @model_validator(mode="after")
    def _points(self) -> Self:
        _check_point(self.from_)
        _check_point(self.to)
        return self


class DiagramZone(_Model):
    id: Id
    x: X
    y: Y
    w: float = Field(gt=0, le=PITCH_LENGTH)
    h: float = Field(gt=0, le=PITCH_WIDTH)
    label: str | None = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def _inside(self) -> Self:
        if self.x + self.w > PITCH_LENGTH + 1e-6 or self.y + self.h > PITCH_WIDTH + 1e-6:
            raise ValueError("zone must lie inside the pitch")
        return self


class DiagramFrame(_Model):
    id: Id
    positions: dict[str, Point] = Field(default_factory=dict)
    ball: Point | None = None
    duration_ms: int = Field(default=DEFAULT_FRAME_MS, ge=200, le=10_000)

    @model_validator(mode="after")
    def _points(self) -> Self:
        for p in self.positions.values():
            _check_point(p)
        if self.ball is not None:
            _check_point(self.ball)
        return self


class Diagram(_Model):
    """Bir rutin sürümünün çizimi."""

    schema_: Literal[1] = Field(default=1, alias="schema")
    players: list[DiagramPlayer] = Field(default_factory=list, max_length=MAX_PLAYERS)
    lines: list[DiagramLine] = Field(default_factory=list, max_length=MAX_LINES)
    zones: list[DiagramZone] = Field(default_factory=list, max_length=MAX_ZONES)
    ball: Point | None = None
    frames: list[DiagramFrame] = Field(default_factory=list, max_length=MAX_FRAMES)

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _references(self) -> Self:
        for name, items in (
            ("players", self.players),
            ("lines", self.lines),
            ("zones", self.zones),
            ("frames", self.frames),
        ):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name} ids must be unique")
        players = {p.id for p in self.players}
        for line in self.lines:
            if line.player_id is not None and line.player_id not in players:
                raise ValueError(f"line {line.id} refers to unknown player {line.player_id}")
        for frame in self.frames:
            unknown = set(frame.positions) - players
            if unknown:
                raise ValueError(f"frame {frame.id} refers to unknown players {sorted(unknown)}")
        if self.ball is not None:
            _check_point(self.ball)
        return self

    def dump(self) -> dict[str, Any]:
        """JSON'a yazılacak biçim (`schema`, `from` adlarıyla)."""
        return self.model_dump(mode="json", by_alias=True)


def control_point(start: Point, end: Point, curve: float) -> Point:
    """Bézier kontrol noktası: orta nokta + curve × (−dy, dx), metre."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return ((start[0] + end[0]) / 2 - curve * dy, (start[1] + end[1]) / 2 + curve * dx)


def point_on_curve(start: Point, end: Point, curve: float, t: float) -> Point:
    c = control_point(start, end, curve)
    u = 1 - t
    return (
        u * u * start[0] + 2 * u * t * c[0] + t * t * end[0],
        u * u * start[1] + 2 * u * t * c[1] + t * t * end[1],
    )


def mirror_point(p: Point) -> Point:
    return (p[0], round(PITCH_WIDTH - p[1], 4))


def mirror(diagram: Diagram) -> Diagram:
    """Sol / sağ varyasyon: y → 68 − y; kavisin işareti döner."""
    raw = diagram.dump()
    for p in raw["players"]:
        p["y"] = round(PITCH_WIDTH - p["y"], 4)
    for line in raw["lines"]:
        line["from"] = list(mirror_point(tuple(line["from"])))
        line["to"] = list(mirror_point(tuple(line["to"])))
        line["curve"] = -line["curve"] if line["curve"] else 0.0
    for z in raw["zones"]:
        z["y"] = round(PITCH_WIDTH - z["y"] - z["h"], 4)
    if raw["ball"] is not None:
        raw["ball"] = list(mirror_point(tuple(raw["ball"])))
    for f in raw["frames"]:
        f["positions"] = {k: list(mirror_point(tuple(v))) for k, v in f["positions"].items()}
        if f["ball"] is not None:
            f["ball"] = list(mirror_point(tuple(f["ball"])))
    return Diagram.model_validate(raw)


def keyframe(diagram: Diagram, index: int) -> tuple[dict[str, Point], Point | None]:
    """Anahtar karedeki konumlar: 0 başlangıç; her kare yalnızca değiştirdiklerini yazar."""
    positions: dict[str, Point] = {p.id: (p.x, p.y) for p in diagram.players}
    ball = diagram.ball
    for frame in diagram.frames[: max(0, index)]:
        for pid, pos in frame.positions.items():
            if pid in positions:
                positions[pid] = pos
        if frame.ball is not None:
            ball = frame.ball
    return positions, ball


def from_template(template: dict[str, Any]) -> Diagram:
    """`seed/routine_templates.json` şablonunu v1 diyagramına çevirir (kimlikler p1…, l1…).

    Top, ilk top yolunun başlangıcına konur. Koşu çizgisi bir oyuncunun 2 m yakınından
    başlıyorsa o oyuncuya bağlanır.
    """
    players = [
        {
            "id": f"p{i}",
            "team": p["team"],
            "role": p["role"],
            "number": p.get("number"),
            "x": p["x"],
            "y": p["y"],
        }
        for i, p in enumerate(template["players"], start=1)
    ]
    lines = []
    for i, line in enumerate(template["lines"], start=1):
        owner = None
        if line["kind"] == "run":
            sx, sy = line["from"]
            near = [
                (abs(p["x"] - sx) ** 2 + abs(p["y"] - sy) ** 2, p["id"])
                for p in players
                if p["team"] == "own"
            ]
            dist, pid = min(near, default=(1e9, None))
            owner = pid if dist <= 4.0 else None
        lines.append(
            {
                "id": f"l{i}",
                "kind": line["kind"],
                "from": line["from"],
                "to": line["to"],
                "curve": line["curve"],
                "player_id": owner,
            }
        )
    first_ball = next((ln["from"] for ln in template["lines"] if ln["kind"] == "ball_path"), None)
    return Diagram.model_validate(
        {
            "schema": 1,
            "players": players,
            "lines": lines,
            "zones": [],
            "ball": first_ball,
            "frames": [],
        }
    )


def find_roles_file() -> Path:
    """`KURGU_ROLES_PATH` ya da üst dizinlerdeki `packages/pitch/roles.json`."""
    env = os.environ.get(ROLES_ENV)
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _ROLES_RELATIVE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"roles.json bulunamadı; {ROLES_ENV} ayarlayın")


@cache
def role_labels() -> dict[tuple[str, str], dict[str, str]]:
    raw = json.loads(find_roles_file().read_text(encoding="utf-8"))
    return {
        (team, r["id"]): {"tr": r["tr"], "en": r["en"]}
        for team in ("own", "opponent")
        for r in raw[team]
    }


def role_label(team: str, role: str, lang: str = "tr") -> str:
    """Rolün görünen adı; sözlükte yoksa kimliğin kendisi."""
    entry = role_labels().get((team, role))
    if entry is None:
        return role
    return entry["en"] if lang.startswith("en") else entry["tr"]
