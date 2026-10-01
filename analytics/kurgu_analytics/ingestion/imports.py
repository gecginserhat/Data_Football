"""CSV/Excel içe aktarım: şablonlar, sütun eşleştirme, kalite kontrolleri (SPEC §5.6; A-08).

İki şablon vardır:
- `team_season_stats`: takım başına bir satır, sütunlar metrik adları (tohumdaki alanlar).
- `events`: olay düzeyi, SPADL benzeri; koordinatlar kanonik (105 × 68 m, olayı yapan takımın
  hücum yönünde, SPEC §4).

Kontroller pandera ile yapılır. Önem dereceleri:
- `critical`: veri yanlış; yükleme karantinaya alınır, metriklere girmez.
- `warning`: rapora girer, yüklemeyi durdurmaz.
Takım eşleştirmesi veritabanı gerektirdiği için API katmanındadır; buradaki `match_names`
yalnızca benzerlik puanını hesaplar.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, Literal

import pandas as pd
import pandera.pandas as pa

from kurgu_analytics.canonical.model import ACTION_TYPES, BODYPARTS, RESULTS

Kind = Literal["team_season_stats", "events"]
Severity = Literal["critical", "warning"]

MAX_ROWS = 200_000
MIN_EVENTS_PER_MATCH = 300
MAX_EVENTS_PER_MATCH = 6000
AUTO_MATCH_SCORE = 0.85
"""Bu puanın altındaki takım eşleşmeleri elle onay bekler (SPEC §5.4)."""


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    required: bool
    aliases: tuple[str, ...] = ()


TEAM_STATS_METRICS: tuple[str, ...] = (
    "matches",
    "goals",
    "goals_against",
    "xg",
    "xga",
    "penalty_goals",
    "penalty_attempts",
    "open_play_goals",
    "fast_break_goals",
    "direct_fk_goals",
    "headed_goals",
    "corners_per_match",
    "aerials_won_per_match",
    "aerial_win_pct",
    "clearances_per_match",
    "fouls_committed",
    "fouls_won",
    "accurate_crosses_per_match",
    "set_piece_goals",
    "set_piece_xg",
)

TEMPLATES: dict[Kind, tuple[FieldSpec, ...]] = {
    "team_season_stats": (
        FieldSpec("team", True, ("takim", "kulup", "club", "team_name", "takim_adi")),
        *(FieldSpec(m, False) for m in TEAM_STATS_METRICS),
    ),
    "events": (
        FieldSpec("match_ref", True, ("match", "match_id", "mac", "mac_id")),
        FieldSpec("match_date", True, ("date", "tarih", "mac_tarihi")),
        FieldSpec("home_team", True, ("home", "ev_sahibi", "ev")),
        FieldSpec("away_team", True, ("away", "deplasman", "misafir")),
        FieldSpec("period", True, ("half", "periyot", "devre")),
        FieldSpec("time_s", True, ("time", "seconds", "saniye", "zaman")),
        FieldSpec("team", True, ("takim", "team_name")),
        FieldSpec("player", False, ("oyuncu", "player_name")),
        FieldSpec("type", True, ("action_type", "tur", "type_name")),
        FieldSpec("result", True, ("sonuc", "outcome", "result_name")),
        FieldSpec("bodypart", False, ("body_part", "vucut")),
        FieldSpec("start_x", True, ("x", "baslangic_x")),
        FieldSpec("start_y", True, ("y", "baslangic_y")),
        FieldSpec("end_x", True, ("bitis_x",)),
        FieldSpec("end_y", True, ("bitis_y",)),
        FieldSpec("xg", False, ("expected_goals",)),
    ),
}


@dataclass(frozen=True, slots=True)
class Issue:
    check: str
    severity: Severity
    message: str
    column: str | None = None
    count: int = 1
    rows: tuple[int, ...] = ()
    """Örnek satır numaraları (dosyadaki satır; başlık 1. satırdır)."""


@dataclass(slots=True)
class QualityReport:
    rows: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def critical(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "critical": self.critical,
            "warnings": self.warnings,
            "issues": [asdict(i) | {"rows": list(i.rows)} for i in self.issues],
        }


# --- Okuma ve eşleştirme ------------------------------------------------------


class UnreadableFileError(ValueError):
    pass


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """CSV (ayraç otomatik) ya da Excel (ilk sayfa) okur; tüm hücreler metin olarak gelir."""
    try:
        if filename.lower().endswith((".xlsx", ".xlsm")):
            frame = pd.read_excel(io.BytesIO(content), dtype=str, engine="openpyxl")
        else:
            text = content.decode("utf-8-sig")
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            frame = pd.read_csv(io.StringIO(text), sep=dialect.delimiter, dtype=str)
    except (ValueError, UnicodeDecodeError, csv.Error, KeyError) as exc:
        raise UnreadableFileError(str(exc)) from exc
    if len(frame) > MAX_ROWS:
        raise UnreadableFileError(f"en fazla {MAX_ROWS} satır")
    return frame.fillna("")


def normalize(name: str) -> str:
    """Başlık/isim karşılaştırması için: küçük harf, Türkçe harfler sadeleşir, boşluk → _."""
    folded = name.strip().lower().replace("ı", "i")
    ascii_ = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_).strip("_")


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def suggest_mapping(columns: list[str], kind: Kind) -> dict[str, str | None]:
    """Dosya sütunu → şablon alanı önerisi. Eşleşmeyen sütunlar `None` (yok sayılır)."""
    fields = TEMPLATES[kind]
    result: dict[str, str | None] = {}
    taken: set[str] = set()
    for column in columns:
        key = normalize(column)
        best: tuple[float, str | None] = (0.0, None)
        for spec in fields:
            if spec.name in taken:
                continue
            names = (spec.name, *spec.aliases)
            score = 1.0 if key in names else max(similarity(key, n) for n in names)
            if score > best[0]:
                best = (score, spec.name)
        target = best[1] if best[0] >= 0.8 else None
        result[column] = target
        if target:
            taken.add(target)
    return result


def apply_mapping(frame: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    renamed = {src: dst for src, dst in mapping.items() if dst and src in frame.columns}
    out = frame[list(renamed)].rename(columns=renamed)
    out.index = out.index + 2  # dosyadaki satır numarası (başlık 1. satır)
    return out


def match_names(
    names: list[str], candidates: list[tuple[str, str, str]]
) -> dict[str, tuple[str | None, float]]:
    """İsim → (aday kimliği, puan). Aday: (kimlik, ad, kısa kod). Kısa kod birebir eşleşirse 1."""
    result: dict[str, tuple[str | None, float]] = {}
    for name in names:
        best: tuple[str | None, float] = (None, 0.0)
        for cid, cname, code in candidates:
            score = 1.0 if normalize(name) == normalize(code) else similarity(name, cname)
            if score > best[1]:
                best = (cid, score)
        result[name] = best
    return result


# --- Kalite kontrolleri ----------------------------------------------------------


def _schema(kind: Kind) -> pa.DataFrameSchema:
    if kind == "team_season_stats":
        metric = {
            m: pa.Column(
                float,
                checks=[pa.Check.ge(0), *([pa.Check.le(100)] if m == "aerial_win_pct" else [])],
                nullable=True,
                required=False,
                coerce=True,
            )
            for m in TEAM_STATS_METRICS
        }
        return pa.DataFrameSchema(
            {"team": pa.Column(str, pa.Check.str_length(min_value=1)), **metric}, coerce=True
        )
    return pa.DataFrameSchema(
        {
            "match_ref": pa.Column(str, pa.Check.str_length(min_value=1)),
            "match_date": pa.Column(pd.Timestamp, coerce=True),
            "home_team": pa.Column(str, pa.Check.str_length(min_value=1)),
            "away_team": pa.Column(str, pa.Check.str_length(min_value=1)),
            "period": pa.Column(int, pa.Check.isin([1, 2, 3, 4, 5]), coerce=True),
            "time_s": pa.Column(float, pa.Check.ge(0), coerce=True),
            "team": pa.Column(str, pa.Check.str_length(min_value=1)),
            "player": pa.Column(str, required=False, nullable=True),
            "type": pa.Column(str, pa.Check.isin(ACTION_TYPES)),
            "result": pa.Column(str, pa.Check.isin(RESULTS)),
            "bodypart": pa.Column(str, pa.Check.isin(BODYPARTS), required=False),
            "start_x": pa.Column(float, pa.Check.in_range(0, 105), coerce=True),
            "start_y": pa.Column(float, pa.Check.in_range(0, 68), coerce=True),
            "end_x": pa.Column(float, pa.Check.in_range(0, 105), coerce=True),
            "end_y": pa.Column(float, pa.Check.in_range(0, 68), coerce=True),
            "xg": pa.Column(
                float, pa.Check.in_range(0, 1), required=False, nullable=True, coerce=True
            ),
        }
    )


def _rows(index: Any, limit: int = 5) -> tuple[int, ...]:
    return tuple(int(i) for i in list(index)[:limit] if i is not None and not pd.isna(i))


def _check_label(check: str) -> str:
    """pandera kontrol adını okunur Türkçe etikete çevirir."""
    if check.startswith(("coerce_dtype", "dtype")):
        return "geçersiz değer türü"
    if check.startswith(("in_range", "greater_than", "less_than")):
        return "aralık dışı değer"
    if check.startswith("isin"):
        return "izin verilmeyen değer"
    if check.startswith("not_nullable"):
        return "boş değer"
    if check.startswith("str_length"):
        return "boş metin"
    return check


def _pandera_issues(frame: pd.DataFrame, kind: Kind) -> tuple[pd.DataFrame | None, list[Issue]]:
    try:
        return _schema(kind).validate(frame, lazy=True), []
    except pa.errors.SchemaErrors as exc:
        failures = exc.failure_cases
        issues: list[Issue] = []
        # Aynı sütunda tip dönüşümü ve değer kontrolü aynı satırı iki kez raporlayabilir;
        # sütun başına tek sorun yazılır.
        for column, group in failures.groupby("column", dropna=False, sort=False):
            col = None if pd.isna(column) else str(column)
            checks = ", ".join(dict.fromkeys(_check_label(str(c)) for c in group["check"]))
            rows = group["index"].dropna().drop_duplicates()
            issues.append(
                Issue(
                    check="schema",
                    severity="critical",
                    message=f"{col or 'dosya'}: {checks}",
                    column=col,
                    count=max(len(rows), 1),
                    rows=_rows(rows),
                )
            )
        return None, issues


def validate(frame: pd.DataFrame, kind: Kind) -> tuple[QualityReport, pd.DataFrame | None]:
    """Eşleştirilmiş tabloyu doğrular. Döner: rapor ve (kritik hata yoksa) tipli tablo."""
    report = QualityReport(rows=len(frame))
    fields = TEMPLATES[kind]
    missing = [f.name for f in fields if f.required and f.name not in frame.columns]
    for name in missing:
        report.issues.append(
            Issue("required_column", "critical", f"zorunlu sütun yok: {name}", name)
        )
    if kind == "team_season_stats" and not set(TEAM_STATS_METRICS) & set(frame.columns):
        report.issues.append(
            Issue("required_column", "critical", "en az bir metrik sütunu gerekli")
        )
    if missing or report.critical:
        return report, None
    if len(frame) == 0:
        report.issues.append(Issue("empty", "critical", "dosyada veri satırı yok"))
        return report, None

    blanks = frame.replace("", pd.NA)
    typed, issues = _pandera_issues(blanks, kind)
    report.issues += issues
    if typed is None:
        return report, None

    if kind == "team_season_stats":
        dupes = typed[typed.duplicated("team", keep=False)]
        if len(dupes):
            report.issues.append(
                Issue(
                    "duplicates",
                    "critical",
                    "aynı takım birden çok kez",
                    "team",
                    len(dupes),
                    _rows(dupes.index),
                )
            )
        return report, (typed if not report.critical else None)

    key = ["match_ref", "period", "time_s", "team", "type", "start_x", "start_y"]
    dupes = typed[typed.duplicated(key, keep="first")]
    if len(dupes):
        report.issues.append(
            Issue("duplicates", "critical", "yinelenen olay", None, len(dupes), _rows(dupes.index))
        )
    wrong_team = typed[
        (typed["team"] != typed["home_team"]) & (typed["team"] != typed["away_team"])
    ]
    if len(wrong_team):
        report.issues.append(
            Issue(
                "team_reference",
                "critical",
                "olayın takımı maçın ev sahibi ya da deplasmanı değil",
                "team",
                len(wrong_team),
                _rows(wrong_team.index),
            )
        )
    per_match = typed.groupby("match_ref")[["home_team", "away_team", "match_date"]].nunique()
    inconsistent = per_match[(per_match > 1).any(axis=1)]
    if len(inconsistent):
        report.issues.append(
            Issue(
                "match_consistency",
                "critical",
                f"maç bilgisi tutarsız: {', '.join(map(str, inconsistent.index[:5]))}",
                "match_ref",
                len(inconsistent),
            )
        )
    backwards = 0
    sample: list[int] = []
    for _, group in typed.groupby(["match_ref", "period"], sort=False):
        diffs = group["time_s"].diff()
        bad = group[diffs < -1.0]
        backwards += len(bad)
        sample += list(bad.index[: 5 - len(sample)])
    if backwards:
        report.issues.append(
            Issue(
                "time_order",
                "warning",
                "zamanda geri giden olay",
                "time_s",
                backwards,
                tuple(sample),
            )
        )
    counts = typed.groupby("match_ref").size()
    odd = counts[(counts < MIN_EVENTS_PER_MATCH) | (counts > MAX_EVENTS_PER_MATCH)]
    if len(odd):
        report.issues.append(
            Issue(
                "events_per_match",
                "warning",
                f"maç başına olay sayısı olağan dışı "
                f"({MIN_EVENTS_PER_MATCH}-{MAX_EVENTS_PER_MATCH}): "
                + ", ".join(f"{k}={v}" for k, v in odd.head(5).items()),
                "match_ref",
                len(odd),
            )
        )
    return report, (typed if not report.critical else None)
