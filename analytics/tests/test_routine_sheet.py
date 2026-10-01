"""Rutin sayfası dışa aktarımı (A-42): PNG ve PDF üretilir, görünüm sınırı doğru."""

import io
import json
import re
from pathlib import Path

import pytest
from kurgu_analytics.reports.diagram import Diagram, from_template
from kurgu_analytics.reports.routine_sheet import (
    SheetMeta,
    pdf_pages,
    render_pdf,
    render_png,
    view_x_min,
)
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = json.loads((ROOT / "seed/routine_templates.json").read_text(encoding="utf-8"))
META = SheetMeta(
    title="Yakın direkte sıçratma",
    subtitle="Korner · Sağ · Sürüm 2",
    footer="Kurgu · Sürüm 2",
    notes="Yakın direkteki oyuncu topu arka direğe sıçratır.",
    when_to_use="Rakip yakın direği alanla savunuyorsa.",
)


def _diagram(frames: int = 0) -> Diagram:
    raw = from_template(TEMPLATES["templates"][0]).dump()
    raw["frames"] = [
        {"id": f"f{i}", "positions": {"p10": [90 + i, 27]}, "duration_ms": 1000}
        for i in range(1, frames + 1)
    ]
    return Diagram.model_validate(raw)


@pytest.mark.parametrize("template", TEMPLATES["templates"], ids=lambda t: t["id"])
def test_png_for_every_template(template: dict[str, object]) -> None:
    data = render_png(from_template(template), META, width_px=800)
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    assert image.width == 800
    assert image.height > 400


def _page_count(data: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b", data))


def test_pdf_is_a4_with_frame_pages() -> None:
    single = render_pdf(_diagram(), META)
    assert single.startswith(b"%PDF")
    assert _page_count(single) == 1
    assert b"/MediaBox [ 0 0 595.44 841.68 ]" in single

    # Başlangıç + 7 kare = 8 küçük saha, sayfa başına 6 → iki kare sayfası.
    with_frames = render_pdf(_diagram(frames=7), META)
    assert _page_count(with_frames) == 3
    assert len(pdf_pages(_diagram(frames=2), META)) == 2


def test_pdf_is_deterministic() -> None:
    assert render_pdf(_diagram(), META) == render_pdf(_diagram(), META)


def test_view_window() -> None:
    # Şablonların hepsi x ≥ 78: çizim 70'ten başlar.
    assert view_x_min(_diagram()) == 70
    raw = _diagram().dump()
    raw["players"][0]["x"] = 60.0
    assert view_x_min(Diagram.model_validate(raw)) == 55
    raw["players"][0]["x"] = 40.0
    assert view_x_min(Diagram.model_validate(raw)) == 52.5
    assert view_x_min(Diagram()) == 70


def test_english_labels() -> None:
    meta = SheetMeta(title="Near post", subtitle="Corner", footer="Kurgu", lang="en")
    assert render_png(_diagram(), meta, width_px=400).startswith(b"\x89PNG")


def test_build_meta() -> None:
    import datetime as dt

    from kurgu_analytics.reports.routine_sheet import build_meta

    meta = build_meta(
        name="Arka direk",
        sp_type="corner",
        side="left",
        is_defensive=False,
        version=3,
        saved_at=dt.datetime(2026, 10, 1, 9, 30, tzinfo=dt.UTC),
        saved_by="Serhat",
        club="Trabzonspor (demo)",
        notes="",
        when_to_use="",
    )
    assert meta.subtitle == "Korner · Sol taraf · Sürüm 3 · 01.10.2026"
    assert "Kaydeden Serhat" in meta.footer
    assert meta.footer.startswith("Kurgu · Trabzonspor (demo)")
    en = build_meta(
        name="Back post",
        sp_type="throw_in",
        side=None,
        is_defensive=True,
        version=1,
        saved_at=dt.datetime(2026, 10, 1, tzinfo=dt.UTC),
        saved_by=None,
        club="Club",
        notes="",
        when_to_use="",
        lang="en",
    )
    assert en.subtitle == "Long throw · Defending · Version 1 · 01.10.2026"
    assert en.lang == "en"
