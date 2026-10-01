"""Duran top hedef bölgesi ısı haritası (satır içi SVG, SPEC §14, A-72).

Saha son 27 metredir; hücum edilen kale üstte, y = 0 (hücum eden takımın sağ taç çizgisi)
sağdadır (rutin diyagramlarıyla aynı yön, ADR-0008). Kutulu bölgeler (NP, C6, FP, PS, ED)
`zones.json` sınırlarıyla çizilir; kutusuz bölgeler (SH kısa, OT diğer) çizimin altında
listelenir. Renk yoğunluğu payla artar; sayı ve yüzde her kutuda yazar (renk tek başına anlam
taşımaz).
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

from kurgu_analytics.reports.labels import tr_number
from kurgu_analytics.setpieces.zones import PitchConfig, load_config

X_MIN = 78.0
SCALE = 6.0
MARGIN = 6.0
LINE = "#0E3B2E"
TURF = "#EAF2EC"
HEAT = "#E3A008"
INK = "#0F1B16"


def _point(x: float, y: float, width: float) -> tuple[float, float]:
    return MARGIN + (width - y) * SCALE, MARGIN + (105.0 - x) * SCALE


def _rect(x0: float, x1: float, y0: float, y1: float, width: float) -> tuple[float, ...]:
    left, top = _point(x1, y1, width)
    right, bottom = _point(x0, y0, width)
    return left, top, right - left, bottom - top


def unboxed(counts: dict[str, int], config: PitchConfig | None = None) -> list[str]:
    """Çizimde kutusu olmayan bölgeler (sırasıyla)."""
    config = config or load_config()
    return [z.code for z in config.zones if z.box is None and z.code in counts]


def render_svg(counts: dict[str, int], config: PitchConfig | None = None) -> str:
    config = config or load_config()
    total = sum(counts.values())
    width, length = config.width, config.length
    view_w = width * SCALE + 2 * MARGIN
    view_h = (length - X_MIN) * SCALE + 2 * MARGIN
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w:.0f} {view_h:.0f}" '
        f'role="img" aria-label="Hedef bölge ısı haritası" class="heatmap">',
        f'<rect x="0" y="0" width="{view_w:.0f}" height="{view_h:.0f}" fill="{TURF}"/>',
    ]

    def outline(x0: float, x1: float, y0: float, y1: float) -> None:
        x, y, w, h = _rect(x0, x1, y0, y1, width)
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="none" '
            f'stroke="{LINE}" stroke-width="1.2"/>'
        )

    outline(X_MIN, length, 0, width)
    pb = config.penalty_box
    outline(pb.x_min, length, pb.y_min, pb.y_max)
    outline(99.5, length, 24.84, 43.16)
    gx, gy = _point(length, 37.66, width)
    parts.append(
        f'<rect x="{gx:.1f}" y="{gy - 4:.1f}" width="{(37.66 - 30.34) * SCALE:.1f}" '
        f'height="4" fill="{LINE}"/>'
    )
    sx, sy = _point(94, 34, width)
    parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="1.6" fill="{LINE}"/>')

    for zone in config.zones:
        if zone.box is None:
            continue
        box = zone.box
        x0, x1 = max(box.x_min, X_MIN), min(box.x_max, length)
        y0, y1 = max(box.y_min, 0), min(box.y_max, width)
        count = counts.get(zone.code, 0)
        share = count / total if total else 0.0
        x, y, w, h = _rect(x0, x1, y0, y1, width)
        opacity = 0.06 + 0.8 * share
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{HEAT}" '
            f'fill-opacity="{opacity:.2f}" stroke="{HEAT}" stroke-width="0.8"/>'
        )
        label = f"{zone.code} {count}"
        pct = f"%{tr_number(share * 100, 0)}" if total else "–"
        cx, cy = x + w / 2, y + h / 2
        parts.append(
            f'<text x="{cx:.1f}" y="{cy - 2:.1f}" text-anchor="middle" font-size="10" '
            f'font-weight="600" fill="{INK}">{escape(label)}</text>'
            f'<text x="{cx:.1f}" y="{cy + 9:.1f}" text-anchor="middle" font-size="9" '
            f'fill="{INK}">{escape(pct)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def zone_names(codes: Iterable[str], config: PitchConfig | None = None) -> dict[str, str]:
    config = config or load_config()
    names: dict[str, str] = {z.code: z.name_tr for z in config.zones}
    return {code: names.get(code, code) for code in codes}
