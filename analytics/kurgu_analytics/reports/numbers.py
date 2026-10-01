"""LLM çıktısındaki sayıların girdiyle eşleştirilmesi (SPEC §15, ADR-0013, A-74).

Metindeki her sayı girdideki bir sayının kendisi ya da gösterim biçimindeki karşılığı olmalıdır.
Türkçe biçimler tanınır: ondalık virgül (`20,4`), binlik nokta (`1.234`), yüzde (`%20,4`, `20,4%`),
sıra (`4.` → 4), tarih (`10.10.2026`) ve saat (`20:00`). Nokta tek anlamlı değilse (`1.234` hem
bin iki yüz otuz dört hem bir virgül iki yüz otuz dört olabilir) iki okuma da denenir.

Kurallar:
- Girdideki sayılar (JSON sayıları ve metin alanlarındaki sayılar) izinli kümeyi oluşturur. 0-1
  arasındaki ham değerler yüzde karşılıklarıyla da (× 100) izinlidir.
- İşaret karşılaştırılmaz: `-2,8` ile `2,8` aynı sayılır (anlamsal hata bu denetimin dışındadır).
- Yuvarlama serbest değildir; `15,4` girdisi metinde `15` olarak yazılamaz.
- `id` ya da `_id` ile biten alanlar ve UUID biçimli metinler izinli kümeye girmez.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

_DATE = r"(?P<date>\d{1,2}\.\d{1,2}\.\d{4})"
_TIME = r"(?P<time>\d{1,2}:\d{2})(?!\d)"
_NUM = r"(?P<num>\d+(?:[.,]\d+)*)"
TOKEN = re.compile(rf"(?<![\w.,]){_DATE}(?![\d])|(?<![\w:]){_TIME}|(?<![\w]){_NUM}")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@dataclass(frozen=True, slots=True)
class NumberToken:
    """Metinde bulunan bir sayı: kaynak metin ve olası değer okumaları."""

    text: str
    keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class Verification:
    ok: bool
    numbers: tuple[str, ...]
    """Metinde bulunan sayılar (yazıldığı biçimde)."""
    unmatched: tuple[str, ...]
    """Girdide karşılığı olmayan sayılar."""


def _decimal_key(value: Decimal) -> str:
    value = abs(value)
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f")


def _parse(raw: str) -> set[Decimal]:
    """Bir sayı dizgesinin olası değerleri (Türkçe ve İngilizce biçim belirsizlikleri dahil)."""
    candidates: set[Decimal] = set()
    commas, dots = raw.count(","), raw.count(".")
    texts: list[str] = []
    if commas == 0 and dots == 0:
        texts.append(raw)
    elif commas == 1 and dots == 0:
        texts.append(raw.replace(",", "."))  # 20,4
        if re.fullmatch(r"\d{1,3},\d{3}", raw):
            texts.append(raw.replace(",", ""))  # 1,234 (İngilizce binlik)
    elif dots >= 1 and commas == 0:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
            texts.append(raw.replace(".", ""))  # 1.234 / 1.234.567
        if dots == 1:
            texts.append(raw)  # 15.4
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", raw):
        texts.append(raw.replace(".", "").replace(",", "."))  # 1.234,5
    elif re.fullmatch(r"\d{1,3}(,\d{3})+\.\d+", raw):
        texts.append(raw.replace(",", ""))  # 1,234.5
    for text in texts:
        try:
            candidates.add(Decimal(text))
        except InvalidOperation:
            continue
    return candidates


def extract(text: str) -> list[NumberToken]:
    """Metindeki sayılar. Tarih ve saat tek parça sayılır; sıra noktası sayıya dahil değildir."""
    tokens: list[NumberToken] = []
    for match in TOKEN.finditer(text):
        if match.group("date"):
            day, month, year = (int(p) for p in match.group("date").split("."))
            tokens.append(NumberToken(match.group(0), frozenset({f"date:{day}.{month}.{year}"})))
        elif match.group("time"):
            hour, minute = (int(p) for p in match.group("time").split(":"))
            tokens.append(NumberToken(match.group(0), frozenset({f"time:{hour}:{minute:02d}"})))
        else:
            raw = match.group("num").rstrip(".,")
            values = _parse(raw)
            if values:
                tokens.append(NumberToken(raw, frozenset(_decimal_key(v) for v in values)))
    return tokens


def _number_keys(value: float | int) -> set[str]:
    keys: set[str] = set()
    try:
        exact = Decimal(str(value))
    except InvalidOperation:
        return keys
    keys.add(_decimal_key(exact))
    if isinstance(value, float) and abs(value) <= 1:
        keys.add(_decimal_key(exact * 100))
    return keys


def allowed_keys(data: Any) -> set[str]:
    """Girdideki tüm sayıların anahtarları (JSON sayıları ve metinlerdeki sayılar)."""
    keys: set[str] = set()

    def walk(node: Any, key: str | None) -> None:
        if key is not None and (key == "id" or key.endswith("_id")):
            return
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, int | float):
            keys.update(_number_keys(node))
        elif isinstance(node, str):
            if not UUID.match(node):
                for token in extract(node):
                    keys.update(token.keys)
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, list | tuple):
            for item in node:
                walk(item, None)

    walk(data, None)
    return keys


def verify(text: str, data: Any, allowed: Iterable[str] | None = None) -> Verification:
    """Metindeki her sayının girdide karşılığı var mı?"""
    keys = set(allowed) if allowed is not None else allowed_keys(data)
    tokens = extract(text)
    unmatched = tuple(t.text for t in tokens if not (t.keys & keys))
    return Verification(
        ok=not unmatched, numbers=tuple(t.text for t in tokens), unmatched=unmatched
    )
