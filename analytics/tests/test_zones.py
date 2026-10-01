"""Bölge sınıflandırması: ortak test vektörleri ve normalize y (SPEC §3.3)."""

import json

import pytest
from kurgu_analytics.setpieces.zones import find_zones_file, load_config, normalize_y, zone

VECTORS = json.loads((find_zones_file().parent / "zones.vectors.json").read_text(encoding="utf-8"))[
    "cases"
]


@pytest.mark.parametrize(("x", "y", "delivery_y", "expected"), VECTORS)
def test_shared_vectors(x: float, y: float, delivery_y: float, expected: str) -> None:
    assert zone(x, y, delivery_y) == expected


def test_normalize_y_mirrors_left_side() -> None:
    assert normalize_y(20, 1) == 20
    assert normalize_y(20, 67) == 48


def test_config_matches_spec_geometry() -> None:
    cfg = load_config()
    assert (cfg.length, cfg.width) == (105, 68)
    assert [z.code for z in cfg.zones] == ["NP", "C6", "FP", "PS", "ED", "SH", "OT"]
