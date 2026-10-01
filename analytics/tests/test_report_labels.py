"""Rapor etiketleri web ile aynı kalır (metrik adı, birim, grup, sıra)."""

import json
import re
from pathlib import Path

from kurgu_analytics.reports.labels import METRICS, format_metric, tr_number

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"


def test_labels_match_web_messages() -> None:
    messages = json.loads((WEB / "messages" / "tr.json").read_text(encoding="utf-8"))
    web = messages["analysis"]["metrics"]
    assert {k: v["label"] for k, v in web.items()} == {k: m.label for k, m in METRICS.items()}


def test_units_groups_and_order_match_web() -> None:
    source = (WEB / "src" / "lib" / "metric-display.ts").read_text(encoding="utf-8")
    rows = re.findall(r'^\s+(\w+): \{ unit: "(\w+)", group: "(\w+)" \},$', source, re.M)
    assert rows == [(k, m.unit, m.group) for k, m in METRICS.items()]


def test_turkish_number_format() -> None:
    assert tr_number(1234.5, 1) == "1.234,5"
    assert tr_number(-0.04, 1) == "0,0"
    assert tr_number(-2.84, 1) == "-2,8"


def test_metric_formats() -> None:
    assert format_metric("set_piece_goal_share", 0.20431) == "%20,4"
    assert format_metric("set_piece_goals", 15) == "15"
    assert format_metric("set_piece_goals", 15.5) == "15,5"
    assert format_metric("set_piece_goals_minus_xg", 2.84) == "+2,8"
    assert format_metric("set_piece_goals_minus_xg", -2.84) == "-2,8"
    assert format_metric("set_piece_goals_minus_xg", 0.01) == "0,0"
    assert format_metric("corners_per_match", 6.4) == "6,40"
    assert format_metric("xg_per_set_piece", 0.0425) == "0,043"


def test_unknown_metric_format() -> None:
    assert format_metric("set_pieces", 12.0) == "12"
    assert format_metric("goal_rate", 0.25) == "0,25"
