"""Teslim hedef bölgeleri (SPEC §3.3).

Tanımlar `packages/pitch/zones.json` dosyasından okunur; TS tarafı (`@kurgu/pitch`) aynı
dosyayı kullanır ve iki taraf `zones.vectors.json` test vektörleriyle doğrulanır.

Bölgeler, teslim her zaman `y < 34` tarafından geliyormuş gibi normalize edilmiş koordinatta
tanımlanır: `y' = y` (teslim sağ taraftan, y < 34) ya da `y' = 68 − y`.
Sınırlar: `x_min` ve `y_min` dahil, `x_max` ve `y_max` hariç; dosyadaki `*_inclusive`
alanları bunu değiştirir. Bölgeler dosyadaki sırayla denenir, ilk eşleşen kazanır.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

ZoneCode = Literal["NP", "C6", "FP", "PS", "ED", "SH", "OT"]
ZONES_ENV = "KURGU_ZONES_PATH"
_RELATIVE = Path("packages") / "pitch" / "zones.json"


@dataclass(frozen=True, slots=True)
class Box:
    """Eksen hizalı dikdörtgen bölge (metre)."""

    x_min: float = -math.inf
    x_max: float = math.inf
    y_min: float = -math.inf
    y_max: float = math.inf
    x_max_inclusive: bool = False
    y_min_inclusive: bool = True
    y_max_inclusive: bool = False

    def contains(self, x: float, y: float) -> bool:
        if x < self.x_min or x > self.x_max or (x == self.x_max and not self.x_max_inclusive):
            return False
        if y < self.y_min or (y == self.y_min and not self.y_min_inclusive):
            return False
        return not (y > self.y_max or (y == self.y_max and not self.y_max_inclusive))


@dataclass(frozen=True, slots=True)
class Zone:
    code: ZoneCode
    name_tr: str
    box: Box | None
    rule: str | None = None
    corner_distance_max: float | None = None


@dataclass(frozen=True, slots=True)
class PitchConfig:
    length: float
    width: float
    penalty_box: Box
    zones: tuple[Zone, ...]
    version: int


def find_zones_file() -> Path:
    """`KURGU_ZONES_PATH` ya da bu dosyanın üst dizinlerindeki `packages/pitch/zones.json`."""
    env = os.environ.get(ZONES_ENV)
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _RELATIVE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"zones.json bulunamadı; {ZONES_ENV} ayarlayın")


def parse_config(raw: dict[str, Any]) -> PitchConfig:
    pitch = raw["pitch"]
    pb = pitch["penalty_box"]
    zones: list[Zone] = []
    for z in raw["zones"]:
        box = None
        if "rule" not in z:
            box = Box(
                x_min=z.get("x_min", -math.inf),
                x_max=z.get("x_max", math.inf),
                y_min=z.get("y_min", -math.inf),
                y_max=z.get("y_max", math.inf),
                x_max_inclusive=z.get("x_max_inclusive", False),
                y_min_inclusive=z.get("y_min_inclusive", True),
                y_max_inclusive=z.get("y_max_inclusive", False),
            )
        zones.append(
            Zone(
                code=z["code"],
                name_tr=z["name_tr"],
                box=box,
                rule=z.get("rule"),
                corner_distance_max=z.get("corner_distance_max"),
            )
        )
    return PitchConfig(
        length=pitch["length"],
        width=pitch["width"],
        penalty_box=Box(
            x_min=pb["x_min"],
            x_max=pitch["length"],
            y_min=pb["y_min"],
            y_max=pb["y_max"],
            x_max_inclusive=True,
            y_max_inclusive=True,
        ),
        zones=tuple(zones),
        version=raw["version"],
    )


@cache
def load_config(path: str | None = None) -> PitchConfig:
    file = Path(path) if path else find_zones_file()
    return parse_config(json.loads(file.read_text(encoding="utf-8")))


def normalize_y(y: float, delivery_y: float, width: float = 68.0) -> float:
    """Teslim tarafına göre normalize y: teslim y < 34'ten ise `y`, değilse `68 − y`.

    Birim: metre. Kaynak: SPEC §3.3. Tam ortadan (y = 34) gelen teslim sağ taraf sayılır.
    """
    return y if delivery_y <= width / 2 else width - y


def zone(x: float, y: float, delivery_y: float, config: PitchConfig | None = None) -> ZoneCode:
    """Teslimin hedef bölgesi.

    Girdi: bitiş noktası (x, y) ve teslimin başladığı y (kanonik koordinat, metre).
    Kaynak: SPEC §3.3. `SH`: ceza sahası dışında ve teslim tarafındaki köşe bayrağına
    (105, 0) en fazla `corner_distance_max` metre. Hiçbiri tutmazsa `OT`.
    """
    cfg = config or load_config()
    yn = normalize_y(y, delivery_y, cfg.width)
    for z in cfg.zones:
        if z.box is not None:
            if z.box.contains(x, yn):
                return z.code
        elif z.rule == "outside_penalty_box_within_corner_distance":
            assert z.corner_distance_max is not None
            outside = not cfg.penalty_box.contains(x, yn)
            if outside and math.hypot(cfg.length - x, yn) <= z.corner_distance_max:
                return z.code
        elif z.rule == "fallback":
            return z.code
    return "OT"
