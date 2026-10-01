"""Brifing girdisi ve sahte üretici (A-73, ADR-0013)."""

import json

from kurgu_analytics.reports.briefing import SYSTEM_PROMPT, briefing_input, fake_briefing
from kurgu_analytics.reports.numbers import verify
from kurgu_analytics.testing.reports import opponent_report

PLAN = {"done": 1, "total": 2, "days": [{"md": "MD-3", "focus": "Hücum duran topları"}]}


def test_input_carries_display_forms_and_flags() -> None:
    data = briefing_input(opponent_report(), PLAN)
    assert data["fixture"]["date"] == "10.10.2026"
    assert data["fixture"]["time"] == "20:00"
    assert data["fixture"]["venue"] == "deplasman"
    fouls = next(m for m in data["opponent_metrics"] if m["metric"] == "Yapılan faul / maç")
    assert fouls["display"] == "14,82"
    assert fouls["rank_display"] == "4./18"
    assert fouls["indirect"] is True
    assert data["recommendations"][0]["status"] == "kabul edildi"
    json.dumps(data)  # JSON'a dönüşebilir


def test_fake_briefing_passes_number_check() -> None:
    data = briefing_input(opponent_report(), PLAN)
    text = fake_briefing(data)
    result = verify(text, data)
    assert result.ok, result.unmatched
    assert "Samsunspor" in text


def test_prompt_forbids_new_numbers_and_names() -> None:
    assert "JSON'da olmayan hiçbir sayı yazma" in SYSTEM_PROMPT
    assert "Oyuncu adı" in SYSTEM_PROMPT
