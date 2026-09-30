"""Duran top çıkarımının doğrulaması (SPEC §5.5 ZORUNLU; assumptions A-07).

Şut düzeyinde karşılaştırma: her şut için bizim etiketimiz (şutun ait olduğu dizinin türü ya da
`none`) ile StatsBomb `play_pattern` etiketi (`From Corner` → corner, `From Free Kick` →
free_kick, `From Throw In` → throw_in, diğerleri → none). Penaltılar iki taraftan da çıkarılır.

İki ayar raporlanır: varsayılan (yalnız uzun taçlar, SPEC §5.5) ve tüm taçlar (StatsBomb'un
taç tanımıyla aynı kapsam). Çalıştırma: `make validate`.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from kurgu_analytics.canonical.model import Action
from kurgu_analytics.ingestion.statsbomb import ATTRIBUTION, events_to_actions
from kurgu_analytics.setpieces.extract import RESTARTS, Config, extract, shot_outcome

LABELS = ("corner", "free_kick", "throw_in", "none")
PATTERNS = {"From Corner": "corner", "From Free Kick": "free_kick", "From Throw In": "throw_in"}
SB_SHOT_OUTCOMES = {
    "Goal": "goal",
    "Saved": "shot_on_target",
    "Saved to Post": "shot_on_target",
    "Saved Off Target": "shot_off_target",
    "Off T": "shot_off_target",
    "Wayward": "shot_off_target",
    "Post": "shot_off_target",
    "Blocked": "shot_blocked",
}
TARGET = 0.95
DEFINITIONAL = ("kısa taç", "pencere dışı")


@dataclass
class Mismatch:
    match_id: str
    period: int
    time_s: float
    ours: str
    theirs: str
    reason: str


@dataclass
class Comparison:
    confusion: Counter[tuple[str, str]] = field(default_factory=Counter)
    mismatches: list[Mismatch] = field(default_factory=list)
    matches: int = 0
    shot_outcomes: Counter[tuple[str, str]] = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return sum(self.confusion.values())

    @property
    def agreement(self) -> float:
        same = sum(n for (a, b), n in self.confusion.items() if a == b)
        return same / self.total if self.total else 0.0

    @property
    def definitional(self) -> int:
        """Tanım farkından gelen uyumsuzluklar: kısa taç ve 20 sn pencere dışı (SPEC §3.2)."""
        return sum(1 for m in self.mismatches if m.reason.startswith(DEFINITIONAL))

    @property
    def aligned_agreement(self) -> float:
        """Tanım farkları uyumlu sayıldığında uyum (StatsBomb etiketi kapsamımıza indirgenir)."""
        same = sum(n for (a, b), n in self.confusion.items() if a == b)
        return (same + self.definitional) / self.total if self.total else 0.0

    def set_piece_agreement(self) -> float:
        """Yalnızca en az bir tarafın duran top dediği şutlarda uyum (daha sert ölçü)."""
        rows = {k: n for k, n in self.confusion.items() if k != ("none", "none")}
        total = sum(rows.values())
        same = sum(n for (a, b), n in rows.items() if a == b)
        return same / total if total else 0.0

    def precision_recall(self, label: str) -> tuple[float, float]:
        tp = self.confusion[(label, label)]
        ours = sum(n for (a, _), n in self.confusion.items() if a == label)
        theirs = sum(n for (_, b), n in self.confusion.items() if b == label)
        return (tp / ours if ours else 0.0, tp / theirs if theirs else 0.0)


def _reason(actions: list[Action], i: int, ours: str, theirs: str, cfg: Config) -> str:
    """Uyumsuzluğun olası nedeni: şuttan geriye doğru son duran topa bakar."""
    shot = actions[i]
    for j in range(i - 1, -1, -1):
        a = actions[j]
        if a.period != shot.period:
            break
        if a.type in RESTARTS or a.type in {"goalkick", "shot_penalty"}:
            gap = shot.time_s - a.time_s
            if theirs != "none" and ours == "none":
                if a.type == "throw_in" and not cfg.all_throw_ins:
                    return "kısa taç (uzun taç filtresi)"
                if gap > cfg.window_s:
                    return f"pencere dışı ({gap:.0f} sn)"
                return "top kaybıyla dizi bitti"
            if ours != "none" and theirs == "none":
                return "StatsBomb topa sahip olmayı yeni atak saydı"
            return "farklı duran top türü"
    return "önceki duran top bulunamadı"


def compare(files: Iterable[Path], cfg: Config) -> Comparison:
    result = Comparison()
    for path in files:
        events = json.loads(path.read_text(encoding="utf-8"))
        actions = events_to_actions(events)
        label: dict[int, str] = {}
        for sp in extract(actions, cfg):
            for shot in sp.shots:
                label[shot.action_index] = sp.sp_type
        result.matches += 1
        for i, a in enumerate(actions):
            if a.type not in {"shot", "shot_freekick"}:
                continue
            sb_outcome = SB_SHOT_OUTCOMES.get(a.extra.get("shot_outcome") or "")
            if sb_outcome:
                result.shot_outcomes[(shot_outcome(actions, i), sb_outcome)] += 1
            ours = label.get(a.action_index, "none")
            theirs = PATTERNS.get(a.extra.get("play_pattern") or "", "none")
            result.confusion[(ours, theirs)] += 1
            if ours != theirs:
                result.mismatches.append(
                    Mismatch(
                        path.stem,
                        a.period,
                        a.time_s,
                        ours,
                        theirs,
                        _reason(actions, i, ours, theirs, cfg),
                    )
                )
    return result


def _pct(x: float) -> str:
    return f"%{100 * x:.1f}".replace(".", ",")


def _matrix(c: Comparison) -> list[str]:
    lines = [
        "| Bizim ↓ / StatsBomb → | " + " | ".join(LABELS) + " |",
        "|---|" + "---:|" * len(LABELS),
    ]
    for a in LABELS:
        lines.append(f"| {a} | " + " | ".join(str(c.confusion[(a, b)]) for b in LABELS) + " |")
    return lines


OUTCOMES = ("goal", "shot_on_target", "shot_off_target", "shot_blocked")


def _outcome_agreement(c: Comparison) -> float:
    total = sum(c.shot_outcomes.values())
    same = sum(n for (a, b), n in c.shot_outcomes.items() if a == b)
    return same / total if total else 0.0


def _outcome_matrix(c: Comparison) -> list[str]:
    lines = [
        "| Bizim ↓ / StatsBomb → | " + " | ".join(OUTCOMES) + " |",
        "|---|" + "---:|" * len(OUTCOMES),
    ]
    for a in OUTCOMES:
        cells = " | ".join(str(c.shot_outcomes[(a, b)]) for b in OUTCOMES)
        lines.append(f"| {a} | {cells} |")
    return lines


def render(
    default: Comparison,
    all_throws: Comparison,
    sensitivity: list[tuple[float, Comparison]],
    competitions: list[str],
) -> str:
    raw_verdict = "tuttu" if default.agreement >= TARGET else "tutmadı"
    aligned_verdict = "tuttu" if default.aligned_agreement >= TARGET else "tutmadı"
    lines = [
        "# Duran top çıkarımı doğrulama raporu",
        "",
        "Bu dosya `make validate` ile üretilir; elle düzenlenmez. "
        "Yöntem: SPEC §5.5, assumptions A-07.",
        "",
        f"**Veri:** {default.matches} maç ({', '.join(competitions)}). {ATTRIBUTION}.",
        "",
        "**Ölçü:** Şut düzeyinde etiket uyumu. Bizim etiketimiz şutun ait olduğu duran top "
        "dizisinin türüdür (yoksa `none`); StatsBomb etiketi şutun `play_pattern` alanıdır. "
        "Penaltılar iki taraftan da çıkarılmıştır.",
        "",
        "## Özet",
        "",
        "| Ayar | Şut | Ham uyum | Tanım farkları hariç uyum | Duran top şutlarında ham uyum |",
        "|---|---:|---:|---:|---:|",
        f"| Varsayılan (uzun taç, 20 sn) | {default.total} | {_pct(default.agreement)} "
        f"| {_pct(default.aligned_agreement)} | {_pct(default.set_piece_agreement())} |",
        f"| Tüm taçlar, 20 sn | {all_throws.total} | {_pct(all_throws.agreement)} "
        f"| {_pct(all_throws.aligned_agreement)} | {_pct(all_throws.set_piece_agreement())} |",
        "",
        f"Hedef %95. Ham uyum (StatsBomb etiketiyle birebir): **{raw_verdict}**. "
        f"Tanım farkları hariç uyum: **{aligned_verdict}**.",
        "",
        "Neden iki ölçü var: StatsBomb `play_pattern` etiketi topa sahip olma (possession) boyunca "
        "süre sınırı olmadan taşınır ve tüm taçları kapsar. Şartnamemizdeki duran top tanımı ise "
        "teslimden sonra 20 saniyelik pencereyle ve yalnızca uzun taçlarla sınırlıdır (SPEC §3.1, "
        "§3.2). Bu yüzden StatsBomb'un duran top dediği ama bizim tanımımızın dışında kalan şutlar "
        "(kısa taç, 20 saniyeden sonra gelen şut) ham ölçüde uyumsuz görünür. "
        '"Tanım farkları hariç" ölçüsü bu iki grubu uyumlu sayar; geriye kalan uyumsuzluklar '
        "algoritmanın gerçek farklarıdır (aşağıdaki neden tablosu).",
        "",
        '"Duran top şutlarında ham uyum", iki taraftan en az birinin duran top dediği şutlarla '
        "sınırlı, daha sert ölçüdür.",
        "",
        "## Pencere duyarlılığı (tüm taçlar)",
        "",
        "Pencere uzadıkça etiketimiz StatsBomb'un possession tanımına yaklaşır. Bu tablo farkın "
        "algoritmadan değil tanımdan geldiğini gösterir.",
        "",
        "| Pencere | Ham uyum | Duran top şutlarında ham uyum |",
        "|---:|---:|---:|",
        *[
            f"| {w:.0f} sn | {_pct(c.agreement)} | {_pct(c.set_piece_agreement())} |"
            for w, c in sensitivity
        ],
        "",
        "## Tür bazında kesinlik ve duyarlılık (varsayılan ayar)",
        "",
        "| Tür | Kesinlik | Duyarlılık |",
        "|---|---:|---:|",
    ]
    for label in LABELS[:3]:
        p, r = default.precision_recall(label)
        lines.append(f"| {label} | {_pct(p)} | {_pct(r)} |")
    p, r = all_throws.precision_recall("throw_in")
    lines += [
        f"| throw_in (tüm taçlar) | {_pct(p)} | {_pct(r)} |",
        "",
        "Taç duyarlılığı varsayılan ayarda düşüktür, çünkü tanımımız bilinçli olarak dardır: "
        "yalnızca hücum üçte birinden ceza sahasına atılan uzun taçlar duran toptur "
        "(CLAUDE.md sözlüğü). StatsBomb tüm taçları sayar.",
        "",
        "## Şut sonucu türetme",
        "",
        "Dizi sonucu (`shot_on_target`, `shot_off_target`, `shot_blocked`) sağlayıcıdan bağımsız "
        "türetilir: rakip kaleci kurtarışı isabetli, kale çizgisine ulaşan isabetsiz, ulaşmayan "
        "engellenmiş sayılır. Tüm şutlarda StatsBomb sonucuyla uyum: "
        f"**{_pct(_outcome_agreement(default))}**.",
        "",
        *_outcome_matrix(default),
        "",
        "## Karışıklık matrisi (varsayılan ayar)",
        "",
        *_matrix(default),
        "",
        "## Karışıklık matrisi (tüm taçlar)",
        "",
        *_matrix(all_throws),
        "",
        "## Uyumsuzluk nedenleri (varsayılan ayar)",
        "",
        "| Neden | Adet |",
        "|---|---:|",
    ]
    reasons = Counter(
        m.reason if not m.reason.startswith("pencere dışı") else "pencere dışı (> 20 sn)"
        for m in default.mismatches
    )
    for reason, n in reasons.most_common():
        lines.append(f"| {reason} | {n} |")
    lines += [
        "",
        "Nedenler şuttan geriye doğru son ölü topa bakılarak otomatik atanır; "
        "yaklaşık sınıflamadır.",
        "StatsBomb'un `play_pattern` alanı topa sahip olma (possession) boyunca taşınır ve süre "
        "sınırı yoktur; bizim tanımımız 20 saniyelik pencere ve top kaybıyla biter (SPEC §3.2).",
        "",
        "## Örnek uyumsuzluklar",
        "",
        "| Maç | Periyot | Dakika | Bizim | StatsBomb | Neden |",
        "|---|---:|---:|---|---|---|",
    ]
    seen: Counter[str] = Counter()
    for m in default.mismatches:
        key = m.reason.split(" (")[0]
        if seen[key] >= 3:
            continue
        seen[key] += 1
        minute = f"{int(m.time_s // 60)}:{int(m.time_s % 60):02d}"
        lines.append(
            f"| {m.match_id} | {m.period} | {minute} | {m.ours} | {m.theirs} | {m.reason} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/statsbomb")
    names: list[str] = []
    files: list[Path] = []
    for season_file in sorted((root / "matches").glob("*/*.json")):
        matches = json.loads(season_file.read_text(encoding="utf-8"))
        if matches:
            first = matches[0]
            names.append(
                f"{first['competition']['competition_name']} {first['season']['season_name']}"
            )
        files += [root / "events" / f"{m['match_id']}.json" for m in matches]
    files = [f for f in files if f.is_file()]
    default = compare(files, Config())
    all_throws = compare(files, Config(all_throw_ins=True))
    sensitivity = [(20.0, all_throws)] + [
        (w, compare(files, Config(all_throw_ins=True, window_s=w))) for w in (60.0, 180.0)
    ]
    sys.stdout.write(render(default, all_throws, sensitivity, names))


if __name__ == "__main__":
    main()
