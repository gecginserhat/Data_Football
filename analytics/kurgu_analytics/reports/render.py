"""Rapor HTML'i (Jinja2) ve PDF altlığı (ADR-0012).

HTML tek parçadır: yazı tipleri, saha çizimleri ve QR kodları gömülüdür; dış kaynak yüklenmez.
PDF'e çevirme API/worker'dadır (Chromium); bu modül saf kalır ve Chromium olmadan sınanır.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import re
from functools import cache
from importlib import resources
from typing import Any
from zoneinfo import ZoneInfo

import segno
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from kurgu_analytics.reports import heatmap
from kurgu_analytics.reports.diagram import Diagram
from kurgu_analytics.reports.documents import MatchPlanReport, OpponentReport, ReportMeta
from kurgu_analytics.reports.labels import (
    CONFIDENCE,
    GROUP_LABELS,
    METRICS,
    SIDES,
    SOURCE_LABELS,
    SP_TYPES,
    STATUS,
    format_metric,
    metric_label,
    source_key,
    tr_number,
)
from kurgu_analytics.reports.routine_sheet import own_roles, render_board_svg

TZ = ZoneInfo("Europe/Istanbul")
FONTS = (
    ("IBM Plex Sans", 400, "ibm-plex-sans-latin-400-normal.woff2"),
    ("IBM Plex Sans", 400, "ibm-plex-sans-latin-ext-400-normal.woff2"),
    ("IBM Plex Sans", 600, "ibm-plex-sans-latin-600-normal.woff2"),
    ("IBM Plex Sans", 600, "ibm-plex-sans-latin-ext-600-normal.woff2"),
    ("IBM Plex Sans Condensed", 600, "ibm-plex-sans-condensed-latin-600-normal.woff2"),
    ("IBM Plex Sans Condensed", 600, "ibm-plex-sans-condensed-latin-ext-600-normal.woff2"),
)
LATIN = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,"
    "U+20AC,U+2122,U+2212"
)
LATIN_EXT = "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+1E00-1E9F,U+20A0-20C0"
FORM = {"W": "G", "D": "B", "L": "M"}
MAX_CLIPS = 6
SUBJECTS = {
    "opponent": "Rakip",
    "opponent_current": "Rakip (bu sezon)",
    "club": "Kulüp",
    "club_current": "Kulüp (bu sezon)",
    "league": "Lig",
    "own_log.routine": "Rutin kaydı",
    "own_log.defense": "Savunma kaydı",
}


@cache
def font_css() -> str:
    """IBM Plex (OFL) @font-face kuralları, base64 woff2 ile."""
    rules = []
    folder = resources.files("kurgu_analytics.reports") / "fonts"
    for family, weight, name in FONTS:
        data = base64.b64encode((folder / name).read_bytes()).decode("ascii")
        ranges = LATIN_EXT if "latin-ext" in name else LATIN
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');unicode-range:{ranges};}}"
        )
    return "\n".join(rules)


def local(value: dt.datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    if value is None:
        return "–"
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.astimezone(TZ).strftime(fmt)


def day(value: dt.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "–"


COMMENT = re.compile(r"<!--.*?-->", re.S)


def qr_svg(url: str) -> Markup:
    """QR kodu; segno yalnız modülleri çizer, adres metin olarak SVG'ye girmez."""
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=3, border=1, xmldecl=False, svgns=True)
    return Markup(buf.getvalue().decode("utf-8"))  # noqa: S704 - üretilmiş SVG


def routine_svg(diagram: Diagram) -> Markup:
    """Rutin diyagramı. matplotlib metni yol olarak çizer ama özgün metni yorum satırına yazar;
    kullanıcı etiketleri yorumdan taşamasın diye yorumlar silinir (PDF'te betik de kapalıdır)."""
    return Markup(COMMENT.sub("", render_board_svg(diagram)))  # noqa: S704 - yorumsuz SVG


def roles_of(diagram: Diagram) -> list[str]:
    return own_roles(diagram)


def heatmap_svg(zones: list[Any]) -> Markup:
    svg = heatmap.render_svg({z.zone: z.count for z in zones})
    return Markup(svg)  # noqa: S704 - metinler heatmap içinde kaçışlanır


def sources_text(meta: ReportMeta) -> str:
    keys = sorted({source_key(s) for s in meta.sources})
    return ", ".join(SOURCE_LABELS.get(k, k) for k in keys) or "kayıt yok"


@cache
def environment() -> Environment:
    env = Environment(
        loader=PackageLoader("kurgu_analytics.reports", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        metric=format_metric,
        label=metric_label,
        num=tr_number,
        local=local,
        day=day,
        qr=qr_svg,
        routine_svg=routine_svg,
        roles=roles_of,
        sp_type=lambda v: SP_TYPES.get(v, v),
        side=lambda v: SIDES.get(v, v) if v else "",
        confidence=lambda v: CONFIDENCE.get(v, v),
        status=lambda v: STATUS.get(v, v),
        form=lambda v: FORM.get(v, v),
        subject=lambda v: SUBJECTS.get(v, v),
    )
    env.globals.update(
        font_css=lambda: Markup(font_css()),  # noqa: S704 - paket içi yazı tipleri
        heatmap_svg=heatmap_svg,
        sources_text=sources_text,
        group_labels=GROUP_LABELS,
        metric_group=lambda m: METRICS[m].group if m in METRICS else "other",
        zone_names=heatmap.zone_names,
        unboxed=heatmap.unboxed,
        max_clips=MAX_CLIPS,
    )
    return env


def findings(report: OpponentReport) -> list[dict[str, Any]]:
    """Öne çıkanlar (A-77): rakibin ligde ilk üç ya da son üç sırada olduğu metrikler."""
    rows = []
    for m in report.metrics:
        if m.teams < 6:
            continue
        if m.rank <= 3:
            rows.append({"row": m, "edge": "top"})
        elif m.rank > m.teams - 3:
            rows.append({"row": m, "edge": "bottom"})
    return sorted(rows, key=lambda r: (r["edge"] != "top", r["row"].rank))


def render_opponent_html(report: OpponentReport) -> str:
    return (
        environment()
        .get_template("opponent.html.j2")
        .render(r=report, findings=findings(report), title=_title(report, "Rakip raporu"))
    )


def render_match_plan_html(report: MatchPlanReport) -> str:
    return (
        environment()
        .get_template("match_plan.html.j2")
        .render(r=report, title=_title(report, "Maç planı"))
    )


def _title(report: OpponentReport | MatchPlanReport, kind: str) -> str:
    f = report.fixture
    home, away = (f.club, f.opponent) if f.is_home else (f.opponent, f.club)
    return f"{kind} · {home.name} – {away.name}"


def footer_html(report: OpponentReport | MatchPlanReport) -> str:
    """Chromium altlığı: kaynak, veri tarihi ve sayfa numarası (her sayfada)."""
    env = environment()
    return env.get_template("footer.html.j2").render(r=report)
