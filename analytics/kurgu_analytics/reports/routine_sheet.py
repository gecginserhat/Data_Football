"""Rutin sayfası: diyagramdan PNG ve A4 PDF (SPEC §13.2 dışa aktarım, ADR-0008, A-42).

Çizim yarım sahadır: hücum edilen kale üstte, y = 0 (hücum eden takımın sağ taç çizgisi)
sağda. Kavisler ve kareler `kurgu_analytics.reports.diagram` geometrisiyle çizilir; editör
aynı geometriyi `@kurgu/pitch` ile kullanır. matplotlib'in nesne arayüzü kullanılır (pyplot
yok), böylece eşzamanlı isteklerde genel durum paylaşılmaz.
"""

from __future__ import annotations

import datetime as dt
import io
import math
import textwrap
from dataclasses import dataclass, field
from typing import Any

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Arc, Circle, PathPatch, Polygon, Rectangle
from matplotlib.path import Path as MplPath

from kurgu_analytics.reports.diagram import (
    PITCH_LENGTH,
    PITCH_WIDTH,
    Diagram,
    DiagramLine,
    control_point,
    keyframe,
    role_label,
)

HALF = PITCH_LENGTH / 2
MARGIN = 1.5

# Tasarım tokenları (SPEC §13.3, açık tema).
TURF = "#EAF2EC"
LINE = "#0E3B2E"
INK = "#0F1B16"
INK_2 = "#44524B"
INK_3 = "#63706A"
OWN = "#0E3B2E"
OPPONENT = "#B94C16"
ACCENT = "#E3A008"
RUN = "#0E3B2E"
SCREEN = "#44524B"

FONT = "DejaVu Sans"
"""Türkçe karakterleri kapsayan, matplotlib ile gelen yazı tipi (A-42)."""

LABELS = {
    "tr": {
        "roles": "Roller",
        "when": "Ne zaman kullanılır",
        "notes": "Notlar",
        "frames": "Kareler",
        "start": "Başlangıç",
        "frame": "Kare",
        "legend_run": "Koşu",
        "legend_ball": "Top yolu",
        "legend_screen": "Perdeleme",
        "legend_own": "Bizim oyuncu",
        "legend_opp": "Rakip",
        "none": "—",
        "corner": "Korner",
        "free_kick": "Serbest vuruş",
        "throw_in": "Uzun taç",
        "left": "Sol taraf",
        "right": "Sağ taraf",
        "defensive": "Savunma",
        "version": "Sürüm",
        "saved": "Kaydedildi",
        "by": "Kaydeden",
    },
    "en": {
        "roles": "Roles",
        "when": "When to use",
        "notes": "Notes",
        "frames": "Frames",
        "start": "Start",
        "frame": "Frame",
        "legend_run": "Run",
        "legend_ball": "Ball path",
        "legend_screen": "Screen",
        "legend_own": "Our player",
        "legend_opp": "Opponent",
        "none": "—",
        "corner": "Corner",
        "free_kick": "Free kick",
        "throw_in": "Long throw",
        "left": "Left side",
        "right": "Right side",
        "defensive": "Defending",
        "version": "Version",
        "saved": "Saved",
        "by": "Saved by",
    },
}


@dataclass(frozen=True)
class SheetMeta:
    """Sayfadaki metinler; çağıran (API) yerelleştirir."""

    title: str
    subtitle: str
    footer: str
    notes: str = ""
    when_to_use: str = ""
    lang: str = "tr"
    extra: dict[str, str] = field(default_factory=dict)


def build_meta(
    *,
    name: str,
    sp_type: str,
    side: str | None,
    is_defensive: bool,
    version: int,
    saved_at: dt.datetime,
    saved_by: str | None,
    club: str,
    notes: str,
    when_to_use: str,
    lang: str = "tr",
) -> SheetMeta:
    """Başlık, alt başlık ve altbilgi: tür, taraf, sürüm, kayıt zamanı ve kulüp."""
    lab = _labels(lang)
    parts = [lab.get(sp_type, sp_type)]
    if side:
        parts.append(lab[side])
    if is_defensive:
        parts.append(lab["defensive"])
    date = saved_at.strftime("%d.%m.%Y")
    parts.append(f"{lab['version']} {version} · {date}")
    footer = [f"Kurgu · {club}", f"{name} · {lab['version']} {version}"]
    stamp = f"{lab['saved']} {saved_at.strftime('%d.%m.%Y %H:%M')} UTC"
    footer.append(f"{stamp} · {lab['by']} {saved_by}" if saved_by else stamp)
    return SheetMeta(
        title=name,
        subtitle=" · ".join(parts),
        footer="  |  ".join(footer),
        notes=notes,
        when_to_use=when_to_use,
        lang="en" if lang.startswith("en") else "tr",
    )


def _xy(x: float, y: float) -> tuple[float, float]:
    """Kanonik (x, y) → çizim düzlemi: yatay 68 − y, dikey x."""
    return PITCH_WIDTH - y, x


def _labels(lang: str) -> dict[str, str]:
    return LABELS["en" if lang.startswith("en") else "tr"]


def view_x_min(diagram: Diagram) -> float:
    """Dışa aktarımda gösterilen sahanın alt sınırı (metre).

    Duran toplar son 35 metrede oynandığı için çizim en az x = 70'ten başlar; daha geride öğe
    varsa 5 m pay bırakılarak yarım sahaya kadar genişler. Editör her zaman yarım sahayı
    gösterir (A-45).
    """
    xs = [p.x for p in diagram.players]
    for line in diagram.lines:
        xs += [line.from_[0], line.to[0]]
    xs += [z.x for z in diagram.zones]
    for frame in diagram.frames:
        xs += [pos[0] for pos in frame.positions.values()]
    lowest = min(xs, default=PITCH_LENGTH)
    return max(HALF, min(70.0, math.floor(lowest - 5)))


def _draw_pitch(ax: Axes, x_min: float = HALF) -> None:
    ax.set_xlim(-MARGIN, PITCH_WIDTH + MARGIN)
    ax.set_ylim(x_min - MARGIN, PITCH_LENGTH + MARGIN)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(
        Rectangle(
            (-MARGIN, x_min - MARGIN),
            PITCH_WIDTH + 2 * MARGIN,
            PITCH_LENGTH - x_min + 2 * MARGIN,
            facecolor=TURF,
            edgecolor="none",
            zorder=0,
        )
    )
    lw = 1.0
    kw: dict[str, Any] = {"edgecolor": LINE, "facecolor": "none", "linewidth": lw, "zorder": 1}
    # Taç çizgileri ve kale çizgisi; orta çizgi yalnızca görünüyorsa.
    ax.plot(
        [0, 0, PITCH_WIDTH, PITCH_WIDTH],
        [x_min - MARGIN, PITCH_LENGTH, PITCH_LENGTH, x_min - MARGIN],
        color=LINE,
        linewidth=lw,
        zorder=1,
    )
    if x_min <= HALF:
        ax.plot([0, PITCH_WIDTH], [HALF, HALF], color=LINE, linewidth=lw, zorder=1)
    # Ceza sahası (x ≥ 88,5; y ∈ [13,84; 54,16]) ve altı pas (x ≥ 99,5; y ∈ [24,84; 43,16]).
    ax.add_patch(Rectangle((13.84, 88.5), 40.32, 16.5, **kw))
    ax.add_patch(Rectangle((24.84, 99.5), 18.32, 5.5, **kw))
    # Kale (direkler y = 30,34 ve 37,66).
    ax.add_patch(Rectangle((30.34, 105), 7.32, 1.0, **kw))
    ax.add_patch(Circle((34, 94), 0.25, color=LINE, zorder=1))
    # Ceza yayı: penaltı noktasından 9,15 m, ceza sahası dışında kalan kısım.
    half_angle = math.degrees(math.acos((94 - 88.5) / 9.15))
    ax.add_patch(Arc((34, 94), 18.3, 18.3, theta1=270 - half_angle, theta2=270 + half_angle, **kw))
    # Orta saha çemberinin yarısı ve köşe yayları.
    ax.add_patch(Arc((34, HALF), 18.3, 18.3, theta1=0, theta2=180, **kw))
    ax.add_patch(Arc((0, 105), 2, 2, theta1=270, theta2=360, **kw))
    ax.add_patch(Arc((68, 105), 2, 2, theta1=180, theta2=270, **kw))


def _arrow_head(
    ax: Axes,
    tip: tuple[float, float],
    direction: tuple[float, float],
    color: str,
    size: float = 1.1,
) -> None:
    dx, dy = direction
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    base = (tip[0] - ux * size, tip[1] - uy * size)
    left = (base[0] - uy * size * 0.45, base[1] + ux * size * 0.45)
    right = (base[0] + uy * size * 0.45, base[1] - ux * size * 0.45)
    ax.add_patch(Polygon([tip, left, right], closed=True, color=color, zorder=4))


def _draw_line(ax: Axes, line: DiagramLine) -> None:
    start = _xy(*line.from_)
    end = _xy(*line.to)
    ctrl = _xy(*control_point(line.from_, line.to, line.curve))
    path = MplPath([start, ctrl, end], [MplPath.MOVETO, MplPath.CURVE3, MplPath.CURVE3])
    tangent = (end[0] - ctrl[0], end[1] - ctrl[1])
    if math.hypot(*tangent) < 1e-9:
        tangent = (end[0] - start[0], end[1] - start[1])
    if line.kind == "ball_path":
        ax.add_patch(
            PathPatch(
                path,
                facecolor="none",
                edgecolor=INK,
                linewidth=1.4,
                linestyle=(0, (3, 2)),
                zorder=3,
            )
        )
        _arrow_head(ax, end, tangent, INK)
    elif line.kind == "run":
        ax.add_patch(PathPatch(path, facecolor="none", edgecolor=RUN, linewidth=1.6, zorder=3))
        _arrow_head(ax, end, tangent, RUN)
    else:
        ax.add_patch(PathPatch(path, facecolor="none", edgecolor=SCREEN, linewidth=1.8, zorder=3))
        n = math.hypot(*tangent) or 1.0
        px, py = -tangent[1] / n, tangent[0] / n
        ax.plot(
            [end[0] - px * 1.2, end[0] + px * 1.2],
            [end[1] - py * 1.2, end[1] + py * 1.2],
            color=SCREEN,
            linewidth=2.4,
            solid_capstyle="butt",
            zorder=3,
        )


def _draw_board(
    ax: Axes,
    diagram: Diagram,
    x_min: float,
    index: int | None = None,
    show_lines: bool = True,
    font_scale: float = 1.0,
    lang: str = "tr",
) -> None:
    """Saha, bölgeler, çizgiler, oyuncular ve top. `index` verilirse o anahtar karedeki konumlar."""
    _draw_pitch(ax, x_min)
    for zone in diagram.zones:
        x0, y0 = _xy(zone.x, zone.y + zone.h)
        ax.add_patch(
            Rectangle(
                (x0, y0),
                zone.h,
                zone.w,
                facecolor=ACCENT,
                alpha=0.22,
                edgecolor=ACCENT,
                linewidth=1.0,
                zorder=2,
            )
        )
        if zone.label:
            ax.text(
                x0 + zone.h / 2,
                y0 + zone.w / 2,
                zone.label,
                ha="center",
                va="center",
                fontsize=7 * font_scale,
                color=INK_2,
                family=FONT,
                zorder=2,
            )
    if show_lines:
        for line in diagram.lines:
            _draw_line(ax, line)
    positions, ball = keyframe(diagram, index or 0)
    radius = 1.15
    for p in diagram.players:
        px, py = _xy(*positions[p.id])
        if p.team == "own":
            ax.add_patch(
                Circle((px, py), radius, facecolor=OWN, edgecolor="white", linewidth=0.8, zorder=5)
            )
            text = str(p.number) if p.number is not None else ""
            ax.text(
                px,
                py,
                text,
                ha="center",
                va="center",
                color="white",
                fontsize=6.5 * font_scale,
                fontweight="bold",
                family=FONT,
                zorder=6,
            )
        else:
            ax.add_patch(
                Circle(
                    (px, py), radius, facecolor="white", edgecolor=OPPONENT, linewidth=1.4, zorder=5
                )
            )
            if p.role == "gk":
                gk = "GK" if lang.startswith("en") else "K"
                ax.text(
                    px,
                    py,
                    gk,
                    ha="center",
                    va="center",
                    color=OPPONENT,
                    fontsize=6 * font_scale,
                    fontweight="bold",
                    family=FONT,
                    zorder=6,
                )
    if ball is not None:
        bx, by = _xy(*ball)
        ax.add_patch(
            Circle((bx, by), 0.6, facecolor="white", edgecolor=INK, linewidth=1.0, zorder=7)
        )


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(para, width) or [""])
    return lines


def _own_roles(diagram: Diagram, lang: str) -> list[str]:
    rows = []
    own = sorted(
        (p for p in diagram.players if p.team == "own"),
        key=lambda p: (p.number is None, p.number or 0, p.id),
    )
    for p in own:
        number = str(p.number) if p.number is not None else "·"
        name = f" · {p.label}" if p.label else ""
        rows.append(f"{number:>2}  {role_label(p.team, p.role, lang)}{name}")
    return rows


def own_roles(diagram: Diagram, lang: str = "tr") -> list[str]:
    """Kulübün rol satırları: forma numarası, rol adı ve serbest metin oyuncu etiketi."""
    return _own_roles(diagram, lang)


def render_board_svg(diagram: Diagram, lang: str = "tr", width_in: float = 4.2) -> str:
    """Başlıksız saha çizimi, satır içi SVG (çok sayfalı raporlar için, ADR-0012)."""
    x_min = view_x_min(diagram)
    board_w = PITCH_WIDTH + 2 * MARGIN
    board_h = PITCH_LENGTH - x_min + 2 * MARGIN
    fig = Figure(figsize=(width_in, width_in * board_h / board_w), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1))
    _draw_board(ax, diagram, x_min, font_scale=0.8, lang=lang)
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None, "Creator": "Kurgu"})
    svg = buf.getvalue()
    return svg[svg.index("<svg") :]


def render_png(diagram: Diagram, meta: SheetMeta, width_px: int = 1600) -> bytes:
    """Başlıklı saha görseli (PNG)."""
    x_min = view_x_min(diagram)
    board_w = PITCH_WIDTH + 2 * MARGIN
    board_h = PITCH_LENGTH - x_min + 2 * MARGIN
    width_in = 8.0
    head_in = 0.7
    height_in = width_in * board_h / board_w + head_in
    fig = Figure(figsize=(width_in, height_in), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1 - head_in / height_in))
    _draw_board(ax, diagram, x_min, lang=meta.lang)
    fig.text(
        0.03,
        1 - 0.32 / height_in,
        meta.title,
        fontsize=15,
        fontweight="bold",
        color=INK,
        family=FONT,
        va="center",
    )
    fig.text(
        0.03, 1 - 0.58 / height_in, meta.subtitle, fontsize=9, color=INK_3, family=FONT, va="center"
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=width_px / width_in, metadata={"Software": "Kurgu"})
    return buf.getvalue()


A4 = (8.27, 11.69)


def _page_header(fig: Figure, meta: SheetMeta) -> None:
    fig.text(0.07, 0.955, meta.title, fontsize=17, fontweight="bold", color=INK, family=FONT)
    fig.text(0.07, 0.935, meta.subtitle, fontsize=9, color=INK_3, family=FONT)
    fig.text(0.07, 0.03, meta.footer, fontsize=7.5, color=INK_3, family=FONT)


def _legend(fig: Figure, y: float, lang: str) -> None:
    lab = _labels(lang)
    ax = fig.add_axes((0.07, y, 0.86, 0.025))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 2)
    ax.axis("off")
    x = 0.0
    items = [
        ("own", lab["legend_own"]),
        ("opp", lab["legend_opp"]),
        ("run", lab["legend_run"]),
        ("ball", lab["legend_ball"]),
        ("screen", lab["legend_screen"]),
    ]
    for kind, text in items:
        if kind == "own":
            ax.scatter([x + 1], [1], s=40, color=OWN)
        elif kind == "opp":
            ax.scatter([x + 1], [1], s=40, facecolor="white", edgecolor=OPPONENT, linewidth=1.2)
        elif kind == "run":
            ax.plot([x, x + 3], [1, 1], color=RUN, lw=1.6)
        elif kind == "ball":
            ax.plot([x, x + 3], [1, 1], color=INK, lw=1.4, linestyle=(0, (3, 2)))
        else:
            ax.plot([x, x + 3], [1, 1], color=SCREEN, lw=1.8)
            ax.plot([x + 3, x + 3], [0.4, 1.6], color=SCREEN, lw=2.2)
        ax.text(x + 4, 1, text, va="center", fontsize=8, color=INK_2, family=FONT)
        x += 20


def pdf_pages(diagram: Diagram, meta: SheetMeta) -> list[Figure]:
    """PDF sayfaları (A4 dikey): başlık, saha, açıklama, roller, notlar; kareler sonraki sayfada."""
    lab = _labels(meta.lang)
    x_min = view_x_min(diagram)
    aspect = (PITCH_LENGTH - x_min + 2 * MARGIN) / (PITCH_WIDTH + 2 * MARGIN)
    pages: list[Figure] = []

    fig = Figure(figsize=A4, facecolor="white")
    _page_header(fig, meta)
    board_w = 0.86
    board_h = board_w * A4[0] / A4[1] * aspect
    top = 0.915
    ax = fig.add_axes((0.07, top - board_h, board_w, board_h))
    _draw_board(ax, diagram, x_min, lang=meta.lang)
    legend_y = top - board_h - 0.035
    _legend(fig, legend_y, meta.lang)

    y = legend_y - 0.035
    fig.text(0.07, y, lab["roles"], fontsize=10.5, fontweight="bold", color=INK, family=FONT)
    roles = _own_roles(diagram, meta.lang) or [lab["none"]]
    for i, row in enumerate(roles[:16]):
        fig.text(0.07, y - 0.022 * (i + 1), row, fontsize=8.5, color=INK_2, family=FONT)
    ty = y
    for heading, body in ((lab["when"], meta.when_to_use), (lab["notes"], meta.notes)):
        fig.text(0.5, ty, heading, fontsize=10.5, fontweight="bold", color=INK, family=FONT)
        lines = _wrap(body.strip() or lab["none"], 50)[:14]
        for i, row in enumerate(lines):
            fig.text(0.5, ty - 0.02 * (i + 1), row, fontsize=8.5, color=INK_2, family=FONT)
        ty -= 0.02 * (len(lines) + 2)
    pages.append(fig)

    snapshots = list(range(len(diagram.frames) + 1)) if diagram.frames else []
    per_page = 6
    for start in range(0, len(snapshots), per_page):
        page = Figure(figsize=A4, facecolor="white")
        _page_header(page, meta)
        page.text(
            0.07, 0.9, lab["frames"], fontsize=10.5, fontweight="bold", color=INK, family=FONT
        )
        cell_w = 0.42
        cell_h = cell_w * A4[0] / A4[1] * aspect
        for k, index in enumerate(snapshots[start : start + per_page]):
            col, grid_row = k % 2, k // 2
            left = 0.07 + col * (cell_w + 0.02)
            bottom = 0.875 - (grid_row + 1) * (cell_h + 0.04)
            cell = page.add_axes((left, bottom, cell_w, cell_h))
            _draw_board(
                cell,
                diagram,
                x_min,
                index=index,
                show_lines=index == 0,
                font_scale=0.7,
                lang=meta.lang,
            )
            title = lab["start"] if index == 0 else f"{lab['frame']} {index}"
            page.text(left, bottom + cell_h + 0.008, title, fontsize=8.5, color=INK_2, family=FONT)
        pages.append(page)
    return pages


def render_pdf(diagram: Diagram, meta: SheetMeta) -> bytes:
    """A4 vektör PDF (`pdf_pages`)."""
    from matplotlib.backends.backend_pdf import PdfPages

    buf = io.BytesIO()
    pdf_meta = {"Title": meta.title, "Creator": "Kurgu", "Producer": "Kurgu", "CreationDate": None}
    with PdfPages(buf, metadata=pdf_meta) as pdf:
        for page in pdf_pages(diagram, meta):
            pdf.savefig(page)
    return buf.getvalue()
