"""Kanonik maç için kalite kontrolleri (SPEC §5.6).

Kritik bulgu varsa maç yazılmaz ve yükleme işi karantinaya alınır. Uyarılar rapora girer,
yüklemeyi durdurmaz. Eşikler StatsBomb Open Data maçlarında gözlenen aralığa göre geniş
tutulmuştur (bir maçta tipik olarak 1.500-2.500 SPADL aksiyonu).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any, Literal

from kurgu_analytics.canonical.model import ACTION_TYPES, BODYPARTS, RESULTS, CanonicalMatch

MIN_ACTIONS = 300
MAX_ACTIONS = 6000


@dataclass(frozen=True, slots=True)
class Issue:
    check: str
    severity: Literal["critical", "warning"]
    message: str
    count: int = 1


def check_match(cm: CanonicalMatch) -> list[Issue]:
    issues: list[Issue] = []
    actions = cm.actions
    n = len(actions)
    if not MIN_ACTIONS <= n <= MAX_ACTIONS:
        issues.append(
            Issue("action_count", "critical", f"{n} aksiyon; beklenen {MIN_ACTIONS}-{MAX_ACTIONS}")
        )
    teams = {cm.match.home.provider_id, cm.match.away.provider_id}
    foreign = sum(1 for a in actions if a.team_provider_id not in teams)
    if foreign:
        issues.append(Issue("team_reference", "critical", "maçta olmayan takım", foreign))
    ids = Counter(a.provider_event_id for a in actions if a.provider_event_id)
    dupes = sum(c - 1 for c in ids.values() if c > 1)
    if dupes:
        issues.append(Issue("duplicates", "critical", "yinelenen olay kimliği", dupes))
    bad_vocab = sum(
        1
        for a in actions
        if a.type not in ACTION_TYPES or a.result not in RESULTS or a.bodypart not in BODYPARTS
    )
    if bad_vocab:
        issues.append(Issue("vocabulary", "critical", "SPADL dışı değer", bad_vocab))
    out_of_range = sum(
        1
        for a in actions
        if not (
            0 <= a.start_x <= 105
            and 0 <= a.end_x <= 105
            and 0 <= a.start_y <= 68
            and 0 <= a.end_y <= 68
        )
    )
    if out_of_range:
        issues.append(Issue("coordinates", "critical", "saha dışı koordinat", out_of_range))
    bad_period = sum(1 for a in actions if not 1 <= a.period <= 4 or a.time_s < 0)
    if bad_period:
        issues.append(Issue("period_time", "critical", "geçersiz periyot/zaman", bad_period))
    backwards = sum(
        1
        for prev, cur in pairwise(actions)
        if cur.period == prev.period and cur.time_s + 1.0 < prev.time_s
    )
    if backwards:
        issues.append(Issue("time_order", "warning", "zamanda geri giden aksiyon", backwards))
    return issues


def report(issues: list[Issue]) -> dict[str, Any]:
    return {
        "critical": sum(1 for i in issues if i.severity == "critical"),
        "warnings": sum(1 for i in issues if i.severity == "warning"),
        "issues": [asdict(i) for i in issues],
    }
