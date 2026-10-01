"""LLM brifinginin girdisi, istemi ve sahte üreticisi (SPEC §15, ADR-0013, A-73).

Girdi tek JSON belgesidir; sayılar hem ham hem ekranda gösterilen biçimiyle bulunur. Model yalnız
bu belgedeki sayıları kullanabilir; çıktı `numbers.verify` ile denetlenir.
"""

from __future__ import annotations

from typing import Any

from kurgu_analytics.reports.documents import OpponentReport
from kurgu_analytics.reports.labels import format_metric, metric_label

TZ_NAME = "Europe/Istanbul"
AREAS = {"attack": "hücum", "defense": "savunma"}
STATUS = {"suggested": "öneri", "accepted": "kabul edildi", "rejected": "reddedildi"}

SYSTEM_PROMPT = """\
Bir profesyonel futbol kulübünün duran top analistisin. Teknik ekip için maç öncesi kısa bir \
Türkçe brifing yazacaksın. Kullanıcı mesajındaki JSON tek kaynağındır.

Kurallar:
1. Yalnızca JSON'da bulunan sayıları kullan. Bir metrikten söz ederken değeri "display" alanındaki \
biçimle aynen yaz; sırayı "rank_display" biçimiyle yaz. Hesaplama, yuvarlama, toplama, fark ya da \
yüzde dönüşümü yapma. JSON'da olmayan hiçbir sayı yazma.
2. Sayıları rakamla yaz, yazıyla yazma.
3. Oyuncu adı kullanma, uydurma.
4. "indirect" alanı true olan metrikleri "dolaylı gösterge" diye belirt. "low_sample" true ise \
"az veri" de.
5. Öneriler bölümündeki aksiyonları önceliklendir; kabul edilenleri öne al.
6. 120-180 kelime, üç kısa paragraf: rakibin duran top profili; savunmada dikkat edilecekler; \
hücumdaki fırsatlar ve haftalık plan. Başlık, madde işareti ya da markdown kullanma.
"""

RETRY_NOTE = (
    "Önceki taslakta JSON'da bulunmayan sayılar vardı: {numbers}. Bu sayıları kullanmadan, "
    "yalnız JSON'daki biçimlerle yeniden yaz."
)


def _local(report: OpponentReport) -> tuple[str | None, str | None]:
    from zoneinfo import ZoneInfo

    kickoff = report.fixture.kickoff_at
    if kickoff is None:
        return None, None
    local = kickoff.astimezone(ZoneInfo(TZ_NAME))
    return local.strftime("%d.%m.%Y"), local.strftime("%H:%M")


def briefing_input(report: OpponentReport, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Brifing girdisi (A-73): fikstür, rakip profili, öneriler, MD planı özeti. Oyuncu adı yok."""
    f = report.fixture
    date, time = _local(report)
    metrics = []
    for m in report.metrics:
        row: dict[str, Any] = {
            "metric": metric_label(m.metric),
            "value": m.value,
            "display": format_metric(m.metric, m.value),
            "rank": m.rank,
            "teams": m.teams,
            "rank_display": f"{m.rank}./{m.teams}",
            "indirect": m.indirect,
            "low_sample": m.low_sample,
        }
        if m.league_mean is not None:
            row["league_mean_display"] = format_metric(m.metric, m.league_mean)
        if m.club_value is not None:
            row["club_display"] = format_metric(m.metric, m.club_value)
            row["club_rank"] = m.club_rank
        if m.current_value is not None:
            row["current_season_display"] = format_metric(m.metric, m.current_value)
            row["current_season_rank"] = m.current_rank
        metrics.append(row)
    recommendations = [
        {
            "area": AREAS.get(r.area, r.area),
            "status": STATUS.get(r.status, r.status),
            "confidence": r.confidence,
            "title": r.title,
            "why": r.why,
            "action": r.action,
            "routine": r.routine,
        }
        for r in sorted(report.recommendations, key=lambda r: (r.status != "accepted", r.priority))
    ]
    return {
        "fixture": {
            "season": report.meta.season,
            "week": f.week,
            "date": date,
            "time": time,
            "venue": "ev sahibi" if f.is_home else "deplasman",
            "club": f.club.name,
            "opponent": f.opponent.name,
        },
        "data": {
            "profile_season": report.meta.profile_season,
            "data_week": report.meta.data_week,
            "standing": report.standing,
        },
        "opponent_metrics": metrics,
        "recommendations": recommendations,
        "plan": plan,
    }


def fake_briefing(data: dict[str, Any]) -> str:
    """Geliştirme ve test için belirlenimci metin (`KURGU_LLM_BACKEND=fake`).

    Yalnız girdideki biçimleri kullanır; sayı denetiminden geçer.
    """
    fx = data["fixture"]
    when = " ".join(p for p in (fx.get("date"), fx.get("time")) if p)
    week = f"{fx['week']}. hafta, " if fx.get("week") else ""
    parts = [f"{fx['opponent']} maçı ({week}{fx['venue']}{', ' + when if when else ''})."]
    ranked = sorted(data["opponent_metrics"], key=lambda m: m["rank"])[:3]
    for m in ranked:
        note = " (dolaylı gösterge)" if m["indirect"] else ""
        note += ", az veri" if m["low_sample"] else ""
        parts.append(
            f"Rakip {m['metric'].lower()} metriğinde {m['display']} ile ligde "
            f"{m['rank_display']}{note}."
        )
    for rec in data["recommendations"][:3]:
        parts.append(f"{rec['area'].capitalize()}: {rec['title']}.")
    plan = data.get("plan")
    if plan and plan.get("total"):
        parts.append(f"Haftalık planda {plan['done']}/{plan['total']} madde tamam.")
    return " ".join(parts)
