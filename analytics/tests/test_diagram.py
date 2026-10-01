"""Rutin diyagramı v1 (ADR-0008): doğrulama, geometri ve şablon dönüşümü."""

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from kurgu_analytics.reports.diagram import (
    Diagram,
    control_point,
    from_template,
    keyframe,
    mirror,
    point_on_curve,
    role_label,
    role_labels,
)
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / "packages/pitch/diagram.vectors.json").read_text(encoding="utf-8"))
TEMPLATES = json.loads((ROOT / "seed/routine_templates.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["control_points"])
def test_control_point_vectors(case: dict[str, Any]) -> None:
    cx, cy = control_point(tuple(case["from"]), tuple(case["to"]), case["curve"])
    assert cx == pytest.approx(case["control"][0], abs=1e-6)
    assert cy == pytest.approx(case["control"][1], abs=1e-6)


def test_curve_ends_on_endpoints() -> None:
    assert point_on_curve((90, 30), (100, 40), 0.3, 0) == (90, 30)
    assert point_on_curve((90, 30), (100, 40), 0.3, 1) == (100, 40)


def test_mirror_matches_vectors_and_is_involution() -> None:
    d = Diagram.model_validate(VECTORS["sample"])
    assert mirror(d).dump() == VECTORS["mirrored"]
    assert mirror(mirror(d)) == d


@pytest.mark.parametrize("case", VECTORS["keyframes"])
def test_keyframe_vectors(case: dict[str, Any]) -> None:
    d = Diagram.model_validate(VECTORS["sample"])
    positions, ball = keyframe(d, case["index"])
    assert {k: list(v) for k, v in positions.items()} == case["positions"]
    assert (list(ball) if ball else None) == case["ball"]


@given(
    x=st.floats(0, 105),
    y=st.floats(0, 68),
    curve=st.floats(-1, 1),
)
def test_mirror_keeps_points_on_pitch(x: float, y: float, curve: float) -> None:
    d = Diagram.model_validate(
        {
            "players": [{"id": "p1", "team": "own", "role": "taker", "x": x, "y": y}],
            "lines": [{"id": "l1", "kind": "run", "from": [x, y], "to": [105, 34], "curve": curve}],
        }
    )
    m = mirror(d)
    assert 0 <= m.players[0].y <= 68
    assert m.players[0].y == pytest.approx(68 - y, abs=1e-3)
    assert m.lines[0].curve == pytest.approx(-curve)


def _sample() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(json.dumps(VECTORS["sample"]))
    return raw


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["players"].append(dict(d["players"][0])), "players ids must be unique"),
        (lambda d: d["lines"][1].update(player_id="nobody"), "unknown player"),
        (lambda d: d["frames"][0]["positions"].update(p99=[90, 30]), "unknown players"),
        (lambda d: d["players"][0].update(x=106), "less than or equal"),
        (lambda d: d["lines"][0].update(to=[100, 70]), "outside the 105 x 68 pitch"),
        (lambda d: d["zones"][0].update(w=20), "inside the pitch"),
        (lambda d: d["players"][0].update(role="Taker!"), "pattern"),
        (lambda d: d.update(schema=2), "literal"),
        (lambda d: d.update(extra=1), "Extra inputs"),
    ],
)
def test_invalid_diagrams_are_rejected(mutate: Any, message: str) -> None:
    raw = _sample()
    mutate(raw)
    with pytest.raises(ValidationError, match=message):
        Diagram.model_validate(raw)


def test_limits() -> None:
    raw = _sample()
    raw["players"] = [
        {"id": f"p{i}", "team": "own", "role": "taker", "x": 90, "y": 30} for i in range(31)
    ]
    raw["lines"] = []
    raw["frames"] = []
    with pytest.raises(ValidationError, match="at most 30"):
        Diagram.model_validate(raw)


@pytest.mark.parametrize("template", TEMPLATES["templates"], ids=lambda t: t["id"])
def test_every_template_converts(template: dict[str, Any]) -> None:
    d = from_template(template)
    assert len(d.players) == len(template["players"])
    assert len(d.lines) == len(template["lines"])
    first_ball = next(ln["from"] for ln in template["lines"] if ln["kind"] == "ball_path")
    assert d.ball == tuple(first_ball)
    for p in d.players:
        assert role_label(p.team, p.role) != p.role, f"no label for {p.team}/{p.role}"


def test_template_runs_attach_to_nearby_players() -> None:
    tpl = next(t for t in TEMPLATES["templates"] if t["id"] == "tpl-yakin")
    d = from_template(tpl)
    owners = {ln.id: ln.player_id or "" for ln in d.lines if ln.kind == "run"}
    roles = {p.id: p.role for p in d.players}
    assert roles[owners["l3"]] == "near_post_runner"
    assert roles[owners["l5"]] == "far_post_runner"


def test_role_labels_cover_both_languages() -> None:
    assert role_label("own", "taker") == "Kullanan"
    assert role_label("own", "taker", "en") == "Taker"
    assert role_label("opponent", "zzz") == "zzz"
    assert all(set(v) == {"tr", "en"} for v in role_labels().values())
