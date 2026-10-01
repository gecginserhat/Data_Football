"""Öneri kurallarının şeması (SPEC §7.2, ADR-0009).

Kurallar JSON'dur ve burada Pydantic ile doğrulanır. Koşul operatörleri sabit bir sözlükten
seçilir; metinlerdeki yer tutucular `{özne.metrik|biçim}` dışında bir şey yorumlamaz. Bilinmeyen
özne, operatör, biçim ya da bozuk yer tutucu kuralı geçersiz kılar (`eval` yoktur).
"""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Op = Literal[
    "gte", "lte", "gt", "lt", "eq", "rank_gte", "rank_lte", "pctl_gte", "pctl_lte", "exists"
]
Area = Literal["attack", "defense", "balance", "season"]
Scope = Literal["fixture", "season"]

SUBJECTS = (
    "opponent",
    "opponent_current",
    "club",
    "club_current",
    "league",
    "own_log.routine",
    "own_log.defense",
)
"""Kural koşullarında kullanılabilen özneler (A-46)."""
TEXT_ALIASES = {"routine": "own_log.routine"}
"""Metinlerde kısa ad: `{routine.name}` = `{own_log.routine.name}`."""
FORMATS = ("pct", "pct100", "dec1", "int", "signed")
"""Biçimlendiriciler: `pct` %20,4 (0-1 oran), `pct100` %56,4, `dec1` 5,7, `int`, `signed` +2,8."""
ROUTINE_SUBJECT = "own_log.routine"
"""Bu özneyi kullanan kurallar rutin başına ayrı ayrı değerlendirilir."""

PLACEHOLDER_RE = re.compile(r"\{([a-z_]+(?:\.[a-z0-9_]+)+)(?:\|([a-z0-9]+))?\}")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Condition(_Strict):
    subject: str
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    op: Op
    value: float | bool | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.subject not in SUBJECTS:
            raise ValueError(f"unknown subject {self.subject!r}")
        if self.op == "exists":
            if self.value is not None and not isinstance(self.value, bool):
                raise ValueError("exists takes true/false or nothing")
        elif self.value is None or isinstance(self.value, bool):
            raise ValueError(f"{self.op} needs a numeric value")
        if self.op in ("rank_gte", "rank_lte") and (
            not float(self.value).is_integer() or float(self.value) < 1  # type: ignore[arg-type]
        ):
            raise ValueError("rank thresholds are whole numbers ≥ 1")
        if self.op in ("pctl_gte", "pctl_lte") and not 0 <= float(self.value) <= 100:  # type: ignore[arg-type]
            raise ValueError("percentile thresholds are between 0 and 100")
        return self


class When(_Strict):
    all: list[Condition | When] | None = None
    any: list[Condition | When] | None = None
    not_: Condition | When | None = Field(default=None, alias="not")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _one(self) -> Self:
        given = [x for x in (self.all, self.any, self.not_) if x is not None]
        if len(given) != 1:
            raise ValueError("exactly one of all, any, not")
        if (self.all is not None and not self.all) or (self.any is not None and not self.any):
            raise ValueError("all/any need at least one condition")
        return self


class MinSample(_Strict):
    matches: int | None = Field(default=None, ge=1)


class Rule(_Strict):
    id: str = Field(pattern=r"^[A-Z0-9_]{1,64}$")
    scope: Scope
    area: Area
    priority: int = Field(ge=1, le=9)
    when: When
    title: str = Field(min_length=1, max_length=200)
    why: str = Field(min_length=1, max_length=600)
    action: str = Field(min_length=1, max_length=600)
    enabled: bool
    template: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,64}$")
    min_sample: MinSample | None = None

    @model_validator(mode="after")
    def _texts(self) -> Self:
        for text in (self.title, self.why, self.action):
            check_text(text)
        return self

    def conditions(self) -> list[Condition]:
        return list(iter_conditions(self.when))

    @property
    def per_routine(self) -> bool:
        return any(c.subject == ROUTINE_SUBJECT for c in self.conditions())


class RuleSet(_Strict):
    meta: dict[str, object] = Field(default_factory=dict)
    rules: list[Rule]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique")
        return self


def iter_conditions(when: When | Condition):  # type: ignore[no-untyped-def]
    """Koşul ağacındaki tüm yaprak koşullar (soldan sağa)."""
    if isinstance(when, Condition):
        yield when
        return
    for child in (when.all or []) + (when.any or []):
        yield from iter_conditions(child)
    if when.not_ is not None:
        yield from iter_conditions(when.not_)


def split_path(path: str) -> tuple[str, list[str]]:
    """`opponent.rank.x` → ("opponent", ["rank", "x"]). En uzun özne öneki seçilir."""
    for subject in sorted((*SUBJECTS, *TEXT_ALIASES), key=len, reverse=True):
        if path.startswith(subject + "."):
            rest = path[len(subject) + 1 :].split(".")
            return TEXT_ALIASES.get(subject, subject), rest
    raise ValueError(f"unknown subject in {{{path}}}")


def check_text(text: str) -> None:
    """Metindeki her `{…}` geçerli bir yer tutucu olmalıdır; aksi halde ValueError."""
    stripped = PLACEHOLDER_RE.sub("", text)
    if "{" in stripped or "}" in stripped:
        raise ValueError(f"malformed placeholder in {text!r}")
    for match in PLACEHOLDER_RE.finditer(text):
        path, fmt = match.group(1), match.group(2)
        _, rest = split_path(path)
        if fmt is not None and fmt not in FORMATS:
            raise ValueError(f"unknown format {fmt!r}")
        if rest[0] == "rank":
            if len(rest) != 2 or fmt is not None:
                raise ValueError(f"rank placeholder takes a metric and no format: {{{path}}}")
        elif len(rest) != 1:
            raise ValueError(f"bad placeholder {{{path}}}")
        if not all(_NAME_RE.match(part) for part in rest):
            raise ValueError(f"bad placeholder {{{path}}}")
