"""Rapor HTML'i (ADR-0012): içerik, etiketler ve boş durumlar. Chromium gerekmez."""

import re

from kurgu_analytics.reports import heatmap
from kurgu_analytics.reports.render import (
    findings,
    footer_html,
    render_match_plan_html,
    render_opponent_html,
)
from kurgu_analytics.testing.reports import match_plan_report, opponent_report


def text_of(html: str) -> str:
    body = html.split("<body>", 1)[1]
    body = re.sub(r"<svg.*?</svg>", " ", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


def test_opponent_report_sections_and_values() -> None:
    html = render_opponent_html(opponent_report())
    text = text_of(html)
    assert "<title>Rakip raporu · Samsunspor – Trabzonspor</title>" in html
    for heading in ("Özet", "Profil", "Bulgular", "Öneriler", "hedef bölgeleri", "Klipler"):
        assert heading in text
    assert "Yapılan faul / maç" in text
    assert "14,82" in text
    assert "4./18" in text
    assert "%24,0" in text
    assert "+1,8" in text
    assert "Az veri" in text
    assert "Dolaylı" in text
    assert "Deplasman" in text
    assert "7. hafta" in text
    assert "10.10.2026 20:00" in text
    assert "Kaynak: tohum" in text
    assert "sayılar kayıtla eşleşti" in text
    assert "Ceza sahası çevresinde faul kazanın" in text
    assert "Rakip: Yapılan faul / maç 14,82 (4./18)" in text


def test_form_letters_are_written() -> None:
    text = text_of(render_opponent_html(opponent_report()))
    assert "G B M G G" in text


def test_fonts_are_embedded_and_no_external_resources() -> None:
    html = render_opponent_html(opponent_report())
    assert "font/woff2;base64," in html
    assert not re.search(r"(src|href)=\"https?://", html)


def test_findings_are_top_and_bottom_three() -> None:
    rows = findings(opponent_report())
    assert [(f["row"].metric, f["edge"]) for f in rows] == [
        ("corners_per_match", "top"),
        ("set_piece_goals", "top"),
        ("aerial_win_pct", "bottom"),
    ]


def test_empty_states() -> None:
    report = opponent_report(briefing=False).model_copy(
        update={"metrics": [], "recommendations": [], "zones": [], "clips": []}
    )
    text = text_of(render_opponent_html(report))
    assert "metrik kaydı yok" in text
    assert "tetiklenen öneri yok" in text
    assert "Bölge verisi yok (41 duran top kaydı)" in text
    assert "Brifing" not in text


def test_demo_badge() -> None:
    report = opponent_report()
    report.meta.demo = True
    assert "Örnek veri" in text_of(render_opponent_html(report))
    assert "Örnek veri içerir" in footer_html(report)


def test_heatmap_counts_and_unboxed_zones() -> None:
    svg = heatmap.render_svg({"NP": 14, "FP": 9, "SH": 3})
    assert svg.startswith("<svg")
    assert "NP 14" in svg
    assert "FP 9" in svg
    assert "C6 0" in svg
    assert "%54" in svg
    assert heatmap.unboxed({"NP": 1, "SH": 3, "OT": 2}) == ["SH", "OT"]


def test_match_plan_sections() -> None:
    html = render_match_plan_html(match_plan_report())
    text = text_of(html)
    for heading in (
        "Hücum planı",
        "Savunma organizasyonu",
        "Rutinler",
        "MD planı",
        "Görev atamaları",
    ):
        assert heading in text
    assert "Yakın direkte sıçratma" in text
    assert "sürüm 2" in text
    assert "1/2 madde tamam" in text
    assert "✓ Tamam" in text
    assert "Bekliyor" in text
    assert "Duran Top" in text
    assert "Atanmamış" in text
    assert html.count("<svg") >= 1


def test_footer_has_page_numbers_and_source() -> None:
    footer = footer_html(match_plan_report())
    assert 'class="pageNumber"' in footer
    assert 'class="totalPages"' in footer
    assert "Kaynak: tohum" in footer
    assert "2025/26" in footer


def test_routine_svg_cannot_carry_markup_from_labels() -> None:
    from kurgu_analytics.reports.render import routine_svg
    from kurgu_analytics.testing.reports import template_diagram

    diagram = template_diagram(0)
    player = diagram.players[-1].model_copy(update={"label": "--><script>alert(1)</script>"})
    unsafe = diagram.model_copy(update={"players": [*diagram.players[:-1], player]})
    svg = str(routine_svg(unsafe))
    assert "<script" not in svg
    assert "<!--" not in svg
